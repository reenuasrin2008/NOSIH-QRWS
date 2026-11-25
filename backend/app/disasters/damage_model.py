"""Configurable structural integrity and road impact damage model."""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from app.core.models import Building, BuildingDamageState, CityEnvironment, RoadSegment
from app.storage.json_store import get_runtime_data_dir, read_json_safe

DEFAULT_DAMAGE_THRESHOLDS: Dict[str, float] = {
    "INTACT": 0.85,
    "MINOR_DAMAGE": 0.65,
    "MODERATE_DAMAGE": 0.40,
    "SEVERE_DAMAGE": 0.15,
    "COLLAPSED": 0.0,
}


def load_damage_thresholds() -> Dict[str, float]:
    cfg = read_json_safe(get_runtime_data_dir() / "config" / "simulation_config.json", default={})
    raw = cfg.get("damage_thresholds") if isinstance(cfg, dict) else None
    if isinstance(raw, dict):
        return {k: float(v) for k, v in raw.items()}
    return dict(DEFAULT_DAMAGE_THRESHOLDS)


def integrity_to_damage_state(integrity: float, thresholds: Dict[str, float] | None = None) -> BuildingDamageState:
    t = thresholds or load_damage_thresholds()
    if integrity >= t.get("INTACT", 0.85):
        return BuildingDamageState.INTACT
    if integrity >= t.get("MINOR_DAMAGE", 0.65):
        return BuildingDamageState.MINOR_DAMAGE
    if integrity >= t.get("MODERATE_DAMAGE", 0.40):
        return BuildingDamageState.MODERATE_DAMAGE
    if integrity >= t.get("SEVERE_DAMAGE", 0.15):
        return BuildingDamageState.SEVERE_DAMAGE
    return BuildingDamageState.COLLAPSED


def apply_structural_damage(building: Building, delta_integrity: float, thresholds: Dict[str, float] | None = None) -> BuildingDamageState:
    """Reduce building integrity and update its damage state."""
    building.integrity = round(max(0.0, min(1.0, building.integrity - max(0.0, delta_integrity))), 3)
    new_state = integrity_to_damage_state(building.integrity, thresholds)
    building.damage_state = new_state
    if new_state == BuildingDamageState.COLLAPSED and building.debris_radius <= 0.0:
        building.debris_radius = round(max(building.width, building.depth) * 0.85 + 14.0, 1)
    return new_state


def point_to_segment_distance(px: float, pz: float, a: Tuple[float, float], b: Tuple[float, float]) -> float:
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    len_sq = dx * dx + dz * dz
    if len_sq <= 1e-6:
        return math.hypot(px - ax, pz - az)
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / len_sq))
    cx, cz = ax + t * dx, az + t * dz
    return math.hypot(px - cx, pz - cz)


def find_buildings_in_radius(city: CityEnvironment, cx: float, cz: float, radius: float) -> List[Building]:
    hits: List[Building] = []
    for b in city.buildings:
        if math.hypot(b.x - cx, b.z - cz) <= radius:
            hits.append(b)
    return hits


def find_roads_in_radius(city: CityEnvironment, cx: float, cz: float, radius: float) -> List[RoadSegment]:
    hits: List[RoadSegment] = []
    for r in city.roads:
        if point_to_segment_distance(cx, cz, r.start, r.end) <= radius:
            hits.append(r)
    return hits
