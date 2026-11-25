"""Deterministic simulated survivor generation, discovery, and rescue prioritization."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from app.core.models import (
    CityEnvironment,
    DisasterEvent,
    DisasterType,
    SimulatedSurvivor,
    SurvivorLocationType,
    SurvivorStatus,
    TaskPriority,
)
from app.disasters.damage_model import find_buildings_in_radius


def compute_survivor_priority(health_level: float, exposure_level: float) -> TaskPriority:
    urgency = (1.0 - health_level) * 0.6 + exposure_level * 0.4
    if urgency >= 0.68:
        return TaskPriority.CRITICAL
    if urgency >= 0.48:
        return TaskPriority.HIGH
    if urgency >= 0.28:
        return TaskPriority.MEDIUM
    return TaskPriority.LOW


def generate_survivors_for_disaster(
    city: CityEnvironment,
    disaster: DisasterEvent,
    existing_count: int,
    sim_time_s: float,
) -> List[SimulatedSurvivor]:
    """Generate deterministic simulated survivors anchored to affected buildings or epicentre."""
    rng = random.Random(disaster.seed ^ hash(disaster.event_id) & 0xFFFFFFFF)
    count = max(2, min(10, int(round(3 + disaster.severity * 6))))
    buildings = find_buildings_in_radius(city, disaster.epicentre.x, disaster.epicentre.z, disaster.affected_radius)

    loc_map = {
        DisasterType.FLOOD: SurvivorLocationType.ROOFTOP,
        DisasterType.EARTHQUAKE: SurvivorLocationType.TRAPPED_DEBRIS,
        DisasterType.BUILDING_COLLAPSE: SurvivorLocationType.TRAPPED_DEBRIS,
        DisasterType.FIRE: SurvivorLocationType.ROOFTOP,
        DisasterType.CYCLONE: SurvivorLocationType.SHELTER,
        DisasterType.LANDSLIDE: SurvivorLocationType.OPEN_GROUND,
    }
    default_loc = loc_map.get(disaster.type, SurvivorLocationType.ROOFTOP)

    created: List[SimulatedSurvivor] = []
    for idx in range(count):
        sid = f"SUR-{existing_count + idx + 1:04d}"
        building_id: Optional[str] = None
        if buildings:
            b = buildings[idx % len(buildings)]
            building_id = b.id
            jitter_x = rng.uniform(-b.width * 0.25, b.width * 0.25)
            jitter_z = rng.uniform(-b.depth * 0.25, b.depth * 0.25)
            px = max(20.0, min(city.world_size - 20.0, b.x + jitter_x))
            pz = max(20.0, min(city.world_size - 20.0, b.z + jitter_z))
            py = round(b.height + 1.5 if default_loc == SurvivorLocationType.ROOFTOP else 2.5, 1)
        else:
            angle = rng.uniform(0.0, 2.0 * math.pi)
            dist = rng.uniform(15.0, max(35.0, disaster.affected_radius * 0.75))
            px = max(20.0, min(city.world_size - 20.0, disaster.epicentre.x + math.cos(angle) * dist))
            pz = max(20.0, min(city.world_size - 20.0, disaster.epicentre.z + math.sin(angle) * dist))
            py = 2.0

        health = round(max(0.18, min(0.95, 0.88 - disaster.severity * rng.uniform(0.25, 0.65))), 2)
        exposure = round(max(0.25, min(0.98, disaster.severity * rng.uniform(0.65, 1.1))), 2)
        priority = compute_survivor_priority(health, exposure)

        created.append(
            SimulatedSurvivor(
                survivor_id=sid,
                position=(round(px, 1), py, round(pz, 1)),
                status=SurvivorStatus.UNCONFIRMED,
                priority=priority,
                health_level=health,
                exposure_level=exposure,
                location_type=default_loc,
                detected=False,
                assigned_task_id=None,
                disaster_event_id=disaster.event_id,
                building_id=building_id,
                last_updated_sim_time=round(sim_time_s, 1),
            )
        )
    return created


def update_survivors_health(survivors: Dict[str, SimulatedSurvivor], dt: float, sim_time_s: float) -> None:
    """Gradually degrade health of unrescued exposed simulated survivors over time."""
    for s in survivors.values():
        if s.status in (SurvivorStatus.EVACUATED, SurvivorStatus.MEDICAL_ASSISTANCE, SurvivorStatus.UNAVAILABLE):
            continue
        decay = 0.00035 * s.exposure_level * dt
        s.health_level = round(max(0.05, s.health_level - decay), 3)
        s.priority = compute_survivor_priority(s.health_level, s.exposure_level)
        s.last_updated_sim_time = round(sim_time_s, 1)
