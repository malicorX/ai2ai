"""Routes: board posts and replies."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter

from app import state
from app.models import (
    BoardPost, BoardReply, CreatePostRequest, CreateReplyRequest, PostStatus,
)
from app.ws import ws_manager

router = APIRouter()


@router.get("/board/posts")
def list_posts(status: Optional[PostStatus] = None, tag: Optional[str] = None, limit: int = 50):
    posts = list(state.board_posts.values())
    if status:
        posts = [p for p in posts if p.status == status]
    if tag:
        posts = [p for p in posts if tag in p.tags]
    posts.sort(key=lambda p: p.created_at, reverse=True)
    posts = posts[: max(1, min(limit, 200))]
    return {"posts": [asdict(p) for p in posts]}


@router.get("/board/posts/{post_id}")
def get_post(post_id: str):
    post = state.board_posts.get(post_id)
    if not post:
        return {"error": "not_found", "post_id": post_id}
    replies = state.board_replies.get(post_id, [])
    return {"post": asdict(post), "replies": [asdict(r) for r in replies]}


@router.post("/board/posts")
async def create_post(req: CreatePostRequest):
    state.tick += 1
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
    state.board_posts[post_id] = post
    state.board_replies.setdefault(post_id, [])
    await ws_manager.broadcast_world(state.get_world_snapshot)
    earned_div = await state.award_action_diversity(author_id, "board_post")
    earned_fiverr = await state.try_award_fiverr_discovery(author_id, (req.body or "").strip())
    out = {"ok": True, "post": asdict(post)}
    if earned_div is not None:
        out["earned_diversity"] = earned_div
    if earned_fiverr is not None:
        out["earned_fiverr"] = earned_fiverr
    return out


@router.post("/board/posts/{post_id}/replies")
async def create_reply(post_id: str, req: CreateReplyRequest):
    state.tick += 1
    now = time.time()
    post = state.board_posts.get(post_id)
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
    state.board_replies.setdefault(post_id, []).append(reply)
    post.updated_at = now
    state.board_posts[post_id] = post
    await ws_manager.broadcast_world(state.get_world_snapshot)
    return {"ok": True, "reply": asdict(reply)}
