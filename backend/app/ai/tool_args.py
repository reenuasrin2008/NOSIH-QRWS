from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Type

import pydantic
from pydantic import BaseModel, Field

import app.core.compat  # noqa: F401 - ensures Pydantic v1/v2 model_dump compatibility
from app.world.global_models import DisasterType, SwarmFormation, SwarmMode

_PYDANTIC_V2 = int(pydantic.__version__.split(".")[0]) >= 2

# ---------------------------------------------------------------------------
# Canonical ID Regex Patterns
# ---------------------------------------------------------------------------
COUNTRY_ID_PATTERN = r"^COUNTRY-0[1-7]$"
HOSPITAL_ID_PATTERN = r"^HOSP-\d{2}-\d{2}$"
DRONE_ID_PATTERN = r"^D-\d{2}(?:-\d{2})?$"
DISTRICT_ID_PATTERN = r"^COUNTRY-0[1-7]-CITY-\d{2}-DIST-\d{2}$"
EVENT_ID_PATTERN = r"^DIS-[A-Z0-9-]+$"
ROAD_ID_PATTERN = r"^COUNTRY-0[1-7]-CITY-\d{2}-RD-\d{2}$"
APPROVAL_ID_PATTERN = r"^APR-[A-Z0-9]+$"


def _regex_field(
    default: Any = None,
    *,
    pattern: str,
    description: str = "",
    **kwargs: Any,
) -> Any:
    """Create a Pydantic Field with regex validation compatible with both Pydantic v1 and v2."""
    if _PYDANTIC_V2:
        kwargs["pattern"] = pattern
    else:
        kwargs["regex"] = pattern
    if description:
        kwargs["description"] = description
    return Field(default, **kwargs)


def _country_id_field(
    default: Optional[str] = None,
    description: str = "Country ID (COUNTRY-01 through COUNTRY-07).",
) -> Any:
    return _regex_field(default, pattern=COUNTRY_ID_PATTERN, description=description)


# ---------------------------------------------------------------------------
# Typed Enum Subclasses for Tool Parameters
# ---------------------------------------------------------------------------
class RouteObjective(str, Enum):
    FASTEST = "FASTEST"
    LOWEST_ENERGY = "LOWEST_ENERGY"
    SAFEST = "SAFEST"
    HIGHEST_RELIABILITY = "HIGHEST_RELIABILITY"
    BALANCED = "BALANCED"
    WIND_OPTIMIZED = "WIND_OPTIMIZED"
    EMERGENCY = "EMERGENCY"


class SensorType(str, Enum):
    THERMAL = "thermal"
    LIDAR = "lidar"
    ACOUSTIC = "acoustic"
    GAS_SENSOR = "gas_sensor"
    SONAR = "sonar"
    RF_RELAY = "rf_relay"
    RGB = "rgb"


class MutualAidResourceType(str, Enum):
    AMBULANCES = "ambulances"
    DRONES = "drones"
    FOOD = "food"


class ApprovalStatusFilter(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


# Re-exported for convenience
SwarmModeArg = SwarmMode
SwarmFormationArg = SwarmFormation
DisasterTypeArg = DisasterType


# ---------------------------------------------------------------------------
# Base Tool Arguments Model (Pydantic v1 & v2 Compatible)
# ---------------------------------------------------------------------------
def _resolve_refs_and_harden(schema: Dict[str, Any], defs: Dict[str, Any]) -> Dict[str, Any]:
    """Inline $ref definitions and enforce additionalProperties=False on all object nodes."""
    if not isinstance(schema, dict):
        return schema

    node = dict(schema)

    # Resolve direct $ref
    if "$ref" in node:
        ref_path = node.pop("$ref")
        ref_name = ref_path.rsplit("/", 1)[-1]
        target = defs.get(ref_name, {})
        resolved = _resolve_refs_and_harden(target, defs)
        # Preserve field-level metadata (e.g. description, default)
        merged = dict(resolved)
        for k, v in node.items():
            merged[k] = v
        node = merged

    # Handle Pydantic v1 single-element allOf: [{"$ref": ...}] wrapper (for Enums / nested models with descriptions)
    if "allOf" in node and isinstance(node["allOf"], list):
        if len(node["allOf"]) == 1:
            resolved = _resolve_refs_and_harden(node["allOf"][0], defs)
            node.pop("allOf")
            merged = dict(resolved)
            for k, v in node.items():
                merged[k] = v
            node = merged
        else:
            node["allOf"] = [_resolve_refs_and_harden(item, defs) for item in node["allOf"]]

    # Handle Pydantic v2 Optional[...] -> anyOf: [{...}, {"type": "null"}]
    if "anyOf" in node and isinstance(node["anyOf"], list):
        non_null = [item for item in node["anyOf"] if not (isinstance(item, dict) and item.get("type") == "null")]
        if len(non_null) == 1:
            resolved = _resolve_refs_and_harden(non_null[0], defs)
            node.pop("anyOf")
            merged = dict(resolved)
            for k, v in node.items():
                merged[k] = v
            node = merged
        else:
            node["anyOf"] = [_resolve_refs_and_harden(item, defs) for item in node["anyOf"]]

    if "oneOf" in node and isinstance(node["oneOf"], list):
        node["oneOf"] = [_resolve_refs_and_harden(item, defs) for item in node["oneOf"]]

    # Recurse into properties and items
    if "properties" in node and isinstance(node["properties"], dict):
        node["properties"] = {
            k: _resolve_refs_and_harden(v, defs) for k, v in node["properties"].items()
        }
    if "items" in node and isinstance(node["items"], dict):
        node["items"] = _resolve_refs_and_harden(node["items"], defs)

    if node.get("type") == "object":
        node["additionalProperties"] = False
        node.setdefault("properties", {})
        node.setdefault("required", [])

    # Drop local definitions blocks after inlining
    node.pop("definitions", None)
    node.pop("$defs", None)
    return node


class BaseToolArgs(BaseModel):
    """Strict base model for JARVIS tool arguments (forbids unknown keys on v1 & v2)."""

    if _PYDANTIC_V2:
        model_config = {"extra": "forbid", "use_enum_values": True}
    else:
        class Config:
            extra = "forbid"
            use_enum_values = True

    @classmethod
    def json_schema_dict(cls) -> Dict[str, Any]:
        """Return a strict JSON-Schema dict with additionalProperties=False guaranteed."""
        if _PYDANTIC_V2 and hasattr(cls, "model_json_schema"):
            raw = cls.model_json_schema(mode="serialization")
        else:
            raw = cls.schema()

        defs: Dict[str, Any] = {}
        if isinstance(raw.get("definitions"), dict):
            defs.update(raw["definitions"])
        if isinstance(raw.get("$defs"), dict):
            defs.update(raw["$defs"])

        cleaned = _resolve_refs_and_harden(raw, defs)
        cleaned["type"] = "object"
        cleaned["additionalProperties"] = False
        cleaned.setdefault("properties", {})
        cleaned.setdefault("required", [])
        return cleaned

    def to_handler_dict(self) -> Dict[str, Any]:
        """Serialize validated args to a plain dict with enum values unpacked."""
        data = self.model_dump() if _PYDANTIC_V2 else self.dict()
        return _unpack_enums(data)


def _unpack_enums(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _unpack_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unpack_enums(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Nested Helper Models
# ---------------------------------------------------------------------------
class WhatIfArgs(BaseToolArgs):
    ambulance_loss_ratio: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Fraction of ambulances unavailable (0.0 to 1.0)."
    )
    drone_availability_ratio: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Fraction of drone fleet available (0.0 to 1.0)."
    )
    road_closure_ratio: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Fraction of roads closed or flooded (0.0 to 1.0)."
    )


class WaypointArg(BaseToolArgs):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Waypoint latitude (-90 to 90).")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Waypoint longitude (-180 to 180).")
    elevation_m: float = Field(85.0, ge=0.0, le=5000.0, description="Waypoint elevation in meters.")


# ---------------------------------------------------------------------------
# Navigation & World Camera (4)
# ---------------------------------------------------------------------------
class ViewGlobalWorldArgs(BaseToolArgs):
    pass


class ViewCountryArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class FocusHospitalArgs(BaseToolArgs):
    hospital_id: Optional[str] = _regex_field(
        None, pattern=HOSPITAL_ID_PATTERN, description="Hospital ID (e.g. HOSP-01-11)."
    )
    country_id: Optional[str] = _country_id_field()


class FocusDroneArgs(BaseToolArgs):
    drone_id: Optional[str] = _regex_field(
        None, pattern=DRONE_ID_PATTERN, description="Drone ID (e.g. D-03-01)."
    )
    country_id: Optional[str] = _country_id_field()


# ---------------------------------------------------------------------------
# Global, Country, City, District, Infrastructure & Population (12)
# ---------------------------------------------------------------------------
class GetGlobalWorldOverviewArgs(BaseToolArgs):
    pass


class GetCountryListArgs(BaseToolArgs):
    pass


class GetCountryStatusArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetCountryCitiesArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetDistrictDetailsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    district_id: Optional[str] = _regex_field(
        None, pattern=DISTRICT_ID_PATTERN, description="Optional specific district ID (e.g. COUNTRY-03-CITY-01-DIST-01)."
    )


class GetBuildingsSummaryArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetRoadNetworkArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    road_id: Optional[str] = _regex_field(
        None, pattern=ROAD_ID_PATTERN, description="Optional specific road ID (e.g. COUNTRY-03-CITY-01-RD-01)."
    )


class GetBlockedRoadsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    all_countries: bool = Field(False, description="If true, inspect all 7 countries.")


class GetPopulationSummaryArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetHouseholdStatisticsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetAnimalPopulationArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetSimulationClockArgs(BaseToolArgs):
    pass


# ---------------------------------------------------------------------------
# Disasters & Cascades (4)
# ---------------------------------------------------------------------------
class GetActiveDisastersArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetDisasterImpactArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    event_id: Optional[str] = _regex_field(
        None, pattern=EVENT_ID_PATTERN, description="Optional specific disaster event ID (e.g. DIS-CYC-7C01C5)."
    )


class GetCascadeGraphArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class AnalyzeDisasterArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


# ---------------------------------------------------------------------------
# Medical, Fire & Logistics (9)
# ---------------------------------------------------------------------------
class GetHospitalStatusArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetAvailableBedsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    all_countries: bool = Field(False, description="If true, include hospitals across all 7 countries.")


class GetAmbulanceFleetArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class CalculateAmbulanceRequirementsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    window_hours: float = Field(
        4.0, ge=0.5, le=48.0, description="Planning window in hours (0.5 to 48.0, default 4.0)."
    )


class GetFireUnitsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetShelterCapacityArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetWarehouseInventoryArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class CalculateResourceRequirementsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    horizon_hours: float = Field(
        24.0, ge=1.0, le=168.0, description="Planning horizon in hours (1 to 168, default 24.0)."
    )


class GetResourceShortagesArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    horizon_hours: float = Field(
        24.0, ge=1.0, le=168.0, description="Planning horizon in hours (1 to 168, default 24.0)."
    )


# ---------------------------------------------------------------------------
# Drones, Swarms & Route Intelligence (7)
# ---------------------------------------------------------------------------
class GetDroneFleetArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class GetAvailableDronesArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    min_battery_pct: float = Field(
        25.0, ge=0.0, le=100.0, description="Minimum battery percentage (0 to 100, default 25.0)."
    )
    sensor: Optional[SensorType] = Field(
        None, description="Optional required sensor (thermal, lidar, acoustic, gas_sensor, sonar, rf_relay, rgb)."
    )


class GetLowBatteryDronesArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    threshold: float = Field(
        35.0, ge=1.0, le=100.0, description="Battery percentage threshold (1 to 100, default 35.0)."
    )


class GetSwarmStatusArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class CompareDronesToDestinationArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    hospital_id: Optional[str] = _regex_field(
        None, pattern=HOSPITAL_ID_PATTERN, description="Optional target hospital ID (e.g. HOSP-01-11)."
    )
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Optional target latitude.")
    lon: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Optional target longitude.")
    destination_label: Optional[str] = Field(None, description="Label for destination.")
    objective: RouteObjective = Field(
        RouteObjective.BALANCED,
        description="Optimization objective (FASTEST, LOWEST_ENERGY, SAFEST, HIGHEST_RELIABILITY, BALANCED, WIND_OPTIMIZED, EMERGENCY).",
    )
    payload_kg: float = Field(1.0, ge=0.0, le=50.0, description="Mission payload mass in kg.")
    required_sensor: Optional[SensorType] = Field(None, description="Optional required onboard sensor.")


class PlanMultistopMissionArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    points: Optional[List[WaypointArg]] = Field(None, description="Optional ordered list of waypoint coordinates.")
    sensor_type: SensorType = Field(SensorType.THERMAL, description="Required sensor (default thermal).")
    objective: RouteObjective = Field(
        RouteObjective.LOWEST_ENERGY, description="Optimization objective (default LOWEST_ENERGY)."
    )


class GetRouteLogsArgs(BaseToolArgs):
    limit: int = Field(50, ge=1, le=500, description="Maximum number of log entries (1 to 500, default 50).")


# ---------------------------------------------------------------------------
# Innovations, Governance, Persistence & Audit (8)
# ---------------------------------------------------------------------------
class EvaluateRescueEquityArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class FindMutualAidOptionsArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    resource_type: MutualAidResourceType = Field(
        MutualAidResourceType.AMBULANCES, description="Resource type: ambulances, drones, or food."
    )
    quantity: int = Field(8, ge=1, le=50, description="Requested transfer quantity (1 to 50).")


class RunCounterfactualComparisonArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    what_if: Optional[WhatIfArgs] = Field(
        None, description="Optional what-if parameter overrides (ambulance_loss_ratio, drone_availability_ratio, road_closure_ratio)."
    )


class ListPlaybooksArgs(BaseToolArgs):
    pass


class GetEventTimelineArgs(BaseToolArgs):
    limit: int = Field(40, ge=1, le=500, description="Maximum number of events (1 to 500, default 40).")
    category: Optional[str] = Field(None, description="Optional event category filter.")
    country_id: Optional[str] = _country_id_field()


class GetAuditLogsArgs(BaseToolArgs):
    limit: int = Field(50, ge=1, le=500, description="Maximum number of log entries (1 to 500, default 50).")


class ListPendingApprovalsArgs(BaseToolArgs):
    status: Optional[ApprovalStatusFilter] = Field(
        ApprovalStatusFilter.PENDING, description="Filter by status: PENDING, APPROVED, EXECUTED, REJECTED, or MODIFIED."
    )
    approval_id: Optional[str] = _regex_field(
        None, pattern=APPROVAL_ID_PATTERN, description="Optional specific approval ID (e.g. APR-1A2B3C4D)."
    )


class SaveWorldLocalArgs(BaseToolArgs):
    filename: str = Field(
        "world_snapshot.json",
        min_length=1,
        max_length=128,
        description="Output JSON filename (default world_snapshot.json).",
    )


# ---------------------------------------------------------------------------
# State-Changing Approval-Gated Action Tools (6)
# ---------------------------------------------------------------------------
class PrepareDisasterEventArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    disaster_type: DisasterType = Field(
        DisasterType.FLOOD,
        description="Disaster type (FLOOD, CYCLONE, FIRE, WILDFIRE, EARTHQUAKE, LANDSLIDE, etc.).",
    )
    severity: float = Field(0.78, ge=0.1, le=1.0, description="Severity from 0.1 to 1.0.")
    radius_km: float = Field(11.0, ge=1.0, le=50.0, description="Impact radius in km (1.0 to 50.0).")


class PrepareSwarmOperationArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    drone_count: int = Field(8, ge=1, le=30, description="Number of drones to deploy (1 to 30).")
    mode: SwarmMode = Field(
        SwarmMode.AREA_SCAN,
        description="Swarm operational mode (AREA_SCAN, SURVIVOR_SEARCH, MEDICAL_DELIVERY, FLOOD_ASSESSMENT, FIRE_PERIMETER, COMM_RELAY, COORDINATED_RESCUE, EMERGENCY_RECOVERY).",
    )
    formation: SwarmFormation = Field(
        SwarmFormation.SEARCH_GRID,
        description="Swarm formation (SEARCH_GRID, GRID, LINE, V, CIRCLE, PERIMETER, CLUSTER, CUSTOM_WAYPOINT_FORMATION).",
    )


class PrepareAmbulanceDispatchArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    count: int = Field(6, ge=1, le=50, description="Number of ambulances to dispatch (1 to 50).")


class PrepareCrossCountryAidArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    donor_country_id: str = _country_id_field(
        default="COUNTRY-05", description="Donor country ID (COUNTRY-01 through COUNTRY-07)."
    )
    resource_type: MutualAidResourceType = Field(
        MutualAidResourceType.AMBULANCES, description="Resource type: ambulances, drones, or food."
    )
    quantity: int = Field(6, ge=1, le=50, description="Quantity to transfer (1 to 50).")


class PrepareComprehensiveRescuePlanArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()


class PrepareDroneFailureArgs(BaseToolArgs):
    country_id: Optional[str] = _country_id_field()
    drone_id: Optional[str] = _regex_field(
        None, pattern=DRONE_ID_PATTERN, description="Target drone ID (e.g. D-03-01)."
    )


# ---------------------------------------------------------------------------
# Complete 50-Tool Args Model & Description Registry
# ---------------------------------------------------------------------------
TOOL_ARGS_MODELS: Dict[str, Type[BaseToolArgs]] = {
    # Navigation & World Camera (4)
    "view_global_world": ViewGlobalWorldArgs,
    "view_country": ViewCountryArgs,
    "focus_hospital": FocusHospitalArgs,
    "focus_drone": FocusDroneArgs,
    # Global, Country, City, District, Infrastructure & Population (12)
    "get_global_world_overview": GetGlobalWorldOverviewArgs,
    "get_country_list": GetCountryListArgs,
    "get_country_status": GetCountryStatusArgs,
    "get_country_cities": GetCountryCitiesArgs,
    "get_district_details": GetDistrictDetailsArgs,
    "get_buildings_summary": GetBuildingsSummaryArgs,
    "get_road_network": GetRoadNetworkArgs,
    "get_blocked_roads": GetBlockedRoadsArgs,
    "get_population_summary": GetPopulationSummaryArgs,
    "get_household_statistics": GetHouseholdStatisticsArgs,
    "get_animal_population": GetAnimalPopulationArgs,
    "get_simulation_clock": GetSimulationClockArgs,
    # Disasters & Cascades (4)
    "get_active_disasters": GetActiveDisastersArgs,
    "get_disaster_impact": GetDisasterImpactArgs,
    "get_cascade_graph": GetCascadeGraphArgs,
    "analyze_disaster": AnalyzeDisasterArgs,
    # Medical, Fire & Logistics (9)
    "get_hospital_status": GetHospitalStatusArgs,
    "get_available_beds": GetAvailableBedsArgs,
    "get_ambulance_fleet": GetAmbulanceFleetArgs,
    "calculate_ambulance_requirements": CalculateAmbulanceRequirementsArgs,
    "get_fire_units": GetFireUnitsArgs,
    "get_shelter_capacity": GetShelterCapacityArgs,
    "get_warehouse_inventory": GetWarehouseInventoryArgs,
    "calculate_resource_requirements": CalculateResourceRequirementsArgs,
    "get_resource_shortages": GetResourceShortagesArgs,
    # Drones, Swarms & Route Intelligence (7)
    "get_drone_fleet": GetDroneFleetArgs,
    "get_available_drones": GetAvailableDronesArgs,
    "get_low_battery_drones": GetLowBatteryDronesArgs,
    "get_swarm_status": GetSwarmStatusArgs,
    "compare_drones_to_destination": CompareDronesToDestinationArgs,
    "plan_multistop_mission": PlanMultistopMissionArgs,
    "get_route_logs": GetRouteLogsArgs,
    # Innovations, Governance, Persistence & Audit (8)
    "evaluate_rescue_equity": EvaluateRescueEquityArgs,
    "find_mutual_aid_options": FindMutualAidOptionsArgs,
    "run_counterfactual_comparison": RunCounterfactualComparisonArgs,
    "list_playbooks": ListPlaybooksArgs,
    "get_event_timeline": GetEventTimelineArgs,
    "get_audit_logs": GetAuditLogsArgs,
    "list_pending_approvals": ListPendingApprovalsArgs,
    "save_world_local": SaveWorldLocalArgs,
    # State-changing Approval-Gated Action Tools (6)
    "prepare_disaster_event": PrepareDisasterEventArgs,
    "prepare_swarm_operation": PrepareSwarmOperationArgs,
    "prepare_ambulance_dispatch": PrepareAmbulanceDispatchArgs,
    "prepare_cross_country_aid": PrepareCrossCountryAidArgs,
    "prepare_comprehensive_rescue_plan": PrepareComprehensiveRescuePlanArgs,
    "prepare_drone_failure": PrepareDroneFailureArgs,
}

TOOL_DESCRIPTIONS: Dict[str, str] = {
    "view_global_world": "Focus the 3D World Command camera on the full 7-country continent.",
    "view_country": "Focus the 3D World Command camera on a specific country.",
    "focus_hospital": "Focus the 3D World Command camera on a specific hospital.",
    "focus_drone": "Focus the 3D World Command camera on a specific drone.",
    "get_global_world_overview": "Retrieve planetary totals, clock, active disasters, and summaries for all 7 countries.",
    "get_country_list": "List all 7 countries with readiness, population, and disaster counts.",
    "get_country_status": "Retrieve comprehensive live status, facilities, roads, and analyses for a country.",
    "get_country_cities": "List all cities in a country with population, coordinates, and capital flag.",
    "get_district_details": "Retrieve district-level population, exposure, flood depth, fire risk, and accessibility.",
    "get_buildings_summary": "Summarize building counts, categories, structural damage, and accessibility in a country.",
    "get_road_network": "List all road edges and bridges in a country with accessibility and flood status.",
    "get_blocked_roads": "List blocked or flooded roads and bridges with closure reasons.",
    "get_population_summary": "Summarize total, exposed, evacuated, injured, and vulnerable residents in a country.",
    "get_household_statistics": "Retrieve household counts, vehicle access, pets, assisted transport needs, and evacuation status.",
    "get_animal_population": "Retrieve domestic, livestock, and wildlife animal populations and disaster exposure.",
    "get_simulation_clock": "Retrieve current planetary simulation clock, day phase, speed multiplier, and weather.",
    "get_active_disasters": "List active disasters globally or filtered by country.",
    "get_disaster_impact": "Retrieve detailed disaster impact metrics including exposed residents, injuries, blocked roads, and damaged buildings.",
    "get_cascade_graph": "Retrieve the disaster cascade prediction graph (nodes and causal edges) for a country.",
    "analyze_disaster": "Run full live disaster analysis for a country including medical, resource, and cascade status.",
    "get_hospital_status": "Retrieve hospital operational status, bed occupancy, available beds, and triage loads.",
    "get_available_beds": "Rank open hospitals by available bed capacity in a country or across all 7 countries.",
    "get_ambulance_fleet": "Retrieve ambulance fleet inventory, availability, and equipment profiles for a country.",
    "calculate_ambulance_requirements": "Calculate required ambulance fleet, triage demand, and deficit for a planning window.",
    "get_fire_units": "Retrieve fire and rescue units (trucks, tankers, boats, helicopters) and deployment status.",
    "get_shelter_capacity": "Retrieve relief shelter occupancy, remaining capacity, and on-site supplies.",
    "get_warehouse_inventory": "Retrieve central logistics depot inventory totals (food, water, medical kits, fuel, generators).",
    "calculate_resource_requirements": "Calculate 24h/horizon food, water, medical kit, and shelter requirements vs live stock.",
    "get_resource_shortages": "Identify active shortages and depletion warnings across food, water, medical kits, shelters, and ambulances.",
    "get_drone_fleet": "Retrieve all autonomous drones in a country with status and category breakdown.",
    "get_available_drones": "List available drones meeting battery and optional sensor requirements.",
    "get_low_battery_drones": "List drones whose battery percentage is below a given threshold.",
    "get_swarm_status": "Retrieve active and completed drone swarm operations.",
    "compare_drones_to_destination": "Run Yen's K-shortest 3D route comparison across eligible drones to a hospital or coordinate.",
    "plan_multistop_mission": "Plan a multi-stop sensor survey drone mission with battery return feasibility.",
    "get_route_logs": "Retrieve recent 3D route exploration solver logs and execution timings.",
    "evaluate_rescue_equity": "Evaluate district-level rescue equity scores and flag underserved exposed communities.",
    "find_mutual_aid_options": "Find neighboring countries with surplus ambulances, drones, or food for cross-country mutual aid.",
    "run_counterfactual_comparison": "Run deterministic counterfactual what-if comparison across 4 rescue strategies.",
    "list_playbooks": "List all 24 standardized disaster response playbooks in the catalog.",
    "get_event_timeline": "Retrieve recent authoritative world events from the event bus.",
    "get_audit_logs": "Retrieve approval engine audit logs and JARVIS tool execution logs.",
    "list_pending_approvals": "List operator approval requests filtered by status (default PENDING).",
    "save_world_local": "Persist a zero-database local JSON snapshot of the current planetary world state.",
    "prepare_disaster_event": "Prepare an operator-approval proposal to inject a simulated disaster event.",
    "prepare_swarm_operation": "Prepare an operator-approval proposal to deploy a coordinated drone swarm.",
    "prepare_ambulance_dispatch": "Prepare an operator-approval proposal to dispatch ambulances in a country.",
    "prepare_cross_country_aid": "Prepare an operator-approval proposal for cross-country mutual aid resource transfer.",
    "prepare_comprehensive_rescue_plan": "Generate an adapted multi-subsystem rescue plan and create an operator approval request.",
    "prepare_drone_failure": "Prepare an operator-approval proposal to simulate drone destruction and automatic swarm recovery.",
}
