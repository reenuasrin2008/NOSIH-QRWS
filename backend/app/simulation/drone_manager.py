from __future__ import annotations
import math
import random
from typing import Dict, Optional
from app.core.config import DRONE_CLASS_SPECS
from app.core.models import CityEnvironment, DroneState, DroneStatus, Station


def generate_fleet(city: CityEnvironment, seed: int) -> Dict[str, DroneState]:
    rng = random.Random(seed + 101)
    drones: Dict[str, DroneState] = {}
    stations = [s for s in city.stations if s.active]
    idx = 1

    for dtype, spec in DRONE_CLASS_SPECS.items():
        for _ in range(spec["count"]):
            st: Station = stations[(idx - 1) % len(stations)]
            angle = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(8.0, 24.0)
            px = round(max(30.0, min(city.world_size - 30.0, st.position[0] + math.cos(angle) * r)), 1)
            pz = round(max(30.0, min(city.world_size - 30.0, st.position[2] + math.sin(angle) * r)), 1)
            py = 2.0
            did = f"D-{idx:02d}"
            cap = spec["battery_capacity_wh"]
            drones[did] = DroneState(
                id=did,
                drone_type=dtype,
                class_label=spec["label"],
                capabilities=list(spec["capabilities"]),
                camera=list(spec["camera"]),
                sensors=list(spec["sensors"]),
                battery_capacity_wh=cap,
                remaining_battery_wh=cap,
                battery_percent=100.0,
                max_payload_kg=spec["max_payload_kg"],
                current_payload_kg=0.0,
                max_speed_mps=spec["max_speed_mps"],
                cruise_speed_mps=spec["cruise_speed_mps"],
                cruise_altitude=spec["cruise_altitude"] + (idx % 4) * 3.0,
                max_flight_time_min=spec["max_flight_time_min"],
                home_station_id=st.id,
                home_position=(px, py, pz),
                position=(px, py, pz),
                status=DroneStatus.AVAILABLE,
                estimated_remaining_flight_s=spec["max_flight_time_min"] * 60.0,
            )
            idx += 1
    return drones


def find_nearest_charging_station(drone: DroneState, city: CityEnvironment) -> Optional[Station]:
    active = [s for s in city.stations if s.active]
    if not active:
        return None
    return min(
        active,
        key=lambda s: math.hypot(drone.position[0] - s.position[0], drone.position[2] - s.position[2]),
    )
