"""Atomic, locked, schema-versioned JSON & JSONL local persistence (zero database)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

SCHEMA_VERSION = "2.0.0"

_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: Dict[str, threading.RLock] = {}


def get_project_root() -> Path:
    """Resolve the quantum-rescue repository root directory."""
    env_root = os.environ.get("QUANTUM_RESCUE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # backend/app/storage/json_store.py -> parents[3] == quantum-rescue/
    return Path(__file__).resolve().parents[3]


def get_runtime_data_dir() -> Path:
    env_dir = os.environ.get("QUANTUM_RESCUE_DATA_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return get_project_root() / "runtime_data"


def ensure_runtime_layout(base_dir: Optional[Path] = None) -> Path:
    """Ensure the full runtime_data JSON directory tree exists."""
    root = Path(base_dir).resolve() if base_dir else get_runtime_data_dir()
    subdirs = [
        "config",
        "snapshots",
        "experiments/runs",
        "agent/conversations",
        "agent/execution_logs",
        "agent/audit",
        "agent/memory",
        "logs",
    ]
    for sub in subdirs:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _get_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Thread-safe lock around a target path (plus optional OS advisory lock)."""
    lock = _get_lock(path)
    with lock:
        yield


def _quarantine_corrupt_file(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = path.with_name(f"{path.name}.corrupt.{ts}")
    try:
        shutil.copy2(path, quarantine)
        return quarantine
    except OSError:
        return None


def write_json_atomic(
    path: Path | str,
    data: Any,
    *,
    indent: Optional[int] = 2,
    create_backup: bool = False,
    add_schema_version: bool = False,
) -> Path:
    """Atomically write JSON via temp file in same directory -> flush -> fsync -> os.replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = data
    if add_schema_version and isinstance(data, dict) and "schema_version" not in data:
        payload = {"schema_version": SCHEMA_VERSION, **data}

    serialized = json.dumps(payload, indent=indent, ensure_ascii=False, default=str)

    with file_lock(target):
        if create_backup and target.exists():
            bak = target.with_name(f"{target.name}.bak")
            try:
                shutil.copy2(target, bak)
            except OSError:
                pass

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, target)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise
    return target


def read_json_safe(
    path: Path | str,
    default: Any = None,
    *,
    recover_from_backup: bool = True,
) -> Any:
    """Read JSON safely with corruption quarantine and .bak recovery."""
    target = Path(path)
    with file_lock(target):
        if not target.exists():
            return default
        try:
            raw = target.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("Empty JSON file")
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError, OSError):
            _quarantine_corrupt_file(target)
            bak = target.with_name(f"{target.name}.bak")
            if recover_from_backup and bak.exists():
                try:
                    recovered = json.loads(bak.read_text(encoding="utf-8"))
                    write_json_atomic(target, recovered, create_backup=False)
                    return recovered
                except (json.JSONDecodeError, ValueError, OSError):
                    pass
            return default


def append_jsonl(path: Path | str, record: Dict[str, Any]) -> None:
    """Append a single JSON record as a line to a .jsonl event journal."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with file_lock(target):
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()


def read_jsonl(
    path: Path | str,
    *,
    limit: Optional[int] = None,
    skip_corrupt: bool = True,
) -> List[Dict[str, Any]]:
    """Read JSONL records, recovering gracefully from any partially written/corrupt lines."""
    target = Path(path)
    if not target.exists():
        return []
    records: List[Dict[str, Any]] = []
    with file_lock(target):
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    if not skip_corrupt:
                        raise
    if limit is not None and limit > 0:
        return records[-limit:]
    return records


def recover_jsonl(path: Path | str) -> Dict[str, int]:
    """Strip corrupted lines from a JSONL journal atomically, returning counts."""
    target = Path(path)
    if not target.exists():
        return {"valid": 0, "dropped": 0}
    valid_lines: List[str] = []
    dropped = 0
    with file_lock(target):
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    json.loads(stripped)
                    valid_lines.append(stripped)
                except json.JSONDecodeError:
                    dropped += 1
        if dropped > 0:
            _quarantine_corrupt_file(target)
            fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    for ln in valid_lines:
                        out.write(ln + "\n")
                    out.flush()
                os.replace(tmp_path, target)
            except Exception:
                if tmp_path.exists():
                    tmp_path.unlink()
                raise
    return {"valid": len(valid_lines), "dropped": dropped}


def export_json_bundle(source_dir: Path | str, target_json: Path | str) -> Path:
    """Export all JSON files in a directory into a single portable JSON bundle."""
    src = Path(source_dir)
    bundle: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    if src.exists():
        for fp in sorted(src.glob("*.json")):
            bundle["files"][fp.name] = read_json_safe(fp, default={})
    return write_json_atomic(target_json, bundle, indent=2)


def import_json_bundle(bundle_path: Path | str, target_dir: Path | str) -> List[str]:
    """Import a JSON bundle back into individual JSON files atomically."""
    bundle = read_json_safe(bundle_path, default=None)
    if not isinstance(bundle, dict) or "files" not in bundle:
        raise ValueError("Invalid JSON bundle format")
    dest = Path(target_dir)
    dest.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for name, content in bundle["files"].items():
        safe_name = Path(name).name
        write_json_atomic(dest / safe_name, content, indent=2)
        written.append(safe_name)
    return written
