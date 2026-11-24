export type StrategyType = "greedy" | "classical" | "quantum" | "hybrid";
export type CameraMode = "orbit" | "topdown" | "follow" | "fpv" | "free";
export type PlacementMode = "none" | "add_target" | "set_waypoint";

export interface Building {
  id: string; kind: string; x: number; z: number;
  width: number; depth: number; height: number;
  color: string; has_helipad: boolean; roof_style: string;
}

export interface RoadSegment {
  id: string; start: [number, number]; end: [number, number];
  width: number; is_bridge: boolean; blocked: boolean;
}

export interface HazardZone {
  id: string; kind: "fire" | "flood" | "no_fly" | "blocked_area";
  x: number; z: number; radius: number; severity: number;
  altitude_ceiling: number; active: boolean;
}

export interface Station {
  id: string; name: string; kind: string;
  position: [number, number, number]; active: boolean; capacity: number;
}

export interface VehicleProp {
  id: string; kind: "ambulance" | "fire_truck" | "civilian";
  x: number; z: number; heading_rad: number;
  axis: "x" | "z"; speed_mps: number; road_pos: number;
}

export interface WeatherState {
  condition: string; wind_speed_mps: number; wind_direction_deg: number;
  rain_intensity: number; fog_density: number; day_mode: boolean;
}

export interface CityEnvironment {
  scenario_id: string; scenario_name: string; seed: number;
  world_size: number; city_density: number; building_density: number;
  buildings: Building[]; roads: RoadSegment[]; hazards: HazardZone[];
  stations: Station[]; trees: [number, number, number][];
  streetlights: [number, number][]; vehicles: VehicleProp[];
  river_z: number; river_width: number; weather: WeatherState;
}

export interface RoutePlan {
  route_id: string; drone_id: string; task_id: string | null;
  strategy: string; waypoints: [number, number, number][];
  distance_m: number; estimated_duration_s: number;
  estimated_energy_wh: number; risk_score: number;
  feasible: boolean; color_tag: string; replan_count: number;
}

export interface DroneState {
  id: string; drone_type: string; class_label: string;
  capabilities: string[]; camera: string[]; sensors: string[];
  battery_capacity_wh: number; remaining_battery_wh: number; battery_percent: number;
  max_payload_kg: number; current_payload_kg: number;
  max_speed_mps: number; cruise_speed_mps: number; cruise_altitude: number;
  home_station_id: string; home_position: [number, number, number];
  position: [number, number, number]; velocity: [number, number, number];
  groundspeed_mps: number; heading_rad: number; bank_rad: number; pitch_rad: number;
  power_draw_w: number; battery_temp_c: number; eta_seconds: number;
  status: string; health: number;
  assigned_task_ids: string[]; active_task_id: string | null;
  current_route: RoutePlan | null;
  total_distance_m: number; total_energy_used_wh: number; total_flight_time_s: number;
  tasks_completed: number; tasks_failed: number;
  failure_history: Record<string, unknown>[]; estimated_remaining_flight_s: number;
}

export interface RescueTask {
  id: string; name: string; task_type: string;
  location: [number, number, number];
  priority: "critical" | "high" | "medium" | "low";
  deadline_seconds: number; payload_required_kg: number;
  required_capabilities: string[]; service_time_seconds: number;
  risk_level: number; description: string; status: string;
  assigned_drone_id: string | null; created_at_sim_s: number;
  completed_at_sim_s: number | null; reassignment_count: number;
  deadline_violated: boolean; unassigned_reason: string | null;
}

export interface QuantumMetrics {
  executed: boolean; backend_name: string; num_qubits: number;
  circuit_depth: number; qaoa_layers: number; iterations: number;
  shots: number; best_bitstring: string; best_energy: number;
  execution_time_ms: number; candidates_evaluated: number;
  validation_passed: boolean; repaired_assignments: number;
  subproblem_tasks: string[]; subproblem_drones: string[];
  top_samples: { bitstring: string; count: number; energy: number }[];
  convergence_history?: { iter: number; energy: number }[];
}

export interface StrategyMetrics {
  strategy: StrategyType; status: string; planning_complete: boolean;
  missions_completed: number; missions_pending: number; missions_failed: number;
  failed_drones: number; total_mission_time_s: number; total_energy_wh: number;
  avg_response_time_s: number; operational_risk: number; solver_runtime_ms: number;
  solution_quality: number; score: number; rank: number; replanning_count: number;
  tasks_recovered: number; recovery_rate_pct: number; deadline_violations: number;
  airspace_conflicts: number; feasible: boolean; error: string | null;
}

export interface SimulationEvent {
  id: string; run_id: string; timestamp_iso: string; sim_time_s: number;
  category: string; event_type: string; message: string; entity_id: string | null;
}

export interface AnalyticsPoint {
  t: number; completed: number; energy_wh: number; avg_response_s: number;
  avg_battery_pct: number; distance_m: number; score: number;
}

export interface ActiveSimState {
  run_id: string; strategy: StrategyType; status: string; seed: number;
  sim_time_s: number; speed_multiplier: number; weather: WeatherState;
  hazards: HazardZone[]; stations: Station[]; drones: DroneState[];
  tasks: RescueTask[]; metrics: StrategyMetrics; quantum_metrics: QuantumMetrics | null;
  analytics: AnalyticsPoint[]; events: SimulationEvent[]; city?: CityEnvironment;
  station_utilization?: Record<string, { occupied: number; capacity: number; queued: number }>;
  fleet_alerts?: { drone_id: string; severity: string; reason: string }[];
  recovery_arcs?: RecoveryArc[];
}

export interface RecoveryArc {
  from_pos: [number, number, number];
  to_drone_id: string;
  task_id: string;
  created_at_s: number;
}

export interface GhostRoute {
  drone_id: string; strategy: StrategyType;
  waypoints: [number, number, number][]; color_tag: string;
}

export interface ServerPayload {
  mode: "single" | "benchmark";
  benchmark: {
    benchmark_id: string | null;
    active_view: StrategyType;
    leaderboard: StrategyMetrics[];
    active_state: ActiveSimState;
    ghost_routes: Record<string, GhostRoute[]>;
  };
}
