from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

from app.core.config import CONFIG
from app.core.models import CityEnvironment, DroneState, DroneStatus, RescueTask, RoutePlan, TaskStatus
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.simulation.battery_model import check_battery_feasibility


def _return_route(
    drone: DroneState,
    start: Tuple[float, float, float],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    strategy: str,
) -> Tuple[Optional[RoutePlan], str]:
    active_stations = [station for station in city.stations if station.active]
    station = min(
        active_stations,
        key=lambda station: math.hypot(start[0] - station.position[0], start[2] - station.position[2]),
        default=None,
    )
    if station:
        target = (
            station.position[0],
            grid.safe_surface_altitude(station.position[0], station.position[2], station.position[1]),
            station.position[2],
        )
    else:
        target = (
            drone.home_position[0],
            grid.safe_surface_altitude(drone.home_position[0], drone.home_position[2], drone.home_position[1]),
            drone.home_position[2],
        )
    route = grid.plan_route(start=start, goal=target, drone=drone, strategy=strategy, payload_kg=0.0)
    if not route.feasible or not grid.is_route_valid(route):
        return None, "No validated safe return-to-base route."
    return route, ""


def evaluate_task_sequence(
    drone: DroneState,
    task_ids: List[str],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    strategy: str = "hybrid",
) -> Tuple[bool, str, Optional[RoutePlan], float]:
    """Validate and cost a complete sequenced sortie, including service and RTB.

    Energy is accumulated leg-by-leg from the drone's current position. This
    prevents several individually affordable tasks from jointly exhausting the
    battery before the return leg.
    """
    if drone.status in (
        DroneStatus.DESTROYED,
        DroneStatus.DAMAGED,
        DroneStatus.COMMUNICATION_LOST,
        DroneStatus.LOW_BATTERY,
    ):
        return False, f"Drone {drone.id} is non-operational ({drone.status.value}).", None, 0.0

    valid_ids = list(dict.fromkeys(task_ids))
    if not valid_ids:
        return True, "FEASIBLE", None, 0.0

    current = drone.position
    total_energy = 0.0
    first_route: Optional[RoutePlan] = None
    for tid in valid_ids:
        task = tasks.get(tid)
        if not task or task.status == TaskStatus.COMPLETED:
            return False, f"Task {tid} is missing or already completed.", None, total_energy
        if task.payload_required_kg > drone.max_payload_kg:
            return False, f"Payload {task.payload_required_kg}kg exceeds {drone.id} max {drone.max_payload_kg}kg.", None, total_energy
        if not all(cap in drone.capabilities for cap in task.required_capabilities):
            return False, f"Drone {drone.id} lacks required capabilities {task.required_capabilities}.", None, total_energy
        route = grid.plan_route(
            start=current,
            goal=task.location,
            drone=drone,
            strategy=strategy,
            task_id=task.id,
            payload_kg=task.payload_required_kg,
            service_hover_s=task.service_time_seconds,
        )
        if not route.feasible or not grid.is_route_valid(route):
            return False, f"No validated safe route to {task.id} in the sequenced sortie.", route, total_energy
        if first_route is None:
            first_route = route
        total_energy += route.estimated_energy_wh
        current = task.location

    rtb_route, reason = _return_route(drone, current, city, grid, strategy)
    if rtb_route is None:
        return False, reason, first_route, total_energy
    total_energy += rtb_route.estimated_energy_wh
    ok, projected = check_battery_feasibility(drone, total_energy, 0.0)
    if not ok:
        return False, (
            f"Battery reserve violation for sequenced sortie on {drone.id} "
            f"(projected {proj}Wh < {CONFIG.safety_reserve_ratio*100:.0f}% reserve)."
        ), first_route, total_energy
    return True, "FEASIBLE", first_route, round(total_energy, 3)


def is_drone_eligible_for_task(
    drone: DroneState,
    task: RescueTask,
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    strategy: str = "hybrid",
    assigned_task_ids: Optional[List[str]] = None,
    tasks: Optional[Dict[str, RescueTask]] = None,
) -> Tuple[bool, str, Optional[RoutePlan]]:
    sequence = list(drone.assigned_task_ids if assigned_task_ids is None else assigned_task_ids)
    if task.id not in sequence:
        sequence.append(task.id)
    task_map = tasks if tasks is not None else {task.id: task}
    ok, reason, route, _ = evaluate_task_sequence(drone, sequence, tasks=task_map, city=city, grid=grid, strategy=strategy)
    return ok, reason, route


def is_assignment_sequence_feasible(
    drone: DroneState,
    task_ids: List[str],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    strategy: str = "hybrid",
) -> Tuple[bool, str]:
    ok, reason, _, _ = evaluate_task_sequence(drone, task_ids, tasks, city, grid, strategy)
    return ok, reason


def estimate_assignment_cost(
    drone: DroneState,
    task: RescueTask,
    city: CityEnvironment,
    sim_time_s: float = 0.0,
) -> float:
    dist = math.hypot(drone.position[0] - task.location[0], drone.position[2] - task.location[2])
    flight_time = dist / max(drone.cruise_speed_mps, 1.0) + task.service_time_seconds
    # Retained as a lightweight ranking estimate; admission is always decided
    # by evaluate_task_sequence's routed energy calculation.
    from app.simulation.battery_model import compute_segment_energy_wh

    energy = compute_segment_energy_wh(
        drone.position, task.location, drone, task.payload_required_kg, city.weather, task.service_time_seconds
    )
    slack = max(0.0, (task.deadline_seconds - sim_time_s) - flight_time)
    deadline_pen = 0.0 if slack > 0 else 180.0
    prio_mult = {"critical": 0.65, "high": 0.85, "medium": 1.0, "low": 1.25}.get(task.priority.value, 1.0)
    return round((flight_time * 0.55 + energy * 0.45 + task.risk_level * 40.0 + deadline_pen) * prio_mult, 3)
