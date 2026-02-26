"""
Authentication and authorization helpers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import Request

from app.config import ADMIN_TOKEN, AGENT_TOKENS_PATH

_cached_agent_tokens: Optional[dict] = None
_cached_agent_tokens_mtime: float = 0.0


def _load_agent_tokens() -> dict:
    global _cached_agent_tokens, _cached_agent_tokens_mtime
    if not AGENT_TOKENS_PATH:
        return {}
    try:
        p = Path(AGENT_TOKENS_PATH)
        if not p.exists():
            return {}
        mtime = p.stat().st_mtime
        if _cached_agent_tokens is not None and mtime == _cached_agent_tokens_mtime:
            return _cached_agent_tokens
        data = json.loads(p.read_text(encoding="utf-8", errors="replace") or "{}")
        if isinstance(data, dict):
            _cached_agent_tokens = {str(k): str(v) for k, v in data.items()}
            _cached_agent_tokens_mtime = mtime
            return _cached_agent_tokens
    except Exception:
        pass
    return {}


def load_agent_tokens() -> dict:
    return _load_agent_tokens()


def require_admin(request: Request) -> bool:
    if not ADMIN_TOKEN:
        return True
    auth = (request.headers.get("authorization") or "").strip()
    return auth == f"Bearer {ADMIN_TOKEN}"


def agent_from_auth(request: Request) -> Optional[str]:
    """
    Map Authorization: Bearer <token> to agent_id.
    Returns None if no token auth configured, "" if auth fails, agent_id if ok.
    """
    tokens = _load_agent_tokens()
    if not tokens:
        return None
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.startswith("Bearer "):
        return ""
    token = auth.split(" ", 1)[1].strip()
    return tokens.get(token, "")


def is_agent_route_allowed(request: Request) -> bool:
    path = str(request.url.path or "").rstrip("/") or "/"
    method = str(request.method or "").upper()
    allowed_exact = {
        ("GET", "/world"),
        ("GET", "/world/events"),
        ("POST", "/world/actions"),
        ("POST", "/chat/say"),
        ("POST", "/chat/shout"),
        ("GET", "/chat/inbox"),
        ("POST", "/world/agent/request_token"),
        ("POST", "/world/agent/register"),
    }
    if (method, path) in allowed_exact:
        return True
    if method not in ("GET", "POST"):
        return False
    allowed_prefixes = (
        "/agents/",
        "/chat/",
        "/run",
        "/jobs",
        "/events",
        "/memory/",
        "/economy/",
        "/tools/",
        "/artifacts/",
        "/opportunities",
        "/trace/",
    )
    return any(path.startswith(p) for p in allowed_prefixes)


def is_public_route(request: Request) -> bool:
    path = str(request.url.path or "").rstrip("/") or "/"
    method = str(request.method or "").upper()
    if path.startswith("/ui"):
        return True
    if (method, path) in {
        ("GET", "/health"),
        ("POST", "/world/agent/request_token"),
        ("POST", "/world/agent/register"),
    }:
        return True
    if method == "GET":
        if path == "/world" or path == "/world/events":
            return True
        if path == "/run" or path == "/runs":
            return True
        if path.startswith("/runs/") and "/summary" in path or path.startswith("/runs/") and path.endswith("/viewer"):
            return True
        if path == "/board/posts" or path.startswith("/board/posts/"):
            return True
        if path == "/trace/recent":
            return True
        if path == "/opportunities" or path == "/opportunities/library" or path == "/opportunities/metrics":
            return True
        if path == "/chat/topic" or path == "/chat/recent" or path == "/chat/history":
            return True
        if path == "/economy/balances":
            return True
        if path == "/rules":
            return True
    return False
