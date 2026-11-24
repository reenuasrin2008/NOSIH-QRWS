export interface GeoPoint {
  lat: number;
  lon: number;
  elevation_m: number;
}

export interface GlobalClockInfo {
  sim_time_s: number;
  day: number;
  clock_hhmm: string;
  day_phase: string;
  sun_elevation_deg: number;
  speed_multiplier: number;
  paused: boolean;
  emergency_stopped: boolean;
  mode: string;
  weather: string;
  world_version: number;
}

export interface CountrySummary {
  country_id: string;
  name: string;
  archetype: string;
  flag_code: string;
  color: string;
  capital_city_id: string;
  capital_name: string;
  center: GeoPoint;
  boundary: GeoPoint[];
  land_area_km2: number;
  terrain_profile: string;
  climate_zone: string;
  population_scale: number;
  vulnerable_hazards: string[];
  readiness_score: number;
  total_population: number;
  exposed_population: number;
  evacuated_population: number;
  injured_population: number;
  active_disasters: number;
  hospitals_operational: number;
  hospitals_total: number;
  available_beds: number;
  ambulances_available: number;
  ambulances_total: number;
  drones_available: number;
  drones_active: number;
  drones_total: number;
  shelter_remaining_capacity: number;
}

export interface DisasterEvent {
  event_id: string;
  country_id: string;
  disaster_type: string;
  name: string;
  origin: GeoPoint;
  radius_km: number;
  severity: number;
  wind_kph: number;
  rainfall_mm_hr: number;
  status: string;
  affected_population: number;
  evacuation_demand: number;
  estimated_injuries: number;
  blocked_roads: number;
  affected_buildings: number;
}

export interface GlobalOverview {
  scenario_id: string;
  seed: number;
  selected_country_id: string;
  clock: GlobalClockInfo;
  totals: {
    countries: number;
    countries_affected: number;
    active_disasters: number;
    total_population: number;
    people_at_risk: number;
    people_evacuated: number;
    drones_total: number;
    drones_active: number;
    drones_available: number;
    ambulances_available: number;
    ambulances_total: number;
    hospitals_operational: number;
    hospitals_total: number;
    active_swarms: number;
  };
  countries: CountrySummary[];
  active_disasters: DisasterEvent[];
  frontends: Record<string, { connected: boolean; connections: number }>;
}

export interface ApprovalItem {
  approval_id: string;
  operation_type: string;
  title: string;
  description: string;
  country_id?: string;
  required_resources: Record<string, any>;
  expected_outcomes: string[];
  operational_risks: string[];
  parameters: Record<string, any>;
  world_version_at_proposal: number;
  created_at: string;
  status: string;
  decided_by?: string;
  execution_result?: Record<string, any>;
}

export interface ExecutionTraceStep {
  timestamp: string;
  tool: string;
  arguments: Record<string, any>;
  duration_ms: number;
  status: string;
  summary: string;
}

export interface JarvisReply {
  reply_id: string;
  timestamp: string;
  session_id: string;
  user_message: string;
  assistant_message: string;
  spoken_summary: string;
  provider: string;
  model: string;
  latency_ms: number;
  globe_state: string;
  context: Record<string, any>;
  execution_trace: ExecutionTraceStep[];
  structured_cards: Array<{ type: string; data: any }>;
  frontend_commands: Array<Record<string, any>>;
  pending_approval?: ApprovalItem | null;
}

export interface ProviderStatusPayload {
  primary_provider: string;
  fallback_provider: string;
  last_latency_ms: number;
  providers: Record<
    string,
    {
      status: string;
      configured_keys: number;
      active_keys: number;
      total_requests: number;
      total_errors: number;
      last_error?: string | null;
      model: string;
    }
  >;
}
