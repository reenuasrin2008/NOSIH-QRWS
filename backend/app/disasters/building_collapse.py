"""Building structural collapse engine with debris obstruction and post-collapse hazard."""
from __future__ import annotations

from typing import Any, Dict

from app.core.models import BuildingDamageState, CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import find_buildings_in_radius, find_roads_in_radius


def step_building_collapse(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Mark affected structures collapsed, obstruct adjacent roads with debris, and stabilize."""
    changed = False
    if not event.metadata.get("collapse_applied"):
        event.metadata["collapse_applied"] = True
        buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, max(90.0, event.affected_radius))
        if not buildings and city.buildings:
            nearest = min(city.buildings, key=lambda b: (b.x - event.epicentre.x) ** 2 + (b.z - event.epicentre.z) ** 2)
            buildings = [nearest]
        b_ids = []
        for b in buildings[:max(1, int(round(1 + event.severity * 4)))]:
            b.integrity = 0.0
            b.damage_state = BuildingDamageState.COLLAPSED
            b.debris_radius = round(max(b.width, b.depth) * 0.9 + 18.0, 1)
            b_ids.append(b.id)
        roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, max(90.0, event.affected_radius * 0.9))
        r_ids = []
        for r in roads:
            r.obstructed_by_debris = True
            r.blocked = True
            r_ids.append(r.id)
        event.affected_buildings = b_ids
        event.affected_roads = r_ids
        event.status = DisasterStatus.ACTIVE
        changed = True
    else:
        progress = event.elapsed_time / max(event.duration, 1.0)
        if progress > 0.85:
            event.status = DisasterStatus.CONTAINED
        elif progress > 0.5:
            event.status = DisasterStatus.STABILIZING
    return {"geometry_changed": changed, "affected_buildings": len(event.affected_buildings)}
