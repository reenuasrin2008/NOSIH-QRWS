"""Region-based flood accumulation, river interaction, road flooding, and recession."""
from __future__ import annotations

import math
from typing import Dict, Any

from app.core.models import CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import find_buildings_in_radius, find_roads_in_radius


def step_flood(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Update flood radius, water level, road submersion, and building exposure."""
    changed = False
    progress = event.elapsed_time / max(event.duration, 1.0)
    river_boost = 1.25 if abs(event.epicentre.z - city.river_z) <= event.affected_radius + city.river_width else 1.0
    rain_boost = 1.0 + city.weather.rain_intensity * 0.45

    if progress < 0.72 and event.status in (DisasterStatus.ACTIVE, DisasterStatus.INTENSIFYING, DisasterStatus.PROPAGATING):
        growth = 1.6 * event.propagation_speed * event.severity * river_boost * rain_boost * dt
        new_radius = min(event.max_radius, event.affected_radius + growth)
        if abs(new_radius - event.affected_radius) >= 0.5:
            event.affected_radius = round(new_radius, 1)
            changed = True
        target_depth = min(5.5, 0.6 + event.severity * 3.8 * min(1.0, progress / 0.5 + 0.25) * river_boost)
        event.water_level_m = round(min(target_depth, event.water_level_m + 0.04 * event.severity * dt), 2)
        event.status = DisasterStatus.PROPAGATING if progress > 0.15 else DisasterStatus.INTENSIFYING
    elif progress < 0.92:
        event.status = DisasterStatus.STABILIZING
        event.water_level_m = round(max(0.2, event.water_level_m - 0.025 * dt), 2)
    else:
        event.status = DisasterStatus.CONTAINED
        event.water_level_m = round(max(0.0, event.water_level_m - 0.06 * dt), 2)
        event.affected_radius = round(max(40.0, event.affected_radius - 1.2 * dt), 1)
        changed = True

    event.flow_direction_deg = city.weather.wind_direction_deg

    buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)

    b_ids = []
    for b in buildings:
        dist = math.hypot(b.x - event.epicentre.x, b.z - event.epicentre.z)
        falloff = max(0.15, 1.0 - dist / max(event.affected_radius, 1.0))
        b.flood_depth_m = round(max(b.flood_depth_m, event.water_level_m * falloff), 2)
        b_ids.append(b.id)

    r_ids = []
    for r in roads:
        r.flood_depth_m = round(max(r.flood_depth_m, event.water_level_m * 0.85), 2)
        if r.flood_depth_m >= 0.75:
            r.blocked = True
        r_ids.append(r.id)

    event.affected_buildings = b_ids
    event.affected_roads = r_ids
    return {"geometry_changed": changed, "affected_buildings": len(b_ids), "affected_roads": len(r_ids)}
