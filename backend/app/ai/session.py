from __future__ import annotations

from collections import deque
import time
from typing import Any, Dict, Optional

MAX_SESSIONS = 500


class SessionContext:
    """Structured operational context service (tracks active country, hospital, drone, and pending approval)."""

    def __init__(self, default_country: str = "COUNTRY-03") -> None:
        self.active_country_id: str = default_country
        self.active_city_id: Optional[str] = None
        self.active_district_id: Optional[str] = None
        self.selected_hospital_id: Optional[str] = None
        self.selected_drone_id: Optional[str] = None
        self.selected_disaster_id: Optional[str] = None
        self.pending_approval_id: Optional[str] = None
        self.last_seen: float = time.time()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active_country_id": self.active_country_id,
            "active_city_id": self.active_city_id,
            "active_district_id": self.active_district_id,
            "selected_hospital_id": self.selected_hospital_id,
            "selected_drone_id": self.selected_drone_id,
            "selected_disaster_id": self.selected_disaster_id,
            "pending_approval_id": self.pending_approval_id,
        }


def get_or_create_session(
    sessions: Dict[str, SessionContext],
    conversations: Dict[str, deque],
    session_id: str,
    default_country_id: str,
    valid_countries: Dict[str, Any],
    max_sessions: int = MAX_SESSIONS,
) -> SessionContext:
    sid = (session_id or "default").strip() if isinstance(session_id, str) else "default"
    if not sid:
        sid = "default"
    if sid not in sessions:
        if len(sessions) >= max_sessions:
            oldest_sid = min(sessions, key=lambda k: sessions[k].last_seen)
            sessions.pop(oldest_sid, None)
            conversations.pop(oldest_sid, None)
        sessions[sid] = SessionContext(default_country=default_country_id)
    ctx = sessions[sid]
    if ctx.active_country_id not in valid_countries:
        ctx.active_country_id = default_country_id
    ctx.last_seen = time.time()
    return ctx


def evict_stale_sessions(
    sessions: Dict[str, SessionContext],
    conversations: Dict[str, deque],
    max_age_seconds: float = 3600.0,
) -> int:
    now = time.time()
    stale = [sid for sid, ctx in sessions.items() if (now - ctx.last_seen) > max_age_seconds]
    for sid in stale:
        sessions.pop(sid, None)
        conversations.pop(sid, None)
    for sid in list(conversations.keys()):
        if sid not in sessions:
            conversations.pop(sid, None)
    return len(stale)
