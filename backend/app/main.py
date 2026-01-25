from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import math
import urllib.request
import uuid
import time
import re
import tempfile
import subprocess
import sys
from dataclasses import dataclass, asdict
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

STARTING_AIDOLLARS = float(os.getenv("STARTING_AIDOLLARS", "100"))
TREASURY_ID = os.getenv("TREASURY_ID", "treasury")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
TASK_FAIL_PENALTY = float(os.getenv("TASK_FAIL_PENALTY", "1.0"))

# Run/session id (helps agents reset local state after /admin/new_run without restarting containers)
_run_id: str = time.strftime("%Y%m%d-%H%M%S")
_run_started_at: float = time.time()

EMBEDDINGS_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "").rstrip("/")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "llama3.1:8b")
EMBEDDINGS_TRUNCATE = int(os.getenv("EMBEDDINGS_TRUNCATE", "256"))
EMBEDDINGS_TIMEOUT_SECONDS = float(os.getenv("EMBEDDINGS_TIMEOUT_SECONDS", "30"))


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


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")


@app.get("/run")
def run_info():
    return {"run_id": _run_id, "started_at": _run_started_at}


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
                    "created_at": ca or float(d.get("created_at") or 0.0),
                    "status": "open",
                    "claimed_by": "",
                    "submitted_by": "",
                    "submission": "",
                    "submitted_at": 0.0,
                }
                continue
            j = jobs.get(job_id)
            if not j:
                # Unknown job; initialize a stub so we still show it in summaries.
                j = {"job_id": job_id, "title": "", "body": "", "reward": 0.0, "created_by": "", "created_at": 0.0, "status": "unknown"}
                jobs[job_id] = j
            if t == "claim":
                j["claimed_by"] = str(d.get("agent_id") or "")
                j["status"] = "claimed"
            elif t == "submit":
                j["submitted_by"] = str(d.get("agent_id") or "")
                j["submission"] = str(d.get("submission") or "")
                j["submitted_at"] = ca or float(d.get("created_at") or 0.0)
                j["status"] = "submitted"
            elif t == "verify":
                ok = d.get("ok")
                j["auto_verify_ok"] = ok if isinstance(ok, bool) else None
                j["auto_verify_note"] = str(d.get("note") or "")
                j["auto_verified_at"] = ca or float(d.get("created_at") or 0.0)
            elif t == "review":
                j["status"] = "approved" if bool(d.get("approved")) else "rejected"
                j["reviewed_by"] = str(d.get("reviewed_by") or "")
                j["note"] = str(d.get("note") or "")
            elif t == "cancel":
                j["status"] = "cancelled"
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
        m2 = re.search(
            rf"(?im)^[ \t]*`{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)(?:\r?\n[ \t]*`[ \t]*$|$)",
            text or "",
        )
        if m2:
            return (m2.group(1) or "").strip()

        # Fallback: in some transports (notably Windows PowerShell), backticks can be stripped entirely.
        # Accept a bare language line:
        #   python\n<code...>
        m3 = re.search(rf"(?im)^\s*{re.escape(lang)}\s*$\s*([\s\S]+)$", text or "")
        if m3:
            return (m3.group(1) or "").strip()
        return None
    except Exception:
        return None


def _auto_verify_task(job: Job, submission: str) -> tuple[bool, str]:
    """
    Minimal automatic verifier for a small set of task templates.
    Returns (ok, note).
    """
    title = (job.title or "").lower()
    body = (job.body or "").lower()
    text = (submission or "")

    # Prime task: require python code that prints first 5 primes, one per line.
    if ("prime" in title or "prime" in body) and ("five" in title or "five" in body or "5" in title or "5" in body):
        code = _extract_code_fence(text, "python") or _extract_code_fence(text, "py")
        if not code:
            return (False, "auto_verify failed: missing ```python``` code fence in submission")
        if len(code) > 12000:
            return (False, "auto_verify failed: python code too large")
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                # Run with timeout; no perfect sandbox, but keeps runs short.
                r = subprocess.run(
                    [sys.executable, "-I", str(p)],
                    cwd=td,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if r.returncode != 0:
                    return (False, f"auto_verify failed: script error (code={r.returncode}): {r.stderr.strip()[:300]}")
                out = (r.stdout or "").strip().splitlines()
                out = [ln.strip() for ln in out if ln.strip() != ""]
                expected = ["2", "3", "5", "7", "11"]
                if out[:5] != expected:
                    return (False, f"auto_verify failed: expected first lines {expected}, got {out[:5]}")
                return (True, "auto_verify ok: primes output matches expected 2,3,5,7,11")
        except subprocess.TimeoutExpired:
            return (False, "auto_verify failed: script timeout")
        except Exception as e:
            return (False, f"auto_verify failed: exception {e}")

    # Generic acceptance-criteria heuristic:
    # If the job body contains an "Acceptance criteria:" section with bullet points, require the submission
    # to include an "Evidence" section with a checklist referencing each bullet.
    # This is NOT a proof of correctness, but it prevents pure "I did it" with no artifacts.
    ac_present = False
    try:
        body_lines = (job.body or "").splitlines()
        ac_start = None
        for i, ln in enumerate(body_lines):
            if ln.strip().lower().startswith("acceptance criteria"):
                ac_start = i
                break
        if ac_start is not None:
            bullets = []
            for ln in body_lines[ac_start + 1 : ac_start + 20]:
                s = ln.strip()
                # Accept common bullet markers so agents aren't forced into a single formatting style.
                if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
                    bullets.append(s[2:].strip())
                elif s == "":
                    continue
                elif bullets and not (s.startswith("- ") or s.startswith("* ") or s.startswith("• ")):
                    break
            if bullets:
                ac_present = True
                sub_low = (submission or "").lower()
                if "evidence" not in sub_low:
                    return (False, "auto_verify failed: submission missing an Evidence section for acceptance criteria")
                missing = []
                for b in bullets[:10]:
                    key = b.lower()
                    # very forgiving match: any 10-char substring
                    k = key[: min(24, len(key))]
                    if k and k not in sub_low:
                        missing.append(b[:80])
                if missing:
                    return (False, f"auto_verify failed: missing evidence for acceptance criteria: {missing[:5]}")
    except Exception:
        pass

    # Generic python runnable verifier:
    # For python-flavored jobs, require runnable code in a python fence and ensure it runs successfully.
    # If acceptance criteria bullets exist, the submission must also satisfy the acceptance-criteria heuristic above.
    python_job = ("python" in title) or ("python" in body)
    if python_job:
        code = _extract_code_fence(text, "python") or _extract_code_fence(text, "py")
        if not code:
            return (False, "auto_verify failed: missing python code fence in submission for python job")
        if len(code) > 12000:
            return (False, "auto_verify failed: python code too large")
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run(
                    [sys.executable, "-I", str(p)],
                    cwd=td,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if r.returncode != 0:
                    return (False, f"auto_verify failed: python script error (code={r.returncode}): {r.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            return (False, "auto_verify failed: python script timeout")
        except Exception as e:
            return (False, f"auto_verify failed: python verifier exception {e}")

        # If acceptance criteria were present, we only get here if they passed (no missing evidence).
        if ac_present:
            return (True, "auto_verify ok: python code ran + submission references acceptance criteria")
        return (True, "auto_verify ok: python code ran")

    # If we had acceptance criteria and passed them (no early return), approve.
    if ac_present:
        return (True, "auto_verify ok: submission references all acceptance criteria (heuristic)")

    return (False, "auto_verify skipped: no verifier matched")


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
        # If this is a job-thread, add a small job timeline card first.
        if conv_id.startswith("job:"):
            jid = conv_id.split("job:", 1)[1]
            j = jobs_state.get(jid) or {}
            if j:
                st = str(j.get("status") or "")
                av_note = str(j.get("auto_verify_note") or j.get("note") or "")
                who = f"created_by={j.get('created_by','')} claimed_by={j.get('claimed_by','')} submitted_by={j.get('submitted_by','')}"
                rows.append(
                    "<div class='msg' style='border-color: rgba(122,162,255,0.35);'>"
                    "<div class='msgHeader'><span class='sender'>Job timeline</span>"
                    f"<span class='meta'>{_html.escape(st)} | {_html.escape(who)}</span></div>"
                    f"<div class='msgBody'><strong>{_html.escape(str(j.get('title') or ''))}</strong><br>"
                    f"<span class='meta'>{_html.escape(av_note[:260])}</span></div>"
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

EconomyEntryType = Literal["genesis", "transfer", "award", "spend"]


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
    auto_verify_note: str = ""
    auto_verified_at: float = 0.0


JobEventType = Literal["create", "claim", "submit", "verify", "review", "cancel"]


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


class JobClaimRequest(BaseModel):
    agent_id: str


class JobSubmitRequest(BaseModel):
    agent_id: str
    submission: str


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
            auto_verify_note="",
            auto_verified_at=0.0,
        )
        return

    job = _jobs.get(ev.job_id)
    if not job:
        return

    if t == "claim" and job.status == "open":
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
        job.auto_verify_note = str(d.get("note") or "")[:2000]
        job.auto_verified_at = float(d.get("created_at") or ev.created_at)
        return

    if t == "review" and job.status == "submitted":
        job.reviewed_by = str(d.get("reviewed_by") or "human")[:80]
        job.reviewed_at = float(d.get("created_at") or ev.created_at)
        job.review_note = str(d.get("note") or "")[:2000]
        job.status = "approved" if bool(d.get("approved")) else "rejected"
        return

    if t == "cancel" and job.status in ("open", "claimed", "submitted"):
        job.status = "cancelled"
        return


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


@app.get("/jobs")
def jobs_list(status: Optional[JobStatus] = None, limit: int = 50):
    limit = max(1, min(limit, 200))
    jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j.status == status]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return {"jobs": [asdict(j) for j in jobs[:limit]]}


@app.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    j = _jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    return {"job": asdict(j)}


@app.post("/jobs/create")
async def jobs_create(req: JobCreateRequest):
    global _tick
    _tick += 1
    title = (req.title or "").strip()
    body = (req.body or "").strip()
    reward = float(req.reward or 0.0)
    if not title or not body or reward <= 0:
        return {"error": "invalid_job"}
    job_id = str(uuid.uuid4())
    ev = _append_job_event(
        "create",
        job_id,
        {"title": title, "body": body, "reward": reward, "created_by": req.created_by, "created_at": time.time()},
    )
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})
    return {"ok": True, "job": asdict(_jobs[job_id])}


@app.post("/jobs/{job_id}/claim")
async def jobs_claim(job_id: str, req: JobClaimRequest):
    global _tick
    _tick += 1
    j = _jobs.get(job_id)
    if not j or j.status != "open":
        return {"error": "not_claimable"}
    ensure_account(req.agent_id)
    ev = _append_job_event("claim", job_id, {"agent_id": req.agent_id, "created_at": time.time()})
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(_jobs[job_id])}})
    return {"ok": True, "job": asdict(_jobs[job_id])}


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
    # IMPORTANT: payout should be tied to verification/approval, not to "submission" alone.
    try:
        j2 = _jobs.get(job_id)
        if j2 and j2.status == "submitted":
            ok, note = _auto_verify_task(j2, sub)
            # Record the verifier result for UI / auditing.
            # Skip recording if no verifier matched.
            if not note.startswith("auto_verify skipped"):
                _append_job_event("verify", job_id, {"ok": bool(ok), "note": note, "created_at": time.time()})
            if ok:
                review_req = JobReviewRequest(approved=True, reviewed_by="system:auto_verify", note=note, payout=0.0, penalty=None)
                await jobs_review(job_id, review_req)
            else:
                # If we had a verifier and it failed, auto-reject and penalize the submitter.
                if note.startswith("auto_verify failed"):
                    review_req = JobReviewRequest(
                        approved=False,
                        reviewed_by="system:auto_verify",
                        note=note,
                        payout=0.0,
                        penalty=max(0.0, TASK_FAIL_PENALTY),
                    )
                    await jobs_review(job_id, review_req)
    except Exception:
        pass

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

    ok, note = _auto_verify_task(j, j.submission or "")
    if not note.startswith("auto_verify skipped"):
        _append_job_event("verify", job_id, {"ok": bool(ok), "note": note, "created_at": time.time()})

    if ok:
        review_req = JobReviewRequest(approved=True, reviewed_by=req.by or "human", note=note, payout=0.0, penalty=None)
        await jobs_review(job_id, review_req)
    else:
        if note.startswith("auto_verify failed"):
            review_req = JobReviewRequest(
                approved=False,
                reviewed_by=req.by or "human",
                note=note,
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

