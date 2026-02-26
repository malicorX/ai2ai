"""
Register all route modules with the FastAPI app.
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    from app.routes import (
        world, chat, jobs, economy, memory, board,
        events, opportunities, tools, trace, artifacts, admin,
    )
    app.include_router(world.router)
    app.include_router(chat.router)
    app.include_router(jobs.router)
    app.include_router(economy.router)
    app.include_router(memory.router)
    app.include_router(board.router)
    app.include_router(events.router)
    app.include_router(opportunities.router)
    app.include_router(tools.router)
    app.include_router(trace.router)
    app.include_router(artifacts.router)
    app.include_router(admin.router)
