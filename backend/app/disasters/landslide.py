"""Landslide disaster engine with slope displacement, debris road blockage, and building exposure."""
from __future__ import annotations

from typing import Any, Dict

from app.core.models import CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import (
    apply_structural_damage,
    find_buildings_in_radius,
    find_roads_in_radius,
    load_damage_thresholds,
)


def step_landslide(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Propagate soil/rock displacement across slope corridor, blocking roads and damaging structures."""
    changed = False
    progress = event.elapsed_time / max(event.duration, 1.0)
    if progress < 0.45:
        growth = 1.4 * event.propagation_speed * event.severity * dt
        new_radius = min(event.max_radius, event.affected_radius + growth)
        if abs(new_radius - event.affected_radius) >= 0.5:
            event.affected_radius = round(new_radius, 1)
            changed = True
        event.status = DisasterStatus.PROPAGATING
    elif progress < 0.85:
        event.status = DisasterStatus.STABILIZING
    else:
        event.status = DisasterStatus.CONTAINED

    thresholds = load_damage_thresholds()
    buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)

    b_ids = []
    for b in buildings:
        if not event.metadata.get(f"hit_{b.id}"):
            event.metadata[f"hit_{b.id}"] = True
            apply_structural_damage(b, 0.28 * event.severity, thresholds)
        b_ids.append(b.id)

    r_ids = []
    for r in roads:
        r.obstructed_by_debris = True
        r.blocked = True
        r_ids.append(r.id)

    event.affected_buildings = b_ids
    event.affected_roads = r_ids
    return {"geometry_changed": changed, "affected_buildings": len(b_ids), "affected_roads": len(r_ids)}
