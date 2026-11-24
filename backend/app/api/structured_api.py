from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from app.core.compat import to_dict, utc_now_iso

SCHEMA_VERSION = "2.0"

SUPPORTED_TABLE_RESOURCES = (
    "countries",
    "drones",
    "hospitals",
    "shelters",
    "ambulances",
    "fire_units",
    "disasters",
    "roads",
)


def _enum_val(value: Any) -> Any:
    """Convert Enum values to their underlying scalar representation."""
    if value is None:
        return None
    return value.value if hasattr(value, "value") else value


class VersionedResponseCache:
    """In-memory cache keyed by event_bus.world_version with automatic invalidation."""

    def __init__(self) -> None:
        self._version: int = -1
        self._store: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.hits: int = 0
        self.misses: int = 0

    def get_or_build(
        self,
        world_version: int,
        key: Tuple[Any, ...],
        builder: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        if world_version != self._version:
            self._store.clear()
            self._version = world_version
        cached = self._store.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        result = builder()
        self._store[key] = result
        return result


def _envelope(world_version: int, data: Any, count: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "world_version": world_version,
        "generated_at": utc_now_iso(),
        "count": count,
        "data": data,
    }


def _score_match(query_norm: str, query_tokens: List[str], item_id: str, name: str, extra: str = "") -> float:
    """Fast multi-tier exact, prefix, substring, token, and fuzzy match scorer."""
    id_low = item_id.lower()
    name_low = name.lower()
    extra_low = extra.lower()

    if query_norm == id_low or query_norm == name_low:
        return 1.0
    if id_low.startswith(query_norm) or name_low.startswith(query_norm):
        return 0.94
    if query_norm in id_low or query_norm in name_low:
        return 0.85

    haystack = f"{id_low} {name_low} {extra_low}".strip()
    if query_norm in haystack:
        return 0.78

    if len(query_tokens) > 1 and all(tok in haystack for tok in query_tokens):
        return 0.74

    # Fuzzy matching against name, id, and individual words in name
    best_ratio = max(
        SequenceMatcher(None, query_norm, name_low).ratio(),
        SequenceMatcher(None, query_norm, id_low).ratio(),
    )
    for word in name_low.replace("-", " ").replace("_", " ").split():
        if len(word) >= 3:
            r = SequenceMatcher(None, query_norm, word).ratio()
            if r > best_ratio:
                best_ratio = r

    if best_ratio >= 0.58:
        return round(best_ratio * 0.72, 4)
    return 0.0


def build_v2_router(services: Any) -> APIRouter:
    """Build the version-cached /api/v2 structured Data Access API router (zero DB deps)."""
    router = APIRouter(prefix="/api/v2", tags=["quantum-rescue-v2-structured"])
    cache = VersionedResponseCache()
    router.v2_cache = cache  # type: ignore[attr-defined]

    def _world_version() -> int:
        return int(getattr(services.event_bus, "world_version", 1))

    # ------------------------------------------------------------------
    # Internal normalized builders (cached per world_version)
    # ------------------------------------------------------------------
    def _build_snapshot() -> Dict[str, Any]:
        world = services.world
        overview = world.get_global_overview()

        compact_countries: List[Dict[str, Any]] = []
        for c in overview["countries"]:
            center = c.get("center") or {}
            compact_countries.append(
                {
                    "country_id": c["country_id"],
                    "name": c["name"],
                    "flag_code": c["flag_code"],
                    "archetype": c["archetype"],
                    "color": c["color"],
                    "capital_city_id": c["capital_city_id"],
                    "capital_name": c["capital_name"],
                    "lat": center.get("lat"),
                    "lon": center.get("lon"),
                    "terrain_profile": c["terrain_profile"],
                    "climate_zone": c["climate_zone"],
                    "readiness_score": c["readiness_score"],
                    "comm_uptime_pct": c["comm_uptime_pct"],
                    "power_grid_pct": c["power_grid_pct"],
                    "total_population": c["total_population"],
                    "exposed_population": c["exposed_population"],
                    "evacuated_population": c["evacuated_population"],
                    "injured_population": c["injured_population"],
                    "active_disasters": c["active_disasters"],
                    "hospitals_operational": c["hospitals_operational"],
                    "hospitals_total": c["hospitals_total"],
                    "available_beds": c["available_beds"],
                    "ambulances_available": c["ambulances_available"],
                    "ambulances_total": c["ambulances_total"],
                    "drones_available": c["drones_available"],
                    "drones_active": c["drones_active"],
                    "drones_total": c["drones_total"],
                    "shelter_remaining_capacity": c["shelter_remaining_capacity"],
                }
            )

        active_disasters: List[Dict[str, Any]] = []
        for ev in world.disasters.values():
            if _enum_val(ev.status) == "ACTIVE":
                active_disasters.append(
                    {
                        "event_id": ev.event_id,
                        "country_id": ev.country_id,
                        "city_id": ev.city_id,
                        "disaster_type": _enum_val(ev.disaster_type),
                        "name": ev.name,
                        "lat": ev.origin.lat,
                        "lon": ev.origin.lon,
                        "radius_km": ev.radius_km,
                        "severity": ev.severity,
                        "status": _enum_val(ev.status),
                        "affected_population": ev.affected_population,
                        "evacuation_demand": ev.evacuation_demand,
                        "estimated_injuries": ev.estimated_injuries,
                        "blocked_roads": ev.blocked_roads,
                        "affected_buildings": ev.affected_buildings,
                    }
                )

        counts = {
            "countries": len(world.countries),
            "cities": len(world.cities),
            "districts": len(world.districts),
            "hospitals": len(world.hospitals),
            "shelters": len(world.shelters),
            "warehouses": len(world.warehouses),
            "ambulances": len(world.ambulances),
            "fire_units": len(world.fire_units),
            "drones": len(world.drones),
            "roads": len(world.roads),
            "animals": len(world.animals),
            "disasters_total": len(world.disasters),
            "active_disasters": len(active_disasters),
            "swarms": len(world.swarms),
        }

        data = {
            "scenario_id": overview["scenario_id"],
            "seed": overview["seed"],
            "selected_country_id": overview["selected_country_id"],
            "clock": overview["clock"],
            "totals": overview["totals"],
            "countries": compact_countries,
            "active_disasters": active_disasters,
            "counts": counts,
        }
        return _envelope(_world_version(), data=data, count=len(compact_countries))

    def _build_country_bundle(country_id: str) -> Dict[str, Any]:
        world = services.world
        if country_id not in world.countries:
            raise HTTPException(status_code=404, detail=f"Unknown country_id: {country_id}")

        cities = [to_dict(c) for c in world.cities.values() if c.country_id == country_id]
        districts = [to_dict(d) for d in world.districts.values() if d.country_id == country_id]
        hospitals = [
            {**to_dict(h), "available_beds": h.available_beds}
            for h in world.hospitals.values()
            if h.country_id == country_id
        ]
        shelters = [
            {**to_dict(s), "remaining_capacity": s.remaining_capacity}
            for s in world.shelters.values()
            if s.country_id == country_id
        ]
        warehouses = [to_dict(w) for w in world.warehouses.values() if w.country_id == country_id]
        ambulances = [to_dict(a) for a in world.ambulances.values() if a.country_id == country_id]
        fire_units = [to_dict(f) for f in world.fire_units.values() if f.country_id == country_id]
        drones = [to_dict(d) for d in world.drones.values() if d.country_id == country_id]
        roads = [to_dict(r) for r in world.roads.values() if r.country_id == country_id]
        animals = [to_dict(a) for a in world.animals.values() if a.country_id == country_id]
        disasters = [to_dict(ev) for ev in world.disasters.values() if ev.country_id == country_id]

        data = {
            "profile": to_dict(world.countries[country_id]),
            "cities": cities,
            "districts": districts,
            "hospitals": hospitals,
            "shelters": shelters,
            "warehouses": warehouses,
            "ambulances": ambulances,
            "fire_units": fire_units,
            "drones": drones,
            "roads": roads,
            "animals": animals,
            "disasters": disasters,
            "ambulance_requirements": world.calculate_ambulance_requirements(country_id),
            "resource_requirements": world.calculate_resource_requirements(country_id),
            "equity": world.evaluate_rescue_equity(country_id),
            "cascade_graph": world.get_cascade_graph(country_id),
        }
        entity_count = (
            len(cities)
            + len(districts)
            + len(hospitals)
            + len(shelters)
            + len(warehouses)
            + len(ambulances)
            + len(fire_units)
            + len(drones)
            + len(roads)
            + len(animals)
            + len(disasters)
        )
        return _envelope(_world_version(), data=data, count=entity_count)

    def _build_table(resource: str, country_id: Optional[str]) -> Dict[str, Any]:
        world = services.world
        if resource not in SUPPORTED_TABLE_RESOURCES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported table resource '{resource}'. Allowed: {', '.join(SUPPORTED_TABLE_RESOURCES)}",
            )

        columns: List[str]
        rows: List[Dict[str, Any]] = []

        if resource == "countries":
            columns = [
                "country_id",
                "name",
                "flag_code",
                "archetype",
                "capital_name",
                "lat",
                "lon",
                "total_population",
                "exposed_population",
                "evacuated_population",
                "injured_population",
                "active_disasters",
                "hospitals_operational",
                "available_beds",
                "ambulances_available",
                "drones_available",
                "drones_total",
                "readiness_score",
                "power_grid_pct",
                "comm_uptime_pct",
            ]
            overview_countries = world.get_global_overview()["countries"]
            for c in overview_countries:
                if country_id and c["country_id"] != country_id:
                    continue
                center = c.get("center") or {}
                rows.append(
                    {
                        "country_id": c["country_id"],
                        "name": c["name"],
                        "flag_code": c["flag_code"],
                        "archetype": c["archetype"],
                        "capital_name": c["capital_name"],
                        "lat": center.get("lat"),
                        "lon": center.get("lon"),
                        "total_population": c["total_population"],
                        "exposed_population": c["exposed_population"],
                        "evacuated_population": c["evacuated_population"],
                        "injured_population": c["injured_population"],
                        "active_disasters": c["active_disasters"],
                        "hospitals_operational": c["hospitals_operational"],
                        "available_beds": c["available_beds"],
                        "ambulances_available": c["ambulances_available"],
                        "drones_available": c["drones_available"],
                        "drones_total": c["drones_total"],
                        "readiness_score": c["readiness_score"],
                        "power_grid_pct": c["power_grid_pct"],
                        "comm_uptime_pct": c["comm_uptime_pct"],
                    }
                )

        elif resource == "drones":
            columns = [
                "drone_id",
                "country_id",
                "city_id",
                "home_station",
                "category",
                "status",
                "battery_pct",
                "altitude_m",
                "speed_mps",
                "max_payload_kg",
                "current_load_kg",
                "sensors",
                "assigned_mission_id",
                "swarm_id",
                "comm_connected",
                "lat",
                "lon",
            ]
            for d in world.drones.values():
                if country_id and d.country_id != country_id:
                    continue
                rows.append(
                    {
                        "drone_id": d.drone_id,
                        "country_id": d.country_id,
                        "city_id": d.city_id,
                        "home_station": d.home_station,
                        "category": d.category,
                        "status": _enum_val(d.status),
                        "battery_pct": d.battery_pct,
                        "altitude_m": d.altitude_m,
                        "speed_mps": d.speed_mps,
                        "max_payload_kg": d.max_payload_kg,
                        "current_load_kg": d.current_load_kg,
                        "sensors": ",".join(d.sensors),
                        "assigned_mission_id": d.assigned_mission_id,
                        "swarm_id": d.swarm_id,
                        "comm_connected": d.comm_connected,
                        "lat": d.location.lat,
                        "lon": d.location.lon,
                    }
                )

        elif resource == "hospitals":
            columns = [
                "hospital_id",
                "country_id",
                "city_id",
                "district_id",
                "name",
                "status",
                "total_beds",
                "occupied_beds",
                "available_beds",
                "emergency_staff",
                "ambulance_access",
                "medical_kits",
                "generator_hours_remaining",
                "triage_load",
                "lat",
                "lon",
            ]
            for h in world.hospitals.values():
                if country_id and h.country_id != country_id:
                    continue
                rows.append(
                    {
                        "hospital_id": h.hospital_id,
                        "country_id": h.country_id,
                        "city_id": h.city_id,
                        "district_id": h.district_id,
                        "name": h.name,
                        "status": _enum_val(h.status),
                        "total_beds": h.total_beds,
                        "occupied_beds": h.occupied_beds,
                        "available_beds": h.available_beds,
                        "emergency_staff": h.emergency_staff,
                        "ambulance_access": h.ambulance_access,
                        "medical_kits": h.medical_kits,
                        "generator_hours_remaining": h.generator_hours_remaining,
                        "triage_load": h.triage_load,
                        "lat": h.location.lat,
                        "lon": h.location.lon,
                    }
                )

        elif resource == "shelters":
            columns = [
                "shelter_id",
                "country_id",
                "city_id",
                "district_id",
                "name",
                "status",
                "max_occupancy",
                "current_occupancy",
                "remaining_capacity",
                "food_packages",
                "water_liters",
                "medical_kits",
                "power_backup",
                "accessible",
                "lat",
                "lon",
            ]
            for s in world.shelters.values():
                if country_id and s.country_id != country_id:
                    continue
                rows.append(
                    {
                        "shelter_id": s.shelter_id,
                        "country_id": s.country_id,
                        "city_id": s.city_id,
                        "district_id": s.district_id,
                        "name": s.name,
                        "status": _enum_val(s.status),
                        "max_occupancy": s.max_occupancy,
                        "current_occupancy": s.current_occupancy,
                        "remaining_capacity": s.remaining_capacity,
                        "food_packages": s.food_packages,
                        "water_liters": s.water_liters,
                        "medical_kits": s.medical_kits,
                        "power_backup": s.power_backup,
                        "accessible": s.accessible,
                        "lat": s.location.lat,
                        "lon": s.location.lon,
                    }
                )

        elif resource == "ambulances":
            columns = [
                "ambulance_id",
                "country_id",
                "city_id",
                "home_station",
                "equipment_profile",
                "status",
                "fuel_pct",
                "speed_kph",
                "patient_capacity",
                "patients_onboard",
                "staff_count",
                "assigned_district_id",
                "destination_hospital_id",
                "lat",
                "lon",
            ]
            for a in world.ambulances.values():
                if country_id and a.country_id != country_id:
                    continue
                rows.append(
                    {
                        "ambulance_id": a.ambulance_id,
                        "country_id": a.country_id,
                        "city_id": a.city_id,
                        "home_station": a.home_station,
                        "equipment_profile": a.equipment_profile,
                        "status": _enum_val(a.status),
                        "fuel_pct": a.fuel_pct,
                        "speed_kph": a.speed_kph,
                        "patient_capacity": a.patient_capacity,
                        "patients_onboard": a.patients_onboard,
                        "staff_count": a.staff_count,
                        "assigned_district_id": a.assigned_district_id,
                        "destination_hospital_id": a.destination_hospital_id,
                        "lat": a.location.lat,
                        "lon": a.location.lon,
                    }
                )

        elif resource == "fire_units":
            columns = [
                "unit_id",
                "country_id",
                "city_id",
                "unit_type",
                "status",
                "personnel_count",
                "water_liters",
                "assigned_event_id",
                "lat",
                "lon",
            ]
            for f in world.fire_units.values():
                if country_id and f.country_id != country_id:
                    continue
                rows.append(
                    {
                        "unit_id": f.unit_id,
                        "country_id": f.country_id,
                        "city_id": f.city_id,
                        "unit_type": f.unit_type,
                        "status": _enum_val(f.status),
                        "personnel_count": f.personnel_count,
                        "water_liters": f.water_liters,
                        "assigned_event_id": f.assigned_event_id,
                        "lat": f.location.lat,
                        "lon": f.location.lon,
                    }
                )

        elif resource == "disasters":
            columns = [
                "event_id",
                "country_id",
                "city_id",
                "disaster_type",
                "name",
                "status",
                "severity",
                "radius_km",
                "wind_kph",
                "rainfall_mm_hr",
                "affected_population",
                "evacuation_demand",
                "estimated_injuries",
                "blocked_roads",
                "affected_buildings",
                "lat",
                "lon",
            ]
            for ev in world.disasters.values():
                if country_id and ev.country_id != country_id:
                    continue
                rows.append(
                    {
                        "event_id": ev.event_id,
                        "country_id": ev.country_id,
                        "city_id": ev.city_id,
                        "disaster_type": _enum_val(ev.disaster_type),
                        "name": ev.name,
                        "status": _enum_val(ev.status),
                        "severity": ev.severity,
                        "radius_km": ev.radius_km,
                        "wind_kph": ev.wind_kph,
                        "rainfall_mm_hr": ev.rainfall_mm_hr,
                        "affected_population": ev.affected_population,
                        "evacuation_demand": ev.evacuation_demand,
                        "estimated_injuries": ev.estimated_injuries,
                        "blocked_roads": ev.blocked_roads,
                        "affected_buildings": ev.affected_buildings,
                        "lat": ev.origin.lat,
                        "lon": ev.origin.lon,
                    }
                )

        else:  # roads
            columns = [
                "road_id",
                "country_id",
                "city_id",
                "name",
                "category",
                "length_km",
                "speed_limit_kph",
                "capacity_vph",
                "is_bridge",
                "accessible",
                "flood_depth_m",
                "blocked_reason",
                "start_lat",
                "start_lon",
                "end_lat",
                "end_lon",
            ]
            for r in world.roads.values():
                if country_id and r.country_id != country_id:
                    continue
                rows.append(
                    {
                        "road_id": r.road_id,
                        "country_id": r.country_id,
                        "city_id": r.city_id,
                        "name": r.name,
                        "category": r.category,
                        "length_km": r.length_km,
                        "speed_limit_kph": r.speed_limit_kph,
                        "capacity_vph": r.capacity_vph,
                        "is_bridge": r.is_bridge,
                        "accessible": r.accessible,
                        "flood_depth_m": r.flood_depth_m,
                        "blocked_reason": r.blocked_reason,
                        "start_lat": r.start.lat,
                        "start_lon": r.start.lon,
                        "end_lat": r.end.lat,
                        "end_lon": r.end.lon,
                    }
                )

        data = {
            "resource": resource,
            "country_id": country_id,
            "columns": columns,
            "rows": rows,
        }
        return _envelope(_world_version(), data=data, count=len(rows))

    def _build_search_corpus() -> List[Dict[str, Any]]:
        """Build a normalized searchable corpus across all 8 searchable entity categories."""
        world = services.world
        active_by_country: Dict[str, int] = {}
        for ev in world.disasters.values():
            if _enum_val(ev.status) == "ACTIVE":
                active_by_country[ev.country_id] = active_by_country.get(ev.country_id, 0) + 1

        corpus: List[Dict[str, Any]] = []

        for c in world.countries.values():
            corpus.append(
                {
                    "entity_type": "country",
                    "id": c.country_id,
                    "name": c.name,
                    "country_id": c.country_id,
                    "status": "AFFECTED" if active_by_country.get(c.country_id, 0) > 0 else "NORMAL",
                    "lat": c.center.lat,
                    "lon": c.center.lon,
                    "extra": f"{c.flag_code} {c.archetype} {c.capital_name}",
                }
            )

        for city in world.cities.values():
            corpus.append(
                {
                    "entity_type": "city",
                    "id": city.city_id,
                    "name": city.name,
                    "country_id": city.country_id,
                    "status": "OPERATIONAL" if city.airport_operational else "DEGRADED",
                    "lat": city.center.lat,
                    "lon": city.center.lon,
                    "extra": "capital" if city.is_capital else "",
                }
            )

        for dist in world.districts.values():
            corpus.append(
                {
                    "entity_type": "district",
                    "id": dist.district_id,
                    "name": dist.name,
                    "country_id": dist.country_id,
                    "status": "EXPOSED" if dist.exposed_residents > 0 else "NORMAL",
                    "lat": dist.center.lat,
                    "lon": dist.center.lon,
                    "extra": dist.zone_type,
                }
            )

        for h in world.hospitals.values():
            corpus.append(
                {
                    "entity_type": "hospital",
                    "id": h.hospital_id,
                    "name": h.name,
                    "country_id": h.country_id,
                    "status": _enum_val(h.status),
                    "lat": h.location.lat,
                    "lon": h.location.lon,
                    "extra": f"hospital medical {h.city_id}",
                }
            )

        for s in world.shelters.values():
            corpus.append(
                {
                    "entity_type": "shelter",
                    "id": s.shelter_id,
                    "name": s.name,
                    "country_id": s.country_id,
                    "status": _enum_val(s.status),
                    "lat": s.location.lat,
                    "lon": s.location.lon,
                    "extra": f"shelter {s.city_id}",
                }
            )

        for d in world.drones.values():
            corpus.append(
                {
                    "entity_type": "drone",
                    "id": d.drone_id,
                    "name": f"{d.drone_id} ({d.category})",
                    "country_id": d.country_id,
                    "status": _enum_val(d.status),
                    "lat": d.location.lat,
                    "lon": d.location.lon,
                    "extra": f"drone {d.category} {d.home_station} {' '.join(d.sensors)}",
                }
            )

        for a in world.ambulances.values():
            corpus.append(
                {
                    "entity_type": "ambulance",
                    "id": a.ambulance_id,
                    "name": f"{a.ambulance_id} ({a.equipment_profile})",
                    "country_id": a.country_id,
                    "status": _enum_val(a.status),
                    "lat": a.location.lat,
                    "lon": a.location.lon,
                    "extra": f"ambulance {a.equipment_profile} {a.home_station}",
                }
            )

        for ev in world.disasters.values():
            if _enum_val(ev.status) != "ACTIVE":
                continue
            corpus.append(
                {
                    "entity_type": "disaster",
                    "id": ev.event_id,
                    "name": ev.name,
                    "country_id": ev.country_id,
                    "status": _enum_val(ev.status),
                    "lat": ev.origin.lat,
                    "lon": ev.origin.lon,
                    "extra": f"disaster {_enum_val(ev.disaster_type)}",
                }
            )

        return corpus

    def _build_search(
        q: str,
        limit: int,
        entity_type: Optional[str],
        country_id: Optional[str],
    ) -> Dict[str, Any]:
        q_norm = q.strip().lower()
        if not q_norm:
            return _envelope(_world_version(), data=[], count=0)

        ver = _world_version()
        corpus_box = cache.get_or_build(ver, ("_search_corpus",), lambda: {"items": _build_search_corpus()})
        corpus: List[Dict[str, Any]] = corpus_box["items"]
        tokens = [t for t in q_norm.split() if t]

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for entry in corpus:
            if entity_type and entry["entity_type"] != entity_type:
                continue
            if country_id and entry["country_id"] != country_id:
                continue
            score = _score_match(q_norm, tokens, entry["id"], entry["name"], entry["extra"])
            if score > 0.0:
                scored.append(
                    (
                        score,
                        {
                            "entity_type": entry["entity_type"],
                            "id": entry["id"],
                            "name": entry["name"],
                            "country_id": entry["country_id"],
                            "status": entry["status"],
                            "lat": entry["lat"],
                            "lon": entry["lon"],
                            "score": score,
                        },
                    )
                )

        scored.sort(key=lambda pair: (-pair[0], pair[1]["entity_type"], pair[1]["id"]))
        matches = [item for _, item in scored[:limit]]
        return _envelope(ver, data=matches, count=len(matches))

    def _build_entities_index(
        country_id: Optional[str],
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        world = services.world
        active_by_country: Dict[str, int] = {}
        for ev in world.disasters.values():
            if _enum_val(ev.status) == "ACTIVE":
                active_by_country[ev.country_id] = active_by_country.get(ev.country_id, 0) + 1

        index: Dict[str, Dict[str, Any]] = {}

        def _add(
            eid: str,
            etype: str,
            name: str,
            cid: str,
            status: Any,
            lat: float,
            lon: float,
            elevation_m: float = 0.0,
        ) -> None:
            if country_id and cid != country_id:
                return
            if entity_type and etype != entity_type:
                return
            index[eid] = {
                "id": eid,
                "entity_type": etype,
                "name": name,
                "country_id": cid,
                "status": _enum_val(status),
                "lat": lat,
                "lon": lon,
                "elevation_m": elevation_m,
            }

        for c in world.countries.values():
            _add(
                c.country_id,
                "country",
                c.name,
                c.country_id,
                "AFFECTED" if active_by_country.get(c.country_id, 0) > 0 else "NORMAL",
                c.center.lat,
                c.center.lon,
                c.center.elevation_m,
            )

        for city in world.cities.values():
            _add(
                city.city_id,
                "city",
                city.name,
                city.country_id,
                "OPERATIONAL" if city.airport_operational else "DEGRADED",
                city.center.lat,
                city.center.lon,
                city.elevation_m,
            )

        for dist in world.districts.values():
            _add(
                dist.district_id,
                "district",
                dist.name,
                dist.country_id,
                "EXPOSED" if dist.exposed_residents > 0 else "NORMAL",
                dist.center.lat,
                dist.center.lon,
                dist.center.elevation_m,
            )

        for h in world.hospitals.values():
            _add(
                h.hospital_id,
                "hospital",
                h.name,
                h.country_id,
                h.status,
                h.location.lat,
                h.location.lon,
                h.location.elevation_m,
            )

        for s in world.shelters.values():
            _add(
                s.shelter_id,
                "shelter",
                s.name,
                s.country_id,
                s.status,
                s.location.lat,
                s.location.lon,
                s.location.elevation_m,
            )

        for w in world.warehouses.values():
            _add(
                w.warehouse_id,
                "warehouse",
                w.name,
                w.country_id,
                "OPERATIONAL",
                w.location.lat,
                w.location.lon,
                w.location.elevation_m,
            )

        for a in world.ambulances.values():
            _add(
                a.ambulance_id,
                "ambulance",
                f"{a.ambulance_id} ({a.equipment_profile})",
                a.country_id,
                a.status,
                a.location.lat,
                a.location.lon,
                a.location.elevation_m,
            )

        for f in world.fire_units.values():
            _add(
                f.unit_id,
                "fire_unit",
                f"{f.unit_id} ({f.unit_type})",
                f.country_id,
                f.status,
                f.location.lat,
                f.location.lon,
                f.location.elevation_m,
            )

        for d in world.drones.values():
            _add(
                d.drone_id,
                "drone",
                f"{d.drone_id} ({d.category})",
                d.country_id,
                d.status,
                d.location.lat,
                d.location.lon,
                d.altitude_m or d.location.elevation_m,
            )

        for r in world.roads.values():
            mid_lat = round((r.start.lat + r.end.lat) / 2.0, 6)
            mid_lon = round((r.start.lon + r.end.lon) / 2.0, 6)
            mid_elev = round((r.start.elevation_m + r.end.elevation_m) / 2.0, 2)
            _add(
                r.road_id,
                "road",
                r.name,
                r.country_id,
                "ACCESSIBLE" if r.accessible else "BLOCKED",
                mid_lat,
                mid_lon,
                mid_elev,
            )

        for ev in world.disasters.values():
            _add(
                ev.event_id,
                "disaster",
                ev.name,
                ev.country_id,
                ev.status,
                ev.origin.lat,
                ev.origin.lon,
                ev.origin.elevation_m,
            )

        return _envelope(_world_version(), data=index, count=len(index))

    # ------------------------------------------------------------------
    # Public /api/v2 Endpoints
    # ------------------------------------------------------------------
    @router.get("/snapshot")
    def get_snapshot() -> Dict[str, Any]:
        return cache.get_or_build(_world_version(), ("snapshot",), _build_snapshot)

    @router.get("/country/{country_id}/bundle")
    def get_country_bundle(country_id: str) -> Dict[str, Any]:
        if country_id not in services.world.countries:
            raise HTTPException(status_code=404, detail=f"Unknown country_id: {country_id}")
        return cache.get_or_build(
            _world_version(),
            ("country_bundle", country_id),
            lambda: _build_country_bundle(country_id),
        )

    @router.get("/tables/{resource}")
    def get_table(
        resource: str,
        country_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        if resource not in SUPPORTED_TABLE_RESOURCES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported table resource '{resource}'. Allowed: {', '.join(SUPPORTED_TABLE_RESOURCES)}",
            )
        return cache.get_or_build(
            _world_version(),
            ("table", resource, country_id),
            lambda: _build_table(resource, country_id),
        )

    @router.get("/search")
    def search_entities(
        q: str = Query(default="", description="Fuzzy or substring search query"),
        limit: int = Query(default=25, ge=1, le=200),
        entity_type: Optional[str] = Query(default=None),
        country_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        key = ("search", q.strip().lower(), limit, entity_type, country_id)
        return cache.get_or_build(
            _world_version(),
            key,
            lambda: _build_search(q, limit, entity_type, country_id),
        )

    @router.get("/entities/index")
    def get_entities_index(
        country_id: Optional[str] = Query(default=None),
        entity_type: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        return cache.get_or_build(
            _world_version(),
            ("entities_index", country_id, entity_type),
            lambda: _build_entities_index(country_id, entity_type),
        )

    return router
