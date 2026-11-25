"""JSON execution trace logger, audit journal, and live WebSocket event hub."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket

from app.models.execution import ExecutionTrace
from app.services.json_store import append_jsonl, ensure_agent_storage, read_json_safe, read_jsonl, write_json_atomic


class ExecutionLogger:
    """Persists full execution traces and append-only audit logs strictly as JSON/JSONL."""

    def __init__(self, base_dir: Optional[Path] = None):
        root = ensure_agent_storage(base_dir)
        self.exec_dir = root / "agent" / "execution_logs"
        self.audit_path = root / "agent" / "audit" / "audit_events.jsonl"

    def save_execution(self, trace: ExecutionTrace) -> Path:
        path = self.exec_dir / f"{trace.execution_id}.json"
        return write_json_atomic(path, trace.model_dump())

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        path = self.exec_dir / f"{execution_id}.json"
        return read_json_safe(path, default=None)

    def list_executions(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.exec_dir.exists():
            return []
        files = sorted(self.exec_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: List[Dict[str, Any]] = []
        for fp in files[:limit]:
            doc = read_json_safe(fp, default=None)
            if isinstance(doc, dict):
                out.append({
                    "execution_id": doc.get("execution_id"),
                    "session_id": doc.get("session_id"),
                    "user_message": doc.get("user_message", ""),
                    "mode": doc.get("mode"),
                    "provider_used": doc.get("provider_used", ""),
                    "key_alias_used": doc.get("key_alias_used", ""),
                    "status": doc.get("status"),
                    "started_at": doc.get("started_at"),
                    "completed_at": doc.get("completed_at"),
                    "duration_ms": doc.get("duration_ms", 0.0),
                    "tool_count": len(doc.get("tool_records", [])),
                })
        return out

    def append_audit(self, event_type: str, data: Dict[str, Any]) -> None:
        append_jsonl(
            self.audit_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                **data,
            },
        )

    def read_audit(self, limit: int = 200) -> List[Dict[str, Any]]:
        return read_jsonl(self.audit_path, limit=limit)


class AgentEventHub:
    """Broadcasts live tool execution cards, provider status, and alerts to AI Console clients."""

    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self.recent_events: List[Dict[str, Any]] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        msg = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self.recent_events.append(msg)
        if len(self.recent_events) > 200:
            self.recent_events = self.recent_events[-200:]
        dead: List[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)
