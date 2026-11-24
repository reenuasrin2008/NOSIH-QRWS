from __future__ import annotations
import asyncio
from typing import Any, Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=2.0)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.discard(ws)
