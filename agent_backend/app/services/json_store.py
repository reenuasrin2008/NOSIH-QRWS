"""Atomic local JSON & JSONL persistence for the AI Rescue Agent backend."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

SCHEMA_VERSION = "2.0.0"

_LOCK_GUARD = threading.Lock()
_LOCKS: Dict[str, threading.RLock] = {}


def get_project_root() -> Path:
    env_root = os.environ.get("QUANTUM_RESCUE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[3]


def get_runtime_data_dir() -> Path:
    env_dir = os.environ.get("QUANTUM_RESCUE_DATA_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return get_project_root() / "runtime_data"


def ensure_agent_storage(base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir).resolve() if base_dir else get_runtime_data_dir()
    for sub in ("agent/conversations", "agent/execution_logs", "agent/audit", "agent/memory", "config"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _get_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCK_GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[key] = lk
        return lk


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    with _get_lock(path):
        yield


def write_json_atomic(path: Path | str, data: Any, *, indent: Optional[int] = 2) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=indent, ensure_ascii=False, default=str)
    with file_lock(target):
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(serialized)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, target)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
    return target


def read_json_safe(path: Path | str, default: Any = None) -> Any:
    target = Path(path)
    with file_lock(target):
        if not target.exists():
            return default
        try:
            raw = target.read_text(encoding="utf-8")
            if not raw.strip():
                return default
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError, OSError):
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            try:
                shutil.copy2(target, target.with_name(f"{target.name}.corrupt.{ts}"))
            except OSError:
                pass
            return default


def append_jsonl(path: Path | str, record: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with file_lock(target):
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()


def read_jsonl(path: Path | str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    out: List[Dict[str, Any]] = []
    with file_lock(target):
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                    if isinstance(obj, dict):
                        out.append(obj)
                except json.JSONDecodeError:
                    continue
    if limit is not None and limit > 0:
        return out[-limit:]
    return out
