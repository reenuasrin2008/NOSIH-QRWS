"""Load disaster scenario presets from runtime_data/config/disaster_presets.json."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.storage.json_store import get_runtime_data_dir, read_json_safe


def load_disaster_presets() -> List[Dict[str, Any]]:
    path = get_runtime_data_dir() / "config" / "disaster_presets.json"
    data = read_json_safe(path, default={"presets": []})
    presets = data.get("presets", []) if isinstance(data, dict) else []
    return presets if isinstance(presets, list) else []


def get_disaster_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    for p in load_disaster_presets():
        if p.get("preset_id") == preset_id:
            return p
    return None
