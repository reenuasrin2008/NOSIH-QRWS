"""Wind-coupled fire spread, heat radius, building exposure, smoke direction, and suppression."""
from __future__ import annotations

import math
from typing import Any, Dict

from app.core.models import CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import (
    apply_structural_damage,
    find_buildings_in_radius,
    find_roads_in_radius,
    load_damage_thresholds,
)


def step_fire(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Expand fire based on wind speed and rain suppression, damaging exposed buildings."""
    changed = False
    progress = event.elapsed_time / max(event.duration, 1.0)
    wind_factor = 1.0 + (city.weather.wind_speed_mps / 18.0)
    rain_damping = max(0.25, 1.0 - city.weather.rain_intensity * 0.65)
    event.smoke_direction_deg = city.weather.wind_direction_deg

    if progress < 0.78 and event.status in (DisasterStatus.ACTIVE, DisasterStatus.INTENSIFYING, DisasterStatus.PROPAGATING):
        growth = 1.15 * event.propagation_speed * event.severity * wind_factor * rain_damping * dt
        new_radius = min(event.max_radius, event.affected_radius + growth)
        if abs(new_radius - event.affected_radius) >= 0.5:
            event.affected_radius = round(new_radius, 1)
            changed = True
        event.status = DisasterStatus.PROPAGATING if progress > 0.12 else DisasterStatus.INTENSIFYING
    elif progress < 0.94:
        event.status = DisasterStatus.STABILIZING
    else:
        event.status = DisasterStatus.CONTAINED
        event.affected_radius = round(max(35.0, event.affected_radius - 0.9 * dt), 1)
        changed = True

    thresholds = load_damage_thresholds()
    buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)

    b_ids = []
    for b in buildings:
        b.on_fire = True
        dist = math.hypot(b.x - event.epicentre.x, b.z - event.epicentre.z)
        heat = max(0.15, 1.0 - dist / max(event.affected_radius, 1.0))
        apply_structural_damage(b, 0.0018 * event.severity * heat * dt, thresholds)
        b_ids.append(b.id)

    r_ids = []
    for r in roads:
        r.blocked = True
        r_ids.append(r.id)

    event.affected_buildings = b_ids
    event.affected_roads = r_ids
    return {"geometry_changed": changed, "affected_buildings": len(b_ids), "affected_roads": len(r_ids)}
