"""Dedicated WebSocket observer connecting to ws://127.0.0.1:8000/ws/simulation."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable, Dict, Optional

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore


class SimulationWebSocketClient:
    """Maintains live world snapshot, version tracking, reconnection, and debounced meaningful-event triggers."""

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:8000/ws/simulation",
        on_meaningful_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        debounce_seconds: float = 8.0,
    ):
        self.ws_url = ws_url
        self.on_meaningful_event = on_meaningful_event
        self.debounce_seconds = debounce_seconds

        self.connected: bool = False
        self.last_world_version: int = 0
        self.latest_world_state: Optional[Dict[str, Any]] = None
        self.last_processed_event_id: Optional[str] = None
        self.seen_event_ids: set[str] = set()
        self.reconnect_attempts: int = 0
        self._last_trigger_ts: float = 0.0
        self._stop = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = False
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "ws_url": self.ws_url,
            "last_world_version": self.last_world_version,
            "last_processed_event_id": self.last_processed_event_id,
            "reconnect_attempts": self.reconnect_attempts,
        }

    async def process_raw_message(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        if data.get("type") == "meaningful_event":
            ev_ver = int(data.get("state_version", 0))
            ev_key = f"{data.get('event_type')}:{ev_ver}"
            if ev_key in self.seen_event_ids:
                return
            self.seen_event_ids.add(ev_key)
            self.last_processed_event_id = ev_key
            if ev_ver > self.last_world_version:
                self.last_world_version = ev_ver
            now = time.monotonic()
            if self.on_meaningful_event and (now - self._last_trigger_ts) >= self.debounce_seconds:
                self._last_trigger_ts = now
                asyncio.create_task(self.on_meaningful_event(data))
            return

        bm = data.get("benchmark")
        if isinstance(bm, dict) and isinstance(bm.get("active_state"), dict):
            st = bm["active_state"]
            self.latest_world_state = st
            ver = int(st.get("state_version", 0))
            if ver > self.last_world_version:
                self.last_world_version = ver

    async def _run_loop(self) -> None:
        if websockets is None:
            return
        while not self._stop:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    self.connected = True
                    self.reconnect_attempts = 0
                    async for raw in ws:
                        if self._stop:
                            break
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self.process_raw_message(data)
            except asyncio.CancelledError:
                break
            except Exception:
                self.connected = False
                self.reconnect_attempts += 1
                await asyncio.sleep(min(10.0, 1.5 * self.reconnect_attempts))
        self.connected = False
