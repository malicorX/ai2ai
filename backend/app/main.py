from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import math
import urllib.request
import urllib.parse
import socket
import ipaddress
import uuid
import time
import re
import string
import tempfile
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Literal, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse
from starlette.responses import HTMLResponse, FileResponse


WORLD_SIZE = 32
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ECONOMY_PATH = DATA_DIR / "economy_ledger.jsonl"
JOBS_PATH = DATA_DIR / "jobs_events.jsonl"
EVENTS_PATH = DATA_DIR / "events_events.jsonl"
CHAT_PATH = DATA_DIR / "chat_messages.jsonl"
TRACE_PATH = DATA_DIR / "trace_events.jsonl"
AUDIT_PATH = DATA_DIR / "audit_log.jsonl"
RUNS_DIR = DATA_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_EMBED_DIR = DATA_DIR / "memory_embeddings"
MEMORY_EMBED_DIR.mkdir(parents=True, exist_ok=True)

# Persistent libraries / workspaces (NOT rotated on admin/new_run)
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.jsonl"
ARTIFACTS_DIR = (DATA_DIR / "artifacts").resolve()
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

STARTING_AIDOLLARS = float(os.getenv("STARTING_AIDOLLARS", "100"))
TREASURY_ID = os.getenv("TREASURY_ID", "treasury")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
TASK_FAIL_PENALTY = float(os.getenv("TASK_FAIL_PENALTY", "1.0"))

# PayPal Sandbox Integration
PAYPAL_ENABLED = os.getenv("PAYPAL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").strip().lower()  # "sandbox" or "live"
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()  # For webhook verification
# Conversion rate: 1 USD = X ai$ (default: 1 USD = 10 ai$)
PAYPAL_USD_TO_AIDOLLAR = float(os.getenv("PAYPAL_USD_TO_AIDOLLAR", "10.0"))

# --- Tool Gateway: web fetch (guardrails) ---
WEB_FETCH_ENABLED = os.getenv("WEB_FETCH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
# Comma-separated list of allowed domains/suffixes. Example: "wikipedia.org,open-meteo.com"
WEB_FETCH_ALLOWLIST = [d.strip().lower() for d in os.getenv("WEB_FETCH_ALLOWLIST", "").split(",") if d.strip()]
WEB_FETCH_TIMEOUT_SECONDS = float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15"))
WEB_FETCH_MAX_BYTES = int(float(os.getenv("WEB_FETCH_MAX_BYTES", "200000")))  # 200 KB default
WEB_FETCH_MAX_PER_REQUEST = int(float(os.getenv("WEB_FETCH_MAX_PER_REQUEST", "3")))  # per call, for batch support later

# --- Tool Gateway: web search (Serper API) ---
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SERPER_SEARCH_URL = "https://google.serper.dev/search"

# Run/session id (helps agents reset local state after /admin/new_run without restarting containers)
_run_id: str = time.strftime("%Y%m%d-%H%M%S")
_run_started_at: float = time.time()

EMBEDDINGS_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "").rstrip("/")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "llama3.1:8b")
EMBEDDINGS_TRUNCATE = int(os.getenv("EMBEDDINGS_TRUNCATE", "256"))
EMBEDDINGS_TIMEOUT_SECONDS = float(os.getenv("EMBEDDINGS_TIMEOUT_SECONDS", "30"))

# LLM-based verification for judgment tasks (e.g. "is Fiverr task 123888 done successfully?")
# Use OpenAI-compatible /v1/chat/completions (Ollama, vLLM, OpenAI).
VERIFY_LLM_BASE_URL = os.getenv("VERIFY_LLM_BASE_URL", "").rstrip("/")
VERIFY_LLM_MODEL = os.getenv("VERIFY_LLM_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
VERIFY_LLM_TIMEOUT_SECONDS = float(os.getenv("VERIFY_LLM_TIMEOUT_SECONDS", "60"))


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path, limit: Optional[int] = None) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    if limit is not None and limit > 0:
        return out[-limit:]
    return out


def _write_jsonl_atomic(path: Path, rows: List[dict]) -> None:
    """
    Rewrite a JSONL file atomically.
    Used for maintenance tasks (e.g., purging cancelled jobs) to prevent unbounded growth.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            try:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except Exception:
                continue
    tmp.replace(path)


def _rotate_logs(run_id: str, files: List[Path]) -> dict:
    """
    Copy the current JSONL logs into DATA_DIR/runs/<run_id>/ and truncate originals.
    Returns basic stats for response payloads.
    """
    runs_dir = RUNS_DIR / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    rotated = []
    for p in files:
        try:
            if p.exists():
                dst = runs_dir / p.name
                dst.write_bytes(p.read_bytes())
                p.write_text("", encoding="utf-8")
                rotated.append({"file": str(p.name), "bytes": int(dst.stat().st_size)})
        except Exception:
            continue
    # Best-effort write meta.json so the UI can show run boundaries.
    try:
        (runs_dir / "meta.json").write_text(
            json.dumps({"run_id": run_id, "rotated": rotated, "archived_at": time.time()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return {"run_id": run_id, "rotated": rotated, "dir": str(runs_dir)}


def _safe_json_preview(body: bytes) -> Optional[dict]:
    """Best-effort: parse a small JSON body for audit logs (returns dict only)."""
    try:
        s = body.decode("utf-8", errors="replace").strip()
        if not s:
            return None
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"_": obj}
    except Exception:
        return None


@dataclass
class AuditEntry:
    audit_id: str
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float
    client: str
    content_type: str
    body_preview: str
    body_json: Optional[dict]
    created_at: float


_audit: List[AuditEntry] = []
_audit_max = 2000


def _load_audit() -> None:
    global _audit
    rows = _read_jsonl(AUDIT_PATH, limit=_audit_max)
    out: List[AuditEntry] = []
    for r in rows:
        try:
            out.append(
                AuditEntry(
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
                )
            )
        except Exception:
            continue
    _audit = out[-_audit_max:]


def _append_audit(entry: AuditEntry) -> None:
    _audit.append(entry)
    if len(_audit) > _audit_max:
        del _audit[: len(_audit) - _audit_max]
    _append_jsonl(AUDIT_PATH, asdict(entry))


_load_audit()


@dataclass
class AgentState:
    agent_id: str
    display_name: str
    x: int = 0
    y: int = 0
    last_seen_at: float = 0.0


class MoveRequest(BaseModel):
    dx: Optional[int] = None
    dy: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


class UpsertAgentRequest(BaseModel):
    agent_id: str
    display_name: str = Field(default_factory=str)


class WorldSnapshot(BaseModel):
    world_size: int
    tick: int
    day: int
    minute_of_day: int
    landmarks: List[dict]
    agents: List[dict]


app = FastAPI(title="AI Village Backend (v1)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Serve the viewer UI from the backend so you can open http://sparky1:8000/ui/
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """
    Persist a lightweight, structured audit trail to JSONL for later analysis.
    Notes:
    - We cap body logging to avoid huge files / secrets leakage.
    - We re-inject the request body so endpoints still work.
    """
    started = time.time()
    body = b""
    try:
        body = await request.body()
    except Exception:
        body = b""

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req2 = Request(request.scope, receive)
    resp = await call_next(req2)
    dur_ms = (time.time() - started) * 1000.0

    try:
        preview_bytes = body[:4096]
        preview = preview_bytes.decode("utf-8", errors="replace")
        ctype = (request.headers.get("content-type") or "")[:120]
        parsed = _safe_json_preview(preview_bytes) if "application/json" in ctype.lower() else None
        entry = AuditEntry(
            audit_id=str(uuid.uuid4()),
            method=str(request.method),
            path=str(request.url.path),
            query=str(request.url.query or ""),
            status_code=int(getattr(resp, "status_code", 0) or 0),
            duration_ms=float(dur_ms),
            client=str(getattr(request.client, "host", "") or ""),
            content_type=ctype,
            body_preview=preview[:2000],
            body_json=parsed,
            created_at=time.time(),
        )
        _append_audit(entry)
    except Exception:
        pass
    return resp


def _require_admin(request: Request) -> bool:
    """
    Minimal guardrail:
    - If ADMIN_TOKEN is set, require `Authorization: Bearer <token>`.
    - If not set, allow (intended for LAN/local use).
    """
    if not ADMIN_TOKEN:
        return True
    auth = (request.headers.get("authorization") or "").strip()
    return auth == f"Bearer {ADMIN_TOKEN}"


def _emit_trace(agent_id: str, agent_name: str, kind: TraceKind, summary: str, data: Optional[dict] = None) -> None:
    """Internal helper: append a trace event without going through HTTP."""
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
        _trace.append(ev)
        if len(_trace) > _trace_max:
            del _trace[: len(_trace) - _trace_max]
        _append_jsonl(TRACE_PATH, asdict(ev))
        # Best-effort broadcast; ignore failures.
        try:
            asyncio.create_task(ws_manager.broadcast({"type": "trace", "data": asdict(ev)}))
        except Exception:
            pass
    except Exception:
        return


def _is_allowed_web_url(url: str) -> tuple[bool, str]:
    """
    Guardrails for web tools:
    - only http(s)
    - block localhost / private / link-local / loopback targets (SSRF)
    - optional domain allowlist
    """
    try:
        u = urllib.parse.urlparse(url.strip())
        if u.scheme not in ("http", "https"):
            return (False, "invalid_scheme")
        host = (u.hostname or "").strip().lower()
        if not host:
            return (False, "missing_host")
        if host in ("localhost",):
            return (False, "blocked_host")
        # Optional allowlist
        if WEB_FETCH_ALLOWLIST:
            ok = False
            for allowed in WEB_FETCH_ALLOWLIST:
                if host == allowed or host.endswith("." + allowed):
                    ok = True
                    break
            if not ok:
                return (False, "host_not_allowlisted")
        # Resolve and block private IPs
        try:
            infos = socket.getaddrinfo(host, None)
            addrs = {i[4][0] for i in infos if i and i[4]}
        except Exception:
            addrs = set()
        for ip_s in list(addrs)[:8]:
            try:
                ip = ipaddress.ip_address(ip_s)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return (False, "blocked_ip")
            except Exception:
                continue
        return (True, "")
    except Exception:
        return (False, "parse_error")


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")


@app.get("/run")
def run_info():
    return {"run_id": _run_id, "started_at": _run_started_at, "backend_version": "balanced_array"}


def _list_run_dirs(limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 200))
    items = []
    try:
        dirs = [p for p in RUNS_DIR.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in dirs[:limit]:
            meta = {}
            mp = p / "meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8", errors="replace") or "{}")
                except Exception:
                    meta = {}
            items.append(
                {
                    "run_id": p.name,
                    "mtime": float(p.stat().st_mtime),
                    "meta": meta,
                    "has_viewer": bool((p / "result_viewer.html").exists()),
                }
            )
    except Exception:
        return []
    return items


def _read_run_jsonl(run_id: str, filename: str, limit: Optional[int] = None) -> list[dict]:
    p = (RUNS_DIR / run_id / filename).resolve()
    if not str(p).startswith(str((RUNS_DIR / run_id).resolve())):
        return []
    return _read_jsonl(p, limit=limit)


def _build_run_job_state(job_events: list[dict]) -> dict[str, dict]:
    """
    Reconstruct minimal job/task state from jobs_events.jsonl.
    Output dict: job_id -> state dict.
    """
    jobs: dict[str, dict] = {}
    for r in job_events:
        try:
            t = r.get("event_type")
            job_id = str(r.get("job_id") or "")
            d = r.get("data") if isinstance(r.get("data"), dict) else {}
            ca = float(r.get("created_at") or d.get("created_at") or 0.0)
            if not job_id:
                continue
            if t == "create":
                jobs[job_id] = {
                    "job_id": job_id,
                    "title": str(d.get("title") or ""),
                    "body": str(d.get("body") or ""),
                    "reward": float(d.get("reward") or 0.0),
                    "created_by": str(d.get("created_by") or ""),
                    "source": str(d.get("source") or ""),
                    "created_at": ca or float(d.get("created_at") or 0.0),
                    "status": "open",
                    "claimed_by": "",
                    "claimed_at": 0.0,
                    "submitted_by": "",
                    "submission": "",
                    "submitted_at": 0.0,
                    "auto_verify_ok": None,
                    "auto_verify_name": "",
                    "auto_verify_note": "",
                    "auto_verify_artifacts": {},
                    "auto_verified_at": 0.0,
                    "reviewed_by": "",
                    "reviewed_at": 0.0,
                    "review_note": "",
                    "fingerprint": str(d.get("fingerprint") or ""),
                    "ratings": (dict(d.get("ratings") or {}) if isinstance(d.get("ratings"), dict) else {}),
                    "events": [],
                }
                # Record event for timeline.
                jobs[job_id]["events"].append({"type": "create", "at": ca, "data": d})
                continue
            j = jobs.get(job_id)
            if not j:
                # Unknown job; initialize a stub so we still show it in summaries.
                j = {
                    "job_id": job_id,
                    "title": "",
                    "body": "",
                    "reward": 0.0,
                    "created_by": "",
                    "source": "",
                    "created_at": 0.0,
                    "status": "unknown",
                    "claimed_by": "",
                    "claimed_at": 0.0,
                    "submitted_by": "",
                    "submission": "",
                    "submitted_at": 0.0,
                    "auto_verify_ok": None,
                    "auto_verify_name": "",
                    "auto_verify_note": "",
                    "auto_verify_artifacts": {},
                    "auto_verified_at": 0.0,
                    "reviewed_by": "",
                    "reviewed_at": 0.0,
                    "review_note": "",
                    "fingerprint": "",
                    "ratings": {},
                    "events": [],
                }
                jobs[job_id] = j
            if t == "claim":
                j["claimed_by"] = str(d.get("agent_id") or "")
                j["claimed_at"] = ca or float(d.get("created_at") or 0.0)
                j["status"] = "claimed"
            elif t == "submit":
                j["submitted_by"] = str(d.get("agent_id") or "")
                j["submission"] = str(d.get("submission") or "")
                j["submitted_at"] = ca or float(d.get("created_at") or 0.0)
                j["status"] = "submitted"
            elif t == "verify":
                ok = d.get("ok")
                j["auto_verify_ok"] = ok if isinstance(ok, bool) else None
                j["auto_verify_name"] = str(d.get("verifier") or "")
                j["auto_verify_note"] = str(d.get("note") or "")
                arts = d.get("artifacts")
                j["auto_verify_artifacts"] = arts if isinstance(arts, dict) else {}
                j["auto_verified_at"] = ca or float(d.get("created_at") or 0.0)
            elif t == "update":
                # Edits to title/body/reward (task board).
                if isinstance(d.get("title"), str):
                    j["title"] = str(d.get("title") or "")
                if isinstance(d.get("body"), str):
                    j["body"] = str(d.get("body") or "")
                if d.get("reward") is not None:
                    try:
                        j["reward"] = float(d.get("reward") or j.get("reward") or 0.0)
                    except Exception:
                        pass
                if isinstance(d.get("ratings"), dict):
                    j["ratings"] = dict(d.get("ratings") or {})
                if isinstance(d.get("source"), str):
                    j["source"] = str(d.get("source") or "")
            elif t == "review":
                j["status"] = "approved" if bool(d.get("approved")) else "rejected"
                j["reviewed_by"] = str(d.get("reviewed_by") or "")
                j["reviewed_at"] = ca or float(d.get("created_at") or 0.0)
                j["review_note"] = str(d.get("note") or "")
            elif t == "cancel":
                j["status"] = "cancelled"
            # Record event for timeline (lightweight; viewer may derive the actor from data).
            try:
                j.setdefault("events", []).append({"type": str(t or ""), "at": ca, "data": d})
            except Exception:
                pass
        except Exception:
            continue
    return jobs


def _extract_code_fence(text: str, lang: str) -> Optional[str]:
    """
    Extract the first fenced code block: ```lang ... ```
    Returns code string or None.
    """
    try:
        # Only match a real fence line like:
        #   ```python
        #   <code>
        #   ```
        # Avoid matching inline text like "```python code fence".
        m = re.search(
            rf"(?im)^[ \t]*```{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*$",
            text or "",
        )
        if m:
            return (m.group(1) or "").strip()

        # Fallback: PowerShell/backtick sanitization can collapse ```python into `python.
        # Accept a single-backtick "fence" and take until the next lone backtick or end.
        # IMPORTANT: Use a more robust pattern that captures until the closing backtick on its own line
        # Also handle nested code fences (e.g., json inside markdown)
        # Try multiline mode to match across the entire text, not just from start
        # More flexible: allow closing backtick to be anywhere after the content
        m2 = re.search(
            rf"(?im)`{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*`",
            text or "",
        )
        if m2:
            extracted = (m2.group(1) or "").strip()
            # If extraction looks valid (not just a single character), return it
            if len(extracted) > 2:
                return extracted
        # Even more flexible: match single backtick followed by lang, then capture until next backtick (anywhere)
        m2b = re.search(
            rf"(?im)`{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)`",
            text or "",
        )
        if m2b:
            extracted = (m2b.group(1) or "").strip()
            if len(extracted) > 2:
                return extracted

        # Fallback: in some transports (notably Windows PowerShell), backticks can be stripped entirely.
        # Accept a bare language line:
        #   python\n<code...>
        m3 = re.search(rf"(?im)^\s*{re.escape(lang)}\s*$\s*([\s\S]+)$", text or "")
        if m3:
            return (m3.group(1) or "").strip()
        
        # Final fallback for JSON: try to find a JSON array directly in the text
        # This handles cases where the code fence was completely stripped
        if lang.lower() in ("json", "javascript"):
            # Look for a JSON array pattern: [ ... ]
            json_match = re.search(r'(\[[\s\S]*?\])', text or "", re.MULTILINE | re.DOTALL)
            if json_match:
                candidate = json_match.group(1).strip()
                # Validate it's actually valid JSON
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    pass
        
        return None
    except Exception:
        return None


@dataclass
class AutoVerifyOutcome:
    matched: bool
    ok: bool
    note: str
    verifier: str
    artifacts: dict


def _auto_verify_task(job: Job, submission: str) -> AutoVerifyOutcome:
    """
    Minimal automatic verifier for a small set of task templates.
    Returns (ok, note).
    """
    title = (job.title or "").lower()
    body = (job.body or "").lower()
    text = (submission or "")

    def _extract_bracket_tag(tag: str) -> str:
        """
        Extracts [tag:value] from job title/body (case-insensitive tag name).
        Returns "" if not present.
        """
        try:
            hay = (job.title or "") + "\n" + (job.body or "")
            m = re.search(r"\[" + re.escape(tag) + r"\s*:\s*([^\]]+)\]", hay, flags=re.IGNORECASE)
            return (m.group(1).strip() if m else "")
        except Exception:
            return ""

    def _trunc(s: Any, n: int = 1500) -> str:
        try:
            x = str(s or "")
        except Exception:
            return ""
        x = x.strip()
        return x[:n] + ("…(truncated)" if len(x) > n else "")

    def _verify_acceptance_criteria() -> tuple[bool, bool, str, list[str]]:
        """
        Returns (ac_present, ok, note, bullets).
        """
        try:
            body_lines = (job.body or "").splitlines()
            ac_start = None
            for i, ln in enumerate(body_lines):
                if ln.strip().lower().startswith("acceptance criteria"):
                    ac_start = i
                    break
            if ac_start is None:
                return (False, True, "", [])
            bullets: list[str] = []
            for ln in body_lines[ac_start + 1 : ac_start + 40]:
                s = ln.strip()
                if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
                    bullets.append(s[2:].strip())
                elif s == "":
                    continue
                elif bullets and not (s.startswith("- ") or s.startswith("* ") or s.startswith("• ")):
                    break
            if not bullets:
                return (False, True, "", [])
            sub_low = (submission or "").lower()
            if "evidence" not in sub_low:
                return (True, False, "auto_verify failed: submission missing an Evidence section for acceptance criteria", bullets)
            missing: list[str] = []
            for b in bullets[:10]:
                key = b.lower()
                k = key[: min(24, len(key))]
                if k and k not in sub_low:
                    missing.append(b[:80])
            if missing:
                return (True, False, f"auto_verify failed: missing evidence for acceptance criteria: {missing[:5]}", bullets)
            return (True, True, "auto_verify ok: submission references all acceptance criteria (heuristic)", bullets)
        except Exception:
            return (False, True, "", [])

    def _balanced_array(s: str) -> Optional[str]:
        """Extract first complete JSON array [...] from text. Robust to line endings / fences."""
        i = (s or "").find("[")
        if i < 0:
            return None
        depth = 0
        for j in range(i, len(s)):
            if s[j] == "[":
                depth += 1
            elif s[j] == "]":
                depth -= 1
                if depth == 0:
                    return s[i : j + 1]
        return None

    def _balanced_array_of_objects(s: str) -> Optional[str]:
        """Extract first [...] that looks like a JSON array of objects (starts with [ then {).
        Skips tag-like brackets such as [run:...] or [TEST_RUN_ID:...].
        """
        t = s or ""
        i = 0
        while True:
            i = t.find("[", i)
            if i < 0:
                return None
            j = i + 1
            while j < len(t) and t[j] in " \t\r\n":
                j += 1
            if j < len(t) and t[j] == "{":
                depth = 0
                for k in range(i, len(t)):
                    if t[k] == "[":
                        depth += 1
                    elif t[k] == "]":
                        depth -= 1
                        if depth == 0:
                            return t[i : k + 1]
                return None
            i = i + 1

    def _verifier_json_list() -> Optional[AutoVerifyOutcome]:
        # Explicit tag preferred.
        vtag = _extract_bracket_tag("verifier").lower()
        if vtag not in ("json_list",):
            return None
        # 1) Prefer ```json / ```javascript fence so agent output in fences is used.
        code: Optional[str] = None
        for lang in ("json", "javascript"):
            g = re.search(rf"(?s)```\s*{re.escape(lang)}\s*\r?\n([\s\S]*?)\r?\n\s*```", (text or ""), re.IGNORECASE)
            if g and (g.group(1) or "").strip():
                code = (g.group(1) or "").strip()
                break
        if not code:
            code = _extract_code_fence(text, "json") or _extract_code_fence(text, "javascript")
        # 2) Array-of-objects [... { ... }]: skips tag-like [run:...], [TEST_RUN_ID:...].
        if not code:
            code = _balanced_array_of_objects(text or "")
        # 3) Any balanced [...] (can pick up [run:...] if no array-of-objects found).
        if not code:
            code = _balanced_array(text or "")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: no JSON array found in submission", "json_list", {"submission_preview": (text or "")[:500]})
        if len(code) > 20000:
            return AutoVerifyOutcome(True, False, "auto_verify failed: json too large", "json_list", {"extracted_length": len(code)})
        # Normalize: strip BOM and leading/trailing whitespace (handles encoding/transport quirks)
        code = (code or "").strip()
        if code.startswith("\ufeff"):
            code = code[1:].lstrip()
        # Debug: log what we extracted
        try:
            import logging
            logging.info(f"json_list verifier: extracted {len(code)} chars, first 100: {code[:100]}")
        except Exception:
            pass
        obj = None
        try:
            obj = json.loads(code)
        except Exception as e:
            # If extraction returned invalid/truncated JSON, try array-of-objects or fence (not generic _balanced_array which can be [run:...])
            fallback = _balanced_array_of_objects(text or "")
            if not fallback:
                for lang in ("json", "javascript"):
                    g = re.search(rf"(?s)```\s*{re.escape(lang)}\s*\r?\n([\s\S]*?)\r?\n\s*```", (text or ""), re.IGNORECASE)
                    if g and (g.group(1) or "").strip():
                        fallback = (g.group(1) or "").strip()
                        break
            if fallback:
                try:
                    obj = json.loads(fallback)
                except Exception:
                    pass
            if obj is None:
                artifacts = {
                    "extracted_length": len(code),
                    "extracted_preview": code[:200] if code else "(empty)",
                    "extracted_full": code[:5000] if code else "(empty)",
                    "error_type": str(type(e).__name__),
                    "error_msg": str(e)[:200],
                }
                return AutoVerifyOutcome(True, False, f"auto_verify failed: invalid json ({e})", "json_list", artifacts)
        if not isinstance(obj, list):
            return AutoVerifyOutcome(True, False, "auto_verify failed: expected a JSON list (array)", "json_list", {"type": str(type(obj))})
        min_items = 0
        try:
            min_items = int(float(_extract_bracket_tag("json_min_items") or "0"))
        except Exception:
            min_items = 0
        if min_items < 0:
            min_items = 0
        if min_items and len(obj) < min_items:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: expected at least {min_items} items, got {len(obj)}", "json_list", {"item_count": len(obj), "min_items": min_items})
        req_keys = [k.strip() for k in (_extract_bracket_tag("json_required_keys") or "").split(",") if k.strip()]
        if req_keys:
            missing = []
            for i, it in enumerate(obj[: min(20, len(obj))]):
                if not isinstance(it, dict):
                    missing.append(f"item[{i}] not object")
                    continue
                for k in req_keys:
                    if k not in it:
                        missing.append(f"item[{i}] missing {k}")
                        break
                if len(missing) >= 8:
                    break
            if missing:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: json list missing required keys: {missing[:5]}", "json_list", {"missing": missing[:8], "required_keys": req_keys})

        # Light validation for common citation fields if present/required.
        # (We can't verify truthfulness yet, but we can ensure the structure is sane and includes evidence text.)
        def _is_urlish(s: str) -> bool:
            sl = (s or "").strip().lower()
            return sl.startswith("http://") or sl.startswith("https://")

        cite_url_keys = [k for k in req_keys if k.lower() in ("source_url", "url", "citation_url")]
        cite_quote_keys = [k for k in req_keys if k.lower() in ("source_quote", "quote", "citation_quote", "evidence_quote")]
        cite_issues: list[str] = []
        if cite_url_keys or cite_quote_keys:
            for i, it in enumerate(obj[: min(20, len(obj))]):
                if not isinstance(it, dict):
                    continue
                for k in cite_url_keys:
                    v = it.get(k)
                    if not isinstance(v, str) or (not _is_urlish(v)) or len(v) > 2000:
                        cite_issues.append(f"item[{i}] bad {k}")
                        break
                for k in cite_quote_keys:
                    v = it.get(k)
                    if not isinstance(v, str) or len(v.strip()) < 20:
                        cite_issues.append(f"item[{i}] weak {k}")
                        break
                if len(cite_issues) >= 8:
                    break
        if cite_issues:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: citations malformed: {cite_issues[:5]}", "json_list", {"citation_issues": cite_issues[:8], "required_keys": req_keys})

        # If this is a market scan (or requires citation fields), ensure we have at least one non-example citation domain.
        # This prevents "all example.com" submissions from passing as "cited research".
        try:
            is_market_scan = ("archetype:market_scan" in (job.title or "").lower()) or ("archetype:market_scan" in (job.body or "").lower()) or ("market scan" in (job.title or "").lower())
            wants_citations = bool(cite_url_keys or cite_quote_keys)
            if is_market_scan and wants_citations and cite_url_keys:
                domains: set[str] = set()
                for it in obj:
                    if not isinstance(it, dict):
                        continue
                    for k in cite_url_keys:
                        v = it.get(k)
                        if isinstance(v, str) and _is_urlish(v):
                            host = urllib.parse.urlparse(v).hostname or ""
                            host = host.lower().strip()
                            if host:
                                domains.add(host)
                non_example = sorted([d for d in domains if d not in ("example.com", "www.example.com")])
                if not non_example:
                    return AutoVerifyOutcome(
                        True,
                        False,
                        "auto_verify failed: citations must include at least one non-example domain for market_scan",
                        "json_list",
                        {"domains": sorted(domains)[:20], "required_keys": req_keys},
                    )
        except Exception:
            pass

        return AutoVerifyOutcome(True, True, f"auto_verify ok: json list parsed (items={len(obj)})", "json_list", {"item_count": len(obj), "required_keys": req_keys})

    def _verifier_md_table() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag("verifier").lower()
        if vtag not in ("md_table", "markdown_table"):
            return None
        # Heuristic: find first markdown table block and count rows.
        lines = (submission or "").splitlines()
        table_lines: list[str] = []
        in_table = False
        for ln in lines:
            if "|" in ln:
                # Allow header and rows that look like markdown table
                if ln.strip().startswith("|") or ("|" in ln.strip()):
                    table_lines.append(ln.rstrip("\n"))
                    in_table = True
                    continue
            if in_table:
                break
        if len(table_lines) < 2:
            return AutoVerifyOutcome(True, False, "auto_verify failed: missing markdown table", "md_table", {})
        # Extract header columns.
        header = table_lines[0]
        cols = [c.strip() for c in header.strip().strip("|").split("|") if c.strip()]
        req_cols = [c.strip() for c in (_extract_bracket_tag("md_required_cols") or "").split(",") if c.strip()]
        if req_cols:
            missing_cols = [c for c in req_cols if c not in cols]
            if missing_cols:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: missing required table columns: {missing_cols}", "md_table", {"cols": cols})
        # Count body rows (skip separator line if present)
        body_rows = [ln for ln in table_lines[1:] if not re.match(r"^\s*\|?\s*:-", ln)]
        min_rows = 0
        try:
            min_rows = int(float(_extract_bracket_tag("md_min_rows") or "0"))
        except Exception:
            min_rows = 0
        if min_rows and len(body_rows) < min_rows:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: expected at least {min_rows} table rows, got {len(body_rows)}", "md_table", {"row_count": len(body_rows), "min_rows": min_rows, "cols": cols})
        return AutoVerifyOutcome(True, True, f"auto_verify ok: markdown table present (rows={len(body_rows)})", "md_table", {"row_count": len(body_rows), "cols": cols})

    # ---- Verifier registry (ordered) ----
    # Each verifier returns AutoVerifyOutcome(matched=..., ok=..., note=..., verifier=..., artifacts=...)

    def _verifier_primes_smallest_five() -> Optional[AutoVerifyOutcome]:
        if not (("prime" in title or "prime" in body) and ("five" in title or "five" in body or "5" in title or "5" in body)):
            return None
        code = _extract_code_fence(text, "python") or _extract_code_fence(text, "py")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: missing ```python``` code fence in submission", "primes_smallest_five", {})
        if len(code) > 12000:
            return AutoVerifyOutcome(True, False, "auto_verify failed: python code too large", "primes_smallest_five", {})
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run([sys.executable, "-I", str(p)], cwd=td, capture_output=True, text=True, timeout=3)
                arts = {"exit_code": r.returncode, "stdout": _trunc(r.stdout, 1200), "stderr": _trunc(r.stderr, 1200)}
                if r.returncode != 0:
                    return AutoVerifyOutcome(True, False, f"auto_verify failed: script error (code={r.returncode}): {_trunc(r.stderr, 300)}", "primes_smallest_five", arts)
                out = (r.stdout or "").strip().splitlines()
                out = [ln.strip() for ln in out if ln.strip() != ""]
                expected = ["2", "3", "5", "7", "11"]
                if out[:5] != expected:
                    return AutoVerifyOutcome(True, False, f"auto_verify failed: expected first lines {expected}, got {out[:5]}", "primes_smallest_five", {**arts, "expected": expected, "got_first_lines": out[:8]})
                return AutoVerifyOutcome(True, True, "auto_verify ok: primes output matches expected 2,3,5,7,11", "primes_smallest_five", {**arts, "expected": expected})
        except subprocess.TimeoutExpired:
            return AutoVerifyOutcome(True, False, "auto_verify failed: script timeout", "primes_smallest_five", {})
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: exception {e}", "primes_smallest_five", {})

    def _verifier_python_run() -> Optional[AutoVerifyOutcome]:
        """
        Verifier for Python code execution:
        - Extracts Python code from submission
        - Runs it in a sandboxed environment
        - Checks for test results if tests are included
        - Validates output matches expectations
        """
        python_job = ("python" in title) or ("python" in body)
        if not python_job:
            return None
        code = _extract_code_fence(text, "python") or _extract_code_fence(text, "py")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: missing python code fence in submission for python job", "python_run", {})
        if len(code) > 12000:
            return AutoVerifyOutcome(True, False, "auto_verify failed: python code too large", "python_run", {})

        # If acceptance criteria exist, enforce the evidence heuristic too.
        ac_present, ac_ok, ac_note, bullets = _verify_acceptance_criteria()
        if ac_present and not ac_ok:
            return AutoVerifyOutcome(True, False, ac_note, "python_run", {"acceptance_criteria": bullets[:10]})

        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run([sys.executable, "-I", str(p)], cwd=td, capture_output=True, text=True, timeout=3)
                arts = {"exit_code": r.returncode, "stdout": _trunc(r.stdout, 1200), "stderr": _trunc(r.stderr, 1200)}
                if r.returncode != 0:
                    return AutoVerifyOutcome(True, False, f"auto_verify failed: python script error (code={r.returncode}): {_trunc(r.stderr, 300)}", "python_run", arts)
        except subprocess.TimeoutExpired:
            return AutoVerifyOutcome(True, False, "auto_verify failed: python script timeout", "python_run", {})
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: python verifier exception {e}", "python_run", {})

        if ac_present:
            return AutoVerifyOutcome(True, True, "auto_verify ok: python code ran + submission references acceptance criteria", "python_run", {"acceptance_criteria": bullets[:10]})
        return AutoVerifyOutcome(True, True, "auto_verify ok: python code ran", "python_run", {})

    def _verifier_python_test() -> Optional[AutoVerifyOutcome]:
        """
        Verifier for Python code with test execution:
        - Extracts Python code and tests from submission
        - Runs tests using pytest or unittest
        - Validates all tests pass
        """
        vtag = _extract_bracket_tag("verifier").lower()
        if vtag not in ("python_test", "pytest", "unittest"):
            return None
        
        # Extract code and test code
        code = _extract_code_fence(text, "python") or _extract_code_fence(text, "py")
        test_code = None
        # Look for separate test code fence
        test_fences = re.findall(r"```(?:python|py|test)\s*\n(.*?)```", text, re.DOTALL)
        if len(test_fences) > 1:
            # First fence is code, second is tests
            code = test_fences[0].strip()
            test_code = test_fences[1].strip()
        elif "def test_" in code or "import unittest" in code or "import pytest" in code:
            # Tests are in the same code block
            test_code = code
        
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: missing python code fence in submission", "python_test", {})
        if len(code) > 20000:
            return AutoVerifyOutcome(True, False, "auto_verify failed: python code too large", "python_test", {})
        
        try:
            with tempfile.TemporaryDirectory() as td:
                # Write main code
                main_file = Path(td) / "task.py"
                main_file.write_text(code, encoding="utf-8")
                
                # Write test file if separate
                test_file = None
                if test_code and test_code != code:
                    test_file = Path(td) / "test_task.py"
                    test_file.write_text(test_code, encoding="utf-8")
                
                # Try pytest first, then unittest
                test_passed = False
                test_output = ""
                test_error = ""
                
                # Try pytest
                try:
                    r = subprocess.run(
                        [sys.executable, "-m", "pytest", str(td), "-v"],
                        cwd=td,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    test_output = _trunc(r.stdout, 2000)
                    test_error = _trunc(r.stderr, 1000)
                    if r.returncode == 0:
                        test_passed = True
                except subprocess.TimeoutExpired:
                    return AutoVerifyOutcome(True, False, "auto_verify failed: test execution timeout (10s)", "python_test", {})
                except Exception:
                    # pytest not available or failed, try unittest
                    pass
                
                # Try unittest if pytest didn't work
                if not test_passed:
                    try:
                        # Create a test runner script
                        runner = Path(td) / "run_tests.py"
                        if test_file:
                            runner.write_text(f"""
import sys
import unittest
sys.path.insert(0, '{td}')
from test_task import *
if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
""", encoding="utf-8")
                        else:
                            # Tests in main file
                            runner.write_text(f"""
import sys
import unittest
sys.path.insert(0, '{td}')
import task
if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(task)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
""", encoding="utf-8")
                        
                        r = subprocess.run(
                            [sys.executable, str(runner)],
                            cwd=td,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        test_output = _trunc(r.stdout, 2000)
                        test_error = _trunc(r.stderr, 1000)
                        if r.returncode == 0:
                            test_passed = True
                    except subprocess.TimeoutExpired:
                        return AutoVerifyOutcome(True, False, "auto_verify failed: test execution timeout (10s)", "python_test", {})
                    except Exception as e:
                        return AutoVerifyOutcome(True, False, f"auto_verify failed: test execution error: {str(e)[:200]}", "python_test", {})
                
                arts = {
                    "test_passed": test_passed,
                    "test_output": test_output,
                    "test_error": test_error,
                }
                
                if not test_passed:
                    return AutoVerifyOutcome(
                        True,
                        False,
                        f"auto_verify failed: tests did not pass. Output: {test_output[:300]}, Error: {test_error[:300]}",
                        "python_test",
                        arts
                    )
                
                return AutoVerifyOutcome(
                    True,
                    True,
                    f"auto_verify ok: all tests passed. {test_output[:200]}",
                    "python_test",
                    arts
                )
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: python test verifier exception: {str(e)[:200]}", "python_test", {})

    def _verifier_llm_judge() -> Optional[AutoVerifyOutcome]:
        """
        Judgment verifier for open-ended tasks (e.g. "is Fiverr task 123888 done successfully?").
        Requires [verifier:llm_judge] or [verifier:judgment] and VERIFY_LLM_BASE_URL.
        """
        vtag = _extract_bracket_tag("verifier").lower()
        if vtag not in ("llm_judge", "judgment", "judge"):
            return None
        if not VERIFY_LLM_BASE_URL:
            return AutoVerifyOutcome(True, False, "auto_verify failed: llm judge requested but VERIFY_LLM_BASE_URL not set", "llm_judge", {})
        task_summary = ((job.title or "") + "\n\n" + (job.body or ""))[:8000]
        result = _llm_judge_call(task_summary, text)
        if result is None:
            return AutoVerifyOutcome(True, False, "auto_verify failed: llm judge call failed or timed out", "llm_judge", {})
        ok, reason = result
        note = f"auto_verify ok: {reason}" if ok else f"auto_verify failed: {reason}"
        return AutoVerifyOutcome(True, ok, note, "llm_judge", {"reason": reason[:500]})

    def _verifier_acceptance_criteria_only() -> Optional[AutoVerifyOutcome]:
        ac_present, ac_ok, ac_note, bullets = _verify_acceptance_criteria()
        if not ac_present:
            return None
        return AutoVerifyOutcome(True, bool(ac_ok), ac_note if ac_note else "auto_verify ok: acceptance criteria satisfied", "acceptance_criteria", {"acceptance_criteria": bullets[:10]})

    for v in (_verifier_primes_smallest_five, _verifier_python_test, _verifier_python_run, _verifier_json_list, _verifier_md_table, _verifier_llm_judge, _verifier_acceptance_criteria_only):
        out = v()
        if out is not None:
            return out

    return AutoVerifyOutcome(False, False, "auto_verify skipped: no verifier matched", "", {})


def _normalize_for_fingerprint(s: str) -> str:
    t = (s or "").lower()
    t = re.sub(r"\[run:[^\]]+\]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokenize(s: str) -> set[str]:
    s = _normalize_for_fingerprint(s)
    # Keep alnum only; split on whitespace.
    s = s.translate(str.maketrans({c: " " for c in string.punctuation}))
    toks = [t for t in s.split() if len(t) >= 3]
    return set(toks[:600])


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union or 1)


def _fingerprint(title: str, body: str) -> str:
    base = _normalize_for_fingerprint(title) + "\n" + _normalize_for_fingerprint(body)
    # Stable but short fingerprint for logs/UI.
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _calc_reward_from_ratings(ratings: dict) -> tuple[float, dict]:
    """
    Compute a suggested reward from 1..10 ratings.

    Design goals:
    - Reward scales with difficulty/complexity/usefulness.
    - Penalize tasks that rely heavily on external tools (harder to verify/reproduce).
    - Hard clamps to avoid runaway payouts.
    """
    def _r(key: str, default: int = 5) -> int:
        try:
            v = int(float(ratings.get(key, default)))
            return max(1, min(10, v))
        except Exception:
            return default

    complexity = _r("complexity", 5)
    difficulty = _r("difficulty", 5)
    external = _r("external_tools", 2)
    uniqueness = _r("uniqueness", 5)
    usefulness = _r("usefulness", 5)
    money = _r("money_potential", 1)
    # Newer optional ratings (still 1..10; safe defaults)
    clarity = _r("clarity", 6)
    verifiability = _r("verifiability", 6)
    impact = _r("impact", 5)
    time_cost = _r("time_cost", 5)
    risk = _r("risk", 3)
    learning_value = _r("learning_value", 5)

    # Weights (tunable via env if needed later)
    base = float(os.getenv("REWARD_BASE", "1.0"))
    w_complexity = float(os.getenv("REWARD_W_COMPLEXITY", "1.2"))
    w_difficulty = float(os.getenv("REWARD_W_DIFFICULTY", "1.6"))
    w_usefulness = float(os.getenv("REWARD_W_USEFULNESS", "1.4"))
    w_money = float(os.getenv("REWARD_W_MONEY", "1.8"))
    w_uniqueness = float(os.getenv("REWARD_W_UNIQUENESS", "0.6"))
    w_external_penalty = float(os.getenv("REWARD_W_EXTERNAL_PENALTY", "1.2"))
    w_clarity = float(os.getenv("REWARD_W_CLARITY", "0.4"))
    w_verifiability = float(os.getenv("REWARD_W_VERIFIABILITY", "0.8"))
    w_impact = float(os.getenv("REWARD_W_IMPACT", "1.2"))
    w_time_cost = float(os.getenv("REWARD_W_TIME_COST", "0.6"))
    w_risk_penalty = float(os.getenv("REWARD_W_RISK_PENALTY", "0.7"))
    w_learning = float(os.getenv("REWARD_W_LEARNING", "0.4"))

    # Normalize to 0..1
    def _n(x: int) -> float:
        return float(x - 1) / 9.0

    score = (
        w_complexity * _n(complexity)
        + w_difficulty * _n(difficulty)
        + w_usefulness * _n(usefulness)
        + w_money * _n(money)
        + w_uniqueness * _n(uniqueness)
        + w_clarity * _n(clarity)
        + w_verifiability * _n(verifiability)
        + w_impact * _n(impact)
        + w_time_cost * _n(time_cost)
        + w_learning * _n(learning_value)
        - w_external_penalty * _n(external)
        - w_risk_penalty * _n(risk)
    )
    # Convert score to ai$ range
    scale = float(os.getenv("REWARD_SCALE", "20.0"))
    raw = base + max(0.0, score) * scale
    max_reward = float(os.getenv("REWARD_MAX", "50.0"))
    min_reward = float(os.getenv("REWARD_MIN", "0.01"))
    reward = max(min_reward, min(max_reward, raw))

    meta = {
        "ratings_used": {
            "complexity": complexity,
            "difficulty": difficulty,
            "external_tools": external,
            "uniqueness": uniqueness,
            "usefulness": usefulness,
            "money_potential": money,
            "clarity": clarity,
            "verifiability": verifiability,
            "impact": impact,
            "time_cost": time_cost,
            "risk": risk,
            "learning_value": learning_value,
        },
        "score": round(score, 4),
        "reward_raw": round(raw, 4),
        "reward_final": round(reward, 4),
        "params": {
            "base": base,
            "scale": scale,
            "max": max_reward,
            "min": min_reward,
            "w_complexity": w_complexity,
            "w_difficulty": w_difficulty,
            "w_usefulness": w_usefulness,
            "w_money": w_money,
            "w_uniqueness": w_uniqueness,
            "w_external_penalty": w_external_penalty,
            "w_clarity": w_clarity,
            "w_verifiability": w_verifiability,
            "w_impact": w_impact,
            "w_time_cost": w_time_cost,
            "w_risk_penalty": w_risk_penalty,
            "w_learning": w_learning,
        },
    }
    return (reward, meta)


@app.get("/runs")
def runs_list(limit: int = 50):
    return {"runs": _list_run_dirs(limit=limit), "current": {"run_id": _run_id, "started_at": _run_started_at}}


@app.get("/runs/{run_id}/summary")
def runs_summary(run_id: str):
    # Basic log counts + errors
    audit = _read_run_jsonl(run_id, "audit_log.jsonl")
    trace = _read_run_jsonl(run_id, "trace_events.jsonl")
    chat = _read_run_jsonl(run_id, "chat_messages.jsonl")
    jobs_ev = _read_run_jsonl(run_id, "jobs_events.jsonl")

    status_counts: dict[int, int] = {}
    for e in audit:
        sc = int(e.get("status_code") or 0)
        status_counts[sc] = status_counts.get(sc, 0) + 1
    http_errors = sum(v for k, v in status_counts.items() if k >= 400)
    trace_errors = [e for e in trace if e.get("kind") == "error"]

    # Tasks/jobs: focus on agent_1 proposed tasks (task-mode)
    jobs = _build_run_job_state(jobs_ev)
    tasks = [j for j in jobs.values() if str(j.get("created_by") or "") == "agent_1"]
    # Prefer tasks that were tagged with this run_id in title/body.
    tag = f"[run:{run_id}]"
    tagged = [t for t in tasks if (tag in str(t.get("title") or "")) or (tag in str(t.get("body") or ""))]
    tasks = tagged or tasks
    # Sort newest first
    tasks.sort(key=lambda j: float(j.get("created_at") or 0.0), reverse=True)

    verified = [t for t in tasks if t.get("status") == "approved"]
    submitted = [t for t in tasks if t.get("status") == "submitted"]
    open_ = [t for t in tasks if t.get("status") in ("open", "claimed", "unknown")]

    return {
        "run_id": run_id,
        "counts": {"audit": len(audit), "trace": len(trace), "chat": len(chat), "job_events": len(jobs_ev)},
        "http": {"errors_ge_400": http_errors, "status_counts": status_counts},
        "trace": {"errors": len(trace_errors), "last_error": (trace_errors[-1].get("summary") if trace_errors else "")},
        "tasks": {
            "total": len(tasks),
            "verified": len(verified),
            "submitted_unverified": len(submitted),
            "open": len(open_),
            "items": [
                {
                    "job_id": t.get("job_id"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "created_by": t.get("created_by"),
                    "claimed_by": t.get("claimed_by"),
                    "submitted_by": t.get("submitted_by"),
                    "created_at": t.get("created_at"),
                    "submitted_at": t.get("submitted_at"),
                    "auto_verify_ok": t.get("auto_verify_ok"),
                    "auto_verify_note": (str(t.get("auto_verify_note") or "")[:500]),
                    "auto_verified_at": t.get("auto_verified_at"),
                    "submission_preview": (str(t.get("submission") or "")[:500]),
                }
                for t in tasks[:50]
            ],
        },
    }


def _extract_tag(text: str, tag: str) -> Optional[str]:
    try:
        import re
        m = re.search(r"\[" + re.escape(tag) + r":([^\]]+)\]", text or "")
        return str(m.group(1)).strip() if m else None
    except Exception:
        return None


def _escape_and_format(text: str) -> str:
    import html as _html
    import re as _re

    s = _html.escape(text or "")
    s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\g<1></strong>", s)
    s = _re.sub(r"`([^`]+)`", r"<code>\g<1></code>", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\n", "<br>")


def _fmt_ts(created_at: Any) -> str:
    import datetime as dt

    try:
        x = float(created_at)
        return dt.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _build_viewer_html(messages: list[dict], thoughts: list[dict], jobs_state: dict[str, dict], title: str) -> str:
    # Minimal embedded version of export_chat_html.py (no external deps).
    import html as _html
    import json as _json
    import re as _re
    import time as _time

    def _job_id_from_text(t: str) -> str:
        s = (t or "")
        m = _re.search(r"\[task:([0-9a-fA-F\-]{12,})\]", s)
        if m:
            return str(m.group(1)).strip()
        m = _re.search(r"`([0-9a-fA-F\-]{12,})`", s)
        if m:
            return str(m.group(1)).strip()
        m = _re.search(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b", s)
        if m:
            return str(m.group(1)).strip()
        return ""

    def _group_key_for_message(m: dict) -> str:
        text = str(m.get("text") or "")
        conv = _extract_tag(text, "conv")
        if conv:
            return f"conv:{conv}"
        jid = _job_id_from_text(text)
        if jid:
            return f"job:{jid}"
        return "misc"

    groups: dict[str, list[dict]] = {}
    for m in messages:
        groups.setdefault(_group_key_for_message(m), []).append(m)

    tgroups: dict[str, list[dict]] = {}
    for e in thoughts:
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        conv = str(data.get("conv") or "").strip()
        key = f"conv:{conv}" if conv else "misc"
        tgroups.setdefault(key, []).append(e)

    def last_ts(items: list[dict]) -> float:
        try:
            return float(items[-1].get("created_at") or 0.0)
        except Exception:
            return 0.0

    group_items = sorted(groups.items(), key=lambda kv: last_ts(kv[1]), reverse=True)
    default_conv = "misc"
    if group_items:
        best = None
        for conv_id, items in group_items:
            if conv_id == "misc":
                continue
            bonus = 10 if conv_id.startswith("conv:") else (6 if conv_id.startswith("job:") else 0)
            score = bonus + len(items) + len(tgroups.get(conv_id) or [])
            if best is None or score > best[0]:
                best = (score, conv_id)
        default_conv = best[1] if best else group_items[0][0]

    sidebar_items = []
    conv_sections = []
    for conv_id, items in group_items:
        senders = []
        for mm in items:
            sn = mm.get("sender_name") or mm.get("sender_id") or "?"
            if sn not in senders:
                senders.append(str(sn))
        last_text = str(items[-1].get("text") or "")
        topic = _extract_tag(last_text, "topic") or ""
        label = conv_id
        if conv_id.startswith("job:"):
            jid = conv_id.split("job:", 1)[1]
            jt = str((jobs_state.get(jid) or {}).get("title") or "").strip()
            label = f"job:{jid[:8]} - {jt[:60]}".strip(" -")
        elif conv_id.startswith("conv:"):
            label = f"{conv_id.split('conv:',1)[1]} - {', '.join(senders[:3])}"
        else:
            label = f"{conv_id} - {', '.join(senders[:3])}"
        if topic:
            label += f" - topic: {topic}"
        sidebar_items.append(
            f"<button class='convBtn' data-conv='{_html.escape(conv_id)}' onclick='selectConv(\"{_html.escape(conv_id)}\")'>"
            f"<div class='convTitle'>{_html.escape(label)}</div>"
            f"<div class='convMeta'>{len(items)} msgs - last: {_html.escape(_fmt_ts(items[-1].get('created_at')))}</div>"
            f"</button>"
        )

        # Dedupe consecutive identical messages to reduce spammy repetition.
        def _norm_msg(sender: str, body: str) -> str:
            s = shows = (sender + "|" + body).lower()
            s = _re.sub(r"\s+", " ", s).strip()
            return s[:800]

        deduped: list[tuple[dict, int]] = []
        prev_key = ""
        for mm in items:
            sender = str(mm.get("sender_name") or mm.get("sender_id") or "?")
            raw_text = str(mm.get("text") or "")
            body = _re.sub(r"\\[conv:[^\\]]+\\]\\s*", "", raw_text).strip()
            k = _norm_msg(sender, body)
            if deduped and k == prev_key:
                deduped[-1] = (deduped[-1][0], deduped[-1][1] + 1)
                continue
            deduped.append((mm, 1))
            prev_key = k

        rows = []
        # If this is a job-thread, add a "task card" first (answers who/what/how/verified).
        if conv_id.startswith("job:"):
            jid = conv_id.split("job:", 1)[1]
            j = jobs_state.get(jid) or {}
            if j:
                st = str(j.get("status") or "")
                created_by = str(j.get("created_by") or "")
                source = str(j.get("source") or "")
                claimed_by = str(j.get("claimed_by") or "")
                submitted_by = str(j.get("submitted_by") or "")
                reviewed_by = str(j.get("reviewed_by") or "")
                auto_ok = j.get("auto_verify_ok")
                auto_name = str(j.get("auto_verify_name") or "")
                auto_note = str(j.get("auto_verify_note") or "")
                auto_arts = j.get("auto_verify_artifacts") if isinstance(j.get("auto_verify_artifacts"), dict) else {}
                review_note = str(j.get("review_note") or "")
                ratings = j.get("ratings") if isinstance(j.get("ratings"), dict) else {}
                reward_mode = str(j.get("reward_mode") or "")
                body_txt = str(j.get("body") or "")
                sub_txt = str(j.get("submission") or "")
                events = j.get("events") if isinstance(j.get("events"), list) else []

                verifier = reviewed_by or ("system:auto_verify" if (j.get("auto_verified_at") or 0.0) else "")
                note = (review_note or auto_note).strip()
                sub_excerpt = sub_txt[:3500] + ("\n\n…(truncated)…" if len(sub_txt) > 3500 else "")

                who_line = (
                    f"created_by={created_by or '?'} | "
                    f"source={source or '?'} | "
                    f"claimed_by={claimed_by or '?'} | "
                    f"submitted_by={submitted_by or '?'} | "
                    f"verified_by={verifier or '?'}"
                )
                ratings_line = ""
                try:
                    if ratings:
                        # stable display order for common keys
                        keys = ["complexity", "difficulty", "external_tools", "uniqueness", "usefulness", "money_potential"]
                        rest = [k for k in ratings.keys() if k not in keys]
                        ordered = keys + sorted(rest)
                        parts = []
                        for k in ordered:
                            if k in ratings:
                                parts.append(f"{k}={ratings.get(k)}")
                        ratings_line = "ratings: " + ", ".join(parts[:12])
                except Exception:
                    ratings_line = ""
                reward_line = ""
                if reward_mode:
                    reward_line = f"reward_mode={reward_mode}"
                # Short status line with verifier result when available.
                ver_line = ""
                if auto_ok is True:
                    vn = f"{auto_name} " if auto_name else ""
                    ver_line = f"auto_verify: ok - {vn}{auto_note[:160]}"
                elif auto_ok is False:
                    vn = f"{auto_name} " if auto_name else ""
                    ver_line = f"auto_verify: FAILED - {vn}{auto_note[:160]}"
                elif note:
                    ver_line = note[:160]

                # Timeline (create → claim → submit → verify → review)
                timeline_rows = []
                try:
                    evs = []
                    for e in events:
                        if not isinstance(e, dict):
                            continue
                        et = str(e.get("type") or "")
                        at = float(e.get("at") or 0.0)
                        dd = e.get("data") if isinstance(e.get("data"), dict) else {}
                        evs.append((at, et, dd))
                    evs.sort(key=lambda x: x[0])
                    for at, et, dd in evs[-20:]:
                        actor = ""
                        if et == "create":
                            actor = str(dd.get("created_by") or "")
                        elif et in ("claim", "submit"):
                            actor = str(dd.get("agent_id") or "")
                        elif et == "verify":
                            actor = str(dd.get("verifier") or dd.get("by") or "system:auto_verify")
                        elif et == "review":
                            actor = str(dd.get("reviewed_by") or "")
                        meta = ""
                        if et == "verify":
                            okv = dd.get("ok")
                            ok_s = "OK" if okv is True else ("FAIL" if okv is False else "")
                            vname = str(dd.get("verifier") or "")
                            meta = f"{ok_s} {vname}".strip()
                        if et == "review":
                            meta = "approved" if bool(dd.get("approved")) else "rejected"
                        timeline_rows.append(
                            f"<div class='meta'>{_html.escape(_fmt_ts(at))} — {_html.escape(et)}"
                            + (f" by {_html.escape(actor)}" if actor else "")
                            + (f" ({_html.escape(meta)})" if meta else "")
                            + "</div>"
                        )
                except Exception:
                    timeline_rows = []

                arts_rows = []
                try:
                    if auto_arts:
                        for k in ("exit_code", "stdout", "stderr", "expected", "got_first_lines"):
                            if k in auto_arts and auto_arts.get(k) not in (None, "", [], {}):
                                arts_rows.append(f"<div class='meta'><strong>{_html.escape(k)}</strong>: {_html.escape(str(auto_arts.get(k))[:900])}</div>")
                except Exception:
                    arts_rows = []
                rows.append(
                    "<div class='msg' style='border-color: rgba(122,162,255,0.35);'>"
                    "<div class='msgHeader'><span class='sender'>Task</span>"
                    f"<span class='meta'>{_html.escape(st)}</span></div>"
                    f"<div class='msgBody'>"
                    f"<strong>{_html.escape(str(j.get('title') or ''))}</strong><br>"
                    f"<span class='meta'>{_html.escape('job_id=' + jid)}</span><br>"
                    f"<span class='meta'>{_html.escape(who_line)}</span><br>"
                    + (f"<span class='meta'>{_html.escape(ratings_line)}</span><br>" if ratings_line else "")
                    + (f"<span class='meta'>{_html.escape(reward_line)}</span><br>" if reward_line else "")
                    + (f"<span class='meta'>{_html.escape(ver_line)}</span><br>" if ver_line else "")
                    + ("<details style='margin-top:8px;'><summary class='meta'>Timeline</summary>"
                       + ("".join(timeline_rows) if timeline_rows else "<div class='meta'>(no events)</div>")
                       + "</details>" if True else "")
                    + ("<details style='margin-top:8px;'><summary class='meta'>Verifier artifacts</summary>"
                       + ("".join(arts_rows) if arts_rows else "<div class='meta'>(none)</div>")
                       + "</details>" if True else "")
                    + "<details style='margin-top:8px;'><summary class='meta'>Task text</summary>"
                    + f"<div style='margin-top:6px;'>{_escape_and_format(body_txt)}</div></details>"
                    + "<details style='margin-top:8px;'><summary class='meta'>Submission (excerpt)</summary>"
                    + f"<div style='margin-top:6px;'>{_escape_and_format(sub_excerpt)}</div></details>"
                    + "</div>"
                    "</div>"
                )

        for mm, rep in deduped:
            sender = str(mm.get("sender_name") or mm.get("sender_id") or "?")
            created = _fmt_ts(mm.get("created_at"))
            raw_text = str(mm.get("text") or "")
            body = _re.sub(r"\\[conv:[^\\]]+\\]\\s*", "", raw_text).strip()
            meta_html = f"<span class='meta'>x{rep}</span>" if rep > 1 else ""
            rows.append(
                "<div class='msg'>"
                f"<div class='msgHeader'><span class='sender'>{_html.escape(sender)}</span>"
                f"<span class='time'>{_html.escape(created)}</span>{meta_html}</div>"
                f"<div class='msgBody'>{_escape_and_format(body)}</div>"
                "</div>"
            )

        trows = []
        for e in (tgroups.get(conv_id) or []):
            agent = str(e.get("agent_name") or e.get("agent_id") or "?")
            created = _fmt_ts(e.get("created_at"))
            data = e.get("data") if isinstance(e.get("data"), dict) else {}
            think = str(data.get("think") or "").strip()
            if not think:
                continue
            trows.append(
                "<div class='msg thought'>"
                f"<div class='msgHeader'><span class='sender'>{_html.escape(agent)}</span>"
                f"<span class='time'>{_html.escape(created)}</span>"
                f"<span class='meta'>internal thought</span></div>"
                f"<div class='msgBody'>{_escape_and_format(think)}</div>"
                "</div>"
            )

        conv_sections.append(
            f"<section class='convSection' id='conv-{_html.escape(conv_id)}' data-conv='{_html.escape(conv_id)}'>"
            + "<div class='tabs'>"
            + "<button class='tabBtn active' data-tab='spoken' onclick='selectTab(\"spoken\")'>Spoken</button>"
            + "<button class='tabBtn' data-tab='thoughts' onclick='selectTab(\"thoughts\")'>Thoughts</button>"
            + "</div>"
            + "<div class='tabPane active' data-tab='spoken'>"
            + ("\n".join(rows) if rows else "<div class='convMeta'>(no spoken messages)</div>")
            + "</div>"
            + "<div class='tabPane' data-tab='thoughts'>"
            + ("\n".join(trows) if trows else "<div class='convMeta'>(no thoughts captured)</div>")
            + "</div>"
            + "</section>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_html.escape(title)}</title>
  <style>
    :root {{
      --bg: #0b1220; --panel: #0f1a30; --border: rgba(255,255,255,0.10);
      --text: rgba(255,255,255,0.92); --muted: rgba(255,255,255,0.65);
      --codeBg: rgba(255,255,255,0.08);
    }}
    html, body {{ height: 100%; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family: ui-sans-serif, system-ui, Segoe UI, Roboto, Arial; }}
    header {{ position:sticky; top:0; background:rgba(11,18,32,0.86); border-bottom:1px solid var(--border); padding:12px 16px; z-index:10; }}
    header .sub {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .layout {{ display:grid; grid-template-columns: 360px 1fr; height: calc(100% - 58px); }}
    aside {{ border-right:1px solid var(--border); background:var(--panel); overflow:auto; padding:10px; }}
    main {{ overflow:auto; padding:14px 18px; }}
    .convBtn {{ width:100%; text-align:left; border:1px solid var(--border); background:rgba(255,255,255,0.02); color:var(--text);
      border-radius:10px; padding:10px; margin-bottom:10px; cursor:pointer; }}
    .convBtn.active {{ outline:2px solid rgba(122,162,255,0.35); border-color: rgba(122,162,255,0.55); }}
    .convTitle {{ font-weight:650; font-size:13px; }}
    .convMeta {{ color:var(--muted); font-size:12px; margin-top:6px; }}
    .msg {{ border:1px solid var(--border); background:rgba(255,255,255,0.02); border-radius:12px; padding:10px 12px; margin-bottom:10px; }}
    .msgHeader {{ display:flex; gap:10px; align-items:baseline; }}
    .sender {{ font-weight:700; }}
    .time, .meta {{ color:var(--muted); font-size:12px; }}
    .msgBody {{ margin-top:6px; line-height:1.35; }}
    code {{ background: var(--codeBg); padding: 2px 6px; border-radius: 8px; }}
    .tabs {{ display:flex; gap:8px; margin-bottom:10px; }}
    .tabBtn {{ border:1px solid var(--border); background:rgba(255,255,255,0.02); color:var(--text); border-radius:999px; padding:6px 10px; cursor:pointer; }}
    .tabBtn.active {{ outline:2px solid rgba(122,162,255,0.35); }}
    .tabPane {{ display:none; }}
    .tabPane.active {{ display:block; }}
    .convSection {{ display:none; }}
    .convSection.active {{ display:block; }}
  </style>
</head>
<body>
  <header>
    <div class="title">{_html.escape(title)}</div>
    <div class="sub">Generated {_html.escape(_fmt_ts(_time.time()))} - messages: {len(messages)} - thoughts: {len(thoughts)} - threads: {len(groups)} (conv/job/misc)</div>
  </header>
  <div class="layout">
    <aside>{''.join(sidebar_items)}</aside>
    <main>{''.join(conv_sections)}</main>
  </div>
  <script>
    function selectConv(convId) {{
      document.querySelectorAll('.convBtn').forEach(b => b.classList.toggle('active', b.dataset.conv === convId));
      document.querySelectorAll('.convSection').forEach(s => s.classList.toggle('active', s.dataset.conv === convId));
      selectTab('spoken');
    }}
    function selectTab(tab) {{
      document.querySelectorAll('.tabBtn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
      document.querySelectorAll('.tabPane').forEach(p => p.classList.toggle('active', p.dataset.tab === tab));
    }}
    selectConv({_json.dumps(default_conv)});
  </script>
</body>
</html>"""


@app.get("/runs/{run_id}/viewer")
def runs_viewer(run_id: str, regen: bool = False):
    run_dir = (RUNS_DIR / run_id).resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        return {"error": "not_found"}
    viewer_path = run_dir / "result_viewer.html"
    if viewer_path.exists() and not regen:
        return FileResponse(str(viewer_path), media_type="text/html")
    # Generate on demand
    msgs = _read_jsonl(run_dir / "chat_messages.jsonl")
    trace = _read_jsonl(run_dir / "trace_events.jsonl")
    thoughts = [e for e in trace if e.get("kind") == "chat_thought"]
    jobs_ev = _read_jsonl(run_dir / "jobs_events.jsonl")
    jobs_state = _build_run_job_state(jobs_ev)
    html_txt = _build_viewer_html(msgs, thoughts, jobs_state, title=f"Run {run_id} - Conversations")
    try:
        viewer_path.write_text(html_txt, encoding="utf-8")
    except Exception:
        pass
    return HTMLResponse(content=html_txt)

# In-memory state (Milestone 1). Persistence comes later.
_tick = 0
_agents: Dict[str, AgentState] = {}
_world_started_at = time.time()
SIM_MINUTES_PER_REAL_SECOND = float(os.getenv("SIM_MINUTES_PER_REAL_SECOND", "5"))  # 5 sim-min per sec
_landmarks = [
    {"id": "board", "x": 10, "y": 8, "type": "bulletin_board"},
    {"id": "cafe", "x": 6, "y": 6, "type": "cafe"},
    {"id": "market", "x": 20, "y": 12, "type": "market"},
    {"id": "computer", "x": 16, "y": 16, "type": "computer_access"},
    {"id": "home_agent_1", "x": 3, "y": 26, "type": "home", "agent_id": "agent_1"},
    {"id": "home_agent_2", "x": 28, "y": 4, "type": "home", "agent_id": "agent_2"},
]

AuthorType = Literal["agent", "human", "system"]
AudienceType = Literal["public", "humans", "agents"]
PostStatus = Literal["open", "closed", "moderated"]


@dataclass
class BoardPost:
    post_id: str
    author_type: AuthorType
    author_id: str
    audience: str
    title: str
    body: str
    tags: List[str]
    status: PostStatus
    created_at: float
    updated_at: float


@dataclass
class BoardReply:
    reply_id: str
    post_id: str
    author_type: AuthorType
    author_id: str
    body: str
    created_at: float


@dataclass
class Opportunity:
    """
    Persistent, cross-run representation of a paid gig/service idea discovered by market_scan.
    Stored as JSONL in OPPORTUNITIES_PATH (append-only; we upsert in-memory and rewrite file best-effort).
    """

    opp_id: str
    fingerprint: str
    title: str
    platform: str
    demand_signal: str
    estimated_price_usd: str
    why_fit: str
    first_action: str
    source_url: str
    source_quote: str
    source_domain: str
    status: str  # new | selected | delivering | done | ignored
    tags: list[str]
    notes: str
    created_at: float
    last_seen_at: float
    run_ids: list[str]
    job_ids: list[str]
    client_response: str  # "" | "interested" | "not_interested" | "no_response" | "needs_revision"
    outcome: str  # "" | "success" | "failed" | "pending"
    success_score: float  # 0.0-1.0, calculated from outcomes
    actual_revenue_usd: float  # Actual revenue when completed (0.0 if not completed)
    estimated_value_score: float  # 0.0-1.0, calculated from price, success_score, and fit

class CreatePostRequest(BaseModel):
    title: str
    body: str
    audience: str = "humans"
    tags: List[str] = Field(default_factory=list)
    author_type: AuthorType = "agent"
    author_id: str = ""


class CreateReplyRequest(BaseModel):
    body: str
    author_type: AuthorType = "human"
    author_id: str = "human"


_board_posts: Dict[str, BoardPost] = {}
_board_replies: Dict[str, List[BoardReply]] = {}

# Persistent Opportunity Library (cross-run)
_opportunities: Dict[str, Opportunity] = {}  # fingerprint -> Opportunity


def _norm_text(x: Any) -> str:
    try:
        return str(x or "").strip()
    except Exception:
        return ""


def _opportunity_fingerprint(title: str, platform: str, source_url: str) -> str:
    s = f"{_norm_text(title).lower()}|{_norm_text(platform).lower()}|{_norm_text(source_url)}"
    try:
        return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return str(uuid.uuid4())[:16]


def _url_host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(str(url or "")).hostname or "").lower().strip()
    except Exception:
        return ""


def _save_opportunities() -> None:
    """
    Rewrite opportunities.jsonl from in-memory state (best-effort).
    This is infrequent and the file is expected to remain small (< few thousand lines).
    """
    try:
        rows = [asdict(o) for o in _opportunities.values()]
        rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)
        tmp = OPPORTUNITIES_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(OPPORTUNITIES_PATH)
    except Exception:
        pass


def _load_opportunities() -> None:
    global _opportunities
    _opportunities = {}
    if not OPPORTUNITIES_PATH.exists():
        return
    try:
        for ln in OPPORTUNITIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = (ln or "").strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
                if not isinstance(r, dict):
                    continue
                fp = str(r.get("fingerprint") or "").strip()
                if not fp:
                    continue
                _opportunities[fp] = Opportunity(
                    opp_id=str(r.get("opp_id") or "").strip() or str(uuid.uuid4()),
                    fingerprint=fp,
                    title=_norm_text(r.get("title")),
                    platform=_norm_text(r.get("platform")),
                    demand_signal=_norm_text(r.get("demand_signal")),
                    estimated_price_usd=_norm_text(r.get("estimated_price_usd")),
                    why_fit=_norm_text(r.get("why_fit")),
                    first_action=_norm_text(r.get("first_action")),
                    source_url=_norm_text(r.get("source_url")),
                    source_quote=_norm_text(r.get("source_quote")),
                    source_domain=_norm_text(r.get("source_domain")),
                    status=_norm_text(r.get("status")) or "new",
                    tags=list(r.get("tags") or []) if isinstance(r.get("tags"), list) else [],
                    notes=_norm_text(r.get("notes")),
                    created_at=float(r.get("created_at") or time.time()),
                    last_seen_at=float(r.get("last_seen_at") or r.get("created_at") or time.time()),
                    run_ids=list(r.get("run_ids") or []) if isinstance(r.get("run_ids"), list) else [],
                    job_ids=list(r.get("job_ids") or []) if isinstance(r.get("job_ids"), list) else [],
                    client_response=_norm_text(r.get("client_response")) or "",
                    outcome=_norm_text(r.get("outcome")) or "",
                    success_score=float(r.get("success_score") or 0.0),
                    actual_revenue_usd=float(r.get("actual_revenue_usd") or 0.0),
                    estimated_value_score=float(r.get("estimated_value_score") or 0.0),
                )
            except Exception:
                continue
    except Exception:
        return


def _upsert_opportunity(item: dict, run_id: str, job_id: str) -> Optional[Opportunity]:
    if not isinstance(item, dict):
        return None
    title = _norm_text(item.get("title") or item.get("name"))
    if not title:
        return None
    platform = _norm_text(item.get("platform"))
    demand_signal = _norm_text(item.get("demand_signal"))
    estimated_price_usd = _norm_text(item.get("estimated_price_usd") or item.get("price"))
    why_fit = _norm_text(item.get("why_fit"))
    first_action = _norm_text(item.get("first_action"))
    source_url = _norm_text(item.get("source_url") or item.get("url"))
    source_quote = _norm_text(item.get("source_quote"))
    source_domain = _url_host(source_url)

    fp = _opportunity_fingerprint(title, platform, source_url)
    now = time.time()
    existing = _opportunities.get(fp)
    if existing:
        existing.title = title or existing.title
        existing.platform = platform or existing.platform
        existing.demand_signal = demand_signal or existing.demand_signal
        existing.estimated_price_usd = estimated_price_usd or existing.estimated_price_usd
        existing.why_fit = why_fit or existing.why_fit
        existing.first_action = first_action or existing.first_action
        existing.source_url = source_url or existing.source_url
        existing.source_quote = source_quote or existing.source_quote
        existing.source_domain = source_domain or existing.source_domain
        existing.last_seen_at = now
        if run_id and run_id not in existing.run_ids:
            existing.run_ids.append(run_id)
        if job_id and job_id not in existing.job_ids:
            existing.job_ids.append(job_id)
        return existing

    opp = Opportunity(
        opp_id=str(uuid.uuid4()),
        fingerprint=fp,
        title=title,
        platform=platform,
        demand_signal=demand_signal,
        estimated_price_usd=estimated_price_usd,
        why_fit=why_fit,
        first_action=first_action,
        source_url=source_url,
        source_quote=source_quote,
        source_domain=source_domain,
        status="new",
        tags=[],
        notes="",
        created_at=now,
        last_seen_at=now,
        run_ids=[run_id] if run_id else [],
        job_ids=[job_id] if job_id else [],
        client_response="",
        outcome="",
        success_score=0.0,
        actual_revenue_usd=0.0,
        estimated_value_score=0.0,
    )
    _opportunities[fp] = opp
    # Calculate initial value score for new opportunity
    _recalculate_opportunity_value_score(opp)
    return opp


def _recalculate_opportunity_success_score(opp: Opportunity) -> None:
    """
    Recalculate success_score for an opportunity based on similar opportunities' outcomes.
    This helps prioritize opportunities that have worked well in the past.
    """
    if not opp:
        return
    # Find similar opportunities (same platform or domain pattern)
    similar = []
    for o in _opportunities.values():
        if o.fingerprint == opp.fingerprint:
            continue
        if o.platform == opp.platform and o.platform:
            similar.append(o)
        elif o.source_domain == opp.source_domain and o.source_domain:
            similar.append(o)
    
    # Calculate average success from similar opportunities
    if similar:
        successes = sum(1 for o in similar if o.outcome == "success")
        total_with_outcome = sum(1 for o in similar if o.outcome)
        if total_with_outcome > 0:
            opp.success_score = float(successes) / float(total_with_outcome)
        else:
            opp.success_score = 0.5  # Neutral if no data
    else:
        # No similar opportunities, use individual outcome
        if opp.outcome == "success":
            opp.success_score = 0.8
        elif opp.outcome == "failed":
            opp.success_score = 0.2
        else:
            opp.success_score = 0.5
    
    # Recalculate estimated_value_score: combines price, success_score, and fit
    _recalculate_opportunity_value_score(opp)


def _recalculate_opportunity_value_score(opp: Opportunity) -> None:
    """
    Calculate estimated_value_score: combines price potential, success likelihood, and fit.
    Higher score = better opportunity to pursue.
    """
    if not opp:
        return
    
    # Extract price as number
    price = 0.0
    try:
        price_str = str(opp.estimated_price_usd or "").strip()
        nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
        if nums:
            price = max(nums)
    except Exception:
        pass
    
    # Normalize price to 0-1 (assume $1000+ is max value)
    price_score = min(1.0, price / 1000.0) if price > 0 else 0.3  # Default to 0.3 if no price
    
    # Success likelihood (from success_score)
    success_likelihood = opp.success_score if opp.success_score > 0 else 0.5
    
    # Fit score (based on why_fit field length and quality - simple heuristic)
    fit_score = 0.5
    why_fit = str(opp.why_fit or "").strip()
    if len(why_fit) > 50:
        fit_score = 0.7
    if len(why_fit) > 100:
        fit_score = 0.9
    
    # Combined value score: 40% price, 40% success likelihood, 20% fit
    opp.estimated_value_score = (price_score * 0.4) + (success_likelihood * 0.4) + (fit_score * 0.2)


@dataclass
class ChatMessage:
    msg_id: str
    sender_type: AuthorType
    sender_id: str
    sender_name: str
    text: str
    created_at: float


class ChatSendRequest(BaseModel):
    sender_type: AuthorType = "agent"
    sender_id: str
    sender_name: str
    text: str


_chat: List[ChatMessage] = []
_chat_max = 200


def _load_chat() -> None:
    global _chat
    rows = _read_jsonl(CHAT_PATH, limit=_chat_max)
    out: List[ChatMessage] = []
    for r in rows:
        try:
            out.append(
                ChatMessage(
                    msg_id=str(r.get("msg_id") or uuid.uuid4()),
                    sender_type=r.get("sender_type") or "agent",
                    sender_id=str(r.get("sender_id") or ""),
                    sender_name=str(r.get("sender_name") or ""),
                    text=str(r.get("text") or ""),
                    created_at=float(r.get("created_at") or time.time()),
                )
            )
        except Exception:
            continue
    _chat = out[-_chat_max:]


_load_chat()

_topic: str = "getting started"
_topic_set_at: float = 0.0
_topic_history: List[dict] = []

# ---- Events / Invitations (persistent event log) ----

EventStatus = Literal["scheduled", "cancelled", "completed"]
RsvpStatus = Literal["yes", "no", "maybe"]
EventEventType = Literal["create", "invite", "rsvp", "cancel"]


@dataclass
class VillageEvent:
    event_id: str
    title: str
    description: str
    location_id: str
    start_day: int
    start_minute: int
    duration_min: int
    status: EventStatus
    created_by: str
    created_at: float
    invites: List[dict]
    rsvps: Dict[str, str]


@dataclass
class EventLogEntry:
    log_id: str
    event_type: EventEventType
    event_id: str
    data: dict
    created_at: float


class CreateEventRequest(BaseModel):
    title: str
    description: str = ""
    location_id: str
    start_day: int
    start_minute: int
    duration_min: int = 60
    created_by: str = "human"


class InviteRequest(BaseModel):
    from_agent_id: str
    to_agent_id: str
    message: str = ""


class RsvpRequest(BaseModel):
    agent_id: str
    status: RsvpStatus
    note: str = ""


_events: Dict[str, VillageEvent] = {}
_event_log: List[EventLogEntry] = []


def _apply_event_log(ev: EventLogEntry) -> None:
    d = ev.data or {}
    if ev.event_type == "create":
        _events[ev.event_id] = VillageEvent(
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
            invites=[],
            rsvps={},
        )
        return

    e = _events.get(ev.event_id)
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
        return

    if ev.event_type == "rsvp" and e.status == "scheduled":
        agent_id = str(d.get("agent_id") or "")[:80]
        status = str(d.get("status") or "maybe")
        if agent_id:
            e.rsvps[agent_id] = status
        return

    if ev.event_type == "cancel" and e.status == "scheduled":
        e.status = "cancelled"
        return


def _load_events() -> None:
    global _events, _event_log
    _events = {}
    _event_log = []
    rows = _read_jsonl(EVENTS_PATH)
    for r in rows:
        try:
            ev = EventLogEntry(
                log_id=str(r.get("log_id") or uuid.uuid4()),
                event_type=r.get("event_type"),
                event_id=str(r.get("event_id")),
                data=dict(r.get("data") or {}),
                created_at=float(r.get("created_at") or time.time()),
            )
            _event_log.append(ev)
            _apply_event_log(ev)
        except Exception:
            continue


def _append_event_log(event_type: EventEventType, event_id: str, data: dict) -> EventLogEntry:
    ev = EventLogEntry(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        event_id=event_id,
        data=data,
        created_at=time.time(),
    )
    _event_log.append(ev)
    _append_jsonl(EVENTS_PATH, asdict(ev))
    _apply_event_log(ev)
    return ev


_load_events()


@app.get("/events")
def events_list(day: Optional[int] = None, upcoming_only: bool = True, limit: int = 50):
    limit = max(1, min(limit, 200))
    items = list(_events.values())
    if day is not None:
        items = [e for e in items if e.start_day == int(day)]
    if upcoming_only:
        # compare to current sim time; include events that are upcoming OR currently ongoing
        snap = get_world_snapshot()
        now_total = int(snap.day) * 1440 + int(snap.minute_of_day)
        filtered: List[VillageEvent] = []
        for e in items:
            if e.status != "scheduled":
                continue
            start_total = int(e.start_day) * 1440 + int(e.start_minute)
            end_total = start_total + max(1, int(e.duration_min))
            if end_total >= now_total:
                filtered.append(e)
        items = filtered
    items.sort(key=lambda e: (e.start_day, e.start_minute))
    return {"events": [asdict(e) for e in items[:limit]]}


@app.get("/events/{event_id}")
def events_get(event_id: str):
    e = _events.get(event_id)
    if not e:
        return {"error": "not_found"}
    return {"event": asdict(e)}


@app.post("/events/create")
async def events_create(req: CreateEventRequest):
    global _tick
    _tick += 1
    title = (req.title or "").strip()
    if not title or not req.location_id:
        return {"error": "invalid_event"}
    event_id = str(uuid.uuid4())
    ev = _append_event_log(
        "create",
        event_id,
        {
            "title": title,
            "description": (req.description or "").strip(),
            "location_id": req.location_id,
            "start_day": int(req.start_day),
            "start_minute": int(req.start_minute),
            "duration_min": int(req.duration_min or 60),
            "created_by": req.created_by,
            "created_at": time.time(),
        },
    )
    await ws_manager.broadcast({"type": "events", "data": {"log": asdict(ev), "event": asdict(_events[event_id])}})
    return {"ok": True, "event": asdict(_events[event_id])}


@app.post("/events/{event_id}/invite")
async def events_invite(event_id: str, req: InviteRequest):
    global _tick
    _tick += 1
    e = _events.get(event_id)
    if not e or e.status != "scheduled":
        return {"error": "not_invitable"}
    ev = _append_event_log(
        "invite",
        event_id,
        {"from_agent_id": req.from_agent_id, "to_agent_id": req.to_agent_id, "message": req.message, "created_at": time.time()},
    )
    await ws_manager.broadcast({"type": "events", "data": {"log": asdict(ev), "event": asdict(_events[event_id])}})
    return {"ok": True, "event": asdict(_events[event_id])}


@app.post("/events/{event_id}/rsvp")
async def events_rsvp(event_id: str, req: RsvpRequest):
    global _tick
    _tick += 1
    e = _events.get(event_id)
    if not e or e.status != "scheduled":
        return {"error": "not_rsvpable"}
    ev = _append_event_log(
        "rsvp",
        event_id,
        {"agent_id": req.agent_id, "status": req.status, "note": req.note, "created_at": time.time()},
    )
    await ws_manager.broadcast({"type": "events", "data": {"log": asdict(ev), "event": asdict(_events[event_id])}})
    return {"ok": True, "event": asdict(_events[event_id])}

# ---- aiDollar economy (minimal, persistent JSONL ledger) ----

EconomyEntryType = Literal["genesis", "transfer", "award", "spend", "paypal_payment"]


@dataclass
class EconomyEntry:
    entry_id: str
    entry_type: EconomyEntryType
    amount: float
    from_id: str
    to_id: str
    memo: str
    created_at: float


class TransferRequest(BaseModel):
    from_id: str
    to_id: str
    amount: float
    memo: str = ""


class AwardRequest(BaseModel):
    to_id: str
    amount: float
    reason: str = ""
    by: str = "system"


class PenaltyRequest(BaseModel):
    agent_id: str
    amount: float
    reason: str = ""
    by: str = "system"


_economy_ledger: List[EconomyEntry] = []
_balances: Dict[str, float] = {}


def _recompute_balances() -> None:
    global _balances
    b: Dict[str, float] = {}
    for e in _economy_ledger:
        if e.from_id:
            b[e.from_id] = float(b.get(e.from_id, 0.0)) - float(e.amount)
        if e.to_id:
            b[e.to_id] = float(b.get(e.to_id, 0.0)) + float(e.amount)
    _balances = b


def _load_economy() -> None:
    global _economy_ledger
    rows = _read_jsonl(ECONOMY_PATH)
    ledger: List[EconomyEntry] = []
    for r in rows:
        try:
            ledger.append(
                EconomyEntry(
                    entry_id=str(r.get("entry_id") or r.get("id") or uuid.uuid4()),
                    entry_type=r.get("entry_type") or "award",
                    amount=float(r.get("amount") or 0.0),
                    from_id=str(r.get("from_id") or ""),
                    to_id=str(r.get("to_id") or ""),
                    memo=str(r.get("memo") or ""),
                    created_at=float(r.get("created_at") or time.time()),
                )
            )
        except Exception:
            continue
    _economy_ledger = ledger
    _recompute_balances()


def ensure_account(agent_id: str) -> None:
    # If agent has never appeared in balances, create a genesis entry once.
    if agent_id in _balances:
        return
    if agent_id == TREASURY_ID:
        _balances[agent_id] = float(_balances.get(agent_id, 0.0))
        return
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="genesis",
        amount=float(STARTING_AIDOLLARS),
        from_id="",
        to_id=agent_id,
        memo="starting balance",
        created_at=now,
    )
    _economy_ledger.append(entry)
    _append_jsonl(ECONOMY_PATH, asdict(entry))
    _recompute_balances()


_load_economy()

# ---- long-term memory (minimal, persistent JSONL per agent) ----

MemoryKind = Literal["note", "event", "reflection", "plan", "summary"]


@dataclass
class MemoryEntry:
    memory_id: str
    agent_id: str
    kind: MemoryKind
    text: str
    tags: List[str]
    importance: float
    created_at: float


class MemoryAppendRequest(BaseModel):
    kind: MemoryKind = "note"
    text: str
    tags: List[str] = Field(default_factory=list)
    importance: Optional[float] = None


def _memory_path(agent_id: str) -> Path:
    safe = "".join([c for c in agent_id if c.isalnum() or c in ("-", "_")]) or "agent"
    return MEMORY_DIR / f"{safe}.jsonl"


def _memory_embed_path(agent_id: str) -> Path:
    safe = "".join([c for c in agent_id if c.isalnum() or c in ("-", "_")]) or "agent"
    return MEMORY_EMBED_DIR / f"{safe}.jsonl"


def _get_embedding(text: str) -> Optional[List[float]]:
    """
    Compute a semantic embedding using Ollama's embeddings API:
      POST {EMBEDDINGS_BASE_URL}/api/embeddings {model, prompt}
    """
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
        return None


def _llm_judge_call(task_summary: str, submission: str) -> Optional[tuple[bool, str]]:
    """
    Call an LLM to judge whether a task was completed successfully.
    Uses OpenAI-compatible /v1/chat/completions (Ollama, vLLM, OpenAI).
    Returns (ok, reason) or None on error/missing config.
    """
    if not VERIFY_LLM_BASE_URL:
        return None
    prompt = f"""You are a verifier. Given a TASK and a SUBMISSION, decide if the task was completed successfully.

TASK:
{task_summary[:6000]}

SUBMISSION:
{submission[:6000]}

Reply with ONLY a JSON object, no other text:
{{"ok": true or false, "reason": "brief explanation"}}
"""
    payload = {
        "model": VERIFY_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{VERIFY_LLM_BASE_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=VERIFY_LLM_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            choices = obj.get("choices") or []
            if not choices:
                return None
            content = (choices[0].get("message") or {}).get("content") or ""
            # Extract first {...} from response (LLM may wrap in markdown)
            if "```" in content:
                m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
                if m:
                    content = m.group(1)
            i = content.find("{")
            if i < 0:
                return None
            depth = 0
            for k, c in enumerate(content[i:], start=i):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        parsed = json.loads(content[i : k + 1])
                        ok = bool(parsed.get("ok", False))
                        reason = str(parsed.get("reason", ""))[:1000] or ("ok" if ok else "not ok")
                        return (ok, reason)
            return None
    except Exception:
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        x = float(a[i])
        y = float(b[i])
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (math.sqrt(na) * math.sqrt(nb))))


@app.post("/memory/{agent_id}/append")
async def memory_append(agent_id: str, req: MemoryAppendRequest):
    global _tick
    _tick += 1
    now = time.time()
    text = (req.text or "").strip()
    if not text:
        return {"error": "invalid_text"}
    entry = MemoryEntry(
        memory_id=str(uuid.uuid4()),
        agent_id=agent_id,
        kind=req.kind,
        text=text[:4000],
        tags=[t[:40] for t in (req.tags or [])][:20],
        importance=float(req.importance) if req.importance is not None else 0.3,
        created_at=now,
    )
    _append_jsonl(_memory_path(agent_id), asdict(entry))

    # Store embedding separately (append-only index) so we don't rewrite memory JSONL.
    emb = _get_embedding(text)
    if emb is not None:
        _append_jsonl(
            _memory_embed_path(agent_id),
            {
                "memory_id": entry.memory_id,
                "embedding": emb,
                "model": EMBEDDINGS_MODEL,
                "dim": len(emb),
                "created_at": now,
            },
        )
    return {"ok": True, "memory": asdict(entry)}


@app.get("/memory/{agent_id}/recent")
def memory_recent(agent_id: str, limit: int = 20):
    limit = max(1, min(limit, 200))
    rows = _read_jsonl(_memory_path(agent_id), limit=limit)
    return {"memories": rows}


@app.get("/memory/{agent_id}/search")
def memory_search(agent_id: str, q: str, limit: int = 20):
    q = (q or "").strip().lower()
    limit = max(1, min(limit, 200))
    if not q:
        return {"memories": []}
    rows = _read_jsonl(_memory_path(agent_id))
    hits = []
    for r in rows:
        try:
            txt = str(r.get("text") or "").lower()
            if q in txt:
                hits.append(r)
        except Exception:
            continue
    return {"memories": hits[-limit:]}


@app.post("/memory/{agent_id}/embeddings/backfill")
def memory_embeddings_backfill(agent_id: str, limit: int = 200):
    """
    Create embeddings for older memories that predate embedding storage.
    """
    if not EMBEDDINGS_BASE_URL:
        return {"error": "embeddings_disabled"}

    limit = max(1, min(limit, 500))
    mems = _read_jsonl(_memory_path(agent_id), limit=limit)

    # existing index ids
    idx_rows = _read_jsonl(_memory_embed_path(agent_id))
    existing = {r.get("memory_id") for r in idx_rows if r.get("memory_id")}

    wrote = 0
    for r in mems:
        mid = r.get("memory_id")
        if not mid or mid in existing:
            continue
        txt = str(r.get("text") or "").strip()
        if not txt:
            continue
        emb = _get_embedding(txt)
        if emb is None:
            continue
        _append_jsonl(
            _memory_embed_path(agent_id),
            {"memory_id": mid, "embedding": emb, "model": EMBEDDINGS_MODEL, "dim": len(emb), "created_at": time.time()},
        )
        wrote += 1
        existing.add(mid)

    return {"ok": True, "wrote": wrote, "scanned": len(mems)}


def _tok(s: str) -> set:
    s = (s or "").lower()
    out = []
    cur = []
    for ch in s:
        if ch.isalnum():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    # filter tiny tokens
    return {t for t in out if len(t) >= 3}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union) if union else 0.0


@app.get("/memory/{agent_id}/retrieve")
def memory_retrieve(
    agent_id: str,
    q: str,
    k: int = 8,
    recency_halflife_minutes: float = 180.0,
    w_relevance: float = 0.55,
    w_recency: float = 0.25,
    w_importance: float = 0.20,
):
    """
    Ranked memory retrieval inspired by Generative Agents:
    score = w_rel*relevance + w_rec*recency + w_imp*importance

    - relevance: token Jaccard similarity between query and memory text+tags
    - recency: exponential decay with halflife
    - importance: stored scalar (0..1 recommended)
    """
    q = (q or "").strip()
    if not q:
        return {"memories": []}

    k = max(1, min(int(k), 50))
    now = time.time()
    qtok = _tok(q)
    qemb = _get_embedding(q)
    rows = _read_jsonl(_memory_path(agent_id))

    # load embedding index
    embed_rows = _read_jsonl(_memory_embed_path(agent_id))
    emb_by_id: Dict[str, List[float]] = {}
    for r in embed_rows:
        mid = r.get("memory_id")
        emb = r.get("embedding")
        if isinstance(mid, str) and isinstance(emb, list) and emb:
            try:
                emb_by_id[mid] = [float(x) for x in emb]
            except Exception:
                continue
    scored = []
    hl = max(1.0, float(recency_halflife_minutes)) * 60.0

    for r in rows:
        try:
            text = str(r.get("text") or "")
            tags = r.get("tags") or []
            itok = _tok(text + " " + " ".join([str(t) for t in tags]))
            rel_tok = _jaccard(qtok, itok)
            rel_emb = 0.0
            mid = r.get("memory_id")
            if qemb is not None and isinstance(mid, str) and mid in emb_by_id:
                rel_emb = _cosine(qemb, emb_by_id[mid])
            rel = max(rel_tok, rel_emb)
            created_at = float(r.get("created_at") or 0.0)
            age = max(0.0, now - created_at)
            rec = 0.5 ** (age / hl)  # halflife decay
            # Backward compatible default for older memories that predate importance scoring.
            imp = float(r["importance"]) if ("importance" in r and r["importance"] is not None) else 0.3
            # clamp
            if imp < 0:
                imp = 0.0
            if imp > 1:
                imp = 1.0
            score = float(w_relevance) * rel + float(w_recency) * rec + float(w_importance) * imp
            scored.append(
                (
                    score,
                    {
                        "score": score,
                        "relevance": rel,
                        "recency": rec,
                        "importance": imp,
                        "relevance_token": rel_tok,
                        "relevance_embed": rel_emb,
                        **r,
                    },
                )
            )
        except Exception:
            continue

    scored.sort(key=lambda t: t[0], reverse=True)
    return {"memories": [x[1] for x in scored[:k]]}

# ---- Jobs Board (persistent event log) ----

JobStatus = Literal["open", "claimed", "submitted", "approved", "rejected", "cancelled"]


@dataclass
class Job:
    job_id: str
    title: str
    body: str
    reward: float
    status: JobStatus
    created_by: str
    created_at: float
    claimed_by: str
    claimed_at: float
    submitted_by: str
    submitted_at: float
    submission: str
    reviewed_by: str
    reviewed_at: float
    review_note: str
    auto_verify_ok: Optional[bool] = None
    auto_verify_name: str = ""
    auto_verify_note: str = ""
    auto_verify_artifacts: dict = field(default_factory=dict)
    auto_verified_at: float = 0.0
    fingerprint: str = ""
    ratings: dict = field(default_factory=dict)
    reward_mode: str = "manual"
    reward_calc: dict = field(default_factory=dict)
    source: str = "unknown"
    parent_job_id: str = ""  # If set, this job is a sub-task and requires parent to be approved


JobEventType = Literal["create", "claim", "submit", "verify", "review", "update", "cancel", "unclaim"]


@dataclass
class JobEvent:
    event_id: str
    event_type: JobEventType
    job_id: str
    data: dict
    created_at: float


class JobCreateRequest(BaseModel):
    title: str
    body: str
    reward: float = 10.0
    created_by: str = "human"
    ratings: Optional[dict] = None
    auto_reward: bool = False
    parent_job_id: Optional[str] = None  # If set, this is a sub-task of another job


class JobClaimRequest(BaseModel):
    agent_id: str


class JobSubmitRequest(BaseModel):
    agent_id: str
    submission: str


class JobCancelRequest(BaseModel):
    by: str = "human"
    note: str = ""


class PurgeCancelledJobsRequest(BaseModel):
    """Admin maintenance: permanently remove cancelled jobs from the active job store + jobs_events.jsonl."""

    by: str = "human"
    note: str = ""
    # Only purge jobs cancelled at least this many seconds ago (0 = purge all cancelled).
    older_than_seconds: float = 0.0
    # Safety cap on number of jobs removed in one call.
    limit: int = 5000


class JobUpdateRequest(BaseModel):
    """
    Admin edit of an existing job/task (intended for human-curated task board).
    We restrict edits to open jobs by default to avoid changing requirements mid-execution.
    """

    title: Optional[str] = None
    body: Optional[str] = None
    reward: Optional[float] = None
    ratings: Optional[dict] = None
    auto_reward: bool = False
    by: str = "human"
    force: bool = False


class JobReviewRequest(BaseModel):
    approved: bool
    reviewed_by: str = "human"
    note: str = ""
    payout: Optional[float] = None
    penalty: Optional[float] = None


class JobVerifyRequest(BaseModel):
    """Manual/system verification trigger (admin-only)."""
    by: str = "human"
    force: bool = False


_jobs: Dict[str, Job] = {}
_job_events: List[JobEvent] = []


def _apply_job_event(ev: JobEvent) -> None:
    global _jobs
    t = ev.event_type
    d = ev.data or {}
    if t == "create":
        _jobs[ev.job_id] = Job(
            job_id=ev.job_id,
            title=str(d.get("title") or "")[:200],
            body=str(d.get("body") or "")[:4000],
            reward=float(d.get("reward") or 0.0),
            status="open",
            created_by=str(d.get("created_by") or "human")[:80],
            created_at=float(d.get("created_at") or ev.created_at),
            claimed_by="",
            claimed_at=0.0,
            submitted_by="",
            submitted_at=0.0,
            submission="",
            reviewed_by="",
            reviewed_at=0.0,
            review_note="",
            auto_verify_ok=None,
            auto_verify_name="",
            auto_verify_note="",
            auto_verify_artifacts={},
            auto_verified_at=0.0,
            fingerprint=str(d.get("fingerprint") or "")[:120],
            ratings=(dict(d.get("ratings") or {}) if isinstance(d.get("ratings"), dict) else {}),
            reward_mode=str(d.get("reward_mode") or "manual")[:40],
            reward_calc=(dict(d.get("reward_calc") or {}) if isinstance(d.get("reward_calc"), dict) else {}),
            source=str(d.get("source") or "unknown")[:40],
            parent_job_id=str(d.get("parent_job_id") or "")[:80],
        )
        return

    job = _jobs.get(ev.job_id)
    if not job:
        return

    if t == "claim":
        # Race condition handling: only claim if still open
        if job.status == "open":
            job.status = "claimed"
            job.claimed_by = str(d.get("agent_id") or "")[:80]
            job.claimed_at = float(d.get("created_at") or ev.created_at)
            return
        # If already claimed by someone else, this is a failed race (silently ignore)
        # The caller will get an error when they check the job status
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
        # Allow updating title/body/reward for open tasks (or claimed if forced by admin).
        # Status is not changed here.
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
        # Safety valve: requeue a stale claim (e.g., executor crashed mid-job).
        job.status = "open"
        job.claimed_by = ""
        job.claimed_at = 0.0
        return


def _requeue_stale_claims(now: Optional[float] = None) -> int:
    """
    Requeue jobs that have been stuck in 'claimed' for too long.
    This prevents a single crashed/stalled executor from blocking progress forever.
    """
    now = float(now or time.time())
    stale_seconds = float(os.getenv("CLAIM_STALE_SECONDS", "1800"))  # 30 minutes
    if stale_seconds <= 0:
        return 0

    requeued = 0
    for j in list(_jobs.values()):
        try:
            if j.status != "claimed":
                continue
            if not j.claimed_at:
                continue
            age = now - float(j.claimed_at)
            if age <= stale_seconds:
                continue
            _append_job_event(
                "unclaim",
                j.job_id,
                {
                    "reason": "stale_claim",
                    "stale_seconds": age,
                    "prev_claimed_by": j.claimed_by,
                    "prev_claimed_at": j.claimed_at,
                },
            )
            requeued += 1
        except Exception:
            continue
    return requeued


async def _housekeeping_loop() -> None:
    """Background maintenance tasks."""
    every = float(os.getenv("HOUSEKEEPING_EVERY_SECONDS", "10"))
    every = max(2.0, min(every, 120.0))
    await asyncio.sleep(2.0)
    while True:
        try:
            _requeue_stale_claims()
        except Exception:
            pass
        await asyncio.sleep(every)


@app.on_event("startup")
async def _startup_housekeeping() -> None:
    try:
        asyncio.create_task(_housekeeping_loop())
    except Exception:
        pass


def _load_jobs() -> None:
    global _job_events, _jobs
    _jobs = {}
    _job_events = []
    rows = _read_jsonl(JOBS_PATH)
    for r in rows:
        try:
            ev = JobEvent(
                event_id=str(r.get("event_id") or uuid.uuid4()),
                event_type=r.get("event_type"),
                job_id=str(r.get("job_id")),
                data=dict(r.get("data") or {}),
                created_at=float(r.get("created_at") or time.time()),
            )
            _job_events.append(ev)
            _apply_job_event(ev)
        except Exception:
            continue


def _append_job_event(event_type: JobEventType, job_id: str, data: dict) -> JobEvent:
    ev = JobEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        job_id=job_id,
        data=data,
        created_at=time.time(),
    )
    _job_events.append(ev)
    _append_jsonl(JOBS_PATH, asdict(ev))
    _apply_job_event(ev)
    return ev


_load_jobs()

# Load Opportunity Library (cross-run)
_load_opportunities()


@app.get("/jobs")
def jobs_list(status: Optional[JobStatus] = None, limit: int = 50):
    limit = max(1, min(limit, 200))
    jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j.status == status]
    
    # Filter out sub-tasks whose parents aren't approved yet
    # (Sub-tasks are only claimable after parent is approved)
    available_jobs = []
    for j in jobs:
        parent_id = getattr(j, "parent_job_id", "") or ""
        if parent_id:
            parent = _jobs.get(parent_id)
            if not parent or parent.status != "approved":
                # Parent not approved yet, hide this sub-task from open/claimed lists
                if status in ("open", "claimed"):
                    continue
        available_jobs.append(j)
    
    available_jobs.sort(key=lambda j: j.created_at, reverse=True)
    return {"jobs": [asdict(j) for j in available_jobs[:limit]]}


@app.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    j = _jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    return {"job": asdict(j)}


@app.get("/opportunities")
def opportunities(limit: int = 80):
    """
    Opportunity Board:
    - Source of truth is the persistent Opportunity Library (opportunities.jsonl), which survives new runs.
    - If library is empty, fall back to aggregating from approved market_scan jobs in current run.
    """
    limit = max(1, min(int(limit or 0), 500))

    def _host(url: str) -> str:
        try:
            return (urllib.parse.urlparse(str(url or "")).hostname or "").lower().strip()
        except Exception:
            return ""

    # Prefer library (cross-run)
    if _opportunities:
        rows = [asdict(o) for o in _opportunities.values()]
        # Default: hide ignored unless explicitly requested by UI later (keeps board clean).
        rows = [r for r in rows if str(r.get("status") or "new") != "ignored"]
        rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)

        # Adapt to UI expectations (keep a couple of legacy helper keys)
        items: list[dict] = []
        for r in rows[: limit * 2]:
            rec = dict(r)
            try:
                s = str(rec.get("estimated_price_usd") or "").strip()
                nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s)]
                rec["_price_max"] = (max(nums) if nums else 0.0)
            except Exception:
                rec["_price_max"] = 0.0
            rec["_source_domain"] = _host(rec.get("source_url") or "")
            items.append(rec)
            if len(items) >= limit:
                break

        # Prefer non-example domains first.
        def _is_example(d: str) -> bool:
            return (d or "") in ("example.com", "www.example.com", "")

        items.sort(
            key=lambda r: (
                _is_example(str(r.get("_source_domain") or "")),
                -float(r.get("_price_max") or 0.0),
                -float(r.get("last_seen_at") or r.get("created_at") or 0.0),
            )
        )
        domains = sorted({str(r.get("_source_domain") or "") for r in items if str(r.get("_source_domain") or "")})
        return {"items": items[:limit], "count": len(items[:limit]), "domains": domains[:50]}

    # Fallback: aggregate from current run jobs (legacy behavior)
    items: list[dict] = []
    jobs = sorted(list(_jobs.values()), key=lambda j: float(j.reviewed_at or j.submitted_at or j.created_at or 0.0), reverse=True)
    # scan a bit more than requested to account for filtering
    for j in jobs[: min(len(jobs), limit * 6)]:
        try:
            if str(j.status) != "approved":
                continue
            txt = (str(j.title or "") + "\n" + str(j.body or "")).lower()
            if "archetype:market_scan" not in txt:
                continue
            if "[verifier:json_list]" not in txt and str(j.auto_verify_name or "").lower() != "json_list":
                continue
            sub = str(j.submission or "")
            code = _extract_code_fence(sub, "json") or _extract_code_fence(sub, "javascript")
            if not code:
                continue
            obj = json.loads(code)
            if not isinstance(obj, list):
                continue
            for it in obj:
                if not isinstance(it, dict):
                    continue
                rec = dict(it)
                # best-effort numeric price for sorting (use max of a range if present)
                try:
                    s = str(rec.get("estimated_price_usd") or rec.get("price") or "").strip()
                    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s)]
                    rec["_price_max"] = (max(nums) if nums else 0.0)
                except Exception:
                    rec["_price_max"] = 0.0
                rec["_job_id"] = j.job_id
                rec["_job_title"] = j.title
                rec["_approved_at"] = float(j.reviewed_at or j.submitted_at or 0.0)
                rec["_source_domain"] = _host(rec.get("source_url") or rec.get("url") or "")
                items.append(rec)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        except Exception:
            continue

    # Prefer non-example domains first.
    def _is_example(d: str) -> bool:
        return (d or "") in ("example.com", "www.example.com", "")

    # Prioritize by success_score (from opportunity library), then price, then recency
    # Look up success_score from library for each item
    for r in items:
        title = str(r.get("title") or r.get("name") or "")
        platform = str(r.get("platform") or "")
        url = str(r.get("source_url") or r.get("url") or "")
        if title and platform:
            fp = _opportunity_fingerprint(title, platform, url)
            opp = _opportunities.get(fp)
            if opp:
                r["_success_score"] = opp.success_score
            else:
                r["_success_score"] = 0.5  # Neutral for new opportunities
        else:
            r["_success_score"] = 0.5

    items.sort(
        key=lambda r: (
            _is_example(str(r.get("_source_domain") or "")),
            -float(r.get("_success_score") or 0.5),  # Higher success_score first
            -float(r.get("_price_max") or 0.0),
            -float(r.get("_approved_at") or 0.0),
        )
    )
    domains = sorted({str(r.get("_source_domain") or "") for r in items if str(r.get("_source_domain") or "")})
    return {"items": items[:limit], "count": len(items[:limit]), "domains": domains[:50]}


class OpportunityUpdateRequest(BaseModel):
    fingerprint: str = ""
    status: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    client_response: Optional[str] = None
    outcome: Optional[str] = None


@app.get("/opportunities/library")
def opportunities_library(status: Optional[str] = None, q: Optional[str] = None, limit: int = 200):
    """
    Full Opportunity Library (cross-run).
    """
    limit = max(1, min(int(limit or 0), 500))
    rows = [asdict(o) for o in _opportunities.values()]
    if status:
        rows = [r for r in rows if str(r.get("status") or "").strip() == status]
    if q:
        qq = str(q or "").lower().strip()
        if qq:
            rows = [r for r in rows if qq in str(r.get("title") or "").lower() or qq in str(r.get("platform") or "").lower()]
    rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)
    return {"items": rows[:limit], "count": len(rows[:limit])}


@app.post("/opportunities/update")
def opportunities_update(req: OpportunityUpdateRequest, request: Request):
    """
    Update an opportunity: status/notes/tags.
    Agents can update status/notes/tags for opportunities they're working on.
    Admin can update any opportunity.
    """
    # Allow agents to update opportunities (for status tracking as they work on them)
    # Admin can update anything; agents can update status/notes/tags but not delete
    is_admin = _require_admin(request)
    if not is_admin:
        # Agent access: allow status/notes/tags updates only
        pass  # Agents are allowed
    fp = str(req.fingerprint or "").strip()
    if not fp:
        return {"error": "bad_request"}
    o = _opportunities.get(fp)
    if not o:
        return {"error": "not_found"}
    if req.status is not None:
        st = str(req.status or "").strip() or "new"
        if st not in ("new", "selected", "delivering", "done", "ignored"):
            return {"error": "bad_status"}
        o.status = st
    if req.notes is not None:
        o.notes = str(req.notes or "")[:2000]
    if req.tags is not None and isinstance(req.tags, list):
        o.tags = [str(t or "").strip()[:40] for t in req.tags if str(t or "").strip()][:20]
    if req.client_response is not None:
        o.client_response = str(req.client_response or "").strip()[:100]
    if req.outcome is not None:
        o.outcome = str(req.outcome or "").strip()[:50]
        # Update success_score based on outcome
        if o.outcome == "success":
            o.success_score = min(1.0, o.success_score + 0.3)
        elif o.outcome == "failed":
            o.success_score = max(0.0, o.success_score - 0.2)
        # Recalculate success_score from all opportunities with same platform/domain pattern
        _recalculate_opportunity_success_score(o)
    o.last_seen_at = time.time()
    _save_opportunities()
    return {"ok": True, "item": asdict(o)}


class ClientResponseRequest(BaseModel):
    fingerprint: str
    email_content: str  # The outreach email that was sent
    simulate_delay_hours: Optional[float] = 24.0  # How long to wait before responding


@app.post("/opportunities/client_response")
def opportunities_client_response(req: ClientResponseRequest):
    """
    Simulate a client response to an outreach email.
    Returns a realistic client response based on the opportunity and email quality.
    """
    fp = str(req.fingerprint or "").strip()
    if not fp:
        return {"error": "bad_request"}
    opp = _opportunities.get(fp)
    if not opp:
        return {"error": "not_found"}
    
    # Simulate client response based on opportunity quality and email content
    email = str(req.email_content or "").lower()
    
    # Factors that influence positive response:
    # - High estimated price (client has budget)
    # - Clear value proposition in email
    # - Professional tone
    # - Good fit (why_fit field)
    
    price_score = 0.0
    try:
        price_str = str(opp.estimated_price_usd or "").strip()
        price_nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
        if price_nums:
            price_max = max(price_nums)
            price_score = min(1.0, price_max / 1000.0)  # Normalize to 0-1, $1000+ = 1.0
    except Exception:
        pass
    
    email_quality = 0.5
    if "subject:" in email or "subject line" in email:
        email_quality += 0.1
    if len(email) > 200:
        email_quality += 0.1
    if "value" in email or "benefit" in email or "solution" in email:
        email_quality += 0.2
    email_quality = min(1.0, email_quality)
    
    # Combine factors
    response_prob = 0.3 + (price_score * 0.3) + (email_quality * 0.4)
    
    # Add some randomness but bias towards the calculated probability
    import random
    rand = random.random()
    
    if rand < response_prob * 0.6:
        # Positive response
        response_type = "interested"
        response_text = (
            f"Hi,\n\n"
            f"Thanks for reaching out about {opp.title}. "
            f"I'm interested in learning more about your approach. "
            f"Could you provide a bit more detail on timeline and deliverables?\n\n"
            f"Best regards"
        )
        outcome = "pending"  # Not success yet, but promising
    elif rand < response_prob * 0.9:
        # Neutral/needs revision
        response_type = "needs_revision"
        response_text = (
            f"Hi,\n\n"
            f"Thanks for your message. "
            f"I'd like to see a more detailed proposal with specific deliverables and pricing tiers.\n\n"
            f"Regards"
        )
        outcome = "pending"
    else:
        # No response or negative
        if rand < 0.7:
            response_type = "no_response"
            response_text = "(No response after 48 hours)"
            outcome = "pending"
        else:
            response_type = "not_interested"
            response_text = (
                f"Hi,\n\n"
                f"Thanks for reaching out, but this isn't a good fit for us right now.\n\n"
                f"Best of luck"
            )
            outcome = "failed"
    
    # Update opportunity
    opp.client_response = response_type
    if outcome:
        opp.outcome = outcome
        _recalculate_opportunity_success_score(opp)
    opp.last_seen_at = time.time()
    _save_opportunities()
    
    return {
        "ok": True,
        "response_type": response_type,
        "response_text": response_text,
        "opportunity": asdict(opp),
    }


@app.get("/opportunities/metrics")
def opportunities_metrics():
    """
    Performance metrics for opportunities: success rates, response rates, top performers.
    """
    all_opps = list(_opportunities.values())
    total = len(all_opps)
    
    # Status breakdown
    by_status = {}
    for opp in all_opps:
        st = opp.status or "new"
        by_status[st] = by_status.get(st, 0) + 1
    
    # Outcome breakdown
    by_outcome = {}
    for opp in all_opps:
        oc = opp.outcome or ""
        if oc:
            by_outcome[oc] = by_outcome.get(oc, 0) + 1
    
    # Client response breakdown
    by_response = {}
    for opp in all_opps:
        resp = opp.client_response or ""
        if resp:
            by_response[resp] = by_response.get(resp, 0) + 1
    
    # Success rate by platform
    by_platform = {}
    for opp in all_opps:
        plat = opp.platform or "unknown"
        if plat not in by_platform:
            by_platform[plat] = {"total": 0, "success": 0, "failed": 0, "avg_score": 0.0, "scores": []}
        by_platform[plat]["total"] += 1
        if opp.outcome == "success":
            by_platform[plat]["success"] += 1
        elif opp.outcome == "failed":
            by_platform[plat]["failed"] += 1
        if opp.success_score > 0:
            by_platform[plat]["scores"].append(opp.success_score)
    
    # Calculate averages
    for plat, data in by_platform.items():
        if data["scores"]:
            data["avg_score"] = sum(data["scores"]) / len(data["scores"])
        data.pop("scores", None)
        if data["total"] > 0:
            data["success_rate"] = float(data["success"]) / float(data["total"])
        else:
            data["success_rate"] = 0.0
    
    # Top opportunities by success score
    top_by_score = sorted(
        [o for o in all_opps if o.success_score > 0],
        key=lambda o: o.success_score,
        reverse=True
    )[:10]
    
    # Opportunities with outcomes
    with_outcomes = [o for o in all_opps if o.outcome]
    success_rate = 0.0
    if with_outcomes:
        successes = sum(1 for o in with_outcomes if o.outcome == "success")
        success_rate = float(successes) / float(len(with_outcomes))
    
    # Response rate
    response_rate = 0.0
    with_responses = [o for o in all_opps if o.client_response]
    if all_opps:
        response_rate = float(len(with_responses)) / float(total) if total > 0 else 0.0
    
    # Revenue metrics
    total_revenue = sum(o.actual_revenue_usd for o in all_opps)
    avg_revenue_per_success = 0.0
    successful_opps = [o for o in all_opps if o.outcome == "success" and o.actual_revenue_usd > 0]
    if successful_opps:
        avg_revenue_per_success = sum(o.actual_revenue_usd for o in successful_opps) / len(successful_opps)
    
    # Deliverable type analysis (from notes)
    deliverable_type_counts = {}
    for opp in all_opps:
        if opp.outcome == "success" and opp.notes:
            notes_lower = opp.notes.lower()
            if "deliverable types:" in notes_lower:
                # Extract types
                match = re.search(r"deliverable types:\s*([^\n]+)", notes_lower)
                if match:
                    types_str = match.group(1).strip()
                    for dt in types_str.split(","):
                        dt_clean = dt.strip()
                        if dt_clean:
                            deliverable_type_counts[dt_clean] = deliverable_type_counts.get(dt_clean, 0) + 1
    
    return {
        "total": total,
        "by_status": by_status,
        "by_outcome": by_outcome,
        "by_response": by_response,
        "by_platform": by_platform,
        "success_rate": success_rate,
        "response_rate": response_rate,
        "total_revenue_usd": total_revenue,
        "avg_revenue_per_success": avg_revenue_per_success,
        "deliverable_type_counts": deliverable_type_counts,
        "top_by_score": [asdict(o) for o in top_by_score],
    }


class ArtifactPutRequest(BaseModel):
    job_id: str
    path: str
    content: str
    content_type: str = "text/plain"


@app.post("/artifacts/put")
def artifacts_put(req: ArtifactPutRequest):
    """
    Shared workspace primitive (agent-friendly):
    Store a text artifact under DATA_DIR/artifacts/<job_id>/<path>.
    """
    job_id = str(req.job_id or "").strip()
    rel = str(req.path or "").strip().lstrip("/").replace("\\", "/")
    if not job_id or not rel:
        return {"error": "bad_request"}
    if len(rel) > 200 or ".." in rel:
        return {"error": "bad_path"}
    content = str(req.content or "")
    if len(content) > 250_000:
        return {"error": "too_large"}
    base = (ARTIFACTS_DIR / job_id).resolve()
    base.mkdir(parents=True, exist_ok=True)
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        return {"error": "bad_path"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"error": "write_failed", "detail": str(e)[:200]}
    return {"ok": True, "job_id": job_id, "path": rel, "bytes": len(content), "content_type": str(req.content_type or "")[:80]}


@app.get("/artifacts/{job_id}/list")
def artifacts_list(job_id: str):
    base = (ARTIFACTS_DIR / str(job_id or "").strip()).resolve()
    if not str(base).startswith(str(ARTIFACTS_DIR)) or not base.exists() or not base.is_dir():
        return {"items": []}
    items: list[dict] = []
    try:
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            try:
                st = p.stat()
                items.append({"path": rel, "bytes": int(st.st_size), "mtime": float(st.st_mtime)})
            except Exception:
                items.append({"path": rel})
        items.sort(key=lambda r: float(r.get("mtime") or 0.0), reverse=True)
    except Exception:
        pass
    return {"job_id": str(job_id or ""), "items": items[:500], "count": len(items)}


@app.get("/artifacts/{job_id}/get")
def artifacts_get(job_id: str, path: str):
    rel = str(path or "").strip().lstrip("/").replace("\\", "/")
    base = (ARTIFACTS_DIR / str(job_id or "").strip()).resolve()
    if not rel or ".." in rel:
        return {"error": "bad_path"}
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)) or not p.exists() or not p.is_file():
        return {"error": "not_found"}
    try:
        data = p.read_text(encoding="utf-8", errors="replace")
        # Keep responses bounded
        if len(data) > 250_000:
            data = data[:250_000]
        return {"ok": True, "job_id": str(job_id or ""), "path": rel, "content": data}
    except Exception as e:
        return {"error": "read_failed", "detail": str(e)[:200]}


@app.post("/jobs/{job_id}/update")
async def jobs_update(job_id: str, req: JobUpdateRequest, request: Request):
    """
    Admin edit of an existing job (title/body/reward).
    Intended for a "human task board" where you curate tasks the agents should solve.
    """
    global _tick
    _tick += 1
    if not _require_admin(request):
        return {"error": "unauthorized"}
    j = _jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    # By default only allow edits while open. 'force' allows claimed as well.
    allow = (j.status == "open") or (bool(req.force) and j.status == "claimed")
    if not allow:
        return {"error": "not_editable", "status": j.status}

    title = (req.title or "").strip() if isinstance(req.title, str) else None
    body = (req.body or "").strip() if isinstance(req.body, str) else None
    reward = None
    if req.reward is not None:
        try:
            reward = float(req.reward)
        except Exception:
            reward = None
    ratings = req.ratings if isinstance(req.ratings, dict) else None
    auto_reward = bool(req.auto_reward)

    if (title is None) and (body is None) and (reward is None) and (ratings is None):
        return {"error": "no_changes"}

    data: dict = {"by": str(req.by or "human")[:80], "created_at": time.time()}
    if title is not None:
        data["title"] = title[:200]
    if body is not None:
        data["body"] = body[:4000]
    if reward is not None:
        data["reward"] = float(max(0.0, reward))
    if ratings is not None:
        data["ratings"] = ratings
    if auto_reward and ratings is not None:
        # Auto reward scaling is admin-only via this endpoint; safe to apply.
        rr, meta = _calc_reward_from_ratings(ratings)
        data["reward"] = float(rr)
        data["reward_mode"] = "auto_ratings"
        data["reward_calc"] = meta
    elif reward is not None:
        # Explicit manual reward update clears auto mode.
        data["reward_mode"] = "manual"
        data["reward_calc"] = {}

    ev = _append_job_event("update", job_id, data)
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})
    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/jobs/{job_id}/cancel")
async def jobs_cancel(job_id: str, req: JobCancelRequest, request: Request):
    """Admin cancel an open/claimed/submitted job (useful to remove stale/duplicate tasks)."""
    global _tick
    _tick += 1
    if not _require_admin(request):
        return {"error": "unauthorized"}
    j = _jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    if j.status not in ("open", "claimed", "submitted"):
        return {"error": "not_cancellable", "status": j.status}
    ev = _append_job_event("cancel", job_id, {"by": str(req.by or "human")[:80], "note": str(req.note or "")[:2000], "created_at": time.time()})
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})
    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/admin/jobs/purge_cancelled")
async def admin_purge_cancelled_jobs(req: PurgeCancelledJobsRequest, request: Request):
    """
    Permanently remove cancelled jobs so the system doesn't clog up.
    This rewrites jobs_events.jsonl and drops matching entries from the in-memory job/event stores.
    """
    global _tick, _jobs, _job_events
    _tick += 1
    if not _require_admin(request):
        return {"error": "unauthorized"}

    now = time.time()
    older = float(req.older_than_seconds or 0.0)
    limit = int(req.limit or 0)
    if limit <= 0:
        limit = 5000
    if limit > 20000:
        limit = 20000

    # Determine cancellation time per job (based on last cancel event).
    cancel_ts: Dict[str, float] = {}
    for ev in _job_events:
        if getattr(ev, "event_type", "") == "cancel":
            try:
                cancel_ts[str(ev.job_id)] = float(ev.created_at or 0.0)
            except Exception:
                continue

    # Collect job_ids to purge.
    candidates: List[str] = []
    for jid, job in list(_jobs.items()):
        try:
            if str(job.status) != "cancelled":
                continue
            ts = float(cancel_ts.get(jid) or getattr(job, "created_at", 0.0) or 0.0)
            if older > 0 and (now - ts) < older:
                continue
            candidates.append(jid)
        except Exception:
            continue

    # Deterministic order: oldest cancelled first.
    candidates.sort(key=lambda jid: float(cancel_ts.get(jid) or (_jobs.get(jid).created_at if _jobs.get(jid) else 0.0) or 0.0))
    purge_ids = set(candidates[:limit])

    if not purge_ids:
        return {"ok": True, "removed_jobs": 0, "removed_events": 0, "note": "no cancelled jobs matched"}

    # Filter events and rewrite JSONL.
    before_events = len(_job_events)
    kept_events: List[JobEvent] = [ev for ev in _job_events if str(ev.job_id) not in purge_ids]
    removed_events = before_events - len(kept_events)
    _job_events = kept_events

    # Drop jobs.
    removed_jobs = 0
    for jid in list(purge_ids):
        if jid in _jobs:
            try:
                del _jobs[jid]
                removed_jobs += 1
            except Exception:
                continue

    # Rewrite jobs_events.jsonl to match the in-memory event log.
    try:
        _write_jsonl_atomic(JOBS_PATH, [asdict(ev) for ev in _job_events])
    except Exception:
        pass

    try:
        await ws_manager.broadcast({"type": "jobs", "data": {"purge_cancelled": {"removed_jobs": removed_jobs, "removed_events": removed_events}}})
    except Exception:
        pass

    return {
        "ok": True,
        "removed_jobs": removed_jobs,
        "removed_events": removed_events,
        "by": str(req.by or "human")[:80],
        "note": str(req.note or "")[:2000],
        "older_than_seconds": older,
        "limit": limit,
    }


@app.post("/jobs/create")
async def jobs_create(req: JobCreateRequest):
    global _tick
    _tick += 1
    title = (req.title or "").strip()
    body = (req.body or "").strip()
    reward_in = float(req.reward or 0.0)
    if not title or not body or reward_in <= 0:
        return {"error": "invalid_job"}

    # Ratings (optional): clamp into 1..10
    ratings: dict = {}
    if isinstance(req.ratings, dict):
        for k, v in req.ratings.items():
            try:
                kk = str(k)[:40]
                iv = int(float(v))
                if iv < 1:
                    iv = 1
                if iv > 10:
                    iv = 10
                ratings[kk] = iv
            except Exception:
                continue

    # Duplicate prevention: reject near-identical tasks compared to recent jobs.
    fp = _fingerprint(title, body)
    toks = _tokenize(title + "\n" + body)
    created_by = str(req.created_by or "human")[:80]
    source = "agent" if created_by.startswith("agent_") else ("system" if created_by.startswith("system:") else "human")

    # Allow intentional repeats for specific recurring agent tasks (e.g., periodic market scans).
    # This is intentionally narrow to avoid disabling dedupe generally.
    text_l = (title.lower() + "\n" + body.lower())
    allow_repeat = ("[repeat_ok:1]" in text_l) and ("archetype:market_scan" in text_l) and (created_by == "agent_1")

    # Safety: ensure agent-created jobs are tagged with the current run id so the executor will pick them up.
    # (Some jobs created via conversation flow historically missed the run tag and became "invisible" to executor.)
    try:
        if source == "agent" and _run_id:
            tag = f"[run:{_run_id}]"
            if (tag not in title) and (tag not in body) and ("[run:" not in title.lower()) and ("[run:" not in body.lower()):
                title = f"{tag} {title}".strip()
    except Exception:
        pass
    if not allow_repeat:
        recent = sorted(list(_jobs.values()), key=lambda j: float(j.created_at or 0.0), reverse=True)[:200]
        for jj in recent:
            try:
                # Prefer dedup within same creator OR within run-tagged tasks.
                if created_by and jj.created_by and (jj.created_by == created_by):
                    pass
                else:
                    # If creator differs, only dedupe run-tagged jobs (prevents cross-user surprises).
                    if "[run:" not in (title.lower() + body.lower()):
                        continue
                    if "[run:" not in ((jj.title or "").lower() + (jj.body or "").lower()):
                        continue
                fp2 = str(getattr(jj, "fingerprint", "") or "")
                if fp2 and fp2 == fp:
                    return {"error": "duplicate_job", "duplicate_of": jj.job_id, "reason": "fingerprint_match"}
                t2 = _tokenize((jj.title or "") + "\n" + (jj.body or ""))
                sim = _jaccard(toks, t2)
                if sim >= 0.92:
                    return {"error": "duplicate_job", "duplicate_of": jj.job_id, "reason": f"similarity:{sim:.2f}"}
            except Exception:
                continue

    # Auto-reward scaling (opt-in). Only apply for non-agent creators to avoid gaming.
    auto_reward = bool(req.auto_reward)
    reward_mode = "manual"
    reward_calc: dict = {}
    reward = reward_in
    if auto_reward and (not str(created_by).startswith("agent_")) and ratings:
        reward, reward_calc = _calc_reward_from_ratings(ratings)
        reward_mode = "auto_ratings"

    # Validate parent_job_id if provided
    parent_job_id = str(req.parent_job_id or "").strip()
    if parent_job_id:
        parent_job = _jobs.get(parent_job_id)
        if not parent_job:
            return {"error": "parent_job_not_found", "parent_job_id": parent_job_id}
        # Parent must be approved for sub-task to be claimable
        # (We allow creating sub-tasks even if parent isn't approved yet, but they won't be claimable)
    
    job_id = str(uuid.uuid4())
    ev = _append_job_event(
        "create",
        job_id,
        {
            "title": title,
            "body": body,
            "reward": reward,
            "created_by": created_by,
            "parent_job_id": parent_job_id,
            "created_at": time.time(),
            "fingerprint": fp,
            "ratings": ratings,
            "reward_mode": reward_mode,
            "reward_calc": reward_calc,
            "source": source,
        },
    )
    
    # Auto-update opportunity status: if this is a deliver_opportunity job, mark the opportunity as "selected"
    try:
        if "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
            # Extract opportunity title from job title (format: "Deliver: {title}")
            opp_title_match = re.search(r"deliver:\s*(.+?)(?:\s*\[|$)", title, re.IGNORECASE)
            if opp_title_match:
                opp_title = opp_title_match.group(1).strip()
                # Try to find matching opportunity by title
                for opp in _opportunities.values():
                    if opp_title.lower() in opp.title.lower() or opp.title.lower() in opp_title.lower():
                        if opp.status == "new":
                            opp.status = "selected"
                            opp.last_seen_at = time.time()
                            if job_id not in opp.job_ids:
                                opp.job_ids.append(job_id)
                            _save_opportunities()
                            break
    except Exception:
        pass
    
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})
    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/jobs/{job_id}/claim")
async def jobs_claim(job_id: str, req: JobClaimRequest):
    global _tick
    _tick += 1
    j = _jobs.get(job_id)
    if not j:
        return {"error": "job_not_found"}
    
    # Check current status - handle race conditions
    if j.status != "open":
        if j.status == "claimed":
            # Already claimed - return info about who claimed it (for competition visibility)
            return {
                "error": "already_claimed",
                "claimed_by": j.claimed_by,
                "claimed_at": j.claimed_at,
                "job": asdict(j)
            }
        return {"error": "not_claimable", "status": j.status}
    
    # Check if this is a sub-task and parent is approved
    parent_id = getattr(j, "parent_job_id", "") or ""
    if parent_id:
        parent = _jobs.get(parent_id)
        if not parent:
            return {"error": "parent_job_not_found", "parent_job_id": parent_id}
        if parent.status != "approved":
            return {"error": "parent_not_approved", "parent_job_id": parent_id, "parent_status": parent.status}
    
    ensure_account(req.agent_id)
    
    # Create claim event - _apply_job_event will handle race conditions atomically
    ev = _append_job_event("claim", job_id, {"agent_id": req.agent_id, "created_at": time.time()})
    
    # Check if claim succeeded (race condition check)
    j2 = _jobs.get(job_id)
    if not j2 or j2.status != "claimed" or j2.claimed_by != req.agent_id:
        # Race condition: someone else claimed it first
        if j2 and j2.status == "claimed":
            return {
                "error": "race_condition_claim_failed",
                "claimed_by": j2.claimed_by,
                "claimed_at": j2.claimed_at,
                "job": asdict(j2)
            }
        return {"error": "claim_failed"}
    
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(j2)}})
    return {"ok": True, "job": asdict(j2)}


@app.post("/jobs/{job_id}/submit")
async def jobs_submit(job_id: str, req: JobSubmitRequest):
    global _tick
    _tick += 1
    j = _jobs.get(job_id)
    if not j or j.status not in ("open", "claimed"):
        return {"error": "not_submittable"}
    if j.claimed_by and j.claimed_by != req.agent_id:
        return {"error": "not_owner"}
    sub = (req.submission or "").strip()
    if not sub:
        return {"error": "invalid_submission"}
    ev = _append_job_event("submit", job_id, {"agent_id": req.agent_id, "submission": sub, "created_at": time.time()})
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})

    # Auto-verify certain task templates and auto-approve on success.
    # Skip auto_verify when [verifier:proposer_review] or [reviewer:creator]: proposer (e.g. agent1) will review.
    j2 = _jobs.get(job_id)
    proposer_review = False
    if j2 and j2.status == "submitted":
        hay = ((j2.title or "") + "\n" + (j2.body or "")).lower()
        if "[verifier:proposer_review]" in hay or "[reviewer:creator]" in hay:
            proposer_review = True
    if not proposer_review:
        try:
            j2 = _jobs.get(job_id)
            if j2 and j2.status == "submitted":
                out = _auto_verify_task(j2, sub)
                # Record the verifier result for UI / auditing (include artifacts).
                if out.matched:
                    _append_job_event(
                        "verify",
                        job_id,
                        {"ok": bool(out.ok), "note": out.note, "verifier": out.verifier, "artifacts": out.artifacts, "created_at": time.time()},
                    )
                if out.matched and out.ok:
                    review_req = JobReviewRequest(approved=True, reviewed_by="system:auto_verify", note=out.note, payout=0.0, penalty=None)
                    await jobs_review(job_id, review_req)
                elif out.matched and (not out.ok):
                    # If we had a verifier and it failed, auto-reject and penalize the submitter.
                    if out.note.startswith("auto_verify failed"):
                        review_req = JobReviewRequest(
                            approved=False,
                            reviewed_by="system:auto_verify",
                            note=out.note,
                            payout=0.0,
                            penalty=max(0.0, TASK_FAIL_PENALTY),
                        )
                        await jobs_review(job_id, review_req)
        except Exception as e:
            import logging
            logging.exception("auto_verify in submit failed: %s", e)

    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/jobs/{job_id}/review")
async def jobs_review(job_id: str, req: JobReviewRequest):
    """Human reviews a submission; if approved, auto-award ai$."""
    global _tick
    _tick += 1
    j = _jobs.get(job_id)
    if not j or j.status != "submitted":
        return {"error": "not_reviewable"}
    ev = _append_job_event(
        "review",
        job_id,
        {
            "approved": bool(req.approved),
            "reviewed_by": req.reviewed_by,
            "note": req.note,
            "payout": req.payout,
            "penalty": req.penalty,
            "created_at": time.time(),
        },
    )
    j2 = _jobs[job_id]
    if j2.submitted_by:
        if j2.status == "approved":
            payout = float(req.payout) if (req.payout is not None) else float(j2.reward)
            payout = max(0.0, min(payout, float(j2.reward)))
            if payout > 0:
                award_req = AwardRequest(
                    to_id=j2.submitted_by,
                    amount=payout,
                    reason=f"job approved: {j2.title}",
                    by=f"human:{req.reviewed_by}",
                )
                await economy_award(award_req)
            
            # Auto-update opportunity outcome: if this is a deliver_opportunity job, mark as "success"
            try:
                title = str(j2.title or "")
                if "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
                    # Extract opportunity title from job title
                    opp_title_match = re.search(r"deliver:\s*(.+?)(?:\s*\[|$)", title, re.IGNORECASE)
                    if opp_title_match:
                        opp_title = opp_title_match.group(1).strip()
                        # Find matching opportunity
                        for opp in _opportunities.values():
                            if opp_title.lower() in opp.title.lower() or opp.title.lower() in opp_title.lower():
                                # Check if this job is linked to this opportunity
                                if job_id in opp.job_ids:
                                    opp.status = "done"
                                    opp.outcome = "success"
                                    # Estimate actual revenue from job reward or estimated price
                                    try:
                                        reward = float(j2.reward or 0.0)
                                        if reward > 0:
                                            # Use job reward as proxy for revenue (in ai$)
                                            # Convert to USD estimate: 1 ai$ ≈ $0.10 (adjustable)
                                            opp.actual_revenue_usd = reward * 0.10
                                        else:
                                            # Fall back to estimated price if no reward
                                            price_str = str(opp.estimated_price_usd or "").strip()
                                            nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
                                            if nums:
                                                opp.actual_revenue_usd = max(nums) * 0.1  # Assume 10% conversion
                                    except Exception:
                                        pass
                                    _recalculate_opportunity_success_score(opp)
                                    
                                    # Auto-create follow-up sub-tasks for multi-step deliverables
                                    try:
                                        submission = str(j2.submission or "")
                                        # Look for delivery plan steps in submission
                                        # Format: "## Delivery Plan" or "## Steps" or numbered list
                                        plan_match = re.search(r"##\s*(?:Delivery\s*Plan|Steps|Implementation\s*Plan)\s*\n\n(.*?)(?:\n\n##|$)", submission, re.DOTALL | re.IGNORECASE)
                                        if plan_match:
                                            plan_text = plan_match.group(1)
                                            # Extract numbered or bulleted steps
                                            steps = []
                                            for line in plan_text.split("\n"):
                                                line = line.strip()
                                                # Match numbered steps (1., 2., etc.) or bullets (-, *)
                                                step_match = re.match(r"^(?:\d+\.|[-*])\s*(.+)$", line)
                                                if step_match:
                                                    step_text = step_match.group(1).strip()
                                                    if len(step_text) > 10:  # Only meaningful steps
                                                        steps.append(step_text)
                                            
                                            # Create sub-tasks for first 3-5 steps (to avoid overwhelming)
                                            if steps and len(steps) > 1:
                                                created_by = str(j2.created_by or "agent_1")
                                                for i, step in enumerate(steps[:5]):  # Max 5 sub-tasks
                                                    sub_title = f"[archetype:deliver_step] Step {i+1}: {step[:100]}"
                                                    sub_body = (
                                                        f"This is a follow-up task for the approved deliver_opportunity job {job_id}.\n\n"
                                                        f"**Parent Job**: {job_id} - {j2.title[:150]}\n\n"
                                                        f"**Step**: {step}\n\n"
                                                        f"**Context**: Complete this step as part of the multi-step delivery plan.\n\n"
                                                        f"Acceptance criteria:\n"
                                                        f"- Complete the step: {step[:200]}\n"
                                                        f"- Provide evidence of completion\n"
                                                        f"- Link to parent job artifacts if applicable\n\n"
                                                        f"Evidence required in submission:\n"
                                                        f"- Evidence section with step_completed=true\n"
                                                        f"- Description of what was done\n"
                                                    )
                                                    
                                                    # Create sub-task job
                                                    sub_req = JobCreateRequest(
                                                        title=sub_title,
                                                        body=sub_body,
                                                        reward=float(j2.reward or 0.0) * 0.3,  # 30% of parent reward
                                                        created_by=created_by,
                                                        parent_job_id=job_id,
                                                    )
                                                    try:
                                                        sub_result = await jobs_create(sub_req)
                                                        if isinstance(sub_result, dict) and "job" in sub_result:
                                                            sub_job_id = sub_result["job"].get("job_id")
                                                            if sub_job_id:
                                                                # Link sub-task to opportunity
                                                                if sub_job_id not in opp.job_ids:
                                                                    opp.job_ids.append(sub_job_id)
                                                    except Exception:
                                                        pass  # Don't fail parent approval if sub-task creation fails
                                                
                                                if steps:
                                                    _save_opportunities()
                                    except Exception:
                                        pass  # Don't fail parent approval if sub-task creation fails
                                    
                                    # Store successful patterns if client was interested
                                    if opp.client_response == "interested":
                                        try:
                                            submission = str(j2.submission or "")
                                            
                                            # Extract and store successful email pattern
                                            email_match = re.search(r"## Client Outreach Email\s*\n\n(.*?)(?:\n\n##|$)", submission, re.DOTALL)
                                            if email_match:
                                                email_content = email_match.group(1).strip()
                                                if email_content:
                                                    if "Successful email pattern:" not in opp.notes:
                                                        opp.notes = f"Successful email pattern: {email_content[:500]}\n\n{opp.notes}".strip()
                                            
                                            # Extract and store deliverable type that worked
                                            deliverable_types = []
                                            if "Sample Code Deliverable" in submission or "code_deliverable" in submission.lower():
                                                deliverable_types.append("code")
                                            if "delivery plan" in submission.lower():
                                                deliverable_types.append("plan")
                                            if "package tiers" in submission.lower():
                                                deliverable_types.append("pricing")
                                            
                                            if deliverable_types:
                                                if "Successful deliverable types:" not in opp.notes:
                                                    opp.notes = f"Successful deliverable types: {', '.join(deliverable_types)}\n\n{opp.notes}".strip()
                                        except Exception:
                                            pass
                                    
                                    opp.last_seen_at = time.time()
                                    _save_opportunities()
                                    break
            except Exception:
                pass

            # Task-mode: on approval, award +1 ai$ to BOTH proposer and executor (if distinct agents).
            try:
                proposer = str(j2.created_by or "").strip()
                executor = str(j2.submitted_by or "").strip()
                if proposer and executor and proposer.startswith("agent_") and executor.startswith("agent_") and proposer != executor:
                    await economy_award(AwardRequest(to_id=proposer, amount=1.0, reason=f"task verified (job {job_id})", by=f"{req.reviewed_by}"))
                    await economy_award(AwardRequest(to_id=executor, amount=1.0, reason=f"task verified (job {job_id})", by=f"{req.reviewed_by}"))
            except Exception:
                pass

        if req.penalty is not None:
            pen = float(req.penalty)
            if pen > 0:
                pen_req = PenaltyRequest(
                    agent_id=j2.submitted_by,
                    amount=pen,
                    reason=f"job review penalty: {j2.title}",
                    by=f"human:{req.reviewed_by}",
                )
                await economy_penalty(pen_req)
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})

    # Cross-run persistence: ingest approved market_scan results into Opportunity Library.
    try:
        j3 = _jobs.get(job_id)
        if j3 and j3.status == "approved":
            txt = (str(j3.title or "") + "\n" + str(j3.body or "")).lower()
            if "archetype:market_scan" in txt:
                sub = str(j3.submission or "")
                code = _extract_code_fence(sub, "json") or _extract_code_fence(sub, "javascript")
                if code:
                    obj = json.loads(code)
                    if isinstance(obj, list):
                        changed = 0
                        for it in obj[:200]:
                            o = _upsert_opportunity(it, _run_id, job_id)
                            if o is not None:
                                changed += 1
                        if changed:
                            _save_opportunities()
    except Exception:
        pass

    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/jobs/{job_id}/verify")
async def jobs_verify(job_id: str, req: JobVerifyRequest, request: Request):
    """
    Admin/manual verification trigger:
    - runs verifier on current submission
    - records a 'verify' job event
    - auto-approves on pass
    - auto-rejects + penalizes on fail (if verifier matched)
    """
    global _tick
    _tick += 1
    if not _require_admin(request):
        return {"error": "unauthorized"}
    j = _jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    if j.status != "submitted":
        return {"error": "not_submitted"}
    # Skip if already verified unless forced
    if (j.auto_verify_ok is not None) and (not req.force):
        return {"ok": True, "job": asdict(j), "note": "already_verified"}

    out = _auto_verify_task(j, j.submission or "")
    if out.matched:
        _append_job_event(
            "verify",
            job_id,
            {"ok": bool(out.ok), "note": out.note, "verifier": out.verifier, "artifacts": out.artifacts, "created_at": time.time()},
        )

    if out.matched and out.ok:
        review_req = JobReviewRequest(approved=True, reviewed_by=req.by or "human", note=out.note, payout=0.0, penalty=None)
        await jobs_review(job_id, review_req)
    elif out.matched and (not out.ok):
        if out.note.startswith("auto_verify failed"):
            review_req = JobReviewRequest(
                approved=False,
                reviewed_by=req.by or "human",
                note=out.note,
                payout=0.0,
                penalty=max(0.0, TASK_FAIL_PENALTY),
            )
            await jobs_review(job_id, review_req)

    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/admin/verify_pending")
async def admin_verify_pending(request: Request):
    """Verify all submitted tasks for the current run (admin-only)."""
    global _tick
    _tick += 1
    if not _require_admin(request):
        return {"error": "unauthorized"}
    tag = f"[run:{_run_id}]"
    submitted = [
        j
        for j in list(_jobs.values())
        if j.status == "submitted" and (tag in (j.title or "") or tag in (j.body or ""))
    ]
    report = {"run_id": _run_id, "submitted": len(submitted), "approved": 0, "rejected": 0, "skipped": 0, "items": []}
    for j in submitted[:200]:
        before = j.status
        try:
            out = await jobs_verify(j.job_id, JobVerifyRequest(by="system:verify_pending", force=False), request)
            jj = _jobs.get(j.job_id)
            st = (jj.status if jj else before) if isinstance(out, dict) else (jj.status if jj else before)
            if st == "approved":
                report["approved"] += 1
            elif st == "rejected":
                report["rejected"] += 1
            else:
                report["skipped"] += 1
            report["items"].append(
                {
                    "job_id": j.job_id,
                    "title": j.title,
                    "status": st,
                    "auto_verify_ok": (jj.auto_verify_ok if jj else None),
                    "auto_verify_note": (jj.auto_verify_note if jj else ""),
                }
            )
        except Exception as e:
            report["items"].append({"job_id": j.job_id, "title": j.title, "status": "error", "error": str(e)[:200]})
    return {"ok": True, "report": report}


class TopicSetRequest(BaseModel):
    topic: str
    by_agent_id: str
    by_agent_name: str
    reason: str = ""


class WSManager:
    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]

    async def broadcast_world(self) -> None:
        snapshot = get_world_snapshot()
        payload = snapshot.model_dump()
        await self.broadcast({"type": "world_state", "data": payload})

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections)
        for ws in conns:
            try:
                await ws.send_json(msg)
            except Exception:
                await self.disconnect(ws)


ws_manager = WSManager()

# ---- Trace stream (thought/action summaries; no raw chain-of-thought) ----

TraceKind = Literal["thought", "action", "error", "status"]


@dataclass
class TraceEvent:
    event_id: str
    agent_id: str
    agent_name: str
    kind: TraceKind
    summary: str
    data: dict
    created_at: float


class TraceEventRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    kind: TraceKind = "action"
    summary: str
    data: dict = Field(default_factory=dict)


class WebFetchRequest(BaseModel):
    agent_id: str = "unknown"
    agent_name: str = ""
    url: str
    # Optional: override defaults (still clamped)
    timeout_seconds: Optional[float] = None
    max_bytes: Optional[int] = None


class WebSearchRequest(BaseModel):
    agent_id: str = "unknown"
    agent_name: str = ""
    query: str
    num: int = 10  # max organic results to return


_trace: List[TraceEvent] = []
_trace_max = 600


def _load_trace() -> None:
    global _trace
    rows = _read_jsonl(TRACE_PATH, limit=_trace_max)
    out: List[TraceEvent] = []
    for r in rows:
        try:
            out.append(
                TraceEvent(
                    event_id=str(r.get("event_id") or uuid.uuid4()),
                    agent_id=str(r.get("agent_id") or ""),
                    agent_name=str(r.get("agent_name") or ""),
                    kind=r.get("kind") or "action",
                    summary=str(r.get("summary") or ""),
                    data=dict(r.get("data") or {}),
                    created_at=float(r.get("created_at") or time.time()),
                )
            )
        except Exception:
            continue
    _trace = out[-_trace_max:]


_load_trace()


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def get_world_snapshot() -> WorldSnapshot:
    elapsed = max(0.0, time.time() - _world_started_at)
    sim_minutes_total = int(elapsed * SIM_MINUTES_PER_REAL_SECOND)
    day = sim_minutes_total // (24 * 60)
    minute_of_day = sim_minutes_total % (24 * 60)
    agents_list = []
    for a in _agents.values():
        agents_list.append(
            {
                "agent_id": a.agent_id,
                "display_name": a.display_name,
                "x": a.x,
                "y": a.y,
                "last_seen_at": a.last_seen_at,
            }
        )
    return WorldSnapshot(
        world_size=WORLD_SIZE,
        tick=_tick,
        day=day,
        minute_of_day=minute_of_day,
        landmarks=_landmarks,
        agents=agents_list,
    )


@app.get("/health")
def health():
    return {"ok": True, "world_size": WORLD_SIZE, "agents": len(_agents)}


@app.get("/world", response_model=WorldSnapshot)
def world():
    return get_world_snapshot()

@app.get("/board/posts")
def list_posts(status: Optional[PostStatus] = None, tag: Optional[str] = None, limit: int = 50):
    posts = list(_board_posts.values())
    if status:
        posts = [p for p in posts if p.status == status]
    if tag:
        posts = [p for p in posts if tag in p.tags]
    posts.sort(key=lambda p: p.created_at, reverse=True)
    posts = posts[: max(1, min(limit, 200))]
    return {"posts": [asdict(p) for p in posts]}


@app.get("/chat/recent")
def chat_recent(limit: int = 50):
    limit = max(1, min(limit, 200))
    msgs = _chat[-limit:]
    return {"messages": [asdict(m) for m in msgs]}


# Backwards-compatible alias (some clients call this "history").
@app.get("/chat/history")
def chat_history(limit: int = 50):
    return chat_recent(limit=limit)


@app.post("/trace/event")
async def trace_event(req: TraceEventRequest):
    global _tick
    _tick += 1
    now = time.time()
    ev = TraceEvent(
        event_id=str(uuid.uuid4()),
        agent_id=req.agent_id,
        agent_name=req.agent_name or req.agent_id,
        kind=req.kind,
        summary=(req.summary or "").strip()[:400],
        data=req.data or {},
        created_at=now,
    )
    _trace.append(ev)
    if len(_trace) > _trace_max:
        del _trace[: len(_trace) - _trace_max]
    _append_jsonl(TRACE_PATH, asdict(ev))
    await ws_manager.broadcast({"type": "trace", "data": asdict(ev)})
    return {"ok": True, "event": asdict(ev)}


@app.get("/trace/recent")
def trace_recent(limit: int = 50):
    limit = max(1, min(limit, 300))
    return {"events": [asdict(e) for e in _trace[-limit:]]}


@app.post("/tools/web_fetch")
async def tools_web_fetch(req: WebFetchRequest, request: Request):
    """
    Tool Gateway: fetch a public web page for agent use (research/citations).

    Guardrails:
    - disabled unless WEB_FETCH_ENABLED=1 (or ADMIN_TOKEN unset + enable flag still required)
    - SSRF protection (no localhost/private IPs)
    - optional domain allowlist (WEB_FETCH_ALLOWLIST)
    - size/time caps
    - logs tool use to trace
    """
    global _tick
    _tick += 1
    if not WEB_FETCH_ENABLED:
        return {"error": "web_fetch_disabled"}

    url = str(req.url or "").strip()
    ok, why = _is_allowed_web_url(url)
    if not ok:
        _emit_trace(req.agent_id, req.agent_name, "status", "tool:web_fetch blocked", {"url": url[:500], "reason": why})
        return {"error": "blocked", "reason": why}

    timeout = float(req.timeout_seconds or WEB_FETCH_TIMEOUT_SECONDS)
    timeout = max(2.0, min(30.0, timeout))
    max_bytes = int(req.max_bytes or WEB_FETCH_MAX_BYTES)
    max_bytes = max(10_000, min(1_000_000, max_bytes))

    # Some sites return 403 to unknown/robotic user agents. Use a common browser UA to reduce false blocks.
    # (We still keep SSRF protection + allowlist.)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Language": "en-US,en;q=0.9",
        # Avoid compressed responses unless we explicitly implement decompression.
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    _emit_trace(req.agent_id, req.agent_name, "action", "tool:web_fetch start", {"url": url[:500], "timeout": timeout, "max_bytes": max_bytes})
    try:
        r = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            final_url = str(getattr(resp, "geturl", lambda: url)() or url)[:1000]
            ct = str(resp.headers.get("content-type") or "")[:200]
            raw = resp.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            if truncated:
                raw = raw[:max_bytes]
            # best-effort decode
            text = raw.decode("utf-8", errors="replace")
            sha = hashlib.sha1(raw).hexdigest()[:16]
            out = {
                "ok": True,
                "url": url,
                "final_url": final_url,
                "content_type": ct,
                "bytes": len(raw),
                "truncated": bool(truncated),
                "sha1_16": sha,
                "text": text,
            }
            _emit_trace(req.agent_id, req.agent_name, "action", "tool:web_fetch ok", {"url": url[:500], "final_url": final_url[:500], "bytes": len(raw), "truncated": bool(truncated), "sha1_16": sha, "content_type": ct})
            return out
    except Exception as e:
        _emit_trace(req.agent_id, req.agent_name, "error", "tool:web_fetch error", {"url": url[:500], "error": str(e)[:300]})
        return {"error": "fetch_failed", "detail": str(e)[:300]}


@app.post("/tools/web_search")
async def tools_web_search(req: WebSearchRequest, request: Request):
    """
    Tool Gateway: web search via Serper API (for agents: discover Fiverr gigs, research, etc.).

    Guardrails:
    - disabled unless WEB_SEARCH_ENABLED=1 and SERPER_API_KEY is set
    - logs tool use to trace
    """
    global _tick
    _tick += 1
    if not WEB_SEARCH_ENABLED or not SERPER_API_KEY:
        _emit_trace(req.agent_id, req.agent_name, "status", "tool:web_search disabled", {"reason": "WEB_SEARCH_ENABLED or SERPER_API_KEY missing"})
        return {"error": "web_search_disabled", "results": []}

    query = (req.query or "").strip()[:500]
    if not query:
        return {"error": "empty_query", "results": []}
    num = max(1, min(int(req.num or 10), 20))

    _emit_trace(req.agent_id, req.agent_name, "action", "tool:web_search start", {"query": query[:200], "num": num})
    try:
        body = json.dumps({"q": query, "num": num}).encode("utf-8")
        request_obj = urllib.request.Request(
            SERPER_SEARCH_URL,
            data=body,
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request_obj, timeout=15) as resp:
            raw = resp.read(512 * 1024)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        organic = data.get("organic") or []
        results = []
        for i, item in enumerate(organic[:num]):
            if not isinstance(item, dict):
                continue
            results.append({
                "title": str(item.get("title") or "")[:400],
                "snippet": str(item.get("snippet") or "")[:800],
                "url": str(item.get("link") or "")[:2000],
            })
        _emit_trace(req.agent_id, req.agent_name, "action", "tool:web_search ok", {"query": query[:200], "count": len(results)})
        return {"ok": True, "results": results}
    except Exception as e:
        _emit_trace(req.agent_id, req.agent_name, "error", "tool:web_search error", {"query": query[:200], "error": str(e)[:300]})
        return {"error": "search_failed", "detail": str(e)[:300], "results": []}


@app.get("/chat/topic")
def chat_topic():
    return {"topic": _topic, "set_at": _topic_set_at, "history": _topic_history[-20:]}


@app.post("/chat/topic/set")
async def chat_topic_set(req: TopicSetRequest):
    global _tick, _topic, _topic_set_at
    _tick += 1
    now = time.time()
    t = req.topic.strip()
    if not t:
        return {"error": "invalid_topic"}
    _topic = t[:140]
    _topic_set_at = now
    _topic_history.append(
        {
            "topic": _topic,
            "by_agent_id": req.by_agent_id,
            "by_agent_name": req.by_agent_name,
            "reason": (req.reason or "").strip()[:400],
            "created_at": now,
        }
    )
    # Notify UI + agents
    await ws_manager.broadcast({"type": "topic", "data": {"topic": _topic, "set_at": _topic_set_at}})
    return {"ok": True, "topic": _topic, "set_at": _topic_set_at}


@app.post("/chat/send")
async def chat_send(req: ChatSendRequest):
    global _tick
    _tick += 1
    now = time.time()
    msg = ChatMessage(
        msg_id=str(uuid.uuid4()),
        sender_type=req.sender_type,
        sender_id=req.sender_id,
        sender_name=req.sender_name,
        text=req.text.strip(),
        created_at=now,
    )
    _chat.append(msg)
    if len(_chat) > _chat_max:
        del _chat[: len(_chat) - _chat_max]
    _append_jsonl(CHAT_PATH, asdict(msg))
    await ws_manager.broadcast({"type": "chat", "data": asdict(msg)})
    return {"ok": True, "message": asdict(msg)}


@app.get("/audit/recent")
def audit_recent(limit: int = 100):
    limit = max(1, min(limit, 500))
    return {"events": [asdict(e) for e in _audit[-limit:]]}


class NewRunRequest(BaseModel):
    """
    Starts a new run:
    - rotates/truncates audit/chat/trace logs into /app/data/runs/<run_id>/
    - resets in-memory world state and clock
    """
    run_id: str = ""
    reset_board: bool = True
    reset_topic: bool = True


@app.post("/admin/new_run")
async def admin_new_run(req: NewRunRequest, request: Request):
    global _tick, _agents, _world_started_at, _chat, _trace, _audit, _topic, _topic_set_at, _topic_history, _board_posts, _board_replies
    global _jobs, _job_events, _economy_ledger, _balances
    global _run_id, _run_started_at
    if not _require_admin(request):
        return {"error": "unauthorized"}

    # Archive the *current* run into its own directory, then start a fresh run_id.
    archived_run_id = _run_id
    archived_started_at = _run_started_at
    archived_info = _rotate_logs(
        archived_run_id,
        [
            AUDIT_PATH,
            TRACE_PATH,
            CHAT_PATH,
            JOBS_PATH,
            ECONOMY_PATH,
            EVENTS_PATH,
        ],
    )
    # Update meta.json with run boundaries.
    try:
        meta_p = RUNS_DIR / archived_run_id / "meta.json"
        meta = {}
        if meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8", errors="replace") or "{}")
        meta.update({"run_id": archived_run_id, "started_at": archived_started_at, "ended_at": time.time()})
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Reset in-memory state (agents will re-upsert)
    _tick = 0
    _agents = {}
    _world_started_at = time.time()
    _chat = []
    _trace = []
    _audit = []
    _jobs = {}
    _job_events = []
    _economy_ledger = []
    _balances = {}

    new_run_id = (req.run_id or "").strip() or time.strftime("%Y%m%d-%H%M%S")
    _run_id = new_run_id
    _run_started_at = time.time()

    if req.reset_topic:
        _topic = "getting started"
        _topic_set_at = 0.0
        _topic_history = []

    if req.reset_board:
        _board_posts = {}
        _board_replies = {}

    return {
        "ok": True,
        "run_id": _run_id,
        "started_at": _run_started_at,
        "archived": {"run_id": archived_run_id, "started_at": archived_started_at, **archived_info},
    }


@app.get("/economy/balances")
def economy_balances():
    # Ensure all known agents have accounts (so UI doesn't show missing)
    for aid in list(_agents.keys()):
        ensure_account(aid)
    return {"balances": _balances, "starting": STARTING_AIDOLLARS}


@app.get("/economy/balance/{agent_id}")
def economy_balance(agent_id: str):
    ensure_account(agent_id)
    return {"agent_id": agent_id, "balance": float(_balances.get(agent_id, 0.0))}


@app.get("/economy/ledger")
def economy_ledger(agent_id: Optional[str] = None, limit: int = 100):
    limit = max(1, min(limit, 500))
    rows = _economy_ledger
    if agent_id:
        rows = [e for e in rows if e.from_id == agent_id or e.to_id == agent_id]
    return {"entries": [asdict(e) for e in rows[-limit:]]}


@app.post("/economy/transfer")
async def economy_transfer(req: TransferRequest):
    global _tick
    _tick += 1
    if req.from_id == req.to_id:
        return {"error": "invalid_transfer"}
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    ensure_account(req.from_id)
    ensure_account(req.to_id)
    if float(_balances.get(req.from_id, 0.0)) < amount:
        return {"error": "insufficient_funds"}
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="transfer",
        amount=amount,
        from_id=req.from_id,
        to_id=req.to_id,
        memo=(req.memo or "").strip()[:400],
        created_at=now,
    )
    _economy_ledger.append(entry)
    _append_jsonl(ECONOMY_PATH, asdict(entry))
    _recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": _balances}})
    return {"ok": True, "entry": asdict(entry), "balances": _balances}


@app.post("/economy/award")
async def economy_award(req: AwardRequest):
    """Admin/human/system awards ai$ to an agent. (No auth yet; Milestone 0.)"""
    global _tick
    _tick += 1
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    ensure_account(req.to_id)
    ensure_account(TREASURY_ID)
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="award",
        amount=amount,
        from_id=TREASURY_ID,
        to_id=req.to_id,
        memo=(req.reason or "").strip()[:400],
        created_at=now,
    )
    _economy_ledger.append(entry)
    _append_jsonl(ECONOMY_PATH, asdict(entry))
    _recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": _balances}})
    return {"ok": True, "entry": asdict(entry), "balances": _balances}


# ---- PayPal Sandbox Integration ----

class PayPalWebhookRequest(BaseModel):
    """PayPal webhook payload (simplified for sandbox)"""
    event_type: str
    resource: dict
    id: str = ""
    create_time: str = ""


@app.post("/paypal/webhook")
async def paypal_webhook(request: Request):
    """
    PayPal webhook endpoint for payment notifications.
    In sandbox mode, accepts simplified webhook payloads.
    Converts USD payments to ai$ and credits the agent.
    """
    global _tick
    _tick += 1
    
    if not PAYPAL_ENABLED:
        return {"error": "paypal_disabled"}
    
    try:
        body = await request.json()
    except Exception:
        return {"error": "invalid_json"}
    
    # Extract webhook data
    event_type = str(body.get("event_type") or "").lower()
    resource = body.get("resource") or {}
    
    # Handle payment completion events
    if event_type in ("payment.capture.completed", "payment.sale.completed"):
        try:
            # Extract payment details
            amount_dict = resource.get("amount") or {}
            currency = str(amount_dict.get("currency_code") or "USD").upper()
            total_str = str(amount_dict.get("total") or "0.0")
            
            if currency != "USD":
                return {"error": "unsupported_currency", "currency": currency}
            
            usd_amount = float(total_str)
            if usd_amount <= 0:
                return {"error": "invalid_amount"}
            
            # Convert USD to ai$
            ai_dollar_amount = usd_amount * PAYPAL_USD_TO_AIDOLLAR
            
            # Extract agent ID from payment metadata or custom field
            # In sandbox, we'll use a custom field or invoice_id to identify the agent
            agent_id = ""
            custom = str(resource.get("custom") or resource.get("invoice_id") or "")
            if custom.startswith("agent_"):
                agent_id = custom
            else:
                # Try to extract from description or note
                description = str(resource.get("description") or resource.get("note") or "")
                match = re.search(r"agent[_\s]*(\d+)", description, re.IGNORECASE)
                if match:
                    agent_id = f"agent_{match.group(1)}"
            
            if not agent_id:
                # Default: credit to a special "paypal_revenue" account that can be distributed later
                agent_id = "paypal_revenue"
            
            # Credit ai$ to agent
            ensure_account(agent_id)
            ensure_account(TREASURY_ID)
            
            now = time.time()
            payment_id = str(resource.get("id") or body.get("id") or uuid.uuid4())
            
            entry = EconomyEntry(
                entry_id=str(uuid.uuid4()),
                entry_type="paypal_payment",
                amount=ai_dollar_amount,
                from_id=TREASURY_ID,
                to_id=agent_id,
                memo=f"PayPal payment: ${usd_amount:.2f} USD → {ai_dollar_amount:.2f} ai$ (payment_id={payment_id})",
                created_at=now,
            )
            _economy_ledger.append(entry)
            _append_jsonl(ECONOMY_PATH, asdict(entry))
            _recompute_balances()
            
            # Update opportunity revenue if linked
            try:
                # Try to find matching opportunity by payment description or invoice
                description = str(resource.get("description") or resource.get("note") or "")
                opp_title_match = re.search(r"opportunity[:\s]+(.+?)(?:\s|$)", description, re.IGNORECASE)
                if opp_title_match:
                    opp_title = opp_title_match.group(1).strip()
                    for opp in _opportunities.values():
                        if opp_title.lower() in opp.title.lower() or opp.title.lower() in opp_title.lower():
                            opp.actual_revenue_usd = usd_amount
                            opp.outcome = "success"
                            opp.status = "done"
                            _recalculate_opportunity_success_score(opp)
                            _save_opportunities()
                            break
            except Exception:
                pass
            
            await ws_manager.broadcast({"type": "balances", "data": {"balances": _balances}})
            await ws_manager.broadcast({"type": "paypal_payment", "data": {
                "agent_id": agent_id,
                "usd_amount": usd_amount,
                "ai_dollar_amount": ai_dollar_amount,
                "payment_id": payment_id,
            }})
            
            return {"ok": True, "credited": ai_dollar_amount, "agent_id": agent_id, "usd_amount": usd_amount}
        except Exception as e:
            return {"error": "processing_failed", "message": str(e)[:200]}
    
    # Acknowledge other event types
    return {"ok": True, "event_type": event_type, "processed": False}


@app.get("/paypal/status")
def paypal_status():
    """Check PayPal integration status"""
    return {
        "enabled": PAYPAL_ENABLED,
        "mode": PAYPAL_MODE,
        "client_id_set": bool(PAYPAL_CLIENT_ID),
        "client_secret_set": bool(PAYPAL_CLIENT_SECRET),
        "webhook_id_set": bool(PAYPAL_WEBHOOK_ID),
        "conversion_rate": PAYPAL_USD_TO_AIDOLLAR,
        "webhook_url": "/paypal/webhook",
    }


@app.post("/economy/penalty")
async def economy_penalty(req: PenaltyRequest):
    """Penalize an agent by moving ai$ into the treasury. (No auth yet; Milestone 0.)"""
    global _tick
    _tick += 1
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    ensure_account(req.agent_id)
    ensure_account(TREASURY_ID)
    available = float(_balances.get(req.agent_id, 0.0))
    if available <= 0:
        return {"error": "insufficient_funds"}
    if amount > available:
        amount = available
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="spend",
        amount=amount,
        from_id=req.agent_id,
        to_id=TREASURY_ID,
        memo=(f"penalty by {req.by}: {req.reason}" if req.reason else f"penalty by {req.by}").strip()[:400],
        created_at=now,
    )
    _economy_ledger.append(entry)
    _append_jsonl(ECONOMY_PATH, asdict(entry))
    _recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": _balances}})
    return {"ok": True, "entry": asdict(entry), "balances": _balances}


@app.get("/board/posts/{post_id}")
def get_post(post_id: str):
    post = _board_posts.get(post_id)
    if not post:
        return {"error": "not_found", "post_id": post_id}
    replies = _board_replies.get(post_id, [])
    return {"post": asdict(post), "replies": [asdict(r) for r in replies]}


@app.post("/board/posts")
async def create_post(req: CreatePostRequest):
    global _tick
    _tick += 1
    now = time.time()
    post_id = str(uuid.uuid4())
    author_id = req.author_id or (req.author_type == "agent" and req.author_id) or "unknown"
    post = BoardPost(
        post_id=post_id,
        author_type=req.author_type,
        author_id=author_id,
        audience=req.audience,
        title=req.title.strip()[:200],
        body=req.body.strip(),
        tags=req.tags[:20],
        status="open",
        created_at=now,
        updated_at=now,
    )
    _board_posts[post_id] = post
    _board_replies.setdefault(post_id, [])
    # For M2 we piggyback on world broadcast; a dedicated /ws/board can come later.
    await ws_manager.broadcast_world()
    return {"ok": True, "post": asdict(post)}


@app.post("/board/posts/{post_id}/replies")
async def create_reply(post_id: str, req: CreateReplyRequest):
    global _tick
    _tick += 1
    now = time.time()
    post = _board_posts.get(post_id)
    if not post:
        return {"error": "not_found", "post_id": post_id}
    reply = BoardReply(
        reply_id=str(uuid.uuid4()),
        post_id=post_id,
        author_type=req.author_type,
        author_id=req.author_id or "human",
        body=req.body.strip(),
        created_at=now,
    )
    _board_replies.setdefault(post_id, []).append(reply)
    post.updated_at = now
    _board_posts[post_id] = post
    await ws_manager.broadcast_world()
    return {"ok": True, "reply": asdict(reply)}


@app.post("/agents/upsert")
async def upsert_agent(req: UpsertAgentRequest):
    global _tick
    _tick += 1
    now = time.time()
    if req.agent_id not in _agents:
        _agents[req.agent_id] = AgentState(
            agent_id=req.agent_id,
            display_name=req.display_name or req.agent_id,
            x=0,
            y=0,
            last_seen_at=now,
        )
        ensure_account(req.agent_id)
    else:
        a = _agents[req.agent_id]
        if req.display_name:
            a.display_name = req.display_name
        a.last_seen_at = now

    await ws_manager.broadcast_world()
    return {"ok": True, "agent": asdict(_agents[req.agent_id])}


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    a = _agents.get(agent_id)
    if not a:
        return {"error": "not_found", "agent_id": agent_id}
    return {"agent": asdict(a)}


@app.post("/agents/{agent_id}/move")
async def move_agent(agent_id: str, req: MoveRequest):
    global _tick
    _tick += 1
    now = time.time()
    a = _agents.get(agent_id)
    if not a:
        a = AgentState(agent_id=agent_id, display_name=agent_id, x=0, y=0, last_seen_at=now)
        _agents[agent_id] = a

    # Relative move
    if req.dx is not None or req.dy is not None:
        dx = req.dx or 0
        dy = req.dy or 0
        a.x = clamp(a.x + dx, 0, WORLD_SIZE - 1)
        a.y = clamp(a.y + dy, 0, WORLD_SIZE - 1)
    # Absolute move
    elif req.x is not None and req.y is not None:
        a.x = clamp(req.x, 0, WORLD_SIZE - 1)
        a.y = clamp(req.y, 0, WORLD_SIZE - 1)

    a.last_seen_at = now
    await ws_manager.broadcast_world()
    return {"ok": True, "agent_id": a.agent_id, "x": a.x, "y": a.y}


@app.websocket("/ws/world")
async def ws_world(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        # send initial snapshot
        await ws.send_json({"type": "world_state", "data": get_world_snapshot().model_dump()})
        while True:
            # Keep alive; we don't require client messages in v1
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:
        await ws_manager.disconnect(ws)

