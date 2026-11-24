from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperimentRepository:
    """Zero-database local JSON file repository. Generates and stores all records locally on disk."""

    def __init__(self, data_dir: Optional[str] = None):
        base = data_dir or os.getenv("LOCAL_DATA_DIR", "local_data")
        self.base_dir = Path(base)
        self.experiments_dir = self.base_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    def _exp_path(self, run_id: str) -> Path:
        safe_id = "".join(ch for ch in run_id if ch.isalnum() or ch in ("-", "_"))
        return self.experiments_dir / f"{safe_id}.json"

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
    ) -> None:
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "seed": seed,
            "strategy": strategy,
            "status": status,
            "sim_time_s": sim_time_s,
            "score": score,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "replay": replay,
        }
        self._exp_path(run_id).write_text(json.dumps(record, indent=2), encoding="utf-8")

    def list_experiments(self) -> List[Dict[str, Any]]:
        if not self.experiments_dir.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for path in self.experiments_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                rows.append({
                    "run_id": data["run_id"],
                    "scenario_id": data["scenario_id"],
                    "seed": data["seed"],
                    "strategy": data["strategy"],
                    "status": data["status"],
                    "sim_time_s": data["sim_time_s"],
                    "score": data["score"],
                    "created_at": data["created_at"],
                })
            except Exception:
                continue
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:50]

    def get_experiment(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self._exp_path(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_local_world_snapshot(self, snapshot: Dict[str, Any], filename: str = "world_snapshot.json") -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        out = self.base_dir / filename
        out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return str(out)
