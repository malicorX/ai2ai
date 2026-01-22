from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import uuid
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Literal, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse


WORLD_SIZE = 32
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ECONOMY_PATH = DATA_DIR / "economy_ledger.jsonl"
JOBS_PATH = DATA_DIR / "jobs_events.jsonl"
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

STARTING_AIDOLLARS = float(os.getenv("STARTING_AIDOLLARS", "100"))
TREASURY_ID = os.getenv("TREASURY_ID", "treasury")


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


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")

# In-memory state (Milestone 1). Persistence comes later.
_tick = 0
_agents: Dict[str, AgentState] = {}
_landmarks = [
    {"id": "board", "x": 10, "y": 8, "type": "bulletin_board"},
    {"id": "cafe", "x": 6, "y": 6, "type": "cafe"},
    {"id": "market", "x": 20, "y": 12, "type": "market"},
    {"id": "computer", "x": 16, "y": 16, "type": "computer_access"},
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

_topic: str = "getting started"
_topic_set_at: float = 0.0
_topic_history: List[dict] = []

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
    created_at: float


class MemoryAppendRequest(BaseModel):
    kind: MemoryKind = "note"
    text: str
    tags: List[str] = Field(default_factory=list)


def _memory_path(agent_id: str) -> Path:
    safe = "".join([c for c in agent_id if c.isalnum() or c in ("-", "_")]) or "agent"
    return MEMORY_DIR / f"{safe}.jsonl"


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
        created_at=now,
    )
    _append_jsonl(_memory_path(agent_id), asdict(entry))
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


JobEventType = Literal["create", "claim", "submit", "review", "cancel"]


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


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def get_world_snapshot() -> WorldSnapshot:
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
    await ws_manager.broadcast({"type": "chat", "data": asdict(msg)})
    return {"ok": True, "message": asdict(msg)}


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

