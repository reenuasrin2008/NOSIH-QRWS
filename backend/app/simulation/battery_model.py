from __future__ import annotations
import math
from typing import Tuple
from app.core.config import CONFIG
from app.core.models import DroneState, WeatherState


def compute_segment_energy_wh(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    drone: DroneState,
    payload_kg: float,
    weather: WeatherState,
    hover_seconds: float = 0.0,
) -> float:
    coeff = CONFIG.energy
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    horiz_dist = math.hypot(dx, dz)
    total_dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    class_mult = {
        "surveillance": 0.82,
        "medical": 1.0,
        "search_rescue": 1.08,
        "heavy_lift": 1.38,
    }.get(drone.drone_type, 1.0)

    distance_energy = total_dist * coeff.base_distance_wh_per_m * class_mult
    payload_energy = total_dist * max(0.0, payload_kg) * coeff.payload_wh_per_kg_per_m
    climb_energy = max(0.0, dy) * coeff.climb_wh_per_m * (1.0 + 0.08 * payload_kg)
    hover_energy = max(0.0, hover_seconds) * coeff.hover_wh_per_sec * class_mult * (1.0 + 0.06 * payload_kg)

    env_energy = 0.0
    if horiz_dist > 1e-3:
        flight_dir_x = dx / horiz_dist
        flight_dir_z = dz / horiz_dist
        wind_rad = math.radians(weather.wind_direction_deg)
        dot = flight_dir_x * math.cos(wind_rad) + flight_dir_z * math.sin(wind_rad)
        headwind_mps = max(0.0, -dot * weather.wind_speed_mps)
        env_energy += (distance_energy + payload_energy) * (headwind_mps * coeff.wind_penalty_factor)

    if weather.rain_intensity > 0.0:
        env_energy += (distance_energy + hover_energy) * (weather.rain_intensity * coeff.rain_penalty_factor)

    return round(distance_energy + payload_energy + climb_energy + hover_energy + env_energy, 4)


def compute_route_energy_wh(
    waypoints: list[Tuple[float, float, float]],
    drone: DroneState,
    payload_kg: float,
    weather: WeatherState,
    service_hover_s: float = 0.0,
) -> float:
    if len(waypoints) < 2:
        return compute_segment_energy_wh(
            drone.position, drone.position, drone, payload_kg, weather, hover_seconds=service_hover_s
        )
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += compute_segment_energy_wh(waypoints[i], waypoints[i + 1], drone, payload_kg, weather, 0.0)
    if service_hover_s > 0.0:
        total += compute_segment_energy_wh(waypoints[-1], waypoints[-1], drone, payload_kg, weather, service_hover_s)
    return round(total, 3)


def check_battery_feasibility(
    drone: DroneState,
    mission_energy_wh: float,
    rtb_energy_wh: float,
    reserve_ratio: float = CONFIG.safety_reserve_ratio,
) -> Tuple[bool, float]:
    min_reserve_wh = drone.battery_capacity_wh * reserve_ratio
    projected_remaining = drone.remaining_battery_wh - (mission_energy_wh + rtb_energy_wh)
    return (projected_remaining >= min_reserve_wh, round(projected_remaining, 2))
