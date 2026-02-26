"""Routes: web_fetch and web_search tool gateways."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import socket
import urllib.parse
import urllib.request

from fastapi import APIRouter, Request

from app import state
from app.config import (
    SERPER_API_KEY, SERPER_SEARCH_URL, WEB_FETCH_ALLOWLIST,
    WEB_FETCH_ENABLED, WEB_FETCH_MAX_BYTES, WEB_FETCH_TIMEOUT_SECONDS,
    WEB_SEARCH_ENABLED,
)
from app.models import WebFetchRequest, WebSearchRequest

_log = logging.getLogger(__name__)
router = APIRouter()


def _is_allowed_web_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "invalid_url"
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, "unsupported_scheme"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "empty_host"

    # Block private/local IPs
    try:
        for info in socket.getaddrinfo(host, None):
            addr_str = info[4][0]
            ip = ipaddress.ip_address(addr_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False, "ssrf_blocked"
    except socket.gaierror:
        return False, "dns_error"

    if WEB_FETCH_ALLOWLIST:
        allowed = False
        for d in WEB_FETCH_ALLOWLIST:
            if host == d or host.endswith("." + d):
                allowed = True
                break
        if not allowed:
            return False, "domain_not_in_allowlist"

    return True, ""


@router.post("/tools/web_fetch")
async def tools_web_fetch(req: WebFetchRequest, request: Request):
    state.tick += 1
    if not WEB_FETCH_ENABLED:
        return {"error": "web_fetch_disabled"}
    url = str(req.url or "").strip()
    ok, why = _is_allowed_web_url(url)
    if not ok:
        state.emit_trace(req.agent_id, req.agent_name, "status", "tool:web_fetch blocked", {"url": url[:500], "reason": why})
        return {"error": "blocked", "reason": why}
    timeout = float(req.timeout_seconds or WEB_FETCH_TIMEOUT_SECONDS)
    timeout = max(2.0, min(30.0, timeout))
    max_bytes = int(req.max_bytes or WEB_FETCH_MAX_BYTES)
    max_bytes = max(10_000, min(1_000_000, max_bytes))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    state.emit_trace(req.agent_id, req.agent_name, "action", "tool:web_fetch start", {"url": url[:500], "timeout": timeout, "max_bytes": max_bytes})
    try:
        r = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            final_url = str(getattr(resp, "geturl", lambda: url)() or url)[:1000]
            ct = str(resp.headers.get("content-type") or "")[:200]
            raw = resp.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            if truncated:
                raw = raw[:max_bytes]
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
            state.emit_trace(req.agent_id, req.agent_name, "action", "tool:web_fetch ok", {"url": url[:500], "final_url": final_url[:500], "bytes": len(raw), "truncated": bool(truncated), "sha1_16": sha, "content_type": ct})
            return out
    except Exception as e:
        state.emit_trace(req.agent_id, req.agent_name, "error", "tool:web_fetch error", {"url": url[:500], "error": str(e)[:300]})
        return {"error": "fetch_failed", "detail": str(e)[:300]}


@router.post("/tools/web_search")
async def tools_web_search(req: WebSearchRequest, request: Request):
    state.tick += 1
    if not WEB_SEARCH_ENABLED or not SERPER_API_KEY:
        state.emit_trace(req.agent_id, req.agent_name, "status", "tool:web_search disabled", {"reason": "WEB_SEARCH_ENABLED or SERPER_API_KEY missing"})
        return {"error": "web_search_disabled", "results": []}
    query = (req.query or "").strip()[:500]
    if not query:
        return {"error": "empty_query", "results": []}
    num = max(1, min(int(req.num or 10), 20))
    state.emit_trace(req.agent_id, req.agent_name, "action", "tool:web_search start", {"query": query[:200], "num": num})
    try:
        body = json.dumps({"q": query, "num": num}).encode("utf-8")
        request_obj = urllib.request.Request(
            SERPER_SEARCH_URL, data=body,
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
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
        state.emit_trace(req.agent_id, req.agent_name, "action", "tool:web_search ok", {"query": query[:200], "count": len(results)})
        return {"ok": True, "results": results}
    except Exception as e:
        state.emit_trace(req.agent_id, req.agent_name, "error", "tool:web_search error", {"query": query[:200], "error": str(e)[:300]})
        return {"error": "search_failed", "detail": str(e)[:300], "results": []}
