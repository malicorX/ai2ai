from __future__ import annotations

import asyncio
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

