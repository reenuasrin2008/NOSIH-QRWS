from __future__ import annotations
import logging
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from app.core.compat import to_dict, utc_now_iso

logger = logging.getLogger(__name__)


class WorldEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp: str = Field(default_factory=utc_now_iso)
    simulation_id: str = "GLOBAL_DISASTER_7NATIONS_001"
    world_version: int = 1
    country_id: Optional[str] = None
    entity_id: Optional[str] = None
    source: str = "simulation_engine"
    category: str = "simulation"
    payload: Dict[str, Any] = Field(default_factory=dict)


class FrontendCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: f"CMD-{uuid.uuid4().hex[:8].upper()}")
    command_type: str
    target_id: Optional[str] = None
    frontend: str = "quantum-world"  # quantum-world | quantum-operations | quantum-jarvis | all
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)
    acknowledged_by: List[str] = Field(default_factory=list)
    status: str = "dispatched"


class AuthoritativeEventBus:
    """Ordered event bus with world_version tracking, deduplication, and Frontend Command Bus."""

    def __init__(self, max_history: int = 5000) -> None:
        self.world_version: int = 1
        self.simulation_id: str = "GLOBAL_DISASTER_7NATIONS_001"
        self._events: Deque[WorldEvent] = deque(maxlen=max(1, max_history))
        self._seen_ids: Set[str] = set()
        self._commands: Deque[FrontendCommand] = deque(maxlen=1000)
        self._connected_frontends: Dict[str, int] = {
            "quantum-world": 0,
            "quantum-operations": 0,
            "quantum-jarvis": 0,
        }
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []

    def register_frontend(self, client_name: str) -> None:
        self._connected_frontends[client_name] = self._connected_frontends.get(client_name, 0) + 1

    def unregister_frontend(self, client_name: str) -> None:
        if client_name in self._connected_frontends:
            self._connected_frontends[client_name] = max(0, self._connected_frontends[client_name] - 1)

    def frontend_status(self) -> Dict[str, Any]:
        return {
            name: {"connected": count > 0, "connections": count}
            for name, count in self._connected_frontends.items()
        }

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def emit(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        country_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        source: str = "simulation_engine",
        category: str = "simulation",
        event_id: Optional[str] = None,
        bump_version: bool = True,
    ) -> WorldEvent:
        eid = event_id or str(uuid.uuid4())
        if eid in self._seen_ids:
            for existing in reversed(self._events):
                if existing.event_id == eid:
                    return existing
        if bump_version:
            self.world_version += 1
        ev = WorldEvent(
            event_id=eid,
            event_type=event_type,
            simulation_id=self.simulation_id,
            world_version=self.world_version,
            country_id=country_id,
            entity_id=entity_id,
            source=source,
            category=category,
            payload=payload or {},
        )
        if self._events.maxlen is not None and len(self._events) >= self._events.maxlen:
            evicted = self._events[0]
            self._seen_ids.discard(evicted.event_id)
        self._seen_ids.add(eid)
        self._events.append(ev)
        msg = {"type": "world_event", "event": to_dict(ev)}
        for cb in list(self._subscribers):
            try:
                cb(msg)
            except Exception as exc:
                logger.warning("EventBus subscriber error: %s", exc)
        return ev

    def dispatch_frontend_command(
        self,
        command_type: str,
        target_id: Optional[str] = None,
        frontend: str = "quantum-world",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> FrontendCommand:
        connected = self._connected_frontends.get(frontend, 0) > 0 if frontend != "all" else any(
            v > 0 for v in self._connected_frontends.values()
        )
        cmd = FrontendCommand(
            command_type=command_type,
            target_id=target_id,
            frontend=frontend,
            parameters=parameters or {},
            status="dispatched" if connected else "queued_frontend_disconnected",
        )
        self._commands.append(cmd)
        self.emit(
            event_type=f"frontend.command.{command_type}",
            payload=to_dict(cmd),
            entity_id=target_id,
            source="frontend_command_bus",
            category="frontend_sync",
            bump_version=False,
        )
        msg = {"type": "frontend_command", "command": to_dict(cmd)}
        for cb in list(self._subscribers):
            try:
                cb(msg)
            except Exception as exc:
                logger.warning("EventBus subscriber error: %s", exc)
        return cmd

    def acknowledge_command(self, command_id: str, frontend: str) -> Optional[FrontendCommand]:
        for cmd in reversed(self._commands):
            if cmd.command_id == command_id:
                if frontend not in cmd.acknowledged_by:
                    cmd.acknowledged_by.append(frontend)
                cmd.status = "acknowledged"
                return cmd
        return None

    def get_events(
        self,
        limit: int = 100,
        category: Optional[str] = None,
        country_id: Optional[str] = None,
        event_type_prefix: Optional[str] = None,
        since_version: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        results: List[Dict[str, Any]] = []
        for ev in reversed(self._events):
            if since_version is not None and ev.world_version <= since_version:
                continue
            if category and ev.category != category:
                continue
            if country_id and ev.country_id != country_id:
                continue
            if event_type_prefix and not ev.event_type.startswith(event_type_prefix):
                continue
            results.append(to_dict(ev))
            if len(results) >= limit:
                break
        return results

    def get_commands(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return [to_dict(c) for c in list(self._commands)[-limit:]]
