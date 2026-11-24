from __future__ import annotations
import json
import logging
import os
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (deque, set, tuple)):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            tmp_path = fp.name
            json.dump(data, fp, indent=2, default=_json_default)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, str(path))
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class ExperimentRepository:
    """Zero-database local JSON file repository. Generates and stores all records locally on disk."""

    def __init__(self, data_dir: Optional[str] = None):
        base = data_dir or os.getenv("LOCAL_DATA_DIR", "local_data")
        self.base_dir = Path(base)
        self.experiments_dir = self.base_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    def _exp_path(self, run_id: str) -> Path:
        safe_id = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in ("-", "_"))
        if not safe_id:
            raise ValueError(f"Invalid experiment run_id: {run_id!r}")
        target = (self.experiments_dir / f"{safe_id}.json").resolve()
        if target.parent != self.experiments_dir.resolve():
            raise ValueError(f"Path traversal blocked for run_id: {run_id!r}")
        return target

    def _safe_snapshot_path(self, filename: str) -> Path:
        raw_name = Path(str(filename)).name
        safe_name = "".join(ch for ch in raw_name if ch.isalnum() or ch in ("-", "_", "."))
        safe_name = safe_name.lstrip(".")
        if not safe_name or ".." in safe_name:
            raise ValueError(f"Invalid snapshot filename: {filename!r}")
        if not safe_name.endswith(".json"):
            safe_name = f"{safe_name}.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        target = (self.base_dir / safe_name).resolve()
        if target.parent != self.base_dir.resolve():
            raise ValueError(f"Path traversal blocked for snapshot filename: {filename!r}")
        return target

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
        _atomic_write_json(self._exp_path(run_id), record)

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
            except Exception as exc:
                logger.warning("Skipping unreadable experiment file %s: %s", path.name, exc)
                continue
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:50]

    def get_experiment(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            path = self._exp_path(run_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupted or unreadable experiment file %s: %s", path.name, exc)
            return None

    def save_local_world_snapshot(self, snapshot: Dict[str, Any], filename: str = "world_snapshot.json") -> str:
        out = self._safe_snapshot_path(filename)
        _atomic_write_json(out, snapshot)
        return str(out)

    def reset_local_snapshots(self) -> int:
        removed = 0
        if not self.base_dir.exists():
            return removed
        for path in self.base_dir.glob("*.json"):
            if path.is_file():
                path.unlink()
                removed += 1
        return removed
