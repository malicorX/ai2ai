"""Routes: world state, agents, movement, health, rules."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Request

from app import state
from app.auth import agent_from_auth
from app.config import WORLD_SIZE
from app.models import (
    MoveRequest, UpsertAgentRequest, WorldActionRequest,
    AgentState, ChatBroadcastRequest, WorldSnapshot,
)
from app.utils import clamp

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True, "world_size": WORLD_SIZE, "agents": len(state.agents)}


@router.get("/world", response_model=WorldSnapshot)
def world():
    return state.get_world_snapshot()


@router.get("/rules")
def rules():
    return {"rules": state.get_rules_text(), "for_agents": "Check these rules to know what earns or costs ai$."}


@router.post("/agents/upsert")
async def upsert_agent(req: UpsertAgentRequest, request: Request):
    state.tick += 1
    now = time.time()
    agent_from_token = agent_from_auth(request)
    if agent_from_token == "":
        return {"error": "unauthorized"}
    if agent_from_token and agent_from_token != req.agent_id:
        return {"error": "unauthorized_agent", "agent_id": req.agent_id}
    if req.agent_id not in state.agents:
        state.agents[req.agent_id] = AgentState(
            agent_id=req.agent_id,
            display_name=req.display_name or req.agent_id,
            x=0, y=0, last_seen_at=now,
        )
        state.ensure_account(req.agent_id)
    else:
        a = state.agents[req.agent_id]
        if req.display_name:
            a.display_name = req.display_name
        a.last_seen_at = now
    state.save_agents(force=True)
    from app.ws import ws_manager
    await ws_manager.broadcast_world(state.get_world_snapshot)
    return {"ok": True, "agent": asdict(state.agents[req.agent_id])}


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    a = state.agents.get(agent_id)
    if not a:
        return {"error": "not_found", "agent_id": agent_id}
    return {"agent": asdict(a)}


@router.post("/agents/{agent_id}/move")
async def move_agent(agent_id: str, req: MoveRequest, request: Request):
    state.tick += 1
    now = time.time()
    agent_from_token = agent_from_auth(request)
    if agent_from_token == "":
        return {"error": "unauthorized"}
    if agent_from_token and agent_from_token != agent_id:
        return {"error": "unauthorized_agent", "agent_id": agent_id}
    a = state.agents.get(agent_id)
    if not a:
        a = AgentState(agent_id=agent_id, display_name=agent_id, x=0, y=0, last_seen_at=now)
        state.agents[agent_id] = a
        state.save_agents(force=True)
    if req.dx is not None or req.dy is not None:
        dx = req.dx or 0
        dy = req.dy or 0
        a.x = clamp(a.x + dx, 0, WORLD_SIZE - 1)
        a.y = clamp(a.y + dy, 0, WORLD_SIZE - 1)
    elif req.x is not None and req.y is not None:
        a.x = clamp(req.x, 0, WORLD_SIZE - 1)
        a.y = clamp(req.y, 0, WORLD_SIZE - 1)
    a.last_seen_at = now
    state.save_agents()
    from app.ws import ws_manager
    await ws_manager.broadcast_world(state.get_world_snapshot)
    earned = await state.award_action_diversity(agent_id, "move")
    out = {"ok": True, "agent_id": a.agent_id, "x": a.x, "y": a.y}
    if earned is not None:
        out["earned_diversity"] = earned
    return out


@router.post("/world/actions")
async def world_actions(req: WorldActionRequest, request: Request):
    if not req.agent_id:
        return {"error": "missing_agent_id"}
    agent_from_token = agent_from_auth(request)
    if agent_from_token == "":
        return {"error": "unauthorized"}
    if agent_from_token:
        req.agent_id = agent_from_token
    display_name = (req.agent_name or req.agent_id).strip()
    await upsert_agent(UpsertAgentRequest(agent_id=req.agent_id, display_name=display_name), request)
    action = (req.action or "").strip().lower()
    params = req.params or {}
    if action == "move":
        move_req = MoveRequest(dx=params.get("dx"), dy=params.get("dy"), x=params.get("x"), y=params.get("y"))
        return await move_agent(req.agent_id, move_req, request)
    if action == "say":
        text = str(params.get("text") or "").strip()
        if not text:
            return {"error": "missing_text"}
        from app.routes.chat import chat_say
        return await chat_say(ChatBroadcastRequest(sender_id=req.agent_id, sender_name=display_name, text=text))
    if action == "shout":
        text = str(params.get("text") or "").strip()
        if not text:
            return {"error": "missing_text"}
        from app.routes.chat import chat_shout
        return await chat_shout(ChatBroadcastRequest(sender_id=req.agent_id, sender_name=display_name, text=text))
    return {"error": "unknown_action", "action": action}
