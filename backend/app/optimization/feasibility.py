from __future__ import annotations
import math
from typing import Optional, Tuple
from app.core.config import CONFIG
from app.core.models import CityEnvironment, DroneState, DroneStatus, RescueTask, RoutePlan
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.simulation.battery_model import check_battery_feasibility, compute_segment_energy_wh
from app.simulation.drone_manager import find_nearest_charging_station


def is_drone_eligible_for_task(
    drone: DroneState,
    task: RescueTask,
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    strategy: str = "hybrid",
) -> Tuple[bool, str, Optional[RoutePlan]]:
    if drone.status in (
        DroneStatus.DESTROYED,
        DroneStatus.DAMAGED,
        DroneStatus.COMMUNICATION_LOST,
        DroneStatus.LOW_BATTERY,
    ):
        return False, f"Drone {drone.id} is non-operational ({drone.status.value}).", None

    if task.payload_required_kg > drone.max_payload_kg:
        return False, f"Payload {task.payload_required_kg}kg exceeds {drone.id} max {drone.max_payload_kg}kg.", None

    if not all(cap in drone.capabilities for cap in task.required_capabilities):
        return False, f"Drone {drone.id} lacks required capabilities {task.required_capabilities}.", None

    route = grid.plan_route(
        start=drone.position,
        goal=task.location,
        drone=drone,
        strategy=strategy,
        task_id=task.id,
        payload_kg=task.payload_required_kg,
        service_hover_s=task.service_time_seconds,
    )
    if not route.feasible:
        return False, f"No safe obstacle-free route from {drone.id} to {task.id}.", route

    nearest_st = find_nearest_charging_station(drone, city)
    rtb_pos = nearest_st.position if nearest_st else drone.home_position
    rtb_energy = compute_segment_energy_wh(
        task.location, (rtb_pos[0], drone.cruise_altitude, rtb_pos[2]), drone, 0.0, city.weather, hover_seconds=6.0
    )

    ok_bat, proj = check_battery_feasibility(drone, route.estimated_energy_wh, rtb_energy)
    if not ok_bat:
        return False, f"Battery reserve violation for {drone.id} (projected {proj}Wh < {CONFIG.safety_reserve_ratio*100:.0f}% reserve).", route

    return True, "FEASIBLE", route


def estimate_assignment_cost(
    drone: DroneState,
    task: RescueTask,
    city: CityEnvironment,
    sim_time_s: float = 0.0,
) -> float:
    dist = math.hypot(drone.position[0] - task.location[0], drone.position[2] - task.location[2])
    flight_time = dist / max(drone.cruise_speed_mps, 1.0) + task.service_time_seconds
    energy = compute_segment_energy_wh(
        drone.position, task.location, drone, task.payload_required_kg, city.weather, task.service_time_seconds
    )
    slack = max(0.0, (task.deadline_seconds - sim_time_s) - flight_time)
    deadline_pen = 0.0 if slack > 0 else 180.0
    prio_mult = {"critical": 0.65, "high": 0.85, "medium": 1.0, "low": 1.25}[task.priority.value]
    return round((flight_time * 0.55 + energy * 0.45 + task.risk_level * 40.0 + deadline_pen) * prio_mult, 3)
