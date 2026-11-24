from dataclasses import dataclass, field
from typing import Dict

WORLD_SIZE = 4000.0
GRID_CELL_SIZE = 80.0  # 50x50 macro-corridor grid for <5ms 3D A* across 4x4 km
DEFAULT_SCENARIO_ID = "CHENNAI_METRO_FLOOD_005"
DEFAULT_SCENARIO_NAME = "CHENNAI METROPOLITAN DISASTER — 4x4 KM DIGITAL TWIN"
DEFAULT_SEED = 20261121
SAFETY_RESERVE_RATIO = 0.20

@dataclass
class EnergyCoefficients:
    # Calibrated for 4x4 km metropolitan eVTOL/UAV sorties (simulation parameters)
    base_distance_wh_per_m: float = 0.011
    payload_wh_per_kg_per_m: float = 0.0045
    hover_wh_per_sec: float = 0.16
    climb_wh_per_m: float = 0.14
    wind_penalty_factor: float = 0.016
    rain_penalty_factor: float = 0.10

@dataclass
class ScoringWeights:
    w_rescue_time: float = 0.25
    w_energy: float = 0.15
    w_risk: float = 0.15
    w_deadline_violations: float = 0.20
    w_uncompleted: float = 0.25

@dataclass
class SimulationConfig:
    world_size: float = WORLD_SIZE
    grid_cell_size: float = GRID_CELL_SIZE
    tick_dt: float = 1.0
    safety_reserve_ratio: float = SAFETY_RESERVE_RATIO
    min_horizontal_separation_m: float = 24.0
    min_vertical_separation_m: float = 12.0
    qaoa_max_qubits: int = 8
    qaoa_layers: int = 2
    qaoa_shots: int = 512
    qaoa_max_iter: int = 25
    energy: EnergyCoefficients = field(default_factory=EnergyCoefficients)
    weights: ScoringWeights = field(default_factory=ScoringWeights)

DRONE_CLASS_SPECS: Dict[str, dict] = {
    "surveillance": {
        "label": "Class A — Long-Range Surveillance",
        "battery_capacity_wh": 640.0,
        "max_payload_kg": 0.8,
        "max_speed_mps": 44.0,
        "cruise_speed_mps": 36.0,
        "max_flight_time_min": 48.0,
        "cruise_altitude": 115.0,
        "camera": ["rgb", "thermal"],
        "sensors": ["gps", "imu", "lidar", "thermal_cam"],
        "capabilities": ["surveillance", "thermal_scan", "area_scan", "comm_relay"],
        "count": 8,
    },
    "medical": {
        "label": "Class B — Rapid Medical Delivery",
        "battery_capacity_wh": 740.0,
        "max_payload_kg": 2.5,
        "max_speed_mps": 38.0,
        "cruise_speed_mps": 31.0,
        "max_flight_time_min": 40.0,
        "cruise_altitude": 95.0,
        "camera": ["rgb"],
        "sensors": ["gps", "imu", "barometer"],
        "capabilities": ["medical_payload", "light_supply", "first_aid"],
        "count": 8,
    },
    "heavy_lift": {
        "label": "Class C — Heavy-Lift Cargo Hexacopter",
        "battery_capacity_wh": 1120.0,
        "max_payload_kg": 8.0,
        "max_speed_mps": 28.0,
        "cruise_speed_mps": 23.0,
        "max_flight_time_min": 36.0,
        "cruise_altitude": 78.0,
        "camera": ["rgb"],
        "sensors": ["gps", "imu", "obstacle_radar"],
        "capabilities": ["heavy_payload", "water_supply", "equipment_delivery", "light_supply"],
        "count": 7,
    },
    "search_rescue": {
        "label": "Class D — Search & Rescue All-Weather",
        "battery_capacity_wh": 860.0,
        "max_payload_kg": 3.0,
        "max_speed_mps": 36.0,
        "cruise_speed_mps": 29.0,
        "max_flight_time_min": 44.0,
        "cruise_altitude": 105.0,
        "camera": ["rgb", "thermal", "night_vision"],
        "sensors": ["gps", "imu", "thermal_cam", "acoustic"],
        "capabilities": ["survivor_search", "thermal_scan", "medical_payload", "surveillance", "area_scan"],
        "count": 7,
    },
}

TASK_TYPE_SPECS: Dict[str, dict] = {
    "missing_person": {"required_capabilities": ["survivor_search"], "payload_kg": 0.4, "service_time": 20.0},
    "medical_delivery": {"required_capabilities": ["medical_payload"], "payload_kg": 1.2, "service_time": 18.0},
    "water_supply": {"required_capabilities": ["water_supply"], "payload_kg": 4.5, "service_time": 24.0},
    "equipment_delivery": {"required_capabilities": ["equipment_delivery"], "payload_kg": 5.5, "service_time": 28.0},
    "flood_inspection": {"required_capabilities": ["surveillance"], "payload_kg": 0.0, "service_time": 18.0},
    "fire_monitoring": {"required_capabilities": ["thermal_scan"], "payload_kg": 0.0, "service_time": 20.0},
    "survivor_search": {"required_capabilities": ["survivor_search"], "payload_kg": 0.5, "service_time": 22.0},
    "comm_relay": {"required_capabilities": ["comm_relay"], "payload_kg": 0.6, "service_time": 20.0},
    "area_scanning": {"required_capabilities": ["area_scan"], "payload_kg": 0.0, "service_time": 16.0},
}

CONFIG = SimulationConfig()
