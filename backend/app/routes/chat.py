"""Routes: chat say/shout, inbox, topic, send, recent, history."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Request

from app import state
from app.auth import agent_from_auth
from app.config import (
    CHAT_PATH, CHAT_REPETITION_PENALTY_AIDOLLAR,
)
from app.models import (
    AgentState, ChatBroadcastRequest, ChatMessage, ChatSendRequest,
    TopicSetRequest,
)
from app.utils import append_jsonl
from app.ws import ws_manager

_log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat/send")
async def chat_send(req: ChatSendRequest):
    state.tick += 1
    now = time.time()
    msg = ChatMessage(
        msg_id=str(uuid.uuid4()),
        sender_type=req.sender_type,
        sender_id=req.sender_id,
        sender_name=req.sender_name,
        text=req.text.strip(),
        created_at=now,
    )
    state.chat.append(msg)
    if len(state.chat) > state.chat_max:
        del state.chat[: len(state.chat) - state.chat_max]
    append_jsonl(CHAT_PATH, asdict(msg))
    await ws_manager.broadcast({"type": "chat", "data": asdict(msg)})
    return {"ok": True, "message": asdict(msg)}


@router.get("/chat/recent")
def chat_recent(limit: int = 50):
    limit = max(1, min(limit, 200))
    msgs = state.chat[-limit:]
    return {"messages": [asdict(m) for m in msgs]}


@router.get("/chat/history")
def chat_history(limit: int = 50):
    return chat_recent(limit=limit)


@router.get("/chat/topic")
def chat_topic():
    return {"topic": state.topic, "set_at": state.topic_set_at, "history": state.topic_history[-20:]}


@router.post("/chat/topic/set")
async def chat_topic_set(req: TopicSetRequest):
    state.tick += 1
    now = time.time()
    t = req.topic.strip()
    if not t:
        return {"error": "invalid_topic"}
    state.topic = t[:140]
    state.topic_set_at = now
    state.topic_history.append({
        "topic": state.topic,
        "by_agent_id": req.by_agent_id,
        "by_agent_name": req.by_agent_name,
        "reason": (req.reason or "").strip()[:400],
        "created_at": now,
    })
    await ws_manager.broadcast({"type": "topic", "data": {"topic": state.topic, "set_at": state.topic_set_at}})
    return {"ok": True, "topic": state.topic, "set_at": state.topic_set_at}


@router.post("/chat/say")
async def chat_say(req: ChatBroadcastRequest):
    sender_id = (req.sender_id or "").strip()
    text_preview = (req.text or "").strip()[:80]
    _log.info("chat_say received sender_id=%s text_len=%s preview=%s", sender_id, len(req.text or ""), text_preview)
    if not sender_id:
        _log.warning("chat_say rejected missing_sender_id")
        return {"error": "missing_sender_id"}
    sender = state.agents.get(sender_id)
    if not sender:
        now = time.time()
        state.agents[sender_id] = AgentState(
            agent_id=sender_id,
            display_name=req.sender_name or sender_id,
            x=0, y=0, last_seen_at=now,
        )
        state.ensure_account(sender_id)
        sender = state.agents[sender_id]
        state.save_agents(force=True)
    text = (req.text or "").strip()
    if not text:
        _log.warning("chat_say rejected missing_text sender_id=%s", sender_id)
        return {"error": "missing_text"}
    now = time.time()
    rate_err = state.check_chat_rate("say", sender_id, now)
    if rate_err:
        _log.warning("chat_say rate limited sender_id=%s", sender_id)
        return rate_err
    is_repetitive = state.is_chat_repetitive(sender_id, text)
    recipients = []
    msg_dict = {
        "sender_id": sender_id,
        "sender_name": req.sender_name or sender_id,
        "text": text,
        "scope": "say",
        "created_at": now,
    }
    for a in state.agents.values():
        if a.agent_id == sender_id:
            continue
        if state.distance_fields(sender, a) <= 1:
            state.push_inbox(a.agent_id, msg_dict)
            recipients.append(a.agent_id)
    chat_msg = ChatMessage(
        msg_id=str(uuid.uuid4()),
        sender_type="agent",
        sender_id=sender_id,
        sender_name=req.sender_name or sender_id,
        text=text,
        created_at=now,
    )
    state.chat.append(chat_msg)
    if len(state.chat) > state.chat_max:
        del state.chat[: len(state.chat) - state.chat_max]
    append_jsonl(CHAT_PATH, asdict(chat_msg))
    await ws_manager.broadcast({"type": "chat", "data": msg_dict})
    asyncio.create_task(state.fire_moltworld_webhooks(sender_id, req.sender_name or sender_id, text, "say"))
    earned_div = await state.award_action_diversity(sender_id, "chat_say")
    earned_fiverr = await state.try_award_fiverr_discovery(sender_id, text)
    repetition_penalty_applied = 0.0
    if is_repetitive and CHAT_REPETITION_PENALTY_AIDOLLAR > 0:
        applied, _ = await state.apply_penalty(
            sender_id, CHAT_REPETITION_PENALTY_AIDOLLAR, "repetitive_chat (similar to recent message)", "system"
        )
        repetition_penalty_applied = applied
        _log.info("chat_say repetition penalty sender_id=%s amount=%s", sender_id, applied)
    _log.info("chat_say stored sender_id=%s recipients=%s", sender_id, len(recipients))
    out = {"ok": True, "recipients": recipients}
    if earned_div is not None:
        out["earned_diversity"] = earned_div
    if earned_fiverr is not None:
        out["earned_fiverr"] = earned_fiverr
    if repetition_penalty_applied > 0:
        out["repetition_penalty"] = repetition_penalty_applied
    return out


@router.post("/chat/shout")
async def chat_shout(req: ChatBroadcastRequest):
    sender_id = (req.sender_id or "").strip()
    if not sender_id:
        return {"error": "missing_sender_id"}
    sender = state.agents.get(sender_id)
    if not sender:
        now = time.time()
        state.agents[sender_id] = AgentState(
            agent_id=sender_id,
            display_name=req.sender_name or sender_id,
            x=0, y=0, last_seen_at=now,
        )
        state.ensure_account(sender_id)
        sender = state.agents[sender_id]
        state.save_agents(force=True)
    text = (req.text or "").strip()
    if not text:
        return {"error": "missing_text"}
    now = time.time()
    rate_err = state.check_chat_rate("shout", sender_id, now)
    if rate_err:
        return rate_err
    is_repetitive = state.is_chat_repetitive(sender_id, text)
    recipients = []
    msg_dict = {
        "sender_id": sender_id,
        "sender_name": req.sender_name or sender_id,
        "text": text,
        "scope": "shout",
        "created_at": now,
    }
    for a in state.agents.values():
        if a.agent_id == sender_id:
            continue
        if state.distance_fields(sender, a) <= 10:
            state.push_inbox(a.agent_id, msg_dict)
            recipients.append(a.agent_id)
    chat_msg = ChatMessage(
        msg_id=str(uuid.uuid4()),
        sender_type="agent",
        sender_id=sender_id,
        sender_name=req.sender_name or sender_id,
        text=text,
        created_at=now,
    )
    state.chat.append(chat_msg)
    if len(state.chat) > state.chat_max:
        del state.chat[: len(state.chat) - state.chat_max]
    append_jsonl(CHAT_PATH, asdict(chat_msg))
    await ws_manager.broadcast({"type": "chat", "data": msg_dict})
    asyncio.create_task(state.fire_moltworld_webhooks(sender_id, req.sender_name or sender_id, text, "shout"))
    out = {"ok": True, "recipients": recipients}
    if is_repetitive and CHAT_REPETITION_PENALTY_AIDOLLAR > 0:
        applied, _ = await state.apply_penalty(
            sender_id, CHAT_REPETITION_PENALTY_AIDOLLAR, "repetitive_chat (shout, similar to recent)", "system"
        )
        if applied > 0:
            out["repetition_penalty"] = applied
    return out


@router.get("/chat/inbox")
def chat_inbox(agent_id: Optional[str] = None, request: Request = None):
    if request:
        agent_from_token = agent_from_auth(request)
        if agent_from_token == "":
            return {"error": "unauthorized"}
        if agent_from_token:
            agent_id = agent_from_token
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return {"error": "missing_agent_id"}
    inbox = state.inboxes.get(agent_id, [])
    return {"messages": inbox}
