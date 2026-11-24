from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

from app.core.config import CONFIG
from app.core.models import DroneState, DroneStatus
from app.navigation.pathfinder import MAX_SAFE_ALTITUDE_M, SpatialAirspaceGrid


def assign_corridor_altitude(
    drone: DroneState,
    is_critical: bool = False,
    grid: Optional[SpatialAirspaceGrid] = None,
) -> float:
    """Return a bounded directional corridor altitude, never above the safe envelope."""
    base = float(drone.cruise_altitude)
    if grid is not None:
        base = max(base, grid.minimum_safe_altitude(drone.position[0], drone.position[2], base))
    if is_critical:
        altitude = base + 16.0
    elif drone.status == DroneStatus.RETURNING:
        altitude = base + 8.0
    else:
        dir_offset = 4.0 if math.sin(drone.heading_rad) >= 0 else -4.0
        altitude = max(26.0, base + dir_offset)
    return round(min(MAX_SAFE_ALTITUDE_M, altitude), 1)


def _safe_vertical_adjustment(
    drone: DroneState,
    new_altitude: float,
    other_altitude: float,
    grid: Optional[SpatialAirspaceGrid],
) -> bool:
    new_altitude = round(new_altitude, 1)
    if not (10.0 <= new_altitude <= MAX_SAFE_ALTITUDE_M):
        return False
    if abs(new_altitude - other_altitude) < CONFIG.min_vertical_separation_m:
        return False
    x, _, z = drone.position
    if grid is None:
        # Without airspace geometry no vertical mutation can be validated.
        return False
    start = (x, drone.position[1], z)
    end = (x, new_altitude, z)
    if not grid.is_point_safe(start) or not grid.is_point_safe(end):
        return False
    route = drone.current_route
    if route and 0 <= drone.waypoint_index < len(route.waypoints):
        target = route.waypoints[drone.waypoint_index]
        segment_length = math.dist(end, target)
        segment_steps = max(1, int(math.ceil(segment_length / 10.0)))
        if not all(
            grid.is_point_safe(tuple(end[i] + (target[i] - end[i]) * step / segment_steps for i in range(3)))
            for step in range(segment_steps + 1)
        ):
            return False
    length = abs(new_altitude - start[1])
    steps = max(1, int(math.ceil(length / 5.0)))
    return all(
        grid.is_point_safe((x, start[1] + (end[1] - start[1]) * i / steps, z))
        for i in range(steps + 1)
    )


def resolve_airspace_conflicts(
    drones: Dict[str, DroneState],
    grid: Optional[SpatialAirspaceGrid] = None,
) -> List[Tuple[str, str]]:
    """Resolve crossings only through validated vertical corridor adjustments.

    If neither separation direction is safe, the conflict is reported but no
    unsafe altitude mutation is made.
    """
    airborne = [
        d for d in drones.values()
        if d.status in (DroneStatus.IN_FLIGHT, DroneStatus.TAKING_OFF, DroneStatus.RETURNING)
        and d.position[1] > 10.0
    ]
    conflicts: List[Tuple[str, str]] = []
    for i, a in enumerate(airborne):
        for b in airborne[i + 1:]:
            hdist = math.hypot(a.position[0] - b.position[0], a.position[2] - b.position[2])
            vdist = abs(a.position[1] - b.position[1])
            if hdist >= CONFIG.min_horizontal_separation_m or vdist >= CONFIG.min_vertical_separation_m:
                continue
            conflicts.append((a.id, b.id))
            bx, by, bz = b.position
            preferred = max(
                by + CONFIG.min_vertical_separation_m,
                assign_corridor_altitude(b, grid=grid),
            )
            candidates = [preferred, by - CONFIG.min_vertical_separation_m]
            for altitude in candidates:
                if _safe_vertical_adjustment(b, altitude, a.position[1], grid):
                    b.position = (bx, round(altitude, 1), bz)
                    break
    return conflicts
