"""Plain JSON conversation session memory and context tracking (zero database)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.messages import AgentMode, ChatMessage, ConversationSession, ProviderMode
from app.services.json_store import ensure_agent_storage, read_json_safe, write_json_atomic


class ConversationMemoryStore:
    """Persists conversation sessions and active context strictly in local JSON files."""

    def __init__(self, base_dir: Optional[Path] = None, max_messages: int = 40):
        root = ensure_agent_storage(base_dir)
        self.conv_dir = root / "agent" / "conversations"
        self.current_session_path = root / "agent" / "memory" / "current_session.json"
        self.max_messages = max_messages

    def _session_path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in ("-", "_")) or "SESSION-DEFAULT"
        return self.conv_dir / f"{safe}.json"

    def create_session(
        self,
        session_id: Optional[str] = None,
        mode: AgentMode = AgentMode.ASSISTED,
        provider_preference: ProviderMode = ProviderMode.AUTO,
    ) -> ConversationSession:
        now = datetime.now(timezone.utc).isoformat()
        sid = session_id or f"SESSION-{uuid.uuid4().hex[:8].upper()}"
        sess = ConversationSession(
            session_id=sid,
            created_at=now,
            updated_at=now,
            provider_preference=provider_preference,
            mode=mode,
        )
        self.save_session(sess)
        return sess

    def load_session(self, session_id: Optional[str] = None) -> ConversationSession:
        if not session_id:
            cur = read_json_safe(self.current_session_path, default=None)
            if isinstance(cur, dict) and cur.get("session_id"):
                session_id = cur["session_id"]
        if session_id:
            raw = read_json_safe(self._session_path(session_id), default=None)
            if isinstance(raw, dict):
                try:
                    return ConversationSession.model_validate(raw)
                except Exception:
                    pass
        return self.create_session(session_id=session_id)

    def save_session(self, session: ConversationSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        if len(session.messages) > self.max_messages:
            older = session.messages[:-self.max_messages]
            summary_bits = [
                f"{m.role}: {m.content[:100]}"
                for m in older
                if m.role in ("user", "assistant") and m.content
            ][-8:]
            if summary_bits:
                session.summary = " | ".join(summary_bits)
            session.messages = session.messages[-self.max_messages:]

        write_json_atomic(self._session_path(session.session_id), session.model_dump())
        write_json_atomic(
            self.current_session_path,
            {
                "schema_version": "2.0.0",
                "session_id": session.session_id,
                "updated_at": session.updated_at,
                "mode": session.mode.value,
                "provider_preference": session.provider_preference.value,
                "current_context": session.current_context.model_dump(),
            },
        )

    def list_sessions(self, limit: int = 30) -> List[Dict[str, Any]]:
        if not self.conv_dir.exists():
            return []
        files = sorted(self.conv_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: List[Dict[str, Any]] = []
        for fp in files[:limit]:
            raw = read_json_safe(fp, default=None)
            if isinstance(raw, dict):
                out.append({
                    "session_id": raw.get("session_id"),
                    "created_at": raw.get("created_at"),
                    "updated_at": raw.get("updated_at"),
                    "mode": raw.get("mode"),
                    "provider_preference": raw.get("provider_preference"),
                    "message_count": len(raw.get("messages", [])),
                    "execution_count": len(raw.get("execution_ids", [])),
                })
        return out

    def append_message(self, session: ConversationSession, msg: ChatMessage) -> None:
        if not msg.timestamp:
            msg.timestamp = datetime.now(timezone.utc).isoformat()
        session.messages.append(msg)
        self.save_session(session)
