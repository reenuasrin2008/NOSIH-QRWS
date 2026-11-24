from __future__ import annotations
import math
from typing import Dict, List, Tuple
from app.core.config import CONFIG
from app.core.models import DroneState, DroneStatus


def assign_corridor_altitude(drone: DroneState, is_critical: bool = False) -> float:
    """
    Proactive directional altitude banding:
    - Critical express lane: +16m above nominal cruise altitude
    - Returning to base (inbound): +8m above nominal cruise altitude
    - East/Northbound vs West/Southbound separation: +/- 4m
    """
    base = drone.cruise_altitude
    if is_critical:
        return round(base + 16.0, 1)
    if drone.status == DroneStatus.RETURNING:
        return round(base + 8.0, 1)
    dir_offset = 4.0 if math.sin(drone.heading_rad) >= 0 else -4.0
    return round(max(26.0, base + dir_offset), 1)


def resolve_airspace_conflicts(drones: Dict[str, DroneState]) -> List[Tuple[str, str]]:
    """
    Enforce minimum horizontal & vertical separation between active airborne drones.
    Uses proactive corridor banding + reactive vertical deconfliction when trajectories cross.
    """
    airborne = [
        d for d in drones.values()
        if d.status in (DroneStatus.IN_FLIGHT, DroneStatus.TAKING_OFF, DroneStatus.RETURNING)
        and d.position[1] > 10.0
    ]
    conflicts: List[Tuple[str, str]] = []
    n = len(airborne)
    for i in range(n):
        a = airborne[i]
        for j in range(i + 1, n):
            b = airborne[j]
            hdist = math.hypot(a.position[0] - b.position[0], a.position[2] - b.position[2])
            vdist = abs(a.position[1] - b.position[1])
            if hdist < CONFIG.min_horizontal_separation_m and vdist < CONFIG.min_vertical_separation_m:
                conflicts.append((a.id, b.id))
                bx, by, bz = b.position
                b.position = (bx, round(by + CONFIG.min_vertical_separation_m, 1), bz)
    return conflicts
