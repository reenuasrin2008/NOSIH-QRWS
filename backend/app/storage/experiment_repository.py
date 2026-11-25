"""Plain JSON-file experiment repository replacing SQLite completely."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.storage.json_store import (
    SCHEMA_VERSION,
    ensure_runtime_layout,
    file_lock,
    read_json_safe,
    write_json_atomic,
)


class JsonExperimentRepository:
    """Stores experiment index and per-run artifacts strictly as local JSON files."""

    def __init__(self, base_dir: Optional[Path | str] = None):
        root = ensure_runtime_layout(Path(base_dir) if base_dir else None)
        self.experiments_dir = root / "experiments"
        self.runs_dir = self.experiments_dir / "runs"
        self.index_path = self.experiments_dir / "index.json"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            write_json_atomic(
                self.index_path,
                {"schema_version": SCHEMA_VERSION, "updated_at": datetime.now(timezone.utc).isoformat(), "runs": []},
            )

    def _load_index(self) -> Dict[str, Any]:
        data = read_json_safe(self.index_path, default=None)
        if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
            data = {"schema_version": SCHEMA_VERSION, "updated_at": datetime.now(timezone.utc).isoformat(), "runs": []}
        return data

    def save_experiment(
        self,
        run_id: str,
        scenario_id: str,
        seed: int,
        strategy: str,
        status: str,
        sim_time_s: float,
        score: float,
        summary: Dict[str, Any],
        replay: Dict[str, Any],
        *,
        events: Optional[List[Dict[str, Any]]] = None,
        drones: Optional[List[Dict[str, Any]]] = None,
        tasks: Optional[List[Dict[str, Any]]] = None,
        optimizer: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        write_json_atomic(run_dir / "summary.json", summary, create_backup=True, add_schema_version=True)
        write_json_atomic(run_dir / "replay.json", replay, indent=None, create_backup=True, add_schema_version=True)
        write_json_atomic(
            run_dir / "events.json",
            {"schema_version": SCHEMA_VERSION, "run_id": run_id, "events": events if events is not None else replay.get("events", [])},
        )
        write_json_atomic(
            run_dir / "drones.json",
            {"schema_version": SCHEMA_VERSION, "run_id": run_id, "drones": drones or []},
        )
        write_json_atomic(
            run_dir / "tasks.json",
            {"schema_version": SCHEMA_VERSION, "run_id": run_id, "tasks": tasks or []},
        )
        write_json_atomic(
            run_dir / "optimizer.json",
            {"schema_version": SCHEMA_VERSION, "run_id": run_id, "history": optimizer or []},
        )

        entry = {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "seed": seed,
            "strategy": strategy,
            "status": status,
            "sim_time_s": round(float(sim_time_s), 2),
            "score": round(float(score), 2),
            "created_at": created_at,
        }

        with file_lock(self.index_path):
            index = self._load_index()
            runs = [r for r in index["runs"] if r.get("run_id") != run_id]
            runs.insert(0, entry)
            index["runs"] = runs[:200]
            index["updated_at"] = created_at
            write_json_atomic(self.index_path, index, create_backup=True)

        return entry

    def list_experiments(self, limit: int = 50) -> List[Dict[str, Any]]:
        index = self._load_index()
        runs = sorted(index.get("runs", []), key=lambda r: r.get("created_at", ""), reverse=True)
        return runs[:limit]

    def get_experiment(self, run_id: str) -> Optional[Dict[str, Any]]:
        run_dir = self.runs_dir / run_id
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            return None

        summary = read_json_safe(summary_path, default={})
        replay = read_json_safe(run_dir / "replay.json", default={})
        events_doc = read_json_safe(run_dir / "events.json", default={"events": []})
        drones_doc = read_json_safe(run_dir / "drones.json", default={"drones": []})
        tasks_doc = read_json_safe(run_dir / "tasks.json", default={"tasks": []})
        opt_doc = read_json_safe(run_dir / "optimizer.json", default={"history": []})

        meta = next((r for r in self._load_index().get("runs", []) if r.get("run_id") == run_id), {})
        return {
            "run_id": run_id,
            "scenario_id": meta.get("scenario_id", summary.get("scenario_id", "")),
            "seed": meta.get("seed", summary.get("seed", 0)),
            "strategy": meta.get("strategy", summary.get("strategy", "hybrid")),
            "status": meta.get("status", "COMPLETED"),
            "sim_time_s": meta.get("sim_time_s", summary.get("simulation_duration_s", 0.0)),
            "score": meta.get("score", summary.get("metrics", {}).get("score", 0.0)),
            "created_at": meta.get("created_at", summary.get("exported_at", "")),
            "summary": summary,
            "replay": replay,
            "events": events_doc.get("events", []),
            "drones": drones_doc.get("drones", []),
            "tasks": tasks_doc.get("tasks", []),
            "optimizer": opt_doc.get("history", []),
        }


# Backwards-compatible alias so existing imports keep working cleanly
ExperimentRepository = JsonExperimentRepository
