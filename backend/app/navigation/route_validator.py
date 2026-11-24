from __future__ import annotations
from typing import Tuple
from app.core.config import CONFIG
from app.core.models import CityEnvironment, DroneState, RoutePlan
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.simulation.battery_model import check_battery_feasibility, compute_segment_energy_wh
from app.simulation.drone_manager import find_nearest_charging_station


def validate_route_full(
    route: RoutePlan,
    drone: DroneState,
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
) -> Tuple[bool, str]:
    if not route or len(route.waypoints) < 2:
        return False, "Route has insufficient waypoints."
    if not route.feasible:
        return False, "Pathfinder flagged route as infeasible."
    if not grid.is_route_valid(route):
        return False, "Route intersects building envelope, fire exclusion zone, or no-fly airspace."

    goal = route.waypoints[-1]
    st = find_nearest_charging_station(drone, city)
    rtb_pos = st.position if st else drone.home_position
    rtb_e = compute_segment_energy_wh(goal, rtb_pos, drone, 0.0, city.weather, hover_seconds=5.0)
    ok, proj = check_battery_feasibility(drone, route.estimated_energy_wh, rtb_e, CONFIG.safety_reserve_ratio)
    if not ok:
        return False, f"Violates {CONFIG.safety_reserve_ratio*100:.0f}% battery reserve (projected {proj}Wh)."
    return True, "VALID"
