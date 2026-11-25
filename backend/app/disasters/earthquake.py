"""Seeded earthquake engine with structural integrity degradation, fractures, and collapse cascades."""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List

from app.core.models import BuildingDamageState, CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import (
    apply_structural_damage,
    find_buildings_in_radius,
    find_roads_in_radius,
    load_damage_thresholds,
)


def apply_seismic_shock(
    city: CityEnvironment,
    event: DisasterEvent,
    shock_scale: float = 1.0,
) -> Dict[str, Any]:
    """Apply deterministic seismic damage to buildings and roads within epicentre radius."""
    thresholds = load_damage_thresholds()
    rng = random.Random(event.seed + event.aftershock_count * 997)
    mag = event.magnitude if event.magnitude > 0 else round(5.2 + event.severity * 2.6, 1)
    event.magnitude = mag

    buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)

    newly_collapsed: List[Dict[str, Any]] = []
    b_ids: List[str] = []
    for b in buildings:
        dist = math.hypot(b.x - event.epicentre.x, b.z - event.epicentre.z)
        attenuation = max(0.12, 1.0 - (dist / max(event.affected_radius, 1.0)) ** 1.3)
        prev_state = b.damage_state
        delta = event.severity * shock_scale * attenuation * rng.uniform(0.32, 0.78)
        new_state = apply_structural_damage(b, delta, thresholds)
        b_ids.append(b.id)
        if prev_state != BuildingDamageState.COLLAPSED and new_state == BuildingDamageState.COLLAPSED:
            newly_collapsed.append({
                "building_id": b.id,
                "x": b.x,
                "z": b.z,
                "debris_radius": b.debris_radius,
            })

    r_ids: List[str] = []
    for r in roads:
        r_ids.append(r.id)
        if r.is_bridge or rng.random() < event.severity * 0.55 * shock_scale:
            r.fractured = True
            if event.severity * shock_scale >= 0.55:
                r.blocked = True

    event.affected_buildings = b_ids
    event.affected_roads = r_ids
    return {
        "geometry_changed": bool(newly_collapsed),
        "newly_collapsed": newly_collapsed,
        "affected_buildings": len(b_ids),
        "affected_roads": len(r_ids),
    }


def step_earthquake(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Progress earthquake lifecycle: initial shock, periodic aftershocks, stabilization."""
    result: Dict[str, Any] = {"geometry_changed": False, "newly_collapsed": []}
    if not event.metadata.get("initial_shock_applied"):
        event.metadata["initial_shock_applied"] = True
        result = apply_seismic_shock(city, event, shock_scale=1.0)
        event.status = DisasterStatus.ACTIVE
    else:
        progress = event.elapsed_time / max(event.duration, 1.0)
        if progress > 0.75:
            event.status = DisasterStatus.STABILIZING
        elif progress > 0.92:
            event.status = DisasterStatus.CONTAINED
        # Deterministic scheduled aftershock at 30% and 60% duration for severe quakes
        next_at = event.metadata.get("next_aftershock_t", 120.0)
        if event.severity >= 0.65 and event.elapsed_time >= next_at and event.aftershock_count < 2:
            event.aftershock_count += 1
            event.metadata["next_aftershock_t"] = next_at + 180.0
            result = apply_seismic_shock(city, event, shock_scale=0.45)
            result["aftershock_triggered"] = True
    return result
