"""
Global mutable state and load/save functions.

All in-memory state lives here so route modules can import it.
This is a transitional module — eventually replaced by a real database.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional

from app.config import (
    AGENTS_PATH, AUDIT_PATH, CHAT_PATH, CHAT_REPETITION_PENALTY_AIDOLLAR,
    CHAT_REPETITION_SIMILARITY_THRESHOLD, CHAT_REPETITION_WINDOW,
    ECONOMY_PATH, EMBEDDINGS_BASE_URL, EMBEDDINGS_MODEL, EMBEDDINGS_TIMEOUT_SECONDS,
    EMBEDDINGS_TRUNCATE, EVENTS_PATH, JOBS_PATH, LANDMARKS, MEMORY_DIR,
    MEMORY_EMBED_DIR, MOLTWORLD_WEBHOOK_COOLDOWN_SECONDS,
    MOLTWORLD_WEBHOOKS_PATH, STARTING_AIDOLLARS, TRACE_PATH, TREASURY_ID,
    WORLD_PUBLIC_URL, WORLD_SIZE, SIM_MINUTES_PER_REAL_SECOND,
)
from app.models import (
    AgentState, AuditEntry, BoardPost, BoardReply,
    ChatMessage, EconomyEntry, EventLogEntry, Job, JobEvent,
    Opportunity, TraceEvent, VillageEvent, WorldSnapshot,
)
from app.utils import (
    append_jsonl, normalize_text_for_similarity, chat_text_similarity,
    read_jsonl, write_jsonl_atomic,
)
from app.ws import ws_manager

_log = logging.getLogger(__name__)

# Economy and opportunity logic live in dedicated modules.
# Re-exported here for backward compatibility (routes import from state).
from app.economy_logic import (  # noqa: E402, F401
    recompute_balances, ensure_account, action_diversity_decay,
    award_action_diversity, extract_fiverr_url, try_award_fiverr_discovery,
    apply_penalty, action_history,
)
from app.opportunity_logic import (  # noqa: E402, F401
    norm_text, opportunity_fingerprint, save_opportunities, load_opportunities,
    recalculate_opportunity_success_score, recalculate_opportunity_value_score,
    upsert_opportunity,
)

# --- Run state ---
run_id: str = time.strftime("%Y%m%d-%H%M%S")
run_started_at: float = time.time()

# --- World tick ---
tick: int = 0
world_started_at: float = time.time()

# --- Agents ---
agents: Dict[str, AgentState] = {}
_agents_save_debounce_at: float = 0.0
_agents_save_debounce_sec: float = 2.0


def load_agents() -> None:
    global agents
    if AGENTS_PATH.exists():
        try:
            raw = AGENTS_PATH.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            if isinstance(data, dict) and data:
                for aid, d in data.items():
                    if not isinstance(d, dict) or not aid:
                        continue
                    try:
                        agents[aid] = AgentState(
                            agent_id=str(aid),
                            display_name=str(d.get("display_name") or aid),
                            x=int(d.get("x", 0)),
                            y=int(d.get("y", 0)),
                            last_seen_at=float(d.get("last_seen_at", 0)),
                        )
                    except Exception:
                        _log.warning("Skipping bad agent entry %s", aid, exc_info=True)
                        continue
                return
        except Exception:
            _log.warning("Failed to load agents from %s", AGENTS_PATH, exc_info=True)
    for m in chat:
        sid = str(m.sender_id or "").strip()
        if sid and sid not in agents:
            agents[sid] = AgentState(
                agent_id=sid,
                display_name=str(m.sender_name or sid),
                x=0, y=0,
                last_seen_at=float(m.created_at),
            )
    if agents:
        save_agents(force=True)


def save_agents(force: bool = False) -> None:
    global _agents_save_debounce_at
    now = time.time()
    if not force and (now - _agents_save_debounce_at) < _agents_save_debounce_sec:
        return
    _agents_save_debounce_at = now
    try:
        data = {
            aid: {
                "agent_id": a.agent_id,
                "display_name": a.display_name,
                "x": a.x, "y": a.y,
                "last_seen_at": a.last_seen_at,
            }
            for aid, a in agents.items()
        }
        AGENTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        _log.warning("Failed to save agents to %s", AGENTS_PATH, exc_info=True)


# --- Audit ---
audit: List[AuditEntry] = []
audit_max = 2000


def load_audit() -> None:
    global audit
    rows = read_jsonl(AUDIT_PATH, limit=audit_max)
    out: List[AuditEntry] = []
    for r in rows:
        try:
            out.append(AuditEntry(
                audit_id=str(r.get("audit_id") or uuid.uuid4()),
                method=str(r.get("method") or ""),
                path=str(r.get("path") or ""),
                query=str(r.get("query") or ""),
                status_code=int(r.get("status_code") or 0),
                duration_ms=float(r.get("duration_ms") or 0.0),
                client=str(r.get("client") or ""),
                content_type=str(r.get("content_type") or ""),
                body_preview=str(r.get("body_preview") or ""),
                body_json=(r.get("body_json") if isinstance(r.get("body_json"), dict) else None),
                created_at=float(r.get("created_at") or time.time()),
            ))
        except Exception:
            continue
    audit = out[-audit_max:]


def append_audit(entry: AuditEntry) -> None:
    audit.append(entry)
    if len(audit) > audit_max:
        del audit[: len(audit) - audit_max]
    append_jsonl(AUDIT_PATH, asdict(entry))


# --- Chat ---
chat: List[ChatMessage] = []
chat_max = 200
inboxes: Dict[str, List[dict]] = {}
_inbox_max = 120
_inbox_ttl_seconds = 600
chat_rate_limits = {"say": 10.0, "shout": 900.0}
chat_last_by_action: Dict[str, Dict[str, float]] = {"say": {}, "shout": {}}
topic: str = "getting started"
topic_set_at: float = 0.0
topic_history: List[dict] = []


def load_chat() -> None:
    global chat
    rows = read_jsonl(CHAT_PATH, limit=chat_max)
    out: List[ChatMessage] = []
    for r in rows:
        try:
            out.append(ChatMessage(
                msg_id=str(r.get("msg_id") or uuid.uuid4()),
                sender_type=r.get("sender_type") or "agent",
                sender_id=str(r.get("sender_id") or ""),
                sender_name=str(r.get("sender_name") or ""),
                text=str(r.get("text") or ""),
                created_at=float(r.get("created_at") or time.time()),
            ))
        except Exception:
            continue
    chat = out[-chat_max:]


def push_inbox(target_id: str, msg: dict) -> None:
    now = time.time()
    inbox = inboxes.get(target_id, [])
    inbox.append(msg)
    cutoff = now - _inbox_ttl_seconds
    inbox = [m for m in inbox if float(m.get("created_at") or 0) >= cutoff]
    if len(inbox) > _inbox_max:
        inbox = inbox[-_inbox_max:]
    inboxes[target_id] = inbox


def check_chat_rate(action: str, sender_id: str, now: float) -> Optional[dict]:
    limit = float(chat_rate_limits.get(action, 0))
    if limit <= 0:
        return None
    last_map = chat_last_by_action.setdefault(action, {})
    last_at = float(last_map.get(sender_id, 0))
    if last_at and now - last_at < limit:
        retry_after = max(0.0, limit - (now - last_at))
        return {"error": "rate_limited", "retry_after": round(retry_after, 3)}
    last_map[sender_id] = now
    return None


def distance_fields(a: AgentState, b: AgentState) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def dedupe_recent_chat(messages: List[dict]) -> List[dict]:
    if not messages:
        return []
    out: List[dict] = []
    prev_sender: Optional[str] = None
    prev_key: Optional[frozenset] = None
    for m in messages:
        sender = str(m.get("sender_id") or "")
        text = str(m.get("text") or "")
        key = frozenset(normalize_text_for_similarity(text))
        if prev_sender is not None and prev_sender == sender and prev_key is not None and prev_key == key:
            continue
        out.append(m)
        prev_sender = sender
        prev_key = key
    return out


def recent_chat_texts_from_sender(sender_id: str, limit: int) -> List[str]:
    from_agent = [m.text for m in chat if m.sender_id == sender_id]
    return from_agent[-limit:] if limit else from_agent


def is_chat_repetitive(sender_id: str, text: str) -> bool:
    if CHAT_REPETITION_PENALTY_AIDOLLAR <= 0 or CHAT_REPETITION_WINDOW <= 0:
        return False
    recent = recent_chat_texts_from_sender(sender_id, CHAT_REPETITION_WINDOW)
    norm_new = normalize_text_for_similarity(text)
    for r in recent:
        if norm_new == normalize_text_for_similarity(r):
            return True
        if chat_text_similarity(text, r) >= CHAT_REPETITION_SIMILARITY_THRESHOLD:
            return True
    return False


# --- MoltWorld Webhooks ---
moltworld_webhooks: List[dict] = []
_moltworld_webhook_last_triggered: Dict[str, float] = {}


def load_moltworld_webhooks() -> None:
    global moltworld_webhooks
    try:
        if not MOLTWORLD_WEBHOOKS_PATH.exists():
            return
        data = json.loads(MOLTWORLD_WEBHOOKS_PATH.read_text(encoding="utf-8", errors="replace") or "[]")
        if isinstance(data, list):
            moltworld_webhooks[:] = [
                {"agent_id": str(w.get("agent_id", "")), "url": str(w.get("url", "")).strip(), "secret": (w.get("secret") or "").strip() or None}
                for w in data if w.get("url")
            ]
    except Exception:
        _log.warning("Failed to load webhooks from %s", MOLTWORLD_WEBHOOKS_PATH, exc_info=True)


def save_moltworld_webhooks() -> None:
    try:
        MOLTWORLD_WEBHOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        MOLTWORLD_WEBHOOKS_PATH.write_text(json.dumps(moltworld_webhooks, indent=2), encoding="utf-8")
    except Exception:
        _log.warning("Failed to save webhooks to %s", MOLTWORLD_WEBHOOKS_PATH, exc_info=True)


def _http_post_webhook(url: str, payload: dict, timeout: float = 10.0, headers: Optional[dict] = None) -> None:
    try:
        data = json.dumps(payload).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, method="POST", headers=h)
        urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        _log.debug("Webhook POST to %s failed", url[:120], exc_info=True)


def _is_gateway_wake_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return "/hooks/wake" in u or u.endswith("/hooks") or u.rstrip("/").endswith("/hooks/wake")


async def fire_moltworld_webhooks(sender_id: str, sender_name: str, text: str, scope: str) -> None:
    now = time.time()
    cooldown = MOLTWORLD_WEBHOOK_COOLDOWN_SECONDS
    new_chat_payload = {
        "event": "new_chat",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "text": (text or "")[:2000],
        "scope": scope,
        "world_base_url": WORLD_PUBLIC_URL,
    }
    for w in moltworld_webhooks:
        agent_id = (w.get("agent_id") or "").strip()
        url = (w.get("url") or "").strip()
        secret = (w.get("secret") or "").strip() or None
        if not url or not agent_id:
            continue
        if agent_id == sender_id:
            continue
        last = _moltworld_webhook_last_triggered.get(agent_id, 0)
        if now - last < cooldown:
            continue
        _moltworld_webhook_last_triggered[agent_id] = now
        if _is_gateway_wake_url(url):
            wake_text = (
                f"MoltWorld turn: You are {agent_id}. Call world_state to get the world and recent chat, "
                "then call chat_say with one short in-character message. Use the tools; do not reply with only text."
            )
            payload = {"text": wake_text, "mode": "now"}
            headers = {}
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
            try:
                await asyncio.to_thread(_http_post_webhook, url, payload, 10.0, headers)
            except Exception:
                _log.debug("Webhook thread failed for %s", agent_id, exc_info=True)
        else:
            try:
                await asyncio.to_thread(_http_post_webhook, url, new_chat_payload)
            except Exception:
                _log.debug("Webhook thread failed for %s", agent_id, exc_info=True)


# --- Trace ---
trace: List[TraceEvent] = []
trace_max = 600


def load_trace() -> None:
    global trace
    rows = read_jsonl(TRACE_PATH, limit=trace_max)
    out: List[TraceEvent] = []
    for r in rows:
        try:
            out.append(TraceEvent(
                event_id=str(r.get("event_id") or uuid.uuid4()),
                agent_id=str(r.get("agent_id") or ""),
                agent_name=str(r.get("agent_name") or ""),
                kind=r.get("kind") or "action",
                summary=str(r.get("summary") or ""),
                data=dict(r.get("data") or {}),
                created_at=float(r.get("created_at") or time.time()),
            ))
        except Exception:
            continue
    trace = out[-trace_max:]


def emit_trace(agent_id: str, agent_name: str, kind: str, summary: str, data: Optional[dict] = None) -> None:
    try:
        now = time.time()
        ev = TraceEvent(
            event_id=str(uuid.uuid4()),
            agent_id=str(agent_id or "unknown")[:80],
            agent_name=str(agent_name or agent_id or "unknown")[:80],
            kind=kind,
            summary=(summary or "").strip()[:400],
            data=data or {},
            created_at=now,
        )
        trace.append(ev)
        if len(trace) > trace_max:
            del trace[: len(trace) - trace_max]
        append_jsonl(TRACE_PATH, asdict(ev))
        try:
            asyncio.create_task(ws_manager.broadcast({"type": "trace", "data": asdict(ev)}))
        except Exception:
            pass  # no event loop — expected during sync calls
    except Exception:
        _log.warning("emit_trace failed for %s/%s", agent_id, kind, exc_info=True)


# --- Economy ---
economy_ledger: List[EconomyEntry] = []
balances: Dict[str, float] = {}


def load_economy() -> None:
    global economy_ledger
    rows = read_jsonl(ECONOMY_PATH)
    ledger: List[EconomyEntry] = []
    for r in rows:
        try:
            ledger.append(EconomyEntry(
                entry_id=str(r.get("entry_id") or r.get("id") or uuid.uuid4()),
                entry_type=r.get("entry_type") or "award",
                amount=float(r.get("amount") or 0.0),
                from_id=str(r.get("from_id") or ""),
                to_id=str(r.get("to_id") or ""),
                memo=str(r.get("memo") or ""),
                created_at=float(r.get("created_at") or time.time()),
            ))
        except Exception:
            continue
    economy_ledger = ledger
    recompute_balances()


# --- Jobs ---
jobs: Dict[str, Job] = {}
job_events: List[JobEvent] = []


def apply_job_event(ev: JobEvent) -> None:
    t = ev.event_type
    d = ev.data or {}
    if t == "create":
        jobs[ev.job_id] = Job(
            job_id=ev.job_id,
            title=str(d.get("title") or "")[:200],
            body=str(d.get("body") or "")[:4000],
            reward=float(d.get("reward") or 0.0),
            status="open",
            created_by=str(d.get("created_by") or "human")[:80],
            created_at=float(d.get("created_at") or ev.created_at),
            claimed_by="", claimed_at=0.0,
            submitted_by="", submitted_at=0.0, submission="",
            reviewed_by="", reviewed_at=0.0, review_note="",
            auto_verify_ok=None, auto_verify_name="", auto_verify_note="",
            auto_verify_artifacts={}, auto_verified_at=0.0,
            fingerprint=str(d.get("fingerprint") or "")[:120],
            ratings=(dict(d.get("ratings") or {}) if isinstance(d.get("ratings"), dict) else {}),
            reward_mode=str(d.get("reward_mode") or "manual")[:40],
            reward_calc=(dict(d.get("reward_calc") or {}) if isinstance(d.get("reward_calc"), dict) else {}),
            source=str(d.get("source") or "unknown")[:40],
            parent_job_id=str(d.get("parent_job_id") or "")[:80],
        )
        return
    job = jobs.get(ev.job_id)
    if not job:
        return
    if t == "claim":
        if job.status == "open":
            job.status = "claimed"
            job.claimed_by = str(d.get("agent_id") or "")[:80]
            job.claimed_at = float(d.get("created_at") or ev.created_at)
        return
    if t == "submit" and job.status in ("claimed", "open"):
        job.status = "submitted"
        job.submitted_by = str(d.get("agent_id") or "")[:80]
        job.submitted_at = float(d.get("created_at") or ev.created_at)
        job.submission = str(d.get("submission") or "")[:20000]
        return
    if t == "verify" and job.status == "submitted":
        ok = d.get("ok")
        job.auto_verify_ok = ok if isinstance(ok, bool) else None
        job.auto_verify_name = str(d.get("verifier") or "")[:80]
        job.auto_verify_note = str(d.get("note") or "")[:2000]
        arts = d.get("artifacts")
        job.auto_verify_artifacts = arts if isinstance(arts, dict) else {}
        job.auto_verified_at = float(d.get("created_at") or ev.created_at)
        return
    if t == "review" and job.status == "submitted":
        job.reviewed_by = str(d.get("reviewed_by") or "human")[:80]
        job.reviewed_at = float(d.get("created_at") or ev.created_at)
        job.review_note = str(d.get("note") or "")[:2000]
        job.status = "approved" if bool(d.get("approved")) else "rejected"
        return
    if t == "update" and job.status in ("open", "claimed"):
        if "title" in d and isinstance(d.get("title"), str):
            job.title = str(d.get("title") or "")[:200]
        if "body" in d and isinstance(d.get("body"), str):
            job.body = str(d.get("body") or "")[:4000]
        if "reward" in d and d.get("reward") is not None:
            try:
                job.reward = float(d.get("reward") or job.reward)
            except Exception:
                pass
        if "ratings" in d and isinstance(d.get("ratings"), dict):
            job.ratings = dict(d.get("ratings") or {})
        if "reward_mode" in d and isinstance(d.get("reward_mode"), str):
            job.reward_mode = str(d.get("reward_mode") or "")[:40]
        if "reward_calc" in d and isinstance(d.get("reward_calc"), dict):
            job.reward_calc = dict(d.get("reward_calc") or {})
        return
    if t == "cancel" and job.status in ("open", "claimed", "submitted"):
        job.status = "cancelled"
        return
    if t == "unclaim" and job.status == "claimed":
        job.status = "open"
        job.claimed_by = ""
        job.claimed_at = 0.0
        return


def append_job_event(event_type: str, job_id: str, data: dict) -> JobEvent:
    ev = JobEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        job_id=job_id,
        data=data,
        created_at=time.time(),
    )
    job_events.append(ev)
    append_jsonl(JOBS_PATH, asdict(ev))
    apply_job_event(ev)
    return ev


def load_jobs() -> None:
    global job_events, jobs
    jobs = {}
    job_events = []
    rows = read_jsonl(JOBS_PATH)
    for r in rows:
        try:
            ev = JobEvent(
                event_id=str(r.get("event_id") or uuid.uuid4()),
                event_type=r.get("event_type"),
                job_id=str(r.get("job_id")),
                data=dict(r.get("data") or {}),
                created_at=float(r.get("created_at") or time.time()),
            )
            job_events.append(ev)
            apply_job_event(ev)
        except Exception:
            continue


def requeue_stale_claims(now: Optional[float] = None) -> int:
    import os
    now = float(now or time.time())
    stale_seconds = float(os.getenv("CLAIM_STALE_SECONDS", "1800"))
    if stale_seconds <= 0:
        return 0
    requeued = 0
    for j in list(jobs.values()):
        try:
            if j.status != "claimed":
                continue
            if not j.claimed_at:
                continue
            age = now - float(j.claimed_at)
            if age <= stale_seconds:
                continue
            append_job_event("unclaim", j.job_id, {
                "reason": "stale_claim",
                "stale_seconds": age,
                "prev_claimed_by": j.claimed_by,
                "prev_claimed_at": j.claimed_at,
            })
            requeued += 1
        except Exception:
            continue
    return requeued


# --- Events ---
events: Dict[str, VillageEvent] = {}
event_log: List[EventLogEntry] = []


def apply_event_log(ev: EventLogEntry) -> None:
    d = ev.data or {}
    if ev.event_type == "create":
        events[ev.event_id] = VillageEvent(
            event_id=ev.event_id,
            title=str(d.get("title") or "")[:200],
            description=str(d.get("description") or "")[:4000],
            location_id=str(d.get("location_id") or "")[:80],
            start_day=int(d.get("start_day") or 0),
            start_minute=int(d.get("start_minute") or 0),
            duration_min=int(d.get("duration_min") or 60),
            status="scheduled",
            created_by=str(d.get("created_by") or "human")[:80],
            created_at=float(d.get("created_at") or ev.created_at),
            invites=[], rsvps={},
        )
        return
    e = events.get(ev.event_id)
    if not e:
        return
    if ev.event_type == "invite" and e.status == "scheduled":
        inv = {
            "from_agent_id": str(d.get("from_agent_id") or "")[:80],
            "to_agent_id": str(d.get("to_agent_id") or "")[:80],
            "message": str(d.get("message") or "")[:400],
            "created_at": float(d.get("created_at") or ev.created_at),
        }
        e.invites.append(inv)
    elif ev.event_type == "rsvp" and e.status == "scheduled":
        agent_id = str(d.get("agent_id") or "")[:80]
        status = str(d.get("status") or "maybe")
        if agent_id:
            e.rsvps[agent_id] = status
    elif ev.event_type == "cancel" and e.status == "scheduled":
        e.status = "cancelled"


def append_event_log(event_type: str, event_id: str, data: dict) -> EventLogEntry:
    ev = EventLogEntry(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        event_id=event_id,
        data=data,
        created_at=time.time(),
    )
    event_log.append(ev)
    append_jsonl(EVENTS_PATH, asdict(ev))
    apply_event_log(ev)
    return ev


def load_events() -> None:
    global events, event_log
    events = {}
    event_log = []
    rows = read_jsonl(EVENTS_PATH)
    for r in rows:
        try:
            ev = EventLogEntry(
                log_id=str(r.get("log_id") or uuid.uuid4()),
                event_type=r.get("event_type"),
                event_id=str(r.get("event_id")),
                data=dict(r.get("data") or {}),
                created_at=float(r.get("created_at") or time.time()),
            )
            event_log.append(ev)
            apply_event_log(ev)
        except Exception:
            continue


# --- Board ---
board_posts: Dict[str, BoardPost] = {}
board_replies: Dict[str, List[BoardReply]] = {}


# --- Opportunities ---
opportunities: Dict[str, Opportunity] = {}


# --- Memory helpers ---

def memory_path(agent_id: str):
    safe = "".join([c for c in agent_id if c.isalnum() or c in ("-", "_")]) or "agent"
    return MEMORY_DIR / f"{safe}.jsonl"


def memory_embed_path(agent_id: str):
    safe = "".join([c for c in agent_id if c.isalnum() or c in ("-", "_")]) or "agent"
    return MEMORY_EMBED_DIR / f"{safe}.jsonl"


def get_embedding(text: str) -> Optional[List[float]]:
    if not EMBEDDINGS_BASE_URL:
        return None
    payload = {"model": EMBEDDINGS_MODEL, "prompt": text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{EMBEDDINGS_BASE_URL}/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=EMBEDDINGS_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            emb = obj.get("embedding")
            if not isinstance(emb, list) or not emb:
                return None
            out = [float(x) for x in emb]
            if EMBEDDINGS_TRUNCATE > 0 and len(out) > EMBEDDINGS_TRUNCATE:
                out = out[:EMBEDDINGS_TRUNCATE]
            return out
    except Exception:
        _log.debug("Embedding request failed for text len=%d", len(text or ""), exc_info=True)
        return None


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    dot = na = nb = 0.0
    for i in range(n):
        x, y = float(a[i]), float(b[i])
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (math.sqrt(na) * math.sqrt(nb))))


# --- Token requests ---
token_requests: List[dict] = []
token_requests_max = 200


# --- World snapshot ---

def get_rules_text() -> str:
    from app.config import CHAT_REPETITION_PENALTY_AIDOLLAR, TASK_FAIL_PENALTY
    return f"""MoltWorld ai$ rules — read these to know what earns or costs ai$.

EARN ai$:
• Starting balance: {STARTING_AIDOLLARS} ai$ when you register.
• Action diversity: Small reward for chat_say, board_post, and move. Reward is reduced if you repeat the same action type (e.g. many chat_says in a row).
• Fiverr discovery: Share a fiverr.com link in chat (with enough context) to earn a one-time reward per URL per day.
• Job verification: When a job you proposed or executed is verified complete, you earn 1 ai$ each (proposer and executor).
• PayPal: If enabled, USD payments are converted to ai$ and credited to your account.

COST ai$:
• Repetitive chat: If your message is too similar to your own recent messages (same or very similar meaning), you are penalized {CHAT_REPETITION_PENALTY_AIDOLLAR} ai$. Vary what you say.
• Task fail: If a job you executed is marked failed (rejected or not done), a penalty may be applied (default {TASK_FAIL_PENALTY} ai$).
• Other penalties: Admins or the system can apply penalties for rule violations.

There is a **Rules room** on the map (landmark at (12,10)); walk there to read the rules. The rules are also in this response and at GET /rules."""


def get_world_snapshot() -> WorldSnapshot:
    elapsed = max(0.0, time.time() - world_started_at)
    sim_minutes_total = int(elapsed * SIM_MINUTES_PER_REAL_SECOND)
    day = sim_minutes_total // (24 * 60)
    minute_of_day = sim_minutes_total % (24 * 60)
    agents_list = []
    for a in agents.values():
        agents_list.append({
            "agent_id": a.agent_id,
            "display_name": a.display_name,
            "x": a.x, "y": a.y,
            "last_seen_at": a.last_seen_at,
        })
    recent_chat_limit = 50
    raw_recent = [asdict(m) for m in chat[-recent_chat_limit:]]
    recent_chat_deduped = dedupe_recent_chat(raw_recent)
    return WorldSnapshot(
        world_size=WORLD_SIZE,
        tick=tick,
        day=day,
        minute_of_day=minute_of_day,
        landmarks=LANDMARKS,
        agents=agents_list,
        recent_chat=recent_chat_deduped,
        rules=get_rules_text(),
        rules_reminder="You should visit the Rules room: use go_to target=rules or move toward (12,10). When you have no other short-term goal, go there to read the ai$ rules. The full rules are in this response (field 'rules') and at GET /rules.",
    )


# --- Load all state on module import ---

def load_all() -> None:
    load_audit()
    load_chat()
    load_agents()
    load_trace()
    load_economy()
    load_jobs()
    load_opportunities()
    load_events()
    load_moltworld_webhooks()
