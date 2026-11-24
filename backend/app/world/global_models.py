from __future__ import annotations
import math
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lat: float  # -90 to 90
    lon: float  # -180 to 180
    elevation_m: float = 10.0


def geo_to_local(point: GeoPoint, origin: GeoPoint) -> Tuple[float, float, float]:
    """Deterministic equirectangular projection around a city/country origin (meters)."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * max(0.1, math.cos(math.radians(origin.lat)))
    x = (point.lon - origin.lon) * m_per_deg_lon
    z = -(point.lat - origin.lat) * m_per_deg_lat
    return (round(x, 2), round(point.elevation_m, 2), round(z, 2))


def local_to_geo(x: float, y: float, z: float, origin: GeoPoint) -> GeoPoint:
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * max(0.1, math.cos(math.radians(origin.lat)))
    lat = origin.lat - (z / m_per_deg_lat)
    lon = origin.lon + (x / m_per_deg_lon)
    return GeoPoint(lat=round(lat, 6), lon=round(lon, 6), elevation_m=round(y, 2))


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    r = 6371.0
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlon / 2) ** 2
    )
    return 2.0 * r * math.asin(min(1.0, math.sqrt(h)))


class SimulationMode(str, Enum):
    SANDBOX = "SANDBOX"
    DISASTER_RESPONSE = "DISASTER_RESPONSE"
    MULTI_COUNTRY = "MULTI_COUNTRY"
    BENCHMARK = "BENCHMARK"
    AI_COMMAND = "AI_COMMAND"
    TRAINING = "TRAINING"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    REPLAY = "REPLAY"
    STRESS_TEST = "STRESS_TEST"


class WeatherCondition(str, Enum):
    SUNNY = "SUNNY"
    CLOUDY = "CLOUDY"
    LIGHT_RAIN = "LIGHT_RAIN"
    HEAVY_RAIN = "HEAVY_RAIN"
    THUNDERSTORM = "THUNDERSTORM"
    STRONG_WIND = "STRONG_WIND"
    FOG = "FOG"
    HEAT = "HEAT"
    CYCLONE = "CYCLONE"


class DisasterType(str, Enum):
    FLOOD = "FLOOD"
    CYCLONE = "CYCLONE"
    FIRE = "FIRE"
    MULTI_HAZARD_CASCADE = "MULTI_HAZARD_CASCADE"
    EARTHQUAKE = "EARTHQUAKE"
    LANDSLIDE = "LANDSLIDE"
    WILDFIRE = "WILDFIRE"
    INDUSTRIAL_ACCIDENT = "INDUSTRIAL_ACCIDENT"
    POWER_OUTAGE = "POWER_OUTAGE"
    COMM_BLACKOUT = "COMM_BLACKOUT"
    HEATWAVE = "HEATWAVE"


class PersonSafetyState(str, Enum):
    SAFE_AT_HOME = "SAFE_AT_HOME"
    AWARE_OF_EMERGENCY = "AWARE_OF_EMERGENCY"
    REQUESTING_HELP = "REQUESTING_HELP"
    EVACUATING = "EVACUATING"
    WAITING_FOR_TRANSPORT = "WAITING_FOR_TRANSPORT"
    AT_SHELTER = "AT_SHELTER"
    AT_HOSPITAL = "AT_HOSPITAL"
    INJURED = "INJURED"
    RESCUED = "RESCUED"
    UNREACHABLE = "UNREACHABLE"
    NEEDS_SPECIAL_ASSISTANCE = "NEEDS_SPECIAL_ASSISTANCE"


class MobilityCategory(str, Enum):
    INDEPENDENT = "INDEPENDENT"
    ASSISTED_WALKING = "ASSISTED_WALKING"
    WHEELCHAIR_ACCESSIBLE = "WHEELCHAIR_ACCESSIBLE"
    NON_AMBULATORY = "NON_AMBULATORY"


class HospitalStatus(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    OVERLOADED = "OVERLOADED"
    PARTIALLY_OPERATIONAL = "PARTIALLY_OPERATIONAL"
    DAMAGED = "DAMAGED"
    POWER_FAILURE = "POWER_FAILURE"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"
    CLOSED = "CLOSED"


class AmbulanceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE_TO_PATIENT = "EN_ROUTE_TO_PATIENT"
    ON_SCENE = "ON_SCENE"
    TRANSPORTING = "TRANSPORTING"
    AT_HOSPITAL = "AT_HOSPITAL"
    RETURNING = "RETURNING"
    REFUELING = "REFUELING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class SwarmFormation(str, Enum):
    LINE = "LINE"
    V = "V"
    GRID = "GRID"
    CIRCLE = "CIRCLE"
    SEARCH_GRID = "SEARCH_GRID"
    PERIMETER = "PERIMETER"
    CLUSTER = "CLUSTER"
    CUSTOM_WAYPOINT_FORMATION = "CUSTOM_WAYPOINT_FORMATION"


class SwarmMode(str, Enum):
    AREA_SCAN = "AREA_SCAN"
    SURVIVOR_SEARCH = "SURVIVOR_SEARCH"
    MEDICAL_DELIVERY = "MEDICAL_DELIVERY"
    FLOOD_ASSESSMENT = "FLOOD_ASSESSMENT"
    FIRE_PERIMETER = "FIRE_PERIMETER"
    COMM_RELAY = "COMM_RELAY"
    COORDINATED_RESCUE = "COORDINATED_RESCUE"
    EMERGENCY_RECOVERY = "EMERGENCY_RECOVERY"


class TerrainCell(BaseModel):
    cell_id: str
    country_id: str
    row: int
    col: int
    center: GeoPoint
    elevation_m: float
    slope_deg: float
    surface_type: str  # urban, coastline, river, forest, mountain, farmland, desert, wetland
    soil_category: str
    vegetation_density: float
    drainage_capacity: float
    water_depth_m: float = 0.0
    fire_fuel_class: float = 0.3
    fire_intensity: float = 0.0
    climate_zone: str = "temperate"
    accessible: bool = True


class DistrictRecord(BaseModel):
    district_id: str
    city_id: str
    country_id: str
    name: str
    center: GeoPoint
    radius_km: float = 2.5
    zone_type: str  # residential, commercial, industrial, hospital_hub, waterfront, rural
    total_residents: int
    exposed_residents: int = 0
    evacuated_residents: int = 0
    injured_residents: int = 0
    unreachable_residents: int = 0
    vulnerable_residents: int = 0
    household_count: int = 0
    building_count: int = 0
    road_accessibility: float = 1.0  # 0.0 - 1.0
    flood_depth_m: float = 0.0
    fire_risk: float = 0.0
    power_available: bool = True
    comm_available: bool = True


class CityRecord(BaseModel):
    city_id: str
    country_id: str
    name: str
    is_capital: bool = False
    center: GeoPoint
    population: int
    districts: List[str] = Field(default_factory=list)
    elevation_m: float = 15.0
    coastal: bool = False
    airport_operational: bool = True


class BuildingRecord(BaseModel):
    building_id: str
    country_id: str
    city_id: str
    district_id: str
    category: str  # residential, apartment, commercial, office, school, hospital, warehouse, factory, shelter, station
    position: GeoPoint
    height_m: float
    floors: int
    capacity: int
    occupancy: int
    structural_condition: str = "INTACT"  # INTACT, DAMAGED, UNSAFE, COLLAPSED
    accessible: bool = True
    roof_suitable_for_drone: bool = True
    flood_exposure_m: float = 0.0
    fire_exposure: float = 0.0
    power_connected: bool = True
    water_connected: bool = True


class RoadEdge(BaseModel):
    road_id: str
    country_id: str
    city_id: str
    name: str
    category: str  # highway, main, secondary, local, bridge, tunnel
    start: GeoPoint
    end: GeoPoint
    length_km: float
    speed_limit_kph: float = 60.0
    capacity_vph: int = 1200
    is_bridge: bool = False
    accessible: bool = True
    flood_depth_m: float = 0.0
    blocked_reason: Optional[str] = None


class SyntheticPerson(BaseModel):
    person_id: str
    country_id: str
    city_id: str
    district_id: str
    household_id: str
    home_building_id: str
    age_band: str  # child, adult, senior
    occupation: str
    mobility: MobilityCategory = MobilityCategory.INDEPENDENT
    medical_vulnerability: str = "none"  # none, chronic, critical_care
    activity: str = "home"  # sleeping, commuting, working, studying, shopping, evacuating, sheltered
    movement_mode: str = "walking"
    safety_state: PersonSafetyState = PersonSafetyState.SAFE_AT_HOME
    location: GeoPoint
    assigned_shelter_id: Optional[str] = None
    assigned_hospital_id: Optional[str] = None
    triage_class: Optional[str] = None  # immediate, delayed, minor, expectant


class HouseholdRecord(BaseModel):
    household_id: str
    country_id: str
    city_id: str
    district_id: str
    home_building_id: str
    member_ids: List[str]
    resident_count: int
    has_vehicle: bool = True
    has_pets: bool = False
    pet_count: int = 0
    needs_assisted_transport: bool = False
    evacuation_status: str = "SAFE_AT_HOME"  # SAFE_AT_HOME, EVACUATING, EVACUATED, NEEDS_ASSISTANCE
    assigned_shelter_id: Optional[str] = None


class AnimalGroup(BaseModel):
    group_id: str
    country_id: str
    district_id: Optional[str] = None
    category: str  # domestic, livestock, wildlife
    species: str
    count: int
    exposed_count: int = 0
    evacuated_count: int = 0
    habitat: str
    location: GeoPoint
    shelter_needed: bool = False


class HospitalFacility(BaseModel):
    hospital_id: str
    country_id: str
    city_id: str
    district_id: str
    name: str
    location: GeoPoint
    total_beds: int
    occupied_beds: int
    emergency_staff: int
    ambulance_access: bool = True
    status: HospitalStatus = HospitalStatus.OPERATIONAL
    medical_kits: int = 400
    generator_hours_remaining: float = 48.0
    triage_load: int = 0

    @property
    def available_beds(self) -> int:
        return max(0, self.total_beds - self.occupied_beds)


class ShelterFacility(BaseModel):
    shelter_id: str
    country_id: str
    city_id: str
    district_id: str
    name: str
    location: GeoPoint
    max_occupancy: int
    current_occupancy: int = 0
    food_packages: int = 1200
    water_liters: float = 6000.0
    medical_kits: int = 120
    power_backup: bool = True
    accessible: bool = True
    status: str = "STANDBY"  # STANDBY, ACTIVE, FULL, DAMAGED

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.max_occupancy - self.current_occupancy)


class WarehouseInventory(BaseModel):
    warehouse_id: str
    country_id: str
    city_id: str
    name: str
    location: GeoPoint
    food_packages: int = 15000
    water_liters: float = 60000.0
    medical_kits: int = 2500
    first_aid_kits: int = 3000
    blankets: int = 4000
    fuel_liters: float = 25000.0
    generators: int = 25
    comm_devices: int = 150
    rescue_kits: int = 300
    reserved: Dict[str, float] = Field(default_factory=dict)


class AmbulanceUnit(BaseModel):
    ambulance_id: str
    country_id: str
    city_id: str
    home_station: str
    location: GeoPoint
    speed_kph: float = 65.0
    patient_capacity: int = 2
    staff_count: int = 3
    equipment_profile: str = "ALS"  # BLS, ALS, ICU_TRANSPORT
    fuel_pct: float = 95.0
    status: AmbulanceStatus = AmbulanceStatus.AVAILABLE
    assigned_district_id: Optional[str] = None
    destination_hospital_id: Optional[str] = None
    patients_onboard: int = 0


class FireRescueUnit(BaseModel):
    unit_id: str
    country_id: str
    city_id: str
    unit_type: str  # fire_truck, water_tanker, rescue_truck, rescue_boat, helicopter
    location: GeoPoint
    personnel_count: int = 6
    water_liters: float = 4000.0
    status: str = "AVAILABLE"  # AVAILABLE, DISPATCHED, ON_SCENE, RETURNING, OUT_OF_SERVICE
    assigned_event_id: Optional[str] = None


class GlobalDroneUnit(BaseModel):
    drone_id: str
    country_id: str
    city_id: str
    home_station: str
    category: str  # SURVEILLANCE, MEDICAL_DELIVERY, SEARCH_AND_RESCUE, HEAVY_LIFT, COMMUNICATION_RELAY, FIRE_MONITORING, FLOOD_MONITORING
    location: GeoPoint
    altitude_m: float = 0.0
    speed_mps: float = 32.0
    battery_pct: float = 100.0
    battery_wh: float = 750.0
    max_payload_kg: float = 2.5
    current_load_kg: float = 0.0
    sensors: List[str] = Field(default_factory=lambda: ["rgb", "thermal", "lidar"])
    capabilities: List[str] = Field(default_factory=list)
    status: str = "AVAILABLE"  # AVAILABLE, ASSIGNED, IN_FLIGHT, DELIVERING, RETURNING, CHARGING, FAILED, DESTROYED
    assigned_mission_id: Optional[str] = None
    swarm_id: Optional[str] = None
    route: List[GeoPoint] = Field(default_factory=list)
    comm_connected: bool = True
    failure_history: List[Dict[str, Any]] = Field(default_factory=list)


class SwarmOperation(BaseModel):
    swarm_id: str
    country_id: str
    name: str
    mode: SwarmMode
    formation: SwarmFormation
    drone_ids: List[str]
    target_center: GeoPoint
    coverage_radius_km: float = 3.0
    spacing_m: float = 45.0
    altitude_band_m: Tuple[float, float] = (75.0, 125.0)
    status: str = "PREPARED"  # PREPARED, ACTIVE, COMPLETED, STOPPED, RECOVERING
    progress_pct: float = 0.0
    created_at: str = ""
    objective: str = ""


class DisasterEvent(BaseModel):
    event_id: str
    country_id: str
    city_id: Optional[str] = None
    district_ids: List[str] = Field(default_factory=list)
    disaster_type: DisasterType
    name: str
    origin: GeoPoint
    radius_km: float = 8.0
    polygon: List[GeoPoint] = Field(default_factory=list)
    severity: float = 0.75  # 0.1 - 1.0
    growth_rate: float = 0.05
    wind_kph: float = 45.0
    wind_direction_deg: float = 225.0
    rainfall_mm_hr: float = 40.0
    heading_deg: float = 310.0
    travel_speed_kph: float = 18.0
    start_sim_time_s: float = 0.0
    duration_s: float = 7200.0
    status: str = "ACTIVE"  # PREPARED, ACTIVE, PAUSED, CONTAINED, STOPPED
    affected_population: int = 0
    evacuation_demand: int = 0
    estimated_injuries: int = 0
    blocked_roads: int = 0
    affected_buildings: int = 0
    parent_event_id: Optional[str] = None
    triggered_cascades: List[str] = Field(default_factory=list)


class CountryProfile(BaseModel):
    country_id: str
    name: str
    archetype: str
    flag_code: str
    color: str
    capital_city_id: str
    capital_name: str
    center: GeoPoint
    boundary: List[GeoPoint]
    land_area_km2: float
    terrain_profile: str
    climate_zone: str
    population_scale: int
    vulnerable_hazards: List[str]
    readiness_score: float = 82.0
    comm_uptime_pct: float = 99.5
    power_grid_pct: float = 99.0


class RouteCandidate(BaseModel):
    route_id: str
    drone_id: str
    objective: str  # FASTEST, LOWEST_ENERGY, SAFEST, HIGHEST_RELIABILITY, BALANCED, WIND_OPTIMIZED, EMERGENCY
    waypoints: List[GeoPoint]
    waypoint_count: int
    total_distance_km: float
    estimated_duration_min: float
    predicted_battery_used_pct: float
    battery_remaining_pct: float
    return_reserve_ok: bool
    max_altitude_m: float
    avg_altitude_m: float
    min_clearance_m: float
    risk_score: float
    hazard_intersections: int
    weather_impact_factor: float
    comm_quality: float
    feasible: bool
    rejection_reason: Optional[str] = None
    rank: int = 0
    score: float = 0.0


class ApprovalRequest(BaseModel):
    approval_id: str
    operation_type: str
    title: str
    description: str
    country_id: Optional[str] = None
    affected_locations: List[str] = Field(default_factory=list)
    affected_entities: List[str] = Field(default_factory=list)
    required_resources: Dict[str, Any] = Field(default_factory=dict)
    expected_outcomes: List[str] = Field(default_factory=list)
    operational_risks: List[str] = Field(default_factory=list)
    safety_checks: Dict[str, bool] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    world_version_at_proposal: int = 1
    created_at: str = ""
    expires_at: str = ""
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, MODIFIED, EXECUTED, STALE, CANCELLED
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
