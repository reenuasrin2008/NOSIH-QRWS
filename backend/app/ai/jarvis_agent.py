from __future__ import annotations
from collections import deque
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.ai.tool_args import TOOL_ARGS_MODELS, TOOL_DESCRIPTIONS
from app.approvals.engine import PLAYBOOK_CATALOG, ApprovalEngine
from app.core.compat import to_dict, utc_now_iso
from app.database.repository import ExperimentRepository
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import AmbulanceStatus, DisasterType, GeoPoint, HospitalStatus

# Pre-compiled regex patterns for sub-millisecond entity extraction
_RE_COUNTRY_NUM = re.compile(r"\bcountry\s*[-#]?\s*0?([1-7])\b", re.IGNORECASE)
_RE_HOSPITAL_ID = re.compile(r"\b(HOSP-\d{2}-\d{2})\b", re.IGNORECASE)
_RE_DRONE_ID = re.compile(r"\b(D-\d{2}-\d{2}|D-\d{2})\b", re.IGNORECASE)
_RE_DISTRICT_ID = re.compile(r"\b(COUNTRY-\d{2}-CITY-\d{2}-DIST-\d{2})\b", re.IGNORECASE)
_RE_DRONE_COUNT = re.compile(r"\b(\d+)\s*[-\s]?(?:drone|drones|uav|unit|units)\b", re.IGNORECASE)
_RE_AMB_COUNT = re.compile(r"\b(\d+)\s*[-\s]?(?:ambulance|ambulances|ems)\b", re.IGNORECASE)
_RE_QTY_GENERIC = re.compile(r"\b(\d+)\s*[-\s]?(?:food|water|kit|kits|package|packages|shelter|shelters|unit|units)\b", re.IGNORECASE)
_RE_BATTERY_PCT = re.compile(r"(?:below|under|<|threshold\s*=?)\s*(\d{1,2})\s*%?", re.IGNORECASE)
_RE_SEVERITY_PCT = re.compile(r"severity\s*(?:of\s*)?(\d{1,3})\s*%", re.IGNORECASE)
_RE_HOURS = re.compile(r"\b(\d{1,3})\s*(?:h|hr|hrs|hour|hours)\b", re.IGNORECASE)

_DISASTER_KEYWORDS: List[Tuple[str, str]] = [
    ("multi-hazard", "MULTI_HAZARD_CASCADE"),
    ("multi hazard", "MULTI_HAZARD_CASCADE"),
    ("industrial accident", "INDUSTRIAL_ACCIDENT"),
    ("power outage", "POWER_OUTAGE"),
    ("blackout", "COMM_BLACKOUT"),
    ("comm blackout", "COMM_BLACKOUT"),
    ("wildfire", "WILDFIRE"),
    ("forest fire", "WILDFIRE"),
    ("earthquake", "EARTHQUAKE"),
    ("landslide", "LANDSLIDE"),
    ("heatwave", "HEATWAVE"),
    ("cyclone", "CYCLONE"),
    ("hurricane", "CYCLONE"),
    ("flood", "FLOOD"),
    ("fire", "FIRE"),
]

_SENSOR_KEYWORDS: List[str] = ["thermal", "lidar", "acoustic", "gas_sensor", "sonar", "rf_relay", "rgb"]


class SessionContext:
    """Structured operational context service (tracks active country, hospital, drone, and pending approval)."""

    def __init__(self, default_country: str = "COUNTRY-03") -> None:
        self.active_country_id: str = default_country
        self.active_city_id: Optional[str] = None
        self.active_district_id: Optional[str] = None
        self.selected_hospital_id: Optional[str] = None
        self.selected_drone_id: Optional[str] = None
        self.selected_disaster_id: Optional[str] = None
        self.pending_approval_id: Optional[str] = None
        self.last_seen: float = time.time()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active_country_id": self.active_country_id,
            "active_city_id": self.active_city_id,
            "active_district_id": self.active_district_id,
            "selected_hospital_id": self.selected_hospital_id,
            "selected_drone_id": self.selected_drone_id,
            "selected_disaster_id": self.selected_disaster_id,
            "pending_approval_id": self.pending_approval_id,
        }


class JarvisAgent:
    """Fast Universal Command Orchestrator with 50 real callable backend tools & multi-intent routing."""

    def __init__(
        self,
        world: GlobalWorldEngine,
        route_explorer: AdvancedRouteExplorer,
        approval_engine: ApprovalEngine,
        provider_manager: AIProviderManager,
    ) -> None:
        self.world = world
        self.route_explorer = route_explorer
        self.approval_engine = approval_engine
        self.provider_manager = provider_manager
        self.sessions: Dict[str, SessionContext] = {}
        self.conversations: Dict[str, deque] = {}
        self.tool_logs: deque = deque(maxlen=2000)
        self._country_lookup: List[Tuple[str, str]] = self._build_country_lookup()
        self._tool_schemas: List[Dict[str, Any]] = self._build_tool_schemas()
        self._tool_schema_map: Dict[str, Dict[str, Any]] = {s["name"]: s for s in self._tool_schemas}
        self._tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = self._build_tool_handlers()
        self.registry: Dict[str, Dict[str, Any]] = self._build_tool_registry()
        self._assert_registry_integrity()

    @property
    def tool_count(self) -> int:
        return len(self._tool_schemas)

    def _build_country_lookup(self) -> List[Tuple[str, str]]:
        """Pre-index country names, capitals, first tokens, and flag codes for fast resolution."""
        pairs: List[Tuple[str, str]] = []
        for cid, c in self.world.countries.items():
            pairs.append((c.name.lower(), cid))
            pairs.append((c.capital_name.lower(), cid))
            first_word = c.name.split()[0].lower()
            if len(first_word) >= 4:
                pairs.append((first_word, cid))
            if c.flag_code:
                pairs.append((c.flag_code.lower(), cid))
        # Longest match first to prevent partial collisions
        pairs.sort(key=lambda x: len(x[0]), reverse=True)
        return pairs

    def _get_session(self, session_id: str) -> SessionContext:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionContext(default_country=self.world.selected_country_id)
        ctx = self.sessions[session_id]
        ctx.last_seen = time.time()
        return ctx

    def _evict_stale_sessions(self, max_age_seconds: float = 3600.0) -> int:
        now = time.time()
        stale = [sid for sid, ctx in self.sessions.items() if (now - ctx.last_seen) > max_age_seconds]
        for sid in stale:
            self.sessions.pop(sid, None)
            self.conversations.pop(sid, None)
        return len(stale)

    # ------------------------------------------------------------------
    # 50 Real Callable Backend Tool Handlers (Zero Fake Tools)
    # ------------------------------------------------------------------
    def _build_tool_handlers(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        """Every registered JARVIS tool maps directly to a real, fast backend execution handler."""
        def _cid(args: Dict[str, Any]) -> str:
            cid = args.get("country_id") or self.world.selected_country_id
            if cid not in self.world.countries:
                cid = self.world.selected_country_id
            return cid

        def _view_country(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            return to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_country",
                    target_id=cid,
                    frontend="quantum-world",
                    parameters={"transition": "smooth", "show_boundary": True, "show_city_markers": True},
                )
            )

        def _focus_hospital(args: Dict[str, Any]) -> Dict[str, Any]:
            hid = args.get("hospital_id")
            if not hid or hid not in self.world.hospitals:
                cid = _cid(args)
                h = next((x for x in self.world.hospitals.values() if x.country_id == cid), None)
                hid = h.hospital_id if h else None
            return to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_hospital", target_id=hid, frontend="quantum-world"
                )
            )

        def _focus_drone(args: Dict[str, Any]) -> Dict[str, Any]:
            did = args.get("drone_id")
            if not did or did not in self.world.drones:
                cid = _cid(args)
                d = next((x for x in self.world.drones.values() if x.country_id == cid), None)
                did = d.drone_id if d else None
            return to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_drone", target_id=did, frontend="quantum-world"
                )
            )

        def _get_country_cities(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            cities = [to_dict(c) for c in self.world.cities.values() if c.country_id == cid]
            return {"country_id": cid, "count": len(cities), "cities": cities}

        def _get_district_details(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            did = args.get("district_id")
            if did and did in self.world.districts:
                d = self.world.districts[did]
                return {"country_id": d.country_id, "count": 1, "districts": [to_dict(d)]}
            dists = [to_dict(d) for d in self.world.districts.values() if d.country_id == cid]
            return {"country_id": cid, "count": len(dists), "districts": dists}

        def _get_buildings_summary(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            blds = [b for b in self.world.buildings.values() if b.country_id == cid]
            by_cat: Dict[str, int] = {}
            by_cond: Dict[str, int] = {}
            for b in blds:
                by_cat[b.category] = by_cat.get(b.category, 0) + 1
                by_cond[b.structural_condition] = by_cond.get(b.structural_condition, 0) + 1
            return {
                "country_id": cid,
                "total_buildings": len(blds),
                "accessible_count": sum(1 for b in blds if b.accessible),
                "inaccessible_count": sum(1 for b in blds if not b.accessible),
                "damaged_count": sum(1 for b in blds if b.structural_condition != "INTACT"),
                "by_category": by_cat,
                "by_condition": by_cond,
                "sample_buildings": [to_dict(b) for b in blds[:15]],
            }

        def _get_road_network(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            rid = args.get("road_id")
            if rid and rid in self.world.roads:
                roads = [self.world.roads[rid]]
                cid = roads[0].country_id
            else:
                roads = [r for r in self.world.roads.values() if r.country_id == cid]
            return {
                "country_id": cid,
                "total_roads": len(roads),
                "accessible_roads": sum(1 for r in roads if r.accessible),
                "blocked_roads": sum(1 for r in roads if not r.accessible),
                "bridges_total": sum(1 for r in roads if r.is_bridge),
                "bridges_blocked": sum(1 for r in roads if r.is_bridge and not r.accessible),
                "roads": [to_dict(r) for r in roads],
            }

        def _get_blocked_roads(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            all_countries = bool(args.get("all_countries", False))
            roads = [
                r for r in self.world.roads.values()
                if (all_countries or r.country_id == cid)
            ]
            blocked = [r for r in roads if not r.accessible]
            return {
                "country_id": "ALL" if all_countries else cid,
                "total_roads": len(roads),
                "blocked_count": len(blocked),
                "accessible_count": len(roads) - len(blocked),
                "blocked_roads": [to_dict(r) for r in blocked],
            }

        def _get_population_summary(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            dists = [d for d in self.world.districts.values() if d.country_id == cid]
            return {
                "country_id": cid,
                "total_residents": sum(d.total_residents for d in dists),
                "exposed_residents": sum(d.exposed_residents for d in dists),
                "evacuated_residents": sum(d.evacuated_residents for d in dists),
                "injured_residents": sum(d.injured_residents for d in dists),
                "vulnerable_residents": sum(d.vulnerable_residents for d in dists),
                "districts": [to_dict(d) for d in dists],
                "households_count": sum(1 for h in self.world.households.values() if h.country_id == cid),
                "sample_people": [to_dict(p) for p in self.world.people.values() if p.country_id == cid][:15],
            }

        def _get_household_statistics(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            hhs = [h for h in self.world.households.values() if h.country_id == cid]
            dists = [d for d in self.world.districts.values() if d.country_id == cid]
            status_counts: Dict[str, int] = {}
            for h in hhs:
                status_counts[h.evacuation_status] = status_counts.get(h.evacuation_status, 0) + 1
            return {
                "country_id": cid,
                "district_estimated_households": sum(d.household_count for d in dists),
                "tracked_households": len(hhs),
                "tracked_residents": sum(h.resident_count for h in hhs),
                "with_vehicle": sum(1 for h in hhs if h.has_vehicle),
                "without_vehicle": sum(1 for h in hhs if not h.has_vehicle),
                "with_pets": sum(1 for h in hhs if h.has_pets),
                "total_pets": sum(h.pet_count for h in hhs),
                "needs_assisted_transport": sum(1 for h in hhs if h.needs_assisted_transport),
                "evacuation_status_breakdown": status_counts,
                "sample_households": [to_dict(h) for h in hhs[:12]],
            }

        def _get_animal_population(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            animals = [x for x in self.world.animals.values() if x.country_id == cid]
            return {
                "country_id": cid,
                "total_animals": sum(x.count for x in animals),
                "exposed_animals": sum(x.exposed_count for x in animals),
                "evacuated_animals": sum(x.evacuated_count for x in animals),
                "animals": [to_dict(x) for x in animals],
            }

        def _get_active_disasters(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = args.get("country_id")
            evs = [
                to_dict(d) for d in self.world.disasters.values()
                if d.status == "ACTIVE" and (not cid or d.country_id == cid)
            ]
            return {"count": len(evs), "disasters": evs}

        def _get_disaster_impact(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            ev_id = args.get("event_id")
            if ev_id and ev_id in self.world.disasters:
                evs = [self.world.disasters[ev_id]]
                cid = evs[0].country_id
            else:
                evs = [d for d in self.world.disasters.values() if d.country_id == cid and d.status == "ACTIVE"]
            dists = [d for d in self.world.districts.values() if d.country_id == cid]
            blocked = sum(1 for r in self.world.roads.values() if r.country_id == cid and not r.accessible)
            damaged_blds = sum(1 for b in self.world.buildings.values() if b.country_id == cid and b.structural_condition != "INTACT")
            return {
                "country_id": cid,
                "country_name": self.world.countries[cid].name,
                "active_disaster_count": len(evs),
                "disasters": [to_dict(e) for e in evs],
                "exposed_population": sum(d.exposed_residents for d in dists),
                "evacuation_demand": sum(e.evacuation_demand for e in evs),
                "estimated_injuries": sum(d.injured_residents for d in dists),
                "blocked_roads": blocked,
                "damaged_buildings": damaged_blds,
                "power_outage_districts": sum(1 for d in dists if not d.power_available),
            }

        def _get_hospital_status(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            hosps = [h for h in self.world.hospitals.values() if h.country_id == cid]
            return {
                "country_id": cid,
                "total_hospitals": len(hosps),
                "operational_count": sum(1 for h in hosps if h.status in (HospitalStatus.OPERATIONAL, HospitalStatus.PARTIALLY_OPERATIONAL)),
                "total_beds": sum(h.total_beds for h in hosps),
                "occupied_beds": sum(h.occupied_beds for h in hosps),
                "available_beds": sum(h.available_beds for h in hosps),
                "hospitals": [{**to_dict(h), "available_beds": h.available_beds} for h in hosps],
            }

        def _get_available_beds(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            all_countries = bool(args.get("all_countries", False))
            hosps = [
                h for h in self.world.hospitals.values()
                if (all_countries or h.country_id == cid) and h.status != HospitalStatus.CLOSED
            ]
            hosps.sort(key=lambda h: h.available_beds, reverse=True)
            return {
                "country_id": "ALL" if all_countries else cid,
                "total_available_beds": sum(h.available_beds for h in hosps),
                "total_beds": sum(h.total_beds for h in hosps),
                "hospitals": [
                    {
                        "hospital_id": h.hospital_id,
                        "country_id": h.country_id,
                        "name": h.name,
                        "status": h.status.value,
                        "available_beds": h.available_beds,
                        "total_beds": h.total_beds,
                        "triage_load": h.triage_load,
                    }
                    for h in hosps
                ],
            }

        def _get_ambulance_fleet(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            ambs = [a for a in self.world.ambulances.values() if a.country_id == cid]
            by_status: Dict[str, int] = {}
            by_equip: Dict[str, int] = {}
            for a in ambs:
                st = a.status.value if hasattr(a.status, "value") else str(a.status)
                by_status[st] = by_status.get(st, 0) + 1
                by_equip[a.equipment_profile] = by_equip.get(a.equipment_profile, 0) + 1
            return {
                "country_id": cid,
                "total_ambulances": len(ambs),
                "available_count": sum(1 for a in ambs if a.status == AmbulanceStatus.AVAILABLE),
                "by_status": by_status,
                "by_equipment": by_equip,
                "ambulances": [to_dict(a) for a in ambs],
            }

        def _get_fire_units(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            units = [f for f in self.world.fire_units.values() if f.country_id == cid]
            by_type: Dict[str, int] = {}
            for f in units:
                by_type[f.unit_type] = by_type.get(f.unit_type, 0) + 1
            return {
                "country_id": cid,
                "total_units": len(units),
                "available_count": sum(1 for f in units if f.status == "AVAILABLE"),
                "on_scene_count": sum(1 for f in units if f.status == "ON_SCENE"),
                "by_type": by_type,
                "fire_units": [to_dict(f) for f in units],
            }

        def _get_shelter_capacity(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            shelters = [s for s in self.world.shelters.values() if s.country_id == cid]
            return {
                "country_id": cid,
                "total_shelters": len(shelters),
                "accessible_shelters": sum(1 for s in shelters if s.accessible),
                "total_max_occupancy": sum(s.max_occupancy for s in shelters),
                "total_current_occupancy": sum(s.current_occupancy for s in shelters),
                "total_remaining_capacity": sum(s.remaining_capacity for s in shelters),
                "shelters": [{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in shelters],
            }

        def _get_warehouse_inventory(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            whs = [w for w in self.world.warehouses.values() if w.country_id == cid]
            return {
                "country_id": cid,
                "warehouse_count": len(whs),
                "totals": {
                    "food_packages": sum(w.food_packages for w in whs),
                    "water_liters": round(sum(w.water_liters for w in whs), 1),
                    "medical_kits": sum(w.medical_kits for w in whs),
                    "first_aid_kits": sum(w.first_aid_kits for w in whs),
                    "blankets": sum(w.blankets for w in whs),
                    "fuel_liters": round(sum(w.fuel_liters for w in whs), 1),
                    "generators": sum(w.generators for w in whs),
                    "comm_devices": sum(w.comm_devices for w in whs),
                    "rescue_kits": sum(w.rescue_kits for w in whs),
                },
                "warehouses": [to_dict(w) for w in whs],
            }

        def _get_resource_shortages(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            horizon = float(args.get("horizon_hours", 24.0))
            res = self.world.calculate_resource_requirements(cid, horizon_hours=horizon)
            amb = self.world.calculate_ambulance_requirements(cid)
            warnings = list(res["shortage_warnings"])
            if amb["ambulance_deficit"] > 0:
                warnings.append(f"Ambulance deficit of {amb['ambulance_deficit']} units (recommended {amb['recommended_operational_fleet']}, available {amb['available_ambulances']}).")
            return {
                "country_id": cid,
                "horizon_hours": horizon,
                "food_shortage": res["food_packages"]["shortage"],
                "water_shortage_liters": res["water_liters"]["shortage"],
                "medical_kits_shortage": res["medical_kits"]["shortage"],
                "shelter_capacity_shortage": res["shelters"]["shortage"],
                "ambulance_deficit": amb["ambulance_deficit"],
                "shortage_warnings": warnings,
                "has_shortages": bool(warnings) or any(
                    v > 0 for v in (
                        res["food_packages"]["shortage"],
                        res["water_liters"]["shortage"],
                        res["medical_kits"]["shortage"],
                        res["shelters"]["shortage"],
                        amb["ambulance_deficit"],
                    )
                ),
                "resource_analysis": res,
            }

        def _get_drone_fleet(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            drones = [d for d in self.world.drones.values() if d.country_id == cid]
            by_status: Dict[str, int] = {}
            by_cat: Dict[str, int] = {}
            for d in drones:
                by_status[d.status] = by_status.get(d.status, 0) + 1
                by_cat[d.category] = by_cat.get(d.category, 0) + 1
            return {
                "country_id": cid,
                "total_drones": len(drones),
                "available_count": by_status.get("AVAILABLE", 0),
                "by_status": by_status,
                "by_category": by_cat,
                "drones": [to_dict(d) for d in drones],
            }

        def _get_available_drones(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = _cid(args)
            min_batt = float(args.get("min_battery_pct", 25.0))
            sensor = args.get("sensor")
            avail = [
                d for d in self.world.drones.values()
                if d.country_id == cid
                and d.status == "AVAILABLE"
                and d.battery_pct >= min_batt
                and (not sensor or sensor in d.sensors)
            ]
            avail.sort(key=lambda d: d.battery_pct, reverse=True)
            return {
                "country_id": cid,
                "min_battery_pct": min_batt,
                "sensor_filter": sensor,
                "count": len(avail),
                "drones": [to_dict(d) for d in avail],
            }

        def _get_low_battery_drones(args: Dict[str, Any]) -> Dict[str, Any]:
            threshold = float(args.get("threshold", 35.0))
            cid = args.get("country_id")
            drones = [
                to_dict(d) for d in self.world.drones.values()
                if d.battery_pct < threshold and (not cid or d.country_id == cid)
            ]
            return {"threshold_pct": threshold, "country_id": cid or "ALL", "count": len(drones), "drones": drones}

        def _get_swarm_status(args: Dict[str, Any]) -> Dict[str, Any]:
            cid = args.get("country_id")
            swarms = [to_dict(s) for s in self.world.swarms.values() if not cid or s.country_id == cid]
            return {
                "country_id": cid or "ALL",
                "total_swarms": len(swarms),
                "active_swarms": sum(1 for s in swarms if s["status"] == "ACTIVE"),
                "swarms": swarms,
            }

        def _get_route_logs(args: Dict[str, Any]) -> Dict[str, Any]:
            limit = int(args.get("limit", 50))
            logs = self.route_explorer.route_logs[-limit:]
            return {"count": len(logs), "logs": logs}

        def _get_audit_logs(args: Dict[str, Any]) -> Dict[str, Any]:
            limit = int(args.get("limit", 50))
            return {
                "audit_log": list(self.approval_engine.audit_log)[-limit:],
                "tool_logs": list(self.tool_logs)[-limit:],
                "audit_count": len(self.approval_engine.audit_log),
                "tool_log_count": len(self.tool_logs),
            }

        def _save_world_local(args: Dict[str, Any]) -> Dict[str, Any]:
            filename = str(args.get("filename", "world_snapshot.json"))
            repo = ExperimentRepository()
            path = repo.save_local_world_snapshot(self.world.get_global_overview(), filename=filename)
            return {"saved": True, "storage": "local_json", "path": path, "world_version": self.world.event_bus.world_version}

        def _list_pending_approvals(a: Dict[str, Any]) -> Dict[str, Any]:
            aid = a.get("approval_id")
            if aid:
                req = self.approval_engine.approvals.get(aid)
                return {"approvals": [to_dict(req)] if req else []}
            return {"approvals": self.approval_engine.list_approvals(status=a.get("status", "PENDING"))}

        raw_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            # Navigation & World Camera (4)
            "view_global_world": lambda a: to_dict(
                self.world.event_bus.dispatch_frontend_command("camera.focus_world", frontend="quantum-world")
            ),
            "view_country": _view_country,
            "focus_hospital": _focus_hospital,
            "focus_drone": _focus_drone,
            # Global, Country, City, District, Infrastructure & Population (12)
            "get_global_world_overview": lambda a: self.world.get_global_overview(),
            "get_country_list": lambda a: {"countries": self.world.get_global_overview()["countries"]},
            "get_country_status": lambda a: self.world.get_country_detail(_cid(a)),
            "get_country_cities": _get_country_cities,
            "get_district_details": _get_district_details,
            "get_buildings_summary": _get_buildings_summary,
            "get_road_network": _get_road_network,
            "get_blocked_roads": _get_blocked_roads,
            "get_population_summary": _get_population_summary,
            "get_household_statistics": _get_household_statistics,
            "get_animal_population": _get_animal_population,
            "get_simulation_clock": lambda a: self.world.get_clock_info(),
            # Disasters & Cascades (4)
            "get_active_disasters": _get_active_disasters,
            "get_disaster_impact": _get_disaster_impact,
            "get_cascade_graph": lambda a: self.world.get_cascade_graph(_cid(a)),
            "analyze_disaster": lambda a: self.world.get_country_detail(_cid(a)),
            # Medical, Fire & Logistics (9)
            "get_hospital_status": _get_hospital_status,
            "get_available_beds": _get_available_beds,
            "get_ambulance_fleet": _get_ambulance_fleet,
            "calculate_ambulance_requirements": lambda a: self.world.calculate_ambulance_requirements(
                _cid(a), planning_window_hours=float(a.get("window_hours", 4.0))
            ),
            "get_fire_units": _get_fire_units,
            "get_shelter_capacity": _get_shelter_capacity,
            "get_warehouse_inventory": _get_warehouse_inventory,
            "calculate_resource_requirements": lambda a: self.world.calculate_resource_requirements(
                _cid(a), horizon_hours=float(a.get("horizon_hours", 24.0))
            ),
            "get_resource_shortages": _get_resource_shortages,
            # Drones, Swarms & Route Intelligence (7)
            "get_drone_fleet": _get_drone_fleet,
            "get_available_drones": _get_available_drones,
            "get_low_battery_drones": _get_low_battery_drones,
            "get_swarm_status": _get_swarm_status,
            "compare_drones_to_destination": lambda a: self._handle_route_compare(a),
            "plan_multistop_mission": lambda a: self._handle_multistop(a),
            "get_route_logs": _get_route_logs,
            # Innovations, Governance, Persistence & Audit (8)
            "evaluate_rescue_equity": lambda a: self.world.evaluate_rescue_equity(_cid(a)),
            "find_mutual_aid_options": lambda a: self.world.find_mutual_aid_options(
                _cid(a), resource_type=a.get("resource_type", "ambulances"), quantity=int(a.get("quantity", 8))
            ),
            "run_counterfactual_comparison": lambda a: self.world.run_counterfactual_comparison(
                _cid(a), what_if_params=a.get("what_if")
            ),
            "list_playbooks": lambda a: {"playbooks": PLAYBOOK_CATALOG, "count": len(PLAYBOOK_CATALOG)},
            "get_event_timeline": lambda a: {
                "world_version": self.world.event_bus.world_version,
                "events": self.world.event_bus.get_events(
                    limit=int(a.get("limit", 40)),
                    category=a.get("category"),
                    country_id=a.get("country_id"),
                ),
            },
            "get_audit_logs": _get_audit_logs,
            "list_pending_approvals": _list_pending_approvals,
            "save_world_local": _save_world_local,
            # State-changing Approval-Gated Action Tools (6)
            "prepare_disaster_event": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="inject_disaster",
                    title=f"Inject Simulated {a.get('disaster_type', 'FLOOD')} in {self.world.countries[_cid(a)].name}",
                    description=f"Severity {int(float(a.get('severity', 0.78)) * 100)}% centered on capital.",
                    country_id=_cid(a),
                    parameters={
                        "disaster_type": a.get("disaster_type", "FLOOD"),
                        "severity": float(a.get("severity", 0.78)),
                        "radius_km": float(a.get("radius_km", 11.0)),
                    },
                )
            ),
            "prepare_swarm_operation": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="deploy_swarm",
                    title=f"Deploy {int(a.get('drone_count', 8))}-Drone {a.get('mode', 'AREA_SCAN')} Swarm ({self.world.countries[_cid(a)].name})",
                    description=f"Formation: {a.get('formation', 'SEARCH_GRID')}.",
                    country_id=_cid(a),
                    parameters={
                        "drone_count": int(a.get("drone_count", 8)),
                        "mode": a.get("mode", "AREA_SCAN"),
                        "formation": a.get("formation", "SEARCH_GRID"),
                    },
                    required_resources={"drones": int(a.get("drone_count", 8))},
                )
            ),
            "prepare_ambulance_dispatch": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="dispatch_ambulances",
                    title=f"Dispatch {int(a.get('count', 6))} Ambulances in {self.world.countries[_cid(a)].name}",
                    description="Priority medical transport dispatch.",
                    country_id=_cid(a),
                    parameters={"count": int(a.get("count", 6))},
                )
            ),
            "prepare_cross_country_aid": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="cross_country_aid",
                    title=f"Mutual Aid Transfer: {int(a.get('quantity', 6))} {a.get('resource_type', 'ambulances')}",
                    description=f"From {a.get('donor_country_id', 'COUNTRY-05')} to {_cid(a)}.",
                    country_id=_cid(a),
                    parameters={
                        "donor_country_id": a.get("donor_country_id", "COUNTRY-05"),
                        "resource_type": a.get("resource_type", "ambulances"),
                        "quantity": int(a.get("quantity", 6)),
                    },
                )
            ),
            "prepare_comprehensive_rescue_plan": lambda a: self._handle_prepare_rescue_plan(_cid(a)),
            "prepare_drone_failure": lambda a: self._handle_prepare_drone_failure(a),
        }

        def _wrap_handler(tool_name: str, fn: Callable[[Dict[str, Any]], Any]) -> Callable[[Dict[str, Any]], Any]:
            args_model = TOOL_ARGS_MODELS[tool_name]

            def _validated(raw_args: Dict[str, Any]) -> Any:
                parsed = args_model(**(raw_args or {}))
                return fn(parsed.to_handler_dict())

            return _validated

        return {name: _wrap_handler(name, fn) for name, fn in raw_handlers.items()}

    def _handle_route_compare(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        if cid not in self.world.countries:
            cid = self.world.selected_country_id
        target_h = None
        if args.get("hospital_id") and args["hospital_id"] in self.world.hospitals:
            target_h = self.world.hospitals[args["hospital_id"]]
        else:
            hospitals = [h for h in self.world.hospitals.values() if h.country_id == cid]
            target_h = hospitals[0] if hospitals else None
        dest = (
            GeoPoint(lat=float(args["lat"]), lon=float(args["lon"]), elevation_m=90.0)
            if (args.get("lat") is not None and args.get("lon") is not None)
            else (target_h.location if target_h else self.world.countries[cid].center)
        )
        label = args.get("destination_label") or (target_h.name if target_h else self.world.countries[cid].capital_name)
        return self.route_explorer.compare_drones_to_destination(
            cid,
            dest,
            destination_label=label,
            objective=args.get("objective", "BALANCED"),
            payload_kg=float(args.get("payload_kg", 1.0)),
            required_sensor=args.get("required_sensor"),
        )

    def _handle_multistop(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        if cid not in self.world.countries:
            cid = self.world.selected_country_id
        c = self.world.countries[cid].center
        raw_pts = args.get("points")
        if raw_pts and isinstance(raw_pts, list):
            pts = [
                GeoPoint(lat=float(p["lat"]), lon=float(p["lon"]), elevation_m=float(p.get("elevation_m", 85.0)))
                for p in raw_pts
            ]
        else:
            pts = [
                GeoPoint(lat=c.lat + 0.02, lon=c.lon + 0.02, elevation_m=85.0),
                GeoPoint(lat=c.lat - 0.02, lon=c.lon + 0.03, elevation_m=90.0),
                GeoPoint(lat=c.lat + 0.03, lon=c.lon - 0.02, elevation_m=88.0),
            ]
        return self.route_explorer.plan_multistop_mission(
            cid, pts, sensor_type=args.get("sensor_type", "thermal"), objective=args.get("objective", "LOWEST_ENERGY")
        )

    def _handle_prepare_rescue_plan(self, cid: str) -> Dict[str, Any]:
        plan = self.approval_engine.generate_adapted_plan(cid, playbook_id="PB-03")
        pr = plan["proposed_resources"]
        apr = self.approval_engine.create_approval_request(
            operation_type="comprehensive_rescue_plan",
            title=f"Execute {plan['playbook']['title']} — {self.world.countries[cid].name}",
            description=f"Deploy {pr['drones']} drones, {pr['ambulances']} ambulances, and activate {pr['shelters_to_activate']} relief shelters.",
            country_id=cid,
            parameters={"drones": pr["drones"], "ambulances": pr["ambulances"], "plan_id": plan["plan_id"]},
            required_resources=pr,
            expected_outcomes=[f"Addresses {plan['population_at_risk']:,} exposed residents across {self.world.countries[cid].name}"],
            operational_risks=plan["shortages_and_risks"],
        )
        return {"plan": plan, "approval": to_dict(apr)}

    def _handle_prepare_drone_failure(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        target_d = args.get("drone_id")
        if not target_d or target_d not in self.world.drones:
            target_d = next(
                (d.drone_id for d in self.world.drones.values() if d.country_id == cid),
                next(iter(self.world.drones.keys())),
            )
        return to_dict(
            self.approval_engine.create_approval_request(
                operation_type="destroy_drone",
                title=f"Simulate Destruction of {target_d}",
                description=f"Virtual simulation failure injection on {target_d} with automatic swarm task recovery.",
                country_id=self.world.drones[target_d].country_id,
                parameters={"drone_id": target_d, "failure_type": "COMPLETE_DRONE_DESTRUCTION"},
                affected_entities=[target_d],
            )
        )

    # ------------------------------------------------------------------
    # JSON-Schema Tool Definitions (Auto-generated from Typed Pydantic Models)
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_tool_category(name: str) -> str:
        if name.startswith("prepare_"):
            return "action"
        if name.startswith(("view_", "focus_")):
            return "navigation"
        if "route" in name or "multistop" in name or "compare_drones" in name:
            return "routing"
        if any(k in name for k in ("hospital", "ambulance", "bed")):
            return "medical"
        if any(k in name for k in ("shelter", "resource", "mutual_aid", "warehouse")):
            return "logistics"
        if any(k in name for k in ("drone", "swarm")):
            return "drone"
        if any(k in name for k in ("disaster", "cascade", "fire")):
            return "disaster"
        if any(k in name for k in ("audit", "event", "playbook", "approval", "save_world")):
            return "governance"
        return "world"

    def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas: List[Dict[str, Any]] = []
        for name, args_model in TOOL_ARGS_MODELS.items():
            is_action = name.startswith("prepare_")
            cat = self._classify_tool_category(name)
            params = args_model.json_schema_dict()
            params["additionalProperties"] = False
            schemas.append({
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, ""),
                "parameters": params,
                "annotations": {
                    "readOnlyHint": not is_action,
                    "requiresApproval": is_action,
                    "idempotentHint": not is_action,
                    "category": cat,
                },
            })
        return schemas

    def _assert_registry_integrity(self) -> None:
        handler_names = set(self._tool_handlers.keys())
        schema_names = set(self._tool_schema_map.keys())
        if handler_names != schema_names:
            raise AssertionError(
                f"Tool registry mismatch: handlers-schemas={handler_names - schema_names}, "
                f"schemas-handlers={schema_names - handler_names}"
            )
        for name, schema in self._tool_schema_map.items():
            params = schema.get("parameters", {})
            if params.get("additionalProperties") is not False:
                raise AssertionError(f"Tool '{name}' schema must set additionalProperties=False")
            annotations = schema.get("annotations", {})
            if name.startswith("prepare_") and annotations.get("requiresApproval") is not True:
                raise AssertionError(f"Action tool '{name}' must have requiresApproval=True")
            props = params.get("properties", {})
            for cid_key in ("country_id", "donor_country_id"):
                if cid_key in props:
                    prop = props[cid_key]
                    if "pattern" not in prop and "enum" not in prop:
                        raise AssertionError(f"Tool '{name}' property '{cid_key}' must define pattern or enum")

    def get_tool_schemas(self, categories: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Return clean JSON-Schema tool definitions compatible with Gemini function_declarations and Grok/OpenAI tools."""
        if categories is None:
            return [dict(s) for s in self._tool_schemas]
        return [
            dict(s)
            for s in self._tool_schemas
            if s.get("annotations", {}).get("category") in categories
        ]

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        meta: Dict[str, Dict[str, Any]] = {}
        for name in self._tool_handlers:
            schema = self._tool_schema_map.get(name, {})
            annotations = schema.get("annotations", {})
            is_action = bool(annotations.get("requiresApproval", name.startswith("prepare_")))
            cat = annotations.get("category", self._classify_tool_category(name))
            meta[name] = {
                "tool_name": name,
                "category": cat,
                "description": schema.get("description", ""),
                "parameters": schema.get("parameters", {"type": "object", "properties": {}, "required": [], "additionalProperties": False}),
                "annotations": annotations,
                "read_only": not is_action,
                "requires_approval": is_action,
                "callable": True,
            }
        return meta

    def execute_tool_direct(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Direct fast execution endpoint for any registered JARVIS tool."""
        if tool_name not in self._tool_handlers:
            raise ValueError(f"Unknown tool: {tool_name}")
        t0 = time.perf_counter()
        result = self._tool_handlers[tool_name](args or {})
        dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        entry = {
            "timestamp": utc_now_iso(),
            "tool": tool_name,
            "arguments": args or {},
            "duration_ms": dur_ms,
            "status": "OK",
            "summary": self._summarize_result(tool_name, result),
        }
        self.tool_logs.append(entry)
        return {"tool": tool_name, "duration_ms": dur_ms, "result": result, "trace_entry": entry}

    def _run_tool(self, trace: List[Dict[str, Any]], tool_name: str, args: Dict[str, Any]) -> Any:
        t0 = time.perf_counter()
        started = utc_now_iso()
        try:
            res = self._tool_handlers[tool_name](args)
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "OK",
                "summary": self._summarize_result(tool_name, res),
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            return res
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            cat = self._tool_schema_map.get(tool_name, {}).get("annotations", {}).get("category", "unknown")
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "ERROR",
                "summary": str(exc),
                "category": cat,
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            return {
                "status": "ERROR",
                "tool": tool_name,
                "error": str(exc),
                "category": cat,
            }

    def _summarize_result(self, tool_name: str, res: Any) -> str:
        if isinstance(res, dict):
            if "approval_id" in res:
                return f"Prepared approval {res['approval_id']}"
            if "approval" in res and isinstance(res["approval"], dict):
                return f"Prepared plan + approval {res['approval'].get('approval_id')}"
            if "ranked_comparison" in res:
                return f"Evaluated {res['eligible_count']} eligible drones, {len(res['all_candidate_routes'])} routes"
            if "minimum_ambulances_required" in res:
                return f"Recommended {res['recommended_operational_fleet']} ambulances ({res['available_ambulances']} avail)"
            if "command_id" in res:
                return f"Dispatched {res['command_type']} ({res['status']})"
            if "blocked_count" in res:
                return f"Found {res['blocked_count']}/{res['total_roads']} blocked roads"
            if "total_available_beds" in res:
                return f"{res['total_available_beds']}/{res['total_beds']} beds available"
            if "saved" in res and res.get("saved"):
                return f"Saved local world snapshot to {res.get('path')}"
            if "count" in res:
                return f"Returned {res['count']} records"
        return "Completed"

    # ------------------------------------------------------------------
    # Sub-Millisecond Entity Extraction & Multi-Intent Recognition
    # ------------------------------------------------------------------
    def _resolve_country(self, text: str, ctx: SessionContext) -> str:
        m = _RE_COUNTRY_NUM.search(text)
        if m:
            cid = f"COUNTRY-0{m.group(1)}"
            ctx.active_country_id = cid
            return cid
        low = text.lower()
        for token, cid in self._country_lookup:
            if len(token) <= 3:
                if re.search(rf"\b{re.escape(token)}\b", low):
                    ctx.active_country_id = cid
                    return cid
            elif token in low:
                ctx.active_country_id = cid
                return cid
        return ctx.active_country_id

    def _extract_entities(self, message: str, low: str, ctx: SessionContext) -> Dict[str, Any]:
        cid = self._resolve_country(message, ctx)
        country = self.world.countries[cid]

        m_hosp = _RE_HOSPITAL_ID.search(message)
        hospital_id = m_hosp.group(1).upper() if m_hosp else None
        if hospital_id and hospital_id in self.world.hospitals:
            ctx.selected_hospital_id = hospital_id

        m_drone = _RE_DRONE_ID.search(message)
        drone_id = m_drone.group(1).upper() if m_drone else None
        if drone_id and drone_id in self.world.drones:
            ctx.selected_drone_id = drone_id

        m_dist = _RE_DISTRICT_ID.search(message)
        district_id = m_dist.group(1).upper() if m_dist else None
        if district_id and district_id in self.world.districts:
            ctx.active_district_id = district_id

        disaster_type: Optional[str] = None
        for kw, dtype in _DISASTER_KEYWORDS:
            if kw in low:
                disaster_type = dtype
                break

        counts: Dict[str, Any] = {}
        if m := _RE_DRONE_COUNT.search(low):
            counts["drone_count"] = int(m.group(1))
        if m := _RE_AMB_COUNT.search(low):
            counts["ambulance_count"] = int(m.group(1))
        if m := _RE_QTY_GENERIC.search(low):
            counts["quantity"] = int(m.group(1))
        if m := _RE_BATTERY_PCT.search(low):
            counts["battery_threshold"] = float(m.group(1))
        if m := _RE_SEVERITY_PCT.search(low):
            counts["severity"] = round(max(0.1, min(1.0, int(m.group(1)) / 100.0)), 2)
        if m := _RE_HOURS.search(low):
            counts["hours"] = float(m.group(1))

        objective = (
            "LOWEST_ENERGY" if ("battery" in low or "energy" in low)
            else "FASTEST" if ("fastest" in low or "quickest" in low)
            else "SAFEST" if ("safest" in low or "safe route" in low)
            else "HIGHEST_RELIABILITY" if "reliable" in low
            else "WIND_OPTIMIZED" if "wind" in low
            else "EMERGENCY" if "emergency" in low
            else "BALANCED"
        )

        resource_type = (
            "drones" if ("spare drone" in low or "mutual aid drone" in low or "transfer drone" in low)
            else "food" if ("food" in low and ("mutual aid" in low or "transfer" in low))
            else "ambulances"
        )

        sensor_type = next((s for s in _SENSOR_KEYWORDS if s in low), "thermal")

        return {
            "country_id": cid,
            "country_name": country.name,
            "capital_name": country.capital_name,
            "hospital_id": hospital_id,
            "drone_id": drone_id,
            "district_id": district_id,
            "disaster_type": disaster_type,
            "counts": counts,
            "objective": objective,
            "resource_type": resource_type,
            "sensor_type": sensor_type,
        }

    def _recognize_intents(self, low: str, entities: Dict[str, Any]) -> List[str]:
        """Fast multi-intent classifier supporting compound commands in <1 ms."""
        intents: List[str] = []

        # 1. Navigation intents (can combine with any read or routing intent)
        if any(k in low for k in ("whole world", "global view", "all seven countries", "reset camera", "global overview")):
            intents.append("global_world")
        elif any(k in low for k in ("view country", "select country", "zoom into", "open country", "go to country", "focus country")):
            intents.append("view_country")
        elif re.search(r"\b(?:view|zoom|go to|focus on)\s+(?:country|aurelia|valtoria|veridia|solara|ferros|kalahar|sylva)\b", low):
            intents.append("view_country")

        if entities.get("hospital_id") and any(k in low for k in ("focus", "zoom", "view", "locate")):
            intents.append("focus_hospital")
        if entities.get("drone_id") and any(k in low for k in ("focus", "zoom", "track", "locate")) and not any(k in low for k in ("destroy", "kill", "fail")):
            intents.append("focus_drone")

        # 2. Approval-gated action intents (high priority)
        is_action = False
        if any(k in low for k in ("destroy", "kill drone", "fail drone", "drone failure")):
            intents.append("prepare_drone_failure")
            is_action = True
        elif any(k in low for k in ("mutual aid", "another country", "cross-country", "spare ambulance", "additional ambulance")):
            intents.append("mutual_aid")
            is_action = True
        elif any(k in low for k in ("rescue plan", "recovery plan", "complete rescue", "comprehensive rescue")):
            intents.append("prepare_rescue_plan")
            is_action = True
        elif any(k in low for k in ("swarm", "medical delivery", "area scan", "deploy drone")) and any(
            k in low for k in ("prepare", "deploy", "launch", "start", "swarm", "scan", "delivery")
        ):
            if "swarm status" in low or "active swarm" in low or "list swarm" in low:
                intents.append("swarm_status")
            else:
                intents.append("prepare_swarm")
                is_action = True
        elif any(k in low for k in ("dispatch ambulance", "send ambulance", "prepare ambulance")):
            intents.append("prepare_ambulance_dispatch")
            is_action = True
        elif any(k in low for k in ("inject", "trigger", "simulate")) and entities.get("disaster_type") and not any(k in low for k in ("what if", "counterfactual")):
            intents.append("prepare_disaster")
            is_action = True

        # 3. Granular analytical & read-only intents (compound-capable!)
        if not is_action:
            if any(k in low for k in ("blocked road", "road blockage", "closed road", "flooded road", "blocked bridge")):
                intents.append("blocked_roads")
            elif any(k in low for k in ("road network", "all roads", "road status", "bridges")):
                intents.append("road_network")

            if any(k in low for k in ("multistop", "multi-stop", "multi stop", "survey mission")):
                intents.append("multistop_mission")
            elif any(k in low for k in ("route log", "routing log")):
                intents.append("route_logs")
            elif any(k in low for k in ("best drone", "compare drone", "feasible route", "drone route", "drones to reach", "reach the hospital", "route to")):
                intents.append("route_comparison")
            elif any(k in low for k in ("route", "feasible", "reach")) and "road" not in low:
                intents.append("route_comparison")

            if any(k in low for k in ("low battery", "low-battery", "battery below", "battery under")):
                intents.append("low_battery_drones")
            elif any(k in low for k in ("available drone", "ready drone", "idle drone")):
                intents.append("available_drones")
            elif any(k in low for k in ("drone fleet", "all drones", "list drones")):
                intents.append("drone_fleet")

            if any(k in low for k in ("swarm status", "active swarm", "list swarm")) and "swarm_status" not in intents:
                intents.append("swarm_status")

            if any(k in low for k in ("available bed", "free bed", "bed capacity", "hospital bed")):
                intents.append("available_beds")
            elif any(k in low for k in ("hospital status", "hospitals", "medical facility")) and "reach the hospital" not in low:
                intents.append("hospital_status")

            if any(k in low for k in ("ambulance requirement", "how many ambulance", "ambulances needed", "ambulance deficit")):
                intents.append("ambulance_requirements")
            elif any(k in low for k in ("ambulance fleet", "list ambulance", "ambulance status")):
                intents.append("ambulance_fleet")

            if any(k in low for k in ("fire unit", "fire truck", "firefighter", "rescue boat")):
                intents.append("fire_units")

            if any(k in low for k in ("shelter capacity", "shelters", "relief shelter")):
                intents.append("shelter_capacity")
            if any(k in low for k in ("warehouse", "inventory", "depot stock", "supply stock")):
                intents.append("warehouse_inventory")
            if any(k in low for k in ("shortage", "depletion", "deficit")) and "ambulance deficit" not in low:
                intents.append("resource_shortages")
            elif any(k in low for k in ("resource requirement", "food and water", "supply requirement", "supplies needed")):
                intents.append("resource_requirements")

            if any(k in low for k in ("what if", "counterfactual", "conventional")):
                intents.append("counterfactual")
            if any(k in low for k in ("equity", "underserved", "vulnerable priority")):
                intents.append("rescue_equity")
            if any(k in low for k in ("cascade", "chain reaction", "secondary hazard")):
                intents.append("cascade_graph")
            if any(k in low for k in ("disaster impact", "damage assessment")):
                intents.append("disaster_impact")
            elif any(k in low for k in ("active disaster", "list disaster", "current disaster")):
                intents.append("active_disasters")

            if any(k in low for k in ("cities", "city list")):
                intents.append("country_cities")
            if any(k in low for k in ("district", "sector")):
                intents.append("district_details")
            if any(k in low for k in ("building", "structural damage")):
                intents.append("buildings_summary")
            if any(k in low for k in ("household", "families", "pets", "assisted transport")):
                intents.append("household_statistics")
            elif any(k in low for k in ("population", "residents", "demographics")):
                intents.append("population_summary")
            if any(k in low for k in ("animal", "livestock", "wildlife")):
                intents.append("animal_population")

            if any(k in low for k in ("playbook", "sop", "protocol")):
                intents.append("list_playbooks")
            if any(k in low for k in ("event timeline", "recent events", "event log")):
                intents.append("event_timeline")
            if any(k in low for k in ("audit log", "tool log")):
                intents.append("audit_logs")
            if any(k in low for k in ("pending approval", "list approval")):
                intents.append("pending_approvals")
            if any(k in low for k in ("save world", "save snapshot", "save local")):
                intents.append("save_world_local")
            if any(k in low for k in ("list countries", "all countries", "country list")):
                intents.append("country_list")

        if not intents:
            intents.append("country_report")
        return intents

    # ------------------------------------------------------------------
    # Main Fast Command Orchestrator
    # ------------------------------------------------------------------
    @staticmethod
    def _is_tool_error(res: Any) -> bool:
        return isinstance(res, dict) and res.get("status") == "ERROR" and "error" in res

    async def process_command(self, message: str, session_id: str = "default", use_llm_polish: bool = False) -> Dict[str, Any]:
        t_start = time.perf_counter()
        self._evict_stale_sessions(max_age_seconds=3600)
        ctx = self._get_session(session_id)
        trace: List[Dict[str, Any]] = []
        low = message.lower().strip()

        entities = self._extract_entities(message, low, ctx)
        cid = entities["country_id"]
        country = self.world.countries[cid]
        intents = self._recognize_intents(low, entities)

        structured_cards: List[Dict[str, Any]] = []
        frontend_commands: List[Dict[str, Any]] = []
        kpis: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        answer_sections: List[str] = []
        pending_approval: Optional[Dict[str, Any]] = None
        globe_state = "SUCCESS"
        intent_errors = 0

        def _note_err(res: Dict[str, Any]) -> None:
            nonlocal intent_errors
            intent_errors += 1
            answer_sections.append(
                f"Afraid we hit a snag on {res.get('tool', 'that subsystem')}, Sir: {res.get('error', 'unknown error')}."
            )

        for intent in intents:
            if intent == "global_world":
                cmd = self._run_tool(trace, "view_global_world", {})
                if self._is_tool_error(cmd):
                    _note_err(cmd)
                    continue
                frontend_commands.append(cmd)
                overview = self._run_tool(trace, "get_global_world_overview", {})
                if self._is_tool_error(overview):
                    _note_err(overview)
                    continue
                t = overview["totals"]
                structured_cards.append({"type": "global_overview", "data": t})
                kpis.extend([
                    {"label": "Active Disasters", "value": t["active_disasters"]},
                    {"label": "Population at Risk", "value": t["people_at_risk"]},
                    {"label": "Drones Available", "value": f"{t['drones_available']}/{t['drones_total']}"},
                ])
                tables.append({
                    "title": "Seven-Country Continental Status",
                    "columns": ["Country", "Capital", "Active Disasters", "Exposed", "Drones Avail", "Readiness"],
                    "rows": [
                        [c["name"], c["capital_name"], c["active_disasters"], c["exposed_population"], f"{c['drones_available']}/{c['drones_total']}", f"{c['readiness_score']}%"]
                        for c in overview["countries"]
                    ],
                })
                answer_sections.append(
                    f"Right away, Sir. Full 7-country continental telemetry is live: {t['active_disasters']} active disasters, "
                    f"{t['people_at_risk']:,} residents at risk, and {t['drones_available']}/{t['drones_total']} drones flight-ready."
                )

            elif intent == "view_country":
                globe_state = "QUERYING" if globe_state == "SUCCESS" else globe_state
                vcmd = self._run_tool(trace, "view_country", {"country_id": cid})
                if self._is_tool_error(vcmd):
                    _note_err(vcmd)
                    continue
                frontend_commands.append(vcmd)
                if len(intents) == 1:
                    detail = self._run_tool(trace, "get_country_status", {"country_id": cid})
                    if self._is_tool_error(detail):
                        _note_err(detail)
                        continue
                    structured_cards.append({"type": "country_status", "data": detail["profile"]})
                    kpis.extend([
                        {"label": "Country", "value": country.name},
                        {"label": "Exposed Population", "value": detail["resource_analysis"]["exposed_population"]},
                        {"label": "Readiness", "value": f"{country.readiness_score}%"},
                    ])
                    answer_sections.append(
                        f"Right away, Sir. {country.name} ({cid}) telemetry is up in World Command—capital {country.capital_name}, "
                        f"{detail['resource_analysis']['exposed_population']:,} exposed, readiness holding at {country.readiness_score}%."
                    )
                else:
                    answer_sections.append(
                        f"Right away, Sir. World Command camera is locked onto {country.name} ({cid}, capital {country.capital_name})."
                    )

            elif intent == "focus_hospital":
                cmd = self._run_tool(trace, "focus_hospital", {"country_id": cid, "hospital_id": entities["hospital_id"]})
                if self._is_tool_error(cmd):
                    _note_err(cmd)
                    continue
                frontend_commands.append(cmd)
                answer_sections.append(f"Visual locked onto hospital {cmd.get('target_id')}, Sir.")

            elif intent == "focus_drone":
                cmd = self._run_tool(trace, "focus_drone", {"country_id": cid, "drone_id": entities["drone_id"]})
                if self._is_tool_error(cmd):
                    _note_err(cmd)
                    continue
                frontend_commands.append(cmd)
                answer_sections.append(f"Tracking feed locked onto drone {cmd.get('target_id')}, Sir.")

            elif intent == "blocked_roads":
                globe_state = "QUERYING" if globe_state == "SUCCESS" else globe_state
                res = self._run_tool(trace, "get_blocked_roads", {"country_id": cid})
                if self._is_tool_error(res):
                    _note_err(res)
                    continue
                structured_cards.append({"type": "blocked_roads", "data": res})
                kpis.append({"label": "Blocked Roads", "value": f"{res['blocked_count']}/{res['total_roads']}"})
                if res["blocked_roads"]:
                    tables.append({
                        "title": f"Blocked Roads — {country.name}",
                        "columns": ["Road ID", "Name", "Category", "Flood Depth (m)", "Reason"],
                        "rows": [
                            [r["road_id"], r["name"], r["category"], r["flood_depth_m"], r.get("blocked_reason") or "Blocked"]
                            for r in res["blocked_roads"]
                        ],
                    })
                answer_sections.append(
                    f"Ground corridors in {country.name}, Sir: {res['blocked_count']}/{res['total_roads']} roads blocked "
                    f"({res['accessible_count']} still passable)."
                )

            elif intent == "road_network":
                res = self._run_tool(trace, "get_road_network", {"country_id": cid})
                if self._is_tool_error(res):
                    _note_err(res)
                    continue
                structured_cards.append({"type": "road_network", "data": res})
                kpis.extend([
                    {"label": "Accessible Roads", "value": f"{res['accessible_roads']}/{res['total_roads']}"},
                    {"label": "Blocked Bridges", "value": f"{res['bridges_blocked']}/{res['bridges_total']}"},
                ])
                answer_sections.append(
                    f"Road grid telemetry for {country.name}, Sir: {res['accessible_roads']}/{res['total_roads']} open, "
                    f"{res['blocked_roads']} blocked ({res['bridges_blocked']} bridges compromised)."
                )

            elif intent == "route_comparison":
                globe_state = "OPTIMIZING"
                obj = entities["objective"]
                comp = self._run_tool(
                    trace,
                    "compare_drones_to_destination",
                    {"country_id": cid, "hospital_id": entities["hospital_id"], "objective": obj},
                )
                if self._is_tool_error(comp):
                    _note_err(comp)
                    continue
                cmd_routes = to_dict(
                    self.world.event_bus.dispatch_frontend_command(
                        "camera.show_candidate_routes",
                        target_id=cid,
                        frontend="quantum-world",
                        parameters={"candidates": comp["all_candidate_routes"][:10], "destination": comp["destination"]},
                    )
                )
                frontend_commands.append(cmd_routes)
                structured_cards.append({"type": "route_comparison", "data": comp})
                best = comp["best_recommendation"]
                kpis.extend([
                    {"label": "Eligible Drones", "value": f"{comp['eligible_count']}/{comp['total_country_drones']}"},
                    {"label": "Best Drone", "value": best["drone_id"] if best else "None"},
                ])
                if comp["ranked_comparison"]:
                    tables.append({
                        "title": f"Top Drone Routes to {comp['destination_label']} ({obj})",
                        "columns": ["Rank", "Drone", "Route", "Distance (km)", "ETA (min)", "Battery Used (%)", "Feasible"],
                        "rows": [
                            [r["rank"], r["drone_id"], r["route_id"], r["total_distance_km"], r["estimated_duration_min"], r["predicted_battery_used_pct"], "Yes" if r["feasible"] else "No"]
                            for r in comp["ranked_comparison"][:5]
                        ],
                    })
                answer_sections.append(
                    f"Three steps ahead as usual, Sir—route matrix locked for {comp['destination_label']} ({country.name}, {obj}). "
                    f"{comp['eligible_count']}/{comp['total_country_drones']} drones qualify. "
                    + (
                        f"Optimal pick: {best['drone_id']} via {best['route_id']} ({best['total_distance_km']} km, "
                        f"ETA {best['estimated_duration_min']} min, {best['predicted_battery_used_pct']}% battery draw)."
                        if best else "No feasible air corridors under current constraints."
                    )
                )

            elif intent == "multistop_mission":
                globe_state = "OPTIMIZING"
                ms = self._run_tool(trace, "plan_multistop_mission", {"country_id": cid, "sensor_type": entities["sensor_type"]})
                if self._is_tool_error(ms):
                    _note_err(ms)
                    continue
                structured_cards.append({"type": "multistop_mission", "data": ms})
                rec = ms.get("recommended")
                kpis.append({"label": "Eligible Sensor Drones", "value": ms.get("eligible_drones", 0)})
                answer_sections.append(
                    f"Multi-stop {entities['sensor_type']} sweep plotted for {country.name}, Sir: "
                    + (
                        f"assigning {rec['drone_id']} ({rec['total_distance_km']} km round-trip, {rec['estimated_duration_min']} min, {rec['predicted_battery_used_pct']}% battery)."
                        if rec else ms.get("reason", "No feasible flight plan available.")
                    )
                )

            elif intent == "route_logs":
                logs = self._run_tool(trace, "get_route_logs", {"limit": 20})
                if self._is_tool_error(logs):
                    _note_err(logs)
                    continue
                structured_cards.append({"type": "route_logs", "data": logs})
                answer_sections.append(f"Pulled the latest {logs['count']} 3D route solver telemetry logs, Sir.")

            elif intent == "mutual_aid":
                globe_state = "AWAITING_APPROVAL"
                rtype = entities["resource_type"]
                qty = entities["counts"].get("ambulance_count") or entities["counts"].get("quantity") or 8
                aid = self._run_tool(trace, "find_mutual_aid_options", {"country_id": cid, "resource_type": rtype, "quantity": qty})
                if self._is_tool_error(aid):
                    _note_err(aid)
                    continue
                structured_cards.append({"type": "mutual_aid", "data": aid})
                kpis.append({"label": "Eligible Donors", "value": len(aid["eligible_donors"])})
                if aid["eligible_donors"]:
                    top = aid["eligible_donors"][0]
                    apr = self._run_tool(trace, "prepare_cross_country_aid", {
                        "country_id": cid,
                        "donor_country_id": top["donor_country_id"],
                        "resource_type": rtype,
                        "quantity": top["proposed_transfer"],
                    })
                    if self._is_tool_error(apr):
                        _note_err(apr)
                        continue
                    pending_approval = apr
                    ctx.pending_approval_id = apr["approval_id"]
                    tables.append({
                        "title": f"Mutual Aid Donors ({rtype})",
                        "columns": ["Donor", "Distance (km)", "Surplus", "Proposed", "ETA (h)"],
                        "rows": [
                            [d["donor_name"], d["distance_km"], d["available_surplus"], d["proposed_transfer"], d["estimated_arrival_hours"]]
                            for d in aid["eligible_donors"]
                        ],
                    })
                    answer_sections.append(
                        f"{top['donor_name']} can spare {top['available_surplus']} {rtype} ({top['distance_km']} km out, ETA {top['estimated_arrival_hours']}h). "
                        f"I've queued transfer proposal {apr['approval_id']} for {top['proposed_transfer']} {rtype}—standing by for your green light, Sir."
                    )
                else:
                    answer_sections.append(f"No neighboring nations currently hold surplus {rtype} to spare for {country.name}, Sir.")

            elif intent == "prepare_swarm":
                globe_state = "AWAITING_APPROVAL"
                dcount = entities["counts"].get("drone_count", 8)
                mode = (
                    "MEDICAL_DELIVERY" if "medical" in low
                    else "FLOOD_ASSESSMENT" if "flood" in low
                    else "FIRE_PERIMETER" if "fire" in low
                    else "SURVIVOR_SEARCH" if "survivor" in low
                    else "AREA_SCAN"
                )
                formation = "GRID" if "grid" in low and "search grid" not in low else "SEARCH_GRID"
                apr = self._run_tool(trace, "prepare_swarm_operation", {
                    "country_id": cid, "drone_count": dcount, "mode": mode, "formation": formation,
                })
                if self._is_tool_error(apr):
                    _note_err(apr)
                    continue
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                kpis.extend([
                    {"label": "Swarm Size", "value": dcount},
                    {"label": "Approval ID", "value": apr["approval_id"]},
                ])
                answer_sections.append(
                    f"Staged a {dcount}-drone {mode.replace('_', ' ').lower()} swarm ({formation}) for {country.name} "
                    f"[{apr['approval_id']}]. Standing by for your green light, Sir."
                )

            elif intent == "prepare_drone_failure":
                globe_state = "AWAITING_APPROVAL"
                apr = self._run_tool(trace, "prepare_drone_failure", {"country_id": cid, "drone_id": entities["drone_id"]})
                if self._is_tool_error(apr):
                    _note_err(apr)
                    continue
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                answer_sections.append(
                    f"Simulated drone failure injection queued [{apr['approval_id']}] with automatic swarm failover armed. "
                    f"Standing by for your green light, Sir."
                )

            elif intent == "prepare_ambulance_dispatch":
                globe_state = "AWAITING_APPROVAL"
                cnt = entities["counts"].get("ambulance_count", 6)
                apr = self._run_tool(trace, "prepare_ambulance_dispatch", {"country_id": cid, "count": cnt})
                if self._is_tool_error(apr):
                    _note_err(apr)
                    continue
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                answer_sections.append(
                    f"Dispatch order staged for {cnt} ambulances in {country.name} [{apr['approval_id']}]. "
                    f"Standing by for your green light, Sir."
                )

            elif intent == "prepare_disaster":
                globe_state = "AWAITING_APPROVAL"
                dtype = entities["disaster_type"] or "FLOOD"
                sev = entities["counts"].get("severity", 0.78)
                apr = self._run_tool(trace, "prepare_disaster_event", {"country_id": cid, "disaster_type": dtype, "severity": sev})
                if self._is_tool_error(apr):
                    _note_err(apr)
                    continue
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                answer_sections.append(
                    f"Simulated {dtype} event queued for {country.name} at {int(sev * 100)}% severity [{apr['approval_id']}]. "
                    f"Standing by for your green light, Sir."
                )

            elif intent == "prepare_rescue_plan":
                globe_state = "AWAITING_APPROVAL"
                res_bundle = self._run_tool(trace, "prepare_comprehensive_rescue_plan", {"country_id": cid})
                if self._is_tool_error(res_bundle):
                    _note_err(res_bundle)
                    continue
                plan = res_bundle["plan"]
                apr = res_bundle["approval"]
                pr = plan["proposed_resources"]
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                structured_cards.append({"type": "rescue_plan", "data": plan})
                kpis.extend([
                    {"label": "Proposed Drones", "value": pr["drones"]},
                    {"label": "Proposed Ambulances", "value": pr["ambulances"]},
                    {"label": "Shelters to Activate", "value": pr["shelters_to_activate"]},
                ])
                answer_sections.append(
                    f"I've assembled the full rescue playbook for {country.name} ({plan['plan_id']}), Sir: {pr['drones']} drones, "
                    f"{pr['ambulances']} ambulances, and {pr['shelters_to_activate']} shelters covering {plan['population_at_risk']:,} exposed residents "
                    f"[{apr['approval_id']}]. Standing by for your green light, Sir."
                )

            elif intent == "counterfactual":
                globe_state = "OPTIMIZING"
                cf = self._run_tool(trace, "run_counterfactual_comparison", {"country_id": cid})
                if self._is_tool_error(cf):
                    _note_err(cf)
                    continue
                structured_cards.append({"type": "counterfactual", "data": cf})
                s0, s3 = cf["scenarios"][0], cf["scenarios"][-1]
                tables.append({
                    "title": f"Counterfactual Comparison — {country.name}",
                    "columns": ["Strategy", "Evacuated", "First Response (m)", "Completion (m)", "Failures"],
                    "rows": [
                        [s["label"], s["people_safely_evacuated"], s["time_to_first_response_min"], s["rescue_completion_min"], s["mission_failures"]]
                        for s in cf["scenarios"]
                    ],
                })
                answer_sections.append(
                    f"Ran the numbers across all four counterfactual scenarios ({cf['counterfactual_id']}, seed {cf['seed']}) for {country.name}, Sir: "
                    f"Conventional evacuates {s0['people_safely_evacuated']:,} in {s0['rescue_completion_min']}m, whereas "
                    f"Swarm + Mutual Aid evacuates {s3['people_safely_evacuated']:,} in {s3['rescue_completion_min']}m."
                )

            elif intent == "rescue_equity":
                eq = self._run_tool(trace, "evaluate_rescue_equity", {"country_id": cid})
                if self._is_tool_error(eq):
                    _note_err(eq)
                    continue
                structured_cards.append({"type": "rescue_equity", "data": eq})
                kpis.append({"label": "Underserved Districts", "value": eq["underserved_count"]})
                tables.append({
                    "title": f"Rescue Equity Priority — {country.name}",
                    "columns": ["District", "Exposed", "Vulnerable", "Road Access", "Equity Score", "Underserved"],
                    "rows": [
                        [d["name"], d["exposed_residents"], d["vulnerable_residents"], f"{int(d['road_accessibility'] * 100)}%", d["equity_priority_score"], "Yes" if d["underserved_flag"] else "No"]
                        for d in eq["districts"][:6]
                    ],
                })
                answer_sections.append(
                    f"Equity sweep complete for {country.name}, Sir: {eq['underserved_count']} underserved districts flagged for priority attention."
                )

            elif intent == "cascade_graph":
                cg = self._run_tool(trace, "get_cascade_graph", {"country_id": cid})
                if self._is_tool_error(cg):
                    _note_err(cg)
                    continue
                structured_cards.append({"type": "cascade_graph", "data": cg})
                answer_sections.append(
                    f"Cascade model for {country.name} is up, Sir: {len(cg['nodes'])} hazard and infrastructure nodes mapped across {len(cg['edges'])} causal links."
                )

            elif intent == "hospital_status":
                hs = self._run_tool(trace, "get_hospital_status", {"country_id": cid})
                if self._is_tool_error(hs):
                    _note_err(hs)
                    continue
                structured_cards.append({"type": "hospital_status", "data": hs})
                kpis.extend([
                    {"label": "Hospitals Online", "value": f"{hs['operational_count']}/{hs['total_hospitals']}"},
                    {"label": "Available Beds", "value": f"{hs['available_beds']}/{hs['total_beds']}"},
                ])
                tables.append({
                    "title": f"Hospitals — {country.name}",
                    "columns": ["ID", "Name", "Status", "Available Beds", "Total Beds", "Triage Load"],
                    "rows": [[h["hospital_id"], h["name"], h["status"], h["available_beds"], h["total_beds"], h["triage_load"]] for h in hs["hospitals"]],
                })
                answer_sections.append(
                    f"Medical grid in {country.name}, Sir: {hs['operational_count']}/{hs['total_hospitals']} hospitals online with {hs['available_beds']}/{hs['total_beds']} beds open."
                )

            elif intent == "available_beds":
                ab = self._run_tool(trace, "get_available_beds", {"country_id": cid})
                if self._is_tool_error(ab):
                    _note_err(ab)
                    continue
                structured_cards.append({"type": "available_beds", "data": ab})
                kpis.append({"label": "Available Beds", "value": f"{ab['total_available_beds']}/{ab['total_beds']}"})
                answer_sections.append(
                    f"Hospital bed capacity in {country.name}, Sir: {ab['total_available_beds']}/{ab['total_beds']} beds open across {len(ab['hospitals'])} active facilities."
                )

            elif intent == "ambulance_requirements":
                amb = self._run_tool(trace, "calculate_ambulance_requirements", {"country_id": cid, "window_hours": entities["counts"].get("hours", 4.0)})
                if self._is_tool_error(amb):
                    _note_err(amb)
                    continue
                structured_cards.append({"type": "ambulance_requirements", "data": amb})
                kpis.extend([
                    {"label": "Ambulances Available", "value": f"{amb['available_ambulances']}/{amb['recommended_operational_fleet']}"},
                    {"label": "Ambulance Deficit", "value": amb["ambulance_deficit"]},
                ])
                answer_sections.append(f"Medical transport math for {country.name}, Sir: {amb['explanation']}")

            elif intent == "ambulance_fleet":
                af = self._run_tool(trace, "get_ambulance_fleet", {"country_id": cid})
                if self._is_tool_error(af):
                    _note_err(af)
                    continue
                structured_cards.append({"type": "ambulance_fleet", "data": af})
                kpis.append({"label": "Ambulances Ready", "value": f"{af['available_count']}/{af['total_ambulances']}"})
                answer_sections.append(f"EMS fleet in {country.name}, Sir: {af['available_count']}/{af['total_ambulances']} ambulances standing by.")

            elif intent == "fire_units":
                fu = self._run_tool(trace, "get_fire_units", {"country_id": cid})
                if self._is_tool_error(fu):
                    _note_err(fu)
                    continue
                structured_cards.append({"type": "fire_units", "data": fu})
                kpis.append({"label": "Fire Units Available", "value": f"{fu['available_count']}/{fu['total_units']}"})
                answer_sections.append(
                    f"Fire and rescue units in {country.name}, Sir: {fu['available_count']} available, {fu['on_scene_count']} on scene ({fu['total_units']} total)."
                )

            elif intent == "shelter_capacity":
                sc = self._run_tool(trace, "get_shelter_capacity", {"country_id": cid})
                if self._is_tool_error(sc):
                    _note_err(sc)
                    continue
                structured_cards.append({"type": "shelter_capacity", "data": sc})
                kpis.append({"label": "Shelter Capacity Remaining", "value": f"{sc['total_remaining_capacity']:,}"})
                answer_sections.append(
                    f"Relief shelters in {country.name}, Sir: {sc['accessible_shelters']}/{sc['total_shelters']} accessible, "
                    f"{sc['total_remaining_capacity']:,}/{sc['total_max_occupancy']:,} capacity remaining."
                )

            elif intent == "warehouse_inventory":
                wi = self._run_tool(trace, "get_warehouse_inventory", {"country_id": cid})
                if self._is_tool_error(wi):
                    _note_err(wi)
                    continue
                structured_cards.append({"type": "warehouse_inventory", "data": wi})
                wt = wi["totals"]
                kpis.extend([
                    {"label": "Warehouse Food", "value": f"{wt['food_packages']:,} pkgs"},
                    {"label": "Warehouse Water", "value": f"{wt['water_liters']:,.0f} L"},
                ])
                answer_sections.append(
                    f"Depot stock across {wi['warehouse_count']} warehouses in {country.name}, Sir: {wt['food_packages']:,} food pkgs, "
                    f"{wt['water_liters']:,.0f} L water, {wt['medical_kits']:,} medical kits, and {wt['generators']} generators."
                )

            elif intent == "resource_shortages":
                rs = self._run_tool(trace, "get_resource_shortages", {"country_id": cid, "horizon_hours": entities["counts"].get("hours", 24.0)})
                if self._is_tool_error(rs):
                    _note_err(rs)
                    continue
                structured_cards.append({"type": "resource_shortages", "data": rs})
                kpis.append({"label": "Shortage Alerts", "value": len(rs["shortage_warnings"])})
                answer_sections.append(
                    f"Supply risk scan for {country.name}, Sir: "
                    + ("; ".join(rs["shortage_warnings"]) if rs["shortage_warnings"] else "No critical shortages projected.")
                )

            elif intent == "resource_requirements":
                rr = self._run_tool(trace, "calculate_resource_requirements", {"country_id": cid, "horizon_hours": entities["counts"].get("hours", 24.0)})
                if self._is_tool_error(rr):
                    _note_err(rr)
                    continue
                structured_cards.append({"type": "resource_requirements", "data": rr})
                answer_sections.append(
                    f"24h logistics forecast for {country.name}, Sir: Food {rr['food_packages']['needed']:,} pkgs (stock {rr['food_packages']['available']:,}), "
                    f"Water {rr['water_liters']['needed']:,.0f} L (stock {rr['water_liters']['available']:,.0f} L)."
                )

            elif intent == "low_battery_drones":
                thresh = entities["counts"].get("battery_threshold", 35.0)
                lb = self._run_tool(trace, "get_low_battery_drones", {"threshold": thresh})
                if self._is_tool_error(lb):
                    _note_err(lb)
                    continue
                structured_cards.append({"type": "low_battery_drones", "data": lb})
                kpis.append({"label": f"Drones < {int(thresh)}%", "value": lb["count"]})
                answer_sections.append(f"Power check complete, Sir: {lb['count']} drones currently below {int(thresh)}% charge.")

            elif intent == "available_drones":
                ad = self._run_tool(trace, "get_available_drones", {"country_id": cid})
                if self._is_tool_error(ad):
                    _note_err(ad)
                    continue
                structured_cards.append({"type": "available_drones", "data": ad})
                kpis.append({"label": "Available Drones", "value": ad["count"]})
                answer_sections.append(f"Air wing in {country.name}, Sir: {ad['count']} drones charged and cleared for launch.")

            elif intent == "drone_fleet":
                df = self._run_tool(trace, "get_drone_fleet", {"country_id": cid})
                if self._is_tool_error(df):
                    _note_err(df)
                    continue
                structured_cards.append({"type": "drone_fleet", "data": df})
                kpis.append({"label": "Drone Fleet", "value": f"{df['available_count']}/{df['total_drones']} avail"})
                answer_sections.append(f"Drone roster for {country.name}, Sir: {df['available_count']}/{df['total_drones']} flight-ready.")

            elif intent == "swarm_status":
                sw = self._run_tool(trace, "get_swarm_status", {})
                if self._is_tool_error(sw):
                    _note_err(sw)
                    continue
                structured_cards.append({"type": "swarm_status", "data": sw})
                kpis.append({"label": "Active Swarms", "value": sw["active_swarms"]})
                answer_sections.append(f"Swarm telemetry, Sir: {sw['active_swarms']} active formations ({sw['total_swarms']} total logged).")

            elif intent == "active_disasters":
                ad = self._run_tool(trace, "get_active_disasters", {})
                if self._is_tool_error(ad):
                    _note_err(ad)
                    continue
                structured_cards.append({"type": "active_disasters", "data": ad})
                kpis.append({"label": "Active Disasters", "value": ad["count"]})
                answer_sections.append(f"Global hazard board, Sir: {ad['count']} active disaster events under live tracking.")

            elif intent == "disaster_impact":
                di = self._run_tool(trace, "get_disaster_impact", {"country_id": cid})
                if self._is_tool_error(di):
                    _note_err(di)
                    continue
                structured_cards.append({"type": "disaster_impact", "data": di})
                kpis.extend([
                    {"label": "Exposed Population", "value": di["exposed_population"]},
                    {"label": "Blocked Roads", "value": di["blocked_roads"]},
                ])
                answer_sections.append(
                    f"Impact readout for {country.name}, Sir: {di['exposed_population']:,} exposed, {di['estimated_injuries']:,} estimated injuries, "
                    f"{di['blocked_roads']} blocked roads, and {di['damaged_buildings']} damaged structures."
                )

            elif intent == "country_cities":
                cc = self._run_tool(trace, "get_country_cities", {"country_id": cid})
                if self._is_tool_error(cc):
                    _note_err(cc)
                    continue
                structured_cards.append({"type": "country_cities", "data": cc})
                answer_sections.append(f"Urban centers in {country.name}, Sir: {', '.join(c['name'] for c in cc['cities'])}.")

            elif intent == "district_details":
                dd = self._run_tool(trace, "get_district_details", {"country_id": cid, "district_id": entities["district_id"]})
                if self._is_tool_error(dd):
                    _note_err(dd)
                    continue
                structured_cards.append({"type": "district_details", "data": dd})
                answer_sections.append(f"Pulled {dd['count']} district telemetry records for {country.name}, Sir.")

            elif intent == "buildings_summary":
                bs = self._run_tool(trace, "get_buildings_summary", {"country_id": cid})
                if self._is_tool_error(bs):
                    _note_err(bs)
                    continue
                structured_cards.append({"type": "buildings_summary", "data": bs})
                answer_sections.append(
                    f"Structural scan for {country.name}, Sir: {bs['total_buildings']} buildings tracked "
                    f"({bs['damaged_count']} damaged, {bs['inaccessible_count']} cut off)."
                )

            elif intent == "population_summary":
                ps = self._run_tool(trace, "get_population_summary", {"country_id": cid})
                if self._is_tool_error(ps):
                    _note_err(ps)
                    continue
                structured_cards.append({"type": "population_summary", "data": ps})
                kpis.extend([
                    {"label": "Total Residents", "value": ps["total_residents"]},
                    {"label": "Exposed Residents", "value": ps["exposed_residents"]},
                ])
                answer_sections.append(
                    f"Civilian headcount for {country.name}, Sir: {ps['total_residents']:,} total, "
                    f"{ps['exposed_residents']:,} exposed, {ps['vulnerable_residents']:,} vulnerable."
                )

            elif intent == "household_statistics":
                hh = self._run_tool(trace, "get_household_statistics", {"country_id": cid})
                if self._is_tool_error(hh):
                    _note_err(hh)
                    continue
                structured_cards.append({"type": "household_statistics", "data": hh})
                answer_sections.append(
                    f"Household breakdown for {country.name}, Sir: ~{hh['district_estimated_households']:,} estimated "
                    f"({hh['tracked_households']} tracked, {hh['needs_assisted_transport']} requiring assisted transport)."
                )

            elif intent == "animal_population":
                ap = self._run_tool(trace, "get_animal_population", {"country_id": cid})
                if self._is_tool_error(ap):
                    _note_err(ap)
                    continue
                structured_cards.append({"type": "animal_population", "data": ap})
                answer_sections.append(
                    f"Animal populations in {country.name}, Sir: {ap['total_animals']:,} total ({ap['exposed_animals']:,} exposed)."
                )

            elif intent == "list_playbooks":
                pb = self._run_tool(trace, "list_playbooks", {})
                if self._is_tool_error(pb):
                    _note_err(pb)
                    continue
                structured_cards.append({"type": "playbooks", "data": pb})
                answer_sections.append(f"All {pb['count']} disaster response playbooks (PB-01 through PB-24) are loaded and on deck, Sir.")

            elif intent == "event_timeline":
                et = self._run_tool(trace, "get_event_timeline", {"limit": 25})
                if self._is_tool_error(et):
                    _note_err(et)
                    continue
                structured_cards.append({"type": "event_timeline", "data": et})
                answer_sections.append(f"Event bus readout (world v{et['world_version']}), Sir: {len(et['events'])} recent events retrieved.")

            elif intent == "audit_logs":
                al = self._run_tool(trace, "get_audit_logs", {"limit": 25})
                if self._is_tool_error(al):
                    _note_err(al)
                    continue
                structured_cards.append({"type": "audit_logs", "data": al})
                answer_sections.append(
                    f"Audit trail is spotless, Sir: {al['audit_count']} approval records and {al['tool_log_count']} tool executions logged."
                )

            elif intent == "pending_approvals":
                pa = self._run_tool(trace, "list_pending_approvals", {"status": "PENDING"})
                if self._is_tool_error(pa):
                    _note_err(pa)
                    continue
                structured_cards.append({"type": "pending_approvals", "data": pa})
                answer_sections.append(
                    f"You have {len(pa['approvals'])} pending operator approvals awaiting your sign-off, Sir."
                )

            elif intent == "save_world_local":
                sv = self._run_tool(trace, "save_world_local", {})
                if self._is_tool_error(sv):
                    _note_err(sv)
                    continue
                structured_cards.append({"type": "save_world_local", "data": sv})
                answer_sections.append(f"Local snapshot saved (world v{sv['world_version']}) to {sv['path']}, Sir.")

            elif intent == "country_list":
                cl = self._run_tool(trace, "get_country_list", {})
                if self._is_tool_error(cl):
                    _note_err(cl)
                    continue
                structured_cards.append({"type": "country_list", "data": cl})
                answer_sections.append(f"All 7 nations online, Sir: {', '.join(c['name'] for c in cl['countries'])}.")

            else:
                globe_state = "QUERYING"
                detail = self._run_tool(trace, "get_country_status", {"country_id": cid})
                if self._is_tool_error(detail):
                    _note_err(detail)
                    continue
                amb = detail["ambulance_analysis"]
                res = detail["resource_analysis"]
                active_dis = [d for d in detail["disasters"] if d["status"] == "ACTIVE"]
                hosp_op = sum(1 for h in detail["hospitals"] if h["status"] in ("OPERATIONAL", "PARTIALLY_OPERATIONAL"))
                structured_cards.append({"type": "disaster_analysis", "data": {"country": detail["profile"], "ambulance": amb, "resources": res}})
                kpis.extend([
                    {"label": "Active Disasters", "value": len(active_dis)},
                    {"label": "Exposed Population", "value": res["exposed_population"]},
                    {"label": "Available Beds", "value": amb["available_hospital_beds"]},
                    {"label": "Ambulances Ready", "value": f"{amb['available_ambulances']}/{amb['recommended_operational_fleet']}"},
                ])
                answer_sections.append(
                    f"Right away, Sir. Live briefing for {country.name} ({cid}, v{self.world.event_bus.world_version}):\n"
                    f"• Active disasters: {len(active_dis)} ({', '.join(d['name'] for d in active_dis) or 'None'})\n"
                    f"• Exposed: {res['exposed_population']:,} | Evac demand: {res['evacuation_shelter_demand']:,}\n"
                    f"• Hospitals: {hosp_op}/{len(detail['hospitals'])} online ({amb['available_hospital_beds']} beds free) | Ambulances: {amb['available_ambulances']}/{amb['recommended_operational_fleet']} needed\n"
                    f"• 24h Supplies: Food {res['food_packages']['needed']:,} pkgs (stock {res['food_packages']['available']:,}), Water {res['water_liters']['needed']:,.0f} L"
                )

        if trace and all(entry.get("status") == "ERROR" for entry in trace):
            globe_state = "ERROR"

        answer = "\n".join(answer_sections)

        # Ultra-fast grounded response by default (<5ms); optional LLM polish when requested & keys configured
        provider_used = "instant_grounded_orchestrator"
        model_used = "zero-latency-tool-engine"
        if use_llm_polish:
            llm_res = await self.provider_manager.synthesize_narrative(
                message, answer, answer, tool_schemas=self.get_tool_schemas()
            )
            answer = llm_res["text"]
            provider_used = llm_res["provider_used"]
            model_used = llm_res["model_used"]

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        tools_called = [entry["tool"] for entry in trace]
        intent_label = intents[0] if len(intents) == 1 else f"compound:{'+'.join(intents)}"

        reply_record = {
            "reply_id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": utc_now_iso(),
            "session_id": session_id,
            "user_message": message,
            "assistant_message": answer,
            "spoken_summary": answer.replace("\n", " ").replace("•", "")[:280],
            "provider": provider_used,
            "model": model_used,
            "latency_ms": total_ms,
            "globe_state": globe_state,
            "intent": intent_label,
            "intents": intents,
            "entities": entities,
            "kpis": kpis,
            "tables": tables,
            "tools_called": tools_called,
            "context": ctx.snapshot(),
            "execution_trace": trace,
            "structured_cards": structured_cards,
            "frontend_commands": frontend_commands,
            "pending_approval": pending_approval,
        }
        self.conversations.setdefault(session_id, deque(maxlen=200)).append(reply_record)
        return reply_record
