"""Non-blocking JSONL event journals and controlled snapshot manager."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.json_store import (
    SCHEMA_VERSION,
    append_jsonl,
    ensure_runtime_layout,
    read_json_safe,
    read_jsonl,
    write_json_atomic,
)


class EventJournal:
    """Appends meaningful simulation, disaster, drone, and rescue events to JSONL files."""

    def __init__(self, base_dir: Optional[Path | str] = None):
        root = ensure_runtime_layout(Path(base_dir) if base_dir else None)
        self.logs_dir = root / "logs"
        self.snapshots_dir = root / "snapshots"
        self.sim_log = self.logs_dir / "simulation_events.jsonl"
        self.disaster_log = self.logs_dir / "disasters.jsonl"
        self.drone_log = self.logs_dir / "drones.jsonl"
        self.rescue_log = self.logs_dir / "rescue_operations.jsonl"
        self.latest_snapshot_path = self.snapshots_dir / "latest_world.json"

    def record(self, category: str, record: Dict[str, Any]) -> None:
        entry = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        append_jsonl(self.sim_log, entry)
        cat = category.lower()
        if cat in ("disaster", "environment", "hazard"):
            append_jsonl(self.disaster_log, entry)
        elif cat in ("drone", "failure", "replanning"):
            append_jsonl(self.drone_log, entry)
        elif cat in ("task", "rescue", "survivor", "solver"):
            append_jsonl(self.rescue_log, entry)

    def read_events(self, stream: str = "simulation", limit: int = 200) -> List[Dict[str, Any]]:
        mapping = {
            "simulation": self.sim_log,
            "disasters": self.disaster_log,
            "drones": self.drone_log,
            "rescue": self.rescue_log,
        }
        path = mapping.get(stream, self.sim_log)
        return read_jsonl(path, limit=limit)

    def save_world_snapshot(self, snapshot: Dict[str, Any]) -> Path:
        payload = {"schema_version": SCHEMA_VERSION, "saved_at": datetime.now(timezone.utc).isoformat(), **snapshot}
        return write_json_atomic(self.latest_snapshot_path, payload, indent=None, create_backup=True)

    def load_world_snapshot(self) -> Optional[Dict[str, Any]]:
        return read_json_safe(self.latest_snapshot_path, default=None)
