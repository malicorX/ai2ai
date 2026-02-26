"""Routes: trace events."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict

from fastapi import APIRouter

from app import state
from app.models import TraceEvent, TraceEventRequest
from app.utils import append_jsonl
from app.config import TRACE_PATH
from app.ws import ws_manager

router = APIRouter()


@router.post("/trace/event")
async def trace_event(req: TraceEventRequest):
    state.tick += 1
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
    state.trace.append(ev)
    if len(state.trace) > state.trace_max:
        del state.trace[: len(state.trace) - state.trace_max]
    append_jsonl(TRACE_PATH, asdict(ev))
    await ws_manager.broadcast({"type": "trace", "data": asdict(ev)})
    return {"ok": True, "event": asdict(ev)}


@router.get("/trace/recent")
def trace_recent(limit: int = 50):
    limit = max(1, min(limit, 300))
    return {"events": [asdict(e) for e in state.trace[-limit:]]}
