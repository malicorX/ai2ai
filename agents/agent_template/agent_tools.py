"""
Agent API tools — HTTP wrappers, navigation helpers, shared utilities.

Every function that calls WORLD_API lives here. agent.py and do_job.py
import from this module; this module imports nothing from them.
"""
from __future__ import annotations

import json
import os
import random
import re
import time

import requests
from typing import Optional

# ---------------------------------------------------------------------------
# Config (from environment — set before the process starts via Docker/shell)
# ---------------------------------------------------------------------------

WORLD_API = os.getenv("WORLD_API_BASE", "http://localhost:8000").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "agent_1")
DISPLAY_NAME = os.getenv("DISPLAY_NAME", AGENT_ID)
PERSONA_FILE = os.getenv("PERSONA_FILE", "").strip()
PERSONALITY = os.getenv("PERSONALITY", "").strip()
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/app/workspace").strip()
COMPUTER_LANDMARK_ID = os.getenv("COMPUTER_LANDMARK_ID", "computer").strip()
COMPUTER_ACCESS_RADIUS = int(os.getenv("COMPUTER_ACCESS_RADIUS", "1"))
HOME_LANDMARK_ID = os.getenv("HOME_LANDMARK_ID", f"home_{AGENT_ID}").strip()
ROLE = os.getenv("ROLE", "proposer" if AGENT_ID == "agent_1" else "executor").strip().lower()
WORLD_AGENT_TOKEN = os.getenv("WORLD_AGENT_TOKEN", "").strip()
MAX_CHAT_TO_SCAN = int(os.getenv("MAX_CHAT_TO_SCAN", "50"))

USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "0").strip() == "1"

# Shared HTTP session (Bearer token attached when configured)
_world_session = requests.Session()
if WORLD_AGENT_TOKEN:
    _world_session.headers["Authorization"] = f"Bearer {WORLD_AGENT_TOKEN}"

# Dedupe state for chat_send (job-status announcements, keyed by kind+id)
_job_status_last_sent: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

def load_persona() -> str:
    global PERSONALITY
    if PERSONALITY:
        return PERSONALITY
    if not PERSONA_FILE:
        PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
        return PERSONALITY
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            PERSONALITY = f.read().strip()
            if not PERSONALITY:
                PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
            return PERSONALITY
    except Exception:
        PERSONALITY = "Concise, pragmatic, and focused on concrete next steps."
        return PERSONALITY


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _read_file(path: str, max_bytes: int = 20000) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(max_bytes)
    except Exception:
        return ""


def _append_file(path: str, text: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
    except Exception:
        return


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def _sign(n: int) -> int:
    return 0 if n == 0 else (1 if n > 0 else -1)


def _step_towards(ax: int, ay: int, tx: int, ty: int):
    return (_sign(tx - ax), _sign(ty - ay))


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def _get_landmark(world, lm_id: str):
    for lm in world.get("landmarks", []):
        if lm.get("id") == lm_id:
            return lm
    return None


def _at_landmark(world, lm_id: str, radius: int = 0) -> bool:
    lm = _get_landmark(world, lm_id)
    if not lm:
        return False
    agents = world.get("agents", [])
    me = next((a for a in agents if a.get("agent_id") == AGENT_ID), None)
    if not me:
        return False
    ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
    lx, ly = int(lm.get("x", 0)), int(lm.get("y", 0))
    return _chebyshev(ax, ay, lx, ly) <= radius


def _move_towards(world, tx: int, ty: int) -> None:
    agents = world.get("agents", [])
    me = next((a for a in agents if a.get("agent_id") == AGENT_ID), None)
    if not me:
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
    else:
        ax, ay = int(me.get("x", 0)), int(me.get("y", 0))
        dx, dy = _step_towards(ax, ay, tx, ty)
    _world_session.post(f"{WORLD_API}/agents/{AGENT_ID}/move", json={"dx": dx, "dy": dy}, timeout=10)


# ---------------------------------------------------------------------------
# Style (personality-flavored text)
# ---------------------------------------------------------------------------

def _style(text: str) -> str:
    p = (PERSONALITY or "").lower()
    if "sarcast" in p:
        return text + " (sure.)"
    if "formal" in p:
        return "Indeed. " + text
    if any(
        k in text
        for k in (
            "[task:",
            "Job `",
            "was approved",
            "was rejected",
            "I submitted",
            "I executed the task",
            "New task posted",
        )
    ):
        return text
    if "curious" in p and ("?" not in text) and random.random() < 0.35:
        return text + " What do you think?"
    return text


# ---------------------------------------------------------------------------
# World API
# ---------------------------------------------------------------------------

def upsert():
    _world_session.post(
        f"{WORLD_API}/agents/upsert",
        json={"agent_id": AGENT_ID, "display_name": DISPLAY_NAME},
        timeout=10,
    )


def get_world():
    r = _world_session.get(f"{WORLD_API}/world", timeout=10)
    r.raise_for_status()
    return r.json()


def get_run_id() -> str:
    r = _world_session.get(f"{WORLD_API}/run", timeout=10)
    r.raise_for_status()
    return str(r.json().get("run_id") or "")


def world_move(dx: int, dy: int) -> None:
    """Execute a single move (dx, dy). Used by OpenClaw/LangGraph so the LLM decides direction."""
    try:
        _world_session.post(
            f"{WORLD_API}/agents/{AGENT_ID}/move",
            json={"dx": int(dx), "dy": int(dy)},
            timeout=10,
        )
    except Exception as e:
        trace_event("error", "world_move failed", {"error": str(e)[:200]})


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------

def trace_event(kind: str, summary: str, data=None) -> None:
    data = data or {}
    try:
        _world_session.post(
            f"{WORLD_API}/trace/event",
            json={
                "agent_id": AGENT_ID,
                "agent_name": DISPLAY_NAME,
                "kind": kind,
                "summary": summary,
                "data": data,
            },
            timeout=5,
        )
    except Exception:
        return


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

def board_post(title: str, body: str, audience: str = "humans", tags: list | None = None) -> dict:
    payload = {
        "title": str(title or "")[:200],
        "body": str(body or "")[:5000],
        "audience": str(audience or "humans").strip(),
        "author_type": "agent",
        "author_id": AGENT_ID,
        "tags": list(tags or [])[:10],
    }
    try:
        r = _world_session.post(f"{WORLD_API}/board/posts", json=payload, timeout=10)
        if r.status_code >= 400:
            return {"ok": False, "error": (r.text or "")[:200]}
        return r.json() or {"ok": True}
    except Exception as e:
        trace_event("error", "board_post failed", {"error": str(e)[:200]})
        return {"ok": False, "error": str(e)[:200]}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def chat_recent(limit: int = MAX_CHAT_TO_SCAN):
    r = _world_session.get(f"{WORLD_API}/chat/recent?limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("messages", [])


def chat_send(text: str):
    """Centralized chat sender with a small dedupe gate for job-status announcements."""
    global _job_status_last_sent

    try:
        t = str(text or "")
        norm = re.sub(r"\s+what do you think\?\s*$", "", t.strip(), flags=re.IGNORECASE)
        norm = re.sub(r"\s+", " ", norm).strip()

        def _first_uuid(s: str) -> str:
            m0 = re.search(r"(?i)\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", s)
            return (m0.group(1).lower() if m0 else "")

        key = ""
        low = norm.lower()
        if "redo cap reached" in low:
            rid = _first_uuid(norm)
            if rid:
                key = f"redo_cap:root:{rid}"
        elif (" was approved" in low) or (" was rejected" in low):
            outcome = "approved" if " was approved" in low else "rejected"
            jid = _first_uuid(norm)
            if jid:
                key = f"job:{outcome}:{jid}"

        if key:
            if key in _job_status_last_sent:
                return
            _job_status_last_sent[key] = time.time()
    except Exception:
        pass

    payload = {
        "sender_type": "agent",
        "sender_id": AGENT_ID,
        "sender_name": DISPLAY_NAME,
        "text": text,
    }
    try:
        r = _world_session.post(f"{WORLD_API}/chat/send", json=payload, timeout=10)
        if int(getattr(r, "status_code", 0) or 0) >= 400:
            trace_event("error", "chat_send failed", {"status": r.status_code, "body": (r.text or "")[:200]})
    except Exception as e:
        trace_event("error", "chat_send exception", {"error": str(e)[:200]})
        return


def chat_topic_get():
    r = _world_session.get(f"{WORLD_API}/chat/topic", timeout=10)
    r.raise_for_status()
    return r.json()


def chat_topic_set(topic: str, reason: str = ""):
    _world_session.post(
        f"{WORLD_API}/chat/topic/set",
        json={
            "topic": topic,
            "by_agent_id": AGENT_ID,
            "by_agent_name": DISPLAY_NAME,
            "reason": reason,
        },
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------

def economy_balance() -> float:
    r = _world_session.get(f"{WORLD_API}/economy/balance/{AGENT_ID}", timeout=10)
    r.raise_for_status()
    return float(r.json().get("balance") or 0.0)


def economy_balance_of(agent_id: str) -> float:
    r = _world_session.get(f"{WORLD_API}/economy/balance/{agent_id}", timeout=10)
    r.raise_for_status()
    return float(r.json().get("balance") or 0.0)


def economy_transfer(to_id: str, amount: float, memo: str = "") -> None:
    _world_session.post(
        f"{WORLD_API}/economy/transfer",
        json={"from_id": AGENT_ID, "to_id": to_id, "amount": float(amount), "memo": memo},
        timeout=10,
    )


def economy_recent_earnings(limit: int = 10) -> list:
    try:
        r = _world_session.get(f"{WORLD_API}/economy/recent_earnings", params={"agent_id": AGENT_ID, "limit": limit}, timeout=5)
        r.raise_for_status()
        data = r.json()
        return list(data.get("entries") or [])
    except Exception:
        return []


def economy_record_action(action_kind: str) -> None:
    try:
        _world_session.post(
            f"{WORLD_API}/economy/record_action",
            json={"action_kind": action_kind},
            timeout=5,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def memory_append(kind: str, text: str, tags=None) -> None:
    tags = tags or []
    _world_session.post(
        f"{WORLD_API}/memory/{AGENT_ID}/append",
        json={"kind": kind, "text": text, "tags": tags},
        timeout=10,
    )


def memory_recent(limit: int = 10):
    r = _world_session.get(f"{WORLD_API}/memory/{AGENT_ID}/recent?limit={limit}", timeout=10)
    r.raise_for_status()
    return r.json().get("memories", [])


def memory_retrieve(q: str, k: int = 8):
    r = _world_session.get(f"{WORLD_API}/memory/{AGENT_ID}/retrieve", params={"q": q, "k": k}, timeout=10)
    r.raise_for_status()
    return r.json().get("memories", [])


def rate_importance(text: str) -> float:
    """LLM-scored importance in [0,1]."""
    if not USE_LANGGRAPH:
        return 0.3
    sys = "Rate the importance of the memory for future behavior. Return only a number between 0 and 1."
    user = f"Memory:\n{text}\n\nScore 0..1:"
    try:
        from agent_template.langgraph_runtime import llm_chat
        raw = llm_chat(sys, user, max_tokens=8)
        v = float(raw.strip().split()[0])
        if v < 0:
            v = 0.0
        if v > 1:
            v = 1.0
        return v
    except Exception:
        return 0.3


def memory_append_scored(kind: str, text: str, tags=None, importance: float | None = None) -> None:
    tags = tags or []
    if importance is None:
        importance = rate_importance(text)
    try:
        _world_session.post(
            f"{WORLD_API}/memory/{AGENT_ID}/append",
            json={"kind": kind, "text": text, "tags": tags, "importance": float(importance)},
            timeout=10,
        )
    except Exception:
        return


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def jobs_list(status: str | None = "open", limit: int = 20):
    params = {"limit": int(limit)}
    if status is not None:
        params["status"] = str(status)
    r = _world_session.get(f"{WORLD_API}/jobs", params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("jobs", [])


def jobs_get(job_id: str) -> dict:
    r = _world_session.get(f"{WORLD_API}/jobs/{job_id}", timeout=10)
    r.raise_for_status()
    return r.json().get("job", {}) or {}


def jobs_claim(job_id: str) -> bool:
    r = _world_session.post(f"{WORLD_API}/jobs/{job_id}/claim", json={"agent_id": AGENT_ID}, timeout=10)
    try:
        data = r.json()
    except Exception:
        return False
    return bool(data.get("ok"))


def jobs_submit(job_id: str, submission: str) -> bool:
    r = _world_session.post(
        f"{WORLD_API}/jobs/{job_id}/submit",
        json={"agent_id": AGENT_ID, "submission": submission},
        timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        return False
    return bool(data.get("ok"))


def jobs_review(
    job_id: str,
    approved: bool,
    note: str,
    reviewed_by: str | None = None,
    penalty: float | None = None,
) -> bool:
    by = reviewed_by or AGENT_ID
    payload: dict = {
        "approved": bool(approved),
        "reviewed_by": by,
        "note": str(note or "")[:2000],
        "payout": None,
        "penalty": float(penalty) if penalty is not None and penalty > 0 else None,
    }
    r = _world_session.post(
        f"{WORLD_API}/jobs/{job_id}/review",
        json=payload,
        timeout=15,
    )
    try:
        data = r.json()
    except Exception:
        return False
    return "error" not in data and bool(data.get("ok"))


def jobs_create(title: str, body: str, reward: float) -> str:
    """Create a job on the backend. Returns job_id or empty string."""
    title = (title or "").strip()
    body = (body or "").strip()
    reward = float(reward or 0.0)
    if not title or not body or reward <= 0:
        return ""
    r = _world_session.post(
        f"{WORLD_API}/jobs/create",
        json={"title": title, "body": body, "reward": reward, "created_by": AGENT_ID},
        timeout=10,
    )
    try:
        data = r.json()
    except Exception:
        return ""
    try:
        if not bool(data.get("ok")):
            try:
                trace_event(
                    "status",
                    "jobs_create failed",
                    {
                        "title": title[:160],
                        "error": str(data.get("error") or "")[:120],
                        "reason": str(data.get("reason") or "")[:200],
                    },
                )
            except Exception:
                pass
            return ""
        job = data.get("job") or {}
        jid = str(job.get("job_id") or "").strip()
        return jid
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def events_list(upcoming_only: bool = True, limit: int = 20):
    r = _world_session.get(f"{WORLD_API}/events", params={"upcoming_only": str(upcoming_only).lower(), "limit": limit}, timeout=10)
    r.raise_for_status()
    return r.json().get("events", [])


def event_create(title: str, description: str, location_id: str, start_day: int, start_minute: int, duration_min: int) -> str | None:
    r = _world_session.post(
        f"{WORLD_API}/events/create",
        json={
            "title": title,
            "description": description,
            "location_id": location_id,
            "start_day": int(start_day),
            "start_minute": int(start_minute),
            "duration_min": int(duration_min),
            "created_by": AGENT_ID,
        },
        timeout=10,
    )
    try:
        data = r.json()
    except Exception:
        return None
    if not data.get("ok"):
        return None
    ev = data.get("event") or {}
    return ev.get("event_id")


def event_invite(event_id: str, to_agent_id: str, message: str) -> None:
    try:
        _world_session.post(
            f"{WORLD_API}/events/{event_id}/invite",
            json={"from_agent_id": AGENT_ID, "to_agent_id": to_agent_id, "message": message},
            timeout=10,
        )
    except Exception:
        return


def event_rsvp(event_id: str, status: str, note: str = "") -> None:
    try:
        _world_session.post(
            f"{WORLD_API}/events/{event_id}/rsvp",
            json={"agent_id": AGENT_ID, "status": status, "note": note},
            timeout=10,
        )
    except Exception:
        return


# ---------------------------------------------------------------------------
# Tools Gateway
# ---------------------------------------------------------------------------

def web_fetch(url: str, timeout_seconds: float = 15.0, max_bytes: int = 200000) -> dict:
    try:
        payload = {
            "agent_id": AGENT_ID,
            "agent_name": DISPLAY_NAME or AGENT_ID,
            "url": str(url or "")[:2000],
            "timeout_seconds": float(timeout_seconds),
            "max_bytes": int(max_bytes),
        }
        r = _world_session.post(f"{WORLD_API}/tools/web_fetch", json=payload, timeout=20)
        return r.json() if r is not None else {"error": "no_response"}
    except Exception as e:
        return {"error": "web_fetch_failed", "detail": str(e)[:200]}


def web_search(query: str, num: int = 10) -> dict:
    try:
        payload = {
            "agent_id": AGENT_ID,
            "agent_name": DISPLAY_NAME or AGENT_ID,
            "query": str(query or "")[:500],
            "num": max(1, min(int(num or 10), 20)),
        }
        r = _world_session.post(f"{WORLD_API}/tools/web_search", json=payload, timeout=25)
        out = r.json() if r is not None else {}
        if "results" not in out:
            out["results"] = []
        return out
    except Exception as e:
        return {"error": "web_search_failed", "detail": str(e)[:200], "results": []}


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def artifact_put(job_id: str, path: str, content: str, content_type: str = "text/plain") -> dict:
    try:
        payload = {
            "job_id": str(job_id or "")[:80],
            "path": str(path or "")[:200],
            "content": str(content or "")[:250000],
            "content_type": str(content_type or "")[:80],
        }
        r = _world_session.post(f"{WORLD_API}/artifacts/put", json=payload, timeout=15)
        return r.json() if r is not None else {"error": "no_response"}
    except Exception as e:
        return {"error": "artifact_put_failed", "detail": str(e)[:200]}


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------

def opportunities_list(limit: int = 40) -> list[dict]:
    try:
        lim = int(limit or 0)
    except Exception:
        lim = 40
    lim = max(1, min(200, lim))
    try:
        r = _world_session.get(f"{WORLD_API}/opportunities?limit={lim}", timeout=10)
        data = r.json() if r is not None else {}
        items = data.get("items") or []
        return items if isinstance(items, list) else []
    except Exception:
        return []


def opportunities_update(fingerprint: str, status: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None) -> dict:
    try:
        payload = {
            "fingerprint": str(fingerprint or "").strip(),
        }
        if status is not None:
            payload["status"] = str(status).strip()
        if notes is not None:
            payload["notes"] = str(notes)[:2000]
        if tags is not None:
            payload["tags"] = [str(t)[:40] for t in tags if str(t).strip()][:20]
        r = _world_session.post(f"{WORLD_API}/opportunities/update", json=payload, timeout=10)
        return r.json() if r is not None else {"error": "no_response"}
    except Exception as e:
        return {"error": "opportunities_update_failed", "detail": str(e)[:200]}


def email_template_generate(opportunity_title: str, opportunity_platform: str, client_name: Optional[str] = None, package_tier: Optional[str] = None) -> str:
    try:
        from agent_template.langgraph_runtime import llm_chat
        sys_prompt = (
            "You are writing a professional client outreach email for a freelance opportunity.\n"
            "Generate a complete email with:\n"
            "- Subject line (concise, value-focused)\n"
            "- Body (brief intro, value proposition, clear next step)\n"
            "- Professional but friendly tone\n"
            "- No spammy language\n"
            "- Keep total length under 300 words\n"
        )
        user_prompt = (
            f"Opportunity: {opportunity_title}\n"
            f"Platform: {opportunity_platform}\n"
        )
        if client_name:
            user_prompt += f"Client name: {client_name}\n"
        if package_tier:
            user_prompt += f"Package tier: {package_tier}\n"
        user_prompt += "\nGenerate the email now (subject line first, then body)."

        result = llm_chat(sys_prompt, user_prompt, max_tokens=400) or ""
        return result.strip()
    except Exception as e:
        return f"Error generating email template: {str(e)[:200]}"


def client_response_simulate(fingerprint: str, email_content: str) -> dict:
    try:
        payload = {
            "fingerprint": str(fingerprint or "").strip(),
            "email_content": str(email_content or ""),
        }
        r = _world_session.post(f"{WORLD_API}/opportunities/client_response", json=payload, timeout=15)
        return r.json() if r is not None else {"error": "no_response"}
    except Exception as e:
        return {"error": "client_response_simulate_failed", "detail": str(e)[:200]}


# ---------------------------------------------------------------------------
# Reset helper (called by agent.py on new run)
# ---------------------------------------------------------------------------

def reset_chat_dedupe():
    """Clear job-status dedupe state (called when backend run_id changes)."""
    global _job_status_last_sent
    _job_status_last_sent = {}
