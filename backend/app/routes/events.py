"""Routes: village events, invites, RSVPs."""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter

from app import state
from app.models import CreateEventRequest, InviteRequest, RsvpRequest
from app.ws import ws_manager

router = APIRouter()


@router.get("/world/events")
def list_events(status: Optional[str] = None, limit: int = 50):
    evs = list(state.events.values())
    if status:
        evs = [e for e in evs if e.status == status]
    evs.sort(key=lambda e: e.created_at, reverse=True)
    limit = max(1, min(limit, 200))
    return {"events": [asdict(e) for e in evs[:limit]]}


@router.get("/events/{event_id}")
def get_event(event_id: str):
    e = state.events.get(event_id)
    if not e:
        return {"error": "not_found"}
    return {"event": asdict(e)}


@router.post("/events/create")
async def create_event(req: CreateEventRequest):
    state.tick += 1
    import uuid
    event_id = str(uuid.uuid4())
    ev = state.append_event_log("create", event_id, {
        "title": req.title,
        "description": req.description,
        "location_id": req.location_id,
        "start_day": req.start_day,
        "start_minute": req.start_minute,
        "duration_min": req.duration_min,
        "created_by": req.created_by,
        "created_at": time.time(),
    })
    await ws_manager.broadcast({"type": "events", "data": {"event": asdict(state.events[event_id])}})
    return {"ok": True, "event": asdict(state.events[event_id])}


@router.post("/events/{event_id}/invite")
async def invite_to_event(event_id: str, req: InviteRequest):
    state.tick += 1
    e = state.events.get(event_id)
    if not e:
        return {"error": "not_found"}
    if e.status != "scheduled":
        return {"error": "not_scheduled"}
    state.append_event_log("invite", event_id, {
        "from_agent_id": req.from_agent_id,
        "to_agent_id": req.to_agent_id,
        "message": req.message,
        "created_at": time.time(),
    })
    await ws_manager.broadcast({"type": "events", "data": {"event": asdict(state.events[event_id])}})
    return {"ok": True, "event": asdict(state.events[event_id])}


@router.post("/events/{event_id}/rsvp")
async def rsvp_event(event_id: str, req: RsvpRequest):
    state.tick += 1
    e = state.events.get(event_id)
    if not e:
        return {"error": "not_found"}
    if e.status != "scheduled":
        return {"error": "not_scheduled"}
    state.append_event_log("rsvp", event_id, {
        "agent_id": req.agent_id,
        "status": req.status,
        "note": req.note,
        "created_at": time.time(),
    })
    await ws_manager.broadcast({"type": "events", "data": {"event": asdict(state.events[event_id])}})
    return {"ok": True, "event": asdict(state.events[event_id])}
