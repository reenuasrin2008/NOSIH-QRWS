from __future__ import annotations
import app.core.compat  # noqa: F401
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field


class SimulationStatus(str, Enum):
    READY = "READY"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    OPTIMIZING = "OPTIMIZING"
    REPLANNING = "REPLANNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class DroneStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    TAKING_OFF = "TAKING_OFF"
    IN_FLIGHT = "IN_FLIGHT"
    DELIVERING = "DELIVERING"
    RETURNING = "RETURNING"
    CHARGING = "CHARGING"
    LOW_BATTERY = "LOW_BATTERY"
    COMMUNICATION_LOST = "COMMUNICATION_LOST"
    DAMAGED = "DAMAGED"
    DESTROYED = "DESTROYED"
    COMPLETED = "COMPLETED"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REQUIRES_REASSIGNMENT = "requires_reassignment"
    UNASSIGNED = "unassigned"
    FAILED = "failed"


class FailureType(str, Enum):
    MOTOR_FAILURE = "MOTOR_FAILURE"
    BATTERY_FAILURE = "BATTERY_FAILURE"
    GPS_FAILURE = "GPS_FAILURE"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    LOW_BATTERY = "LOW_BATTERY"
    SENSOR_FAILURE = "SENSOR_FAILURE"
    FLIGHT_CONTROL_FAILURE = "FLIGHT_CONTROL_FAILURE"
    COMPLETE_DRONE_DESTRUCTION = "COMPLETE_DRONE_DESTRUCTION"


class StrategyType(str, Enum):
    GREEDY = "greedy"
    CLASSICAL = "classical"
    QUANTUM = "quantum"
    HYBRID = "hybrid"


class Building(BaseModel):
    id: str
    kind: str
    x: float
    z: float
    width: float
    depth: float
    height: float
    color: str
    has_helipad: bool = False
    roof_style: str = "flat"


class RoadSegment(BaseModel):
    id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    width: float
    is_bridge: bool = False
    blocked: bool = False


class HazardZone(BaseModel):
    id: str
    kind: str
    x: float
    z: float
    radius: float
    severity: float = 0.8
    altitude_ceiling: float = 120.0
    active: bool = True


class Station(BaseModel):
    id: str
    name: str
    kind: str
    position: Tuple[float, float, float]
    active: bool = True
    capacity: int = 10


class VehicleProp(BaseModel):
    id: str
    kind: str  # ambulance, fire_truck, civilian
    x: float
    z: float
    heading_rad: float
    axis: str  # "x" or "z"
    speed_mps: float = 0.0
    road_pos: float = 0.0


class WeatherState(BaseModel):
    condition: str = "overcast"
    wind_speed_mps: float = 5.5
    wind_direction_deg: float = 135.0
    rain_intensity: float = 0.25
    fog_density: float = 0.12
    day_mode: bool = False


class CityEnvironment(BaseModel):
    scenario_id: str
    scenario_name: str
    seed: int
    world_size: float = 1000.0
    city_density: float = 1.0
    building_density: float = 1.0
    buildings: List[Building] = Field(default_factory=list)
    roads: List[RoadSegment] = Field(default_factory=list)
    hazards: List[HazardZone] = Field(default_factory=list)
    stations: List[Station] = Field(default_factory=list)
    trees: List[Tuple[float, float, float]] = Field(default_factory=list)
    streetlights: List[Tuple[float, float]] = Field(default_factory=list)
    vehicles: List[VehicleProp] = Field(default_factory=list)
    river_z: float = 500.0
    river_width: float = 54.0
    weather: WeatherState = Field(default_factory=WeatherState)


class RoutePlan(BaseModel):
    route_id: str
    drone_id: str
    task_id: Optional[str] = None
    strategy: str = "hybrid"
    waypoints: List[Tuple[float, float, float]] = Field(default_factory=list)
    distance_m: float = 0.0
    estimated_duration_s: float = 0.0
    estimated_energy_wh: float = 0.0
    risk_score: float = 0.0
    feasible: bool = True
    color_tag: str = "blue"
    replan_count: int = 0


class DroneState(BaseModel):
    id: str
    drone_type: str
    class_label: str
    capabilities: List[str]
    camera: List[str] = Field(default_factory=list)
    sensors: List[str] = Field(default_factory=list)
    battery_capacity_wh: float
    remaining_battery_wh: float
    battery_percent: float
    max_payload_kg: float
    current_payload_kg: float = 0.0
    max_speed_mps: float
    cruise_speed_mps: float
    cruise_altitude: float = 42.0
    max_flight_time_min: float
    home_station_id: str
    home_position: Tuple[float, float, float]
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    groundspeed_mps: float = 0.0
    heading_rad: float = 0.0
    bank_rad: float = 0.0
    pitch_rad: float = 0.0
    power_draw_w: float = 0.0
    battery_temp_c: float = 29.0
    eta_seconds: float = 0.0
    status: DroneStatus = DroneStatus.AVAILABLE
    health: float = 100.0
    assigned_task_ids: List[str] = Field(default_factory=list)
    active_task_id: Optional[str] = None
    current_route: Optional[RoutePlan] = None
    waypoint_index: int = 0
    service_timer_s: float = 0.0
    total_distance_m: float = 0.0
    total_energy_used_wh: float = 0.0
    total_flight_time_s: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    failure_history: List[Dict[str, Any]] = Field(default_factory=list)
    estimated_remaining_flight_s: float = 0.0
    last_telemetry_ts: float = 0.0


class RescueTask(BaseModel):
    id: str
    name: str
    task_type: str
    location: Tuple[float, float, float]
    priority: TaskPriority
    deadline_seconds: float
    payload_required_kg: float
    required_capabilities: List[str]
    service_time_seconds: float
    risk_level: float
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_drone_id: Optional[str] = None
    created_at_sim_s: float = 0.0
    assigned_at_sim_s: Optional[float] = None
    started_at_sim_s: Optional[float] = None
    completed_at_sim_s: Optional[float] = None
    reassignment_count: int = 0
    deadline_violated: bool = False
    unassigned_reason: Optional[str] = None


class QuantumMetrics(BaseModel):
    executed: bool = False
    backend_name: str = "QAOA — Classical quantum-circuit simulation"
    num_qubits: int = 0
    circuit_depth: int = 0
    qaoa_layers: int = 0
    iterations: int = 0
    shots: int = 0
    best_bitstring: str = ""
    best_energy: float = 0.0
    execution_time_ms: float = 0.0
    candidates_evaluated: int = 0
    validation_passed: bool = False
    repaired_assignments: int = 0
    subproblem_tasks: List[str] = Field(default_factory=list)
    subproblem_drones: List[str] = Field(default_factory=list)
    top_samples: List[Dict[str, Any]] = Field(default_factory=list)
    convergence_history: List[Dict[str, float]] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    optimization_id: str
    algorithm: StrategyType
    started_at_iso: str
    completed_at_iso: str
    solver_runtime_ms: float
    objective_value: float
    feasible: bool
    assignments: Dict[str, List[str]] = Field(default_factory=dict)
    completed_tasks: int = 0
    missed_tasks: int = 0
    energy_consumed_wh: float = 0.0
    operational_risk: float = 0.0
    score: float = 0.0
    quantum_metrics: Optional[QuantumMetrics] = None
    fallback_used: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class SimulationEvent(BaseModel):
    id: str
    run_id: str
    timestamp_iso: str
    sim_time_s: float
    category: str
    event_type: str
    message: str
    entity_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class StrategyMetrics(BaseModel):
    strategy: StrategyType
    status: SimulationStatus
    planning_complete: bool = False
    missions_completed: int = 0
    missions_pending: int = 0
    missions_failed: int = 0
    failed_drones: int = 0
    total_mission_time_s: float = 0.0
    total_energy_wh: float = 0.0
    avg_response_time_s: float = 0.0
    operational_risk: float = 0.0
    solver_runtime_ms: float = 0.0
    solution_quality: float = 0.0
    score: float = 0.0
    rank: int = 1
    replanning_count: int = 0
    tasks_recovered: int = 0
    recovery_rate_pct: float = 100.0
    deadline_violations: int = 0
    airspace_conflicts: int = 0
    feasible: bool = True
    error: Optional[str] = None
