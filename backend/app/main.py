"""
AI Village (MoltWorld) Backend — FastAPI Application

Refactored: 2026-02-15
All config, models, utilities, state, auth, verifiers, and routes live in separate modules.
This file is the app factory: creates the FastAPI app, adds middleware, loads state, mounts routes.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, HTMLResponse, JSONResponse

from app import state
from app.auth import agent_from_auth, is_agent_route_allowed, is_public_route, require_admin
from app.config import ADMIN_TOKEN, BACKEND_VERSION, DATA_DIR
from app.models import AuditEntry
from app.utils import safe_json_preview
from app.ws import ws_manager

_log = logging.getLogger(__name__)

# --- Create FastAPI app ---

app = FastAPI(title="MoltWorld", version=BACKEND_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Audit middleware ---

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    start = time.time()
    body = b""
    try:
        body = await request.body()
    except Exception:
        pass
    response = await call_next(request)
    elapsed_ms = round((time.time() - start) * 1000, 2)
    try:
        entry = AuditEntry(
            audit_id=str(uuid.uuid4()),
            method=str(request.method or ""),
            path=str(request.url.path or ""),
            query=str(request.url.query or ""),
            status_code=int(getattr(response, "status_code", 0)),
            duration_ms=elapsed_ms,
            client=str(request.client.host if request.client else "unknown"),
            content_type=str(request.headers.get("content-type") or ""),
            body_preview=(body[:2000].decode("utf-8", errors="replace") if body else ""),
            body_json=safe_json_preview(body) if body else None,
            created_at=time.time(),
        )
        state.append_audit(entry)
    except Exception:
        pass
    return response


# --- Auth middleware ---

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = str(request.url.path or "").rstrip("/") or "/"
    if path.startswith("/ws") or path.startswith("/ui") or path.startswith("/static"):
        return await call_next(request)
    if is_public_route(request):
        return await call_next(request)
    if path.startswith("/admin"):
        if not require_admin(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
    agent_id = agent_from_auth(request)
    if agent_id is None:
        return await call_next(request)
    if agent_id == "":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if not is_agent_route_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await call_next(request)


# --- Load all state on startup ---

state.load_all()


# --- Register all routes ---

from app.routes import register_routes  # noqa: E402
register_routes(app)


# --- Static files for UI ---

_static_dir = DATA_DIR.parent / "app" / "static"
if not _static_dir.exists():
    from pathlib import Path
    _static_dir = Path(__file__).resolve().parent / "static"

if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/ui")
@app.get("/ui/{rest:path}")
async def ui_redirect(rest: str = ""):
    return RedirectResponse("/static/index.html")


# --- WebSocket endpoint ---

@app.websocket("/ws/world")
async def ws_world(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({"type": "world_state", "data": state.get_world_snapshot().model_dump()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:
        await ws_manager.disconnect(ws)
