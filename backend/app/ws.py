"""
WebSocket manager for broadcasting world state, chat, and other events.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import WebSocket


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

    async def broadcast_world(self, snapshot_fn=None) -> None:
        if snapshot_fn is not None:
            snapshot = snapshot_fn()
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
