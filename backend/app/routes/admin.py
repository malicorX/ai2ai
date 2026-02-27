"""Routes: admin endpoints (new_run, purge, verify_pending, webhooks, agent management, run viewer)."""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse

from app import state
from app.auth import load_agent_tokens, require_admin
from app.config import (
    AGENT_TOKENS_PATH, AUDIT_PATH, CHAT_PATH, DATA_DIR, ECONOMY_PATH,
    JOBS_PATH, REGISTRATION_SECRET, RUNS_DIR, TRACE_PATH, BACKEND_VERSION,
)
from app.models import (
    AdminChatSayRequest, AgentState, ChatMessage, JobReviewRequest,
    JobVerifyRequest, MoltWorldWebhookRequest, NewRunRequest,
    PurgeCancelledJobsRequest, RegisterAgentRequest, TokenIssueRequest,
    TokenRequest,
)
from app.utils import append_jsonl, rotate_logs
from app.ws import ws_manager

_log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/run")
def run_info():
    return {
        "run_id": state.run_id,
        "started_at": state.run_started_at,
        "tick": state.tick,
        "agents": len(state.agents),
        "jobs": len(state.jobs),
        "version": BACKEND_VERSION,
    }


@router.get("/runs")
def list_runs():
    runs = []
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            if d.is_dir():
                meta_path = d / "meta.json"
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        _log.debug("Failed to read run meta %s", meta_path)
                runs.append({"run_id": d.name, "dir": str(d), "meta": meta})
    runs.sort(key=lambda r: r.get("run_id", ""), reverse=True)
    return {"runs": runs[:100], "current_run_id": state.run_id}


@router.get("/runs/{run_id}/summary")
def run_summary(run_id: str):
    rd = RUNS_DIR / run_id
    if not rd.exists() or not rd.is_dir():
        return {"error": "not_found"}
    meta_path = rd / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            _log.debug("Failed to read run meta %s", meta_path)
    files = []
    for p in rd.iterdir():
        if p.is_file():
            try:
                files.append({"name": p.name, "bytes": p.stat().st_size})
            except Exception:
                files.append({"name": p.name})
    return {"run_id": run_id, "meta": meta, "files": files}


@router.post("/admin/new_run")
async def admin_new_run(req: NewRunRequest, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    old_run_id = state.run_id
    new_rid = (req.run_id or "").strip() or time.strftime("%Y%m%d-%H%M%S")
    rotation = rotate_logs(old_run_id, [AUDIT_PATH, CHAT_PATH, TRACE_PATH], RUNS_DIR)
    state.run_id = new_rid
    state.run_started_at = time.time()
    state.tick = 0
    state.world_started_at = time.time()
    state.chat.clear()
    state.trace.clear()
    state.audit.clear()
    if req.reset_board:
        state.board_posts.clear()
        state.board_replies.clear()
    if req.reset_topic:
        state.topic = "getting started"
        state.topic_set_at = 0.0
        state.topic_history.clear()
    for a in state.agents.values():
        a.x = 0
        a.y = 0
    state.save_agents(force=True)
    await ws_manager.broadcast({"type": "new_run", "data": {"run_id": new_rid, "old_run_id": old_run_id}})
    return {"ok": True, "run_id": new_rid, "old_run_id": old_run_id, "rotation": rotation}


@router.post("/admin/jobs/purge_cancelled")
async def admin_purge_cancelled_jobs(req: PurgeCancelledJobsRequest, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    now = time.time()
    older = float(req.older_than_seconds or 0.0)
    limit = int(req.limit or 0)
    if limit <= 0:
        limit = 5000
    if limit > 20000:
        limit = 20000
    cancel_ts: Dict[str, float] = {}
    for ev in state.job_events:
        if getattr(ev, "event_type", "") == "cancel":
            try:
                cancel_ts[str(ev.job_id)] = float(ev.created_at or 0.0)
            except Exception:
                continue
    candidates: List[str] = []
    for jid, job in list(state.jobs.items()):
        try:
            if str(job.status) != "cancelled":
                continue
            ts = float(cancel_ts.get(jid) or getattr(job, "created_at", 0.0) or 0.0)
            if older > 0 and (now - ts) < older:
                continue
            candidates.append(jid)
        except Exception:
            continue
    candidates.sort(key=lambda jid: float(cancel_ts.get(jid) or (state.jobs.get(jid).created_at if state.jobs.get(jid) else 0.0) or 0.0))
    purge_ids = set(candidates[:limit])
    if not purge_ids:
        return {"ok": True, "removed_jobs": 0, "removed_events": 0, "note": "no cancelled jobs matched"}
    before_events = len(state.job_events)
    from app.models import JobEvent
    kept_events: List[JobEvent] = [ev for ev in state.job_events if str(ev.job_id) not in purge_ids]
    removed_events = before_events - len(kept_events)
    state.job_events[:] = kept_events
    removed_jobs = 0
    for jid in list(purge_ids):
        if jid in state.jobs:
            try:
                del state.jobs[jid]
                removed_jobs += 1
            except Exception:
                continue
    try:
        from app.utils import write_jsonl_atomic
        write_jsonl_atomic(JOBS_PATH, [asdict(ev) for ev in state.job_events])
    except Exception:
        _log.exception("Failed to write job events after purge")
    try:
        await ws_manager.broadcast({"type": "jobs", "data": {"purge_cancelled": {"removed_jobs": removed_jobs, "removed_events": removed_events}}})
    except Exception:
        _log.debug("Broadcast after purge failed", exc_info=True)
    return {"ok": True, "removed_jobs": removed_jobs, "removed_events": removed_events}


@router.post("/admin/verify_pending")
async def admin_verify_pending(request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    tag = f"[run:{state.run_id}]"
    submitted = [j for j in list(state.jobs.values()) if j.status == "submitted" and (tag in (j.title or "") or tag in (j.body or ""))]
    report = {"run_id": state.run_id, "submitted": len(submitted), "approved": 0, "rejected": 0, "skipped": 0, "items": []}
    from app.routes.jobs import jobs_verify
    for j in submitted[:200]:
        before = j.status
        try:
            out = await jobs_verify(j.job_id, JobVerifyRequest(by="system:verify_pending", force=False), request)
            jj = state.jobs.get(j.job_id)
            st = (jj.status if jj else before)
            if st == "approved":
                report["approved"] += 1
            elif st == "rejected":
                report["rejected"] += 1
            else:
                report["skipped"] += 1
            report["items"].append({
                "job_id": j.job_id, "title": j.title, "status": st,
                "auto_verify_ok": (jj.auto_verify_ok if jj else None),
                "auto_verify_note": (jj.auto_verify_note if jj else ""),
            })
        except Exception as e:
            report["items"].append({"job_id": j.job_id, "title": j.title, "status": "error", "error": str(e)[:200]})
    return {"ok": True, "report": report}


@router.get("/audit/recent")
def audit_recent(limit: int = 100):
    limit = max(1, min(limit, 500))
    return {"events": [asdict(e) for e in state.audit[-limit:]]}


# --- Agent token management ---

@router.post("/world/agent/request_token")
async def request_agent_token(req: TokenRequest):
    now = time.time()
    entry = {
        "request_id": str(uuid.uuid4()),
        "agent_name": (req.agent_name or "").strip()[:80],
        "purpose": (req.purpose or "").strip()[:400],
        "contact": (req.contact or "").strip()[:120],
        "created_at": now,
        "status": "pending",
    }
    state.token_requests.append(entry)
    if len(state.token_requests) > state.token_requests_max:
        del state.token_requests[: len(state.token_requests) - state.token_requests_max]
    return {"ok": True, "request": entry}


@router.post("/world/agent/register")
async def register_agent(req: RegisterAgentRequest):
    if REGISTRATION_SECRET and (req.registration_secret or "").strip() != REGISTRATION_SECRET:
        return {"error": "invalid_registration_secret"}
    if not AGENT_TOKENS_PATH:
        return {"error": "registration_disabled", "detail": "AGENT_TOKENS_PATH not set"}
    display_name = (req.display_name or req.agent_id or "").strip()[:80] or "Agent"
    agent_id = (req.agent_id or "").strip()
    if agent_id:
        agent_id = "".join(c for c in agent_id if c.isalnum() or c == "_")[:64] or ""
    if not agent_id:
        agent_id = "agent_" + uuid.uuid4().hex[:8]
    tokens = load_agent_tokens()
    if agent_id in tokens.values():
        return {"error": "agent_id_taken", "agent_id": agent_id}
    state.ensure_account(agent_id)
    now = time.time()
    if agent_id not in state.agents:
        state.agents[agent_id] = AgentState(agent_id=agent_id, display_name=display_name, x=0, y=0, last_seen_at=now)
    else:
        state.agents[agent_id].display_name = display_name
        state.agents[agent_id].last_seen_at = now
    state.save_agents(force=True)
    token = uuid.uuid4().hex
    tokens[token] = agent_id
    try:
        Path(AGENT_TOKENS_PATH).write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    except Exception as e:
        return {"error": "write_failed", "detail": str(e)[:200]}
    balance = float(state.balances.get(agent_id, 0.0))
    return {"ok": True, "agent_id": agent_id, "token": token, "display_name": display_name, "balance": balance}


@router.get("/admin/agent/requests")
def list_agent_token_requests(request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    return {"requests": list(state.token_requests)}


@router.post("/admin/agent/issue_token")
def admin_issue_agent_token(req: TokenIssueRequest, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    if not AGENT_TOKENS_PATH:
        return {"error": "missing_agent_tokens_path"}
    agent_id = (req.agent_id or "").strip()
    if not agent_id:
        return {"error": "missing_agent_id"}
    token = uuid.uuid4().hex
    tokens = load_agent_tokens()
    tokens[token] = agent_id
    try:
        Path(AGENT_TOKENS_PATH).write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    except Exception as e:
        return {"error": "write_failed", "detail": str(e)[:200]}
    return {"ok": True, "agent_id": agent_id, "token": token}


# --- MoltWorld webhooks management ---

@router.get("/admin/moltworld/webhooks")
def admin_list_moltworld_webhooks(request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    return {"webhooks": [{"agent_id": w["agent_id"], "url": w["url"], "has_secret": bool(w.get("secret"))} for w in state.moltworld_webhooks]}


@router.post("/admin/moltworld/webhooks")
def admin_add_moltworld_webhook(req: MoltWorldWebhookRequest, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    agent_id = (req.agent_id or "").strip()
    url = (req.url or "").strip()
    secret = (req.secret or "").strip() or None
    if not agent_id or not url:
        return {"error": "missing_agent_id_or_url"}
    if not url.startswith(("http://", "https://")):
        return {"error": "url_must_be_http_or_https"}
    for w in state.moltworld_webhooks:
        if w.get("agent_id") == agent_id:
            w["url"] = url
            w["secret"] = secret
            state.save_moltworld_webhooks()
            return {"ok": True, "agent_id": agent_id, "updated": True}
    state.moltworld_webhooks.append({"agent_id": agent_id, "url": url, "secret": secret})
    state.save_moltworld_webhooks()
    return {"ok": True, "agent_id": agent_id}


@router.delete("/admin/moltworld/webhooks/{agent_id}")
def admin_remove_moltworld_webhook(agent_id: str, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    before = len(state.moltworld_webhooks)
    state.moltworld_webhooks[:] = [w for w in state.moltworld_webhooks if w.get("agent_id") != agent_id]
    if len(state.moltworld_webhooks) < before:
        state.save_moltworld_webhooks()
        return {"ok": True, "agent_id": agent_id, "removed": True}
    return {"ok": False, "agent_id": agent_id, "removed": False}


@router.post("/admin/chat/say")
async def admin_chat_say(req: AdminChatSayRequest, request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    sender_id = (req.sender_id or "").strip()
    if not sender_id:
        return {"error": "missing_sender_id"}
    text = (req.text or "").strip()
    if not text:
        return {"error": "missing_text"}
    now = time.time()
    sender_name = (req.sender_name or "").strip() or sender_id
    msg_dict = {"sender_id": sender_id, "sender_name": sender_name, "text": text, "scope": "say", "created_at": now}
    chat_msg = ChatMessage(
        msg_id=str(uuid.uuid4()), sender_type="agent",
        sender_id=sender_id, sender_name=sender_name,
        text=text, created_at=now,
    )
    state.chat.append(chat_msg)
    if len(state.chat) > state.chat_max:
        del state.chat[: len(state.chat) - state.chat_max]
    append_jsonl(CHAT_PATH, asdict(chat_msg))
    await ws_manager.broadcast({"type": "chat", "data": msg_dict})
    return {"ok": True, "message": msg_dict}
