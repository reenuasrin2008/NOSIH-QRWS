"""Cyclone engine updating wind field, rainfall, visibility, lightning, and operational limits."""
from __future__ import annotations

from typing import Any, Dict

from app.core.models import CityEnvironment, DisasterEvent, DisasterStatus
from app.disasters.damage_model import find_buildings_in_radius, find_roads_in_radius


def step_cyclone(city: CityEnvironment, event: DisasterEvent, dt: float) -> Dict[str, Any]:
    """Update metropolitan weather state, wind speed, rain, visibility, and lightning."""
    progress = event.elapsed_time / max(event.duration, 1.0)
    if progress < 0.7:
        intensity = min(1.0, event.severity * (0.65 + 0.35 * min(1.0, progress / 0.35)))
        event.status = DisasterStatus.INTENSIFYING if progress < 0.25 else DisasterStatus.PROPAGATING
    elif progress < 0.92:
        intensity = max(0.3, event.severity * (1.0 - (progress - 0.7) * 2.2))
        event.status = DisasterStatus.STABILIZING
    else:
        intensity = 0.2
        event.status = DisasterStatus.CONTAINED

    event.wind_speed_mps = round(10.0 + intensity * 15.0, 1)
    city.weather.condition = "cyclone" if intensity >= 0.55 else "storm"
    city.weather.wind_speed_mps = max(city.weather.wind_speed_mps, event.wind_speed_mps)
    city.weather.wind_direction_deg = round((city.weather.wind_direction_deg + 0.35 * dt) % 360.0, 1)
    city.weather.rain_intensity = round(min(0.98, max(city.weather.rain_intensity, 0.45 + intensity * 0.5)), 2)
    city.weather.fog_density = round(min(0.6, max(city.weather.fog_density, 0.18 + intensity * 0.35)), 2)
    city.weather.visibility_m = round(max(60.0, 900.0 - intensity * 740.0), 1)
    city.weather.lightning_active = intensity >= 0.62 and (int(event.elapsed_time) % 9 == 0)

    buildings = find_buildings_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    roads = find_roads_in_radius(city, event.epicentre.x, event.epicentre.z, event.affected_radius)
    event.affected_buildings = [b.id for b in buildings]
    event.affected_roads = [r.id for r in roads]
    return {"geometry_changed": False, "wind_speed_mps": event.wind_speed_mps, "lightning": city.weather.lightning_active}
