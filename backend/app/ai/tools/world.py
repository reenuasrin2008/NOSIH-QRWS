from __future__ import annotations

from typing import Any, Callable, Dict

from app.core.compat import to_dict
from app.world.global_engine import GlobalWorldEngine


def _cid(world: GlobalWorldEngine, args: Dict[str, Any]) -> str:
    cid = args.get("country_id") or world.selected_country_id
    if cid not in world.countries:
        cid = world.selected_country_id
    return cid


def build_handlers(world: GlobalWorldEngine) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _get_country_cities(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        cities = [to_dict(c) for c in world.cities.values() if c.country_id == cid]
        return {"country_id": cid, "count": len(cities), "cities": cities}

    def _get_district_details(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        did = args.get("district_id")
        if did and did in world.districts:
            d = world.districts[did]
            return {"country_id": d.country_id, "count": 1, "districts": [to_dict(d)]}
        dists = [to_dict(d) for d in world.districts.values() if d.country_id == cid]
        return {"country_id": cid, "count": len(dists), "districts": dists}

    def _get_buildings_summary(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        blds = [b for b in world.buildings.values() if b.country_id == cid]
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
        cid = _cid(world, args)
        rid = args.get("road_id")
        if rid and rid in world.roads:
            roads = [world.roads[rid]]
            cid = roads[0].country_id
        else:
            roads = [r for r in world.roads.values() if r.country_id == cid]
        return {
            "country_id": cid,
            "total_roads": len(roads),
            "accessible_roads": sum(1 for r in roads if r.accessible),
            "blocked_roads": sum(1 for r in roads if not r.accessible),
            "bridges_total": sum(1 for r in roads if r.is_bridge),
            "bridges_blocked": sum(1 for r in roads if r.is_bridge and not r.accessible),
            "roads": [to_dict(r) for r in roads],
        }

    def _get_population_summary(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        dists = [d for d in world.districts.values() if d.country_id == cid]
        return {
            "country_id": cid,
            "total_residents": sum(d.total_residents for d in dists),
            "exposed_residents": sum(d.exposed_residents for d in dists),
            "evacuated_residents": sum(d.evacuated_residents for d in dists),
            "injured_residents": sum(d.injured_residents for d in dists),
            "vulnerable_residents": sum(d.vulnerable_residents for d in dists),
            "districts": [to_dict(d) for d in dists],
            "households_count": sum(1 for h in world.households.values() if h.country_id == cid),
            "sample_people": [to_dict(p) for p in world.people.values() if p.country_id == cid][:15],
        }

    def _get_household_statistics(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        hhs = [h for h in world.households.values() if h.country_id == cid]
        dists = [d for d in world.districts.values() if d.country_id == cid]
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
        cid = _cid(world, args)
        animals = [x for x in world.animals.values() if x.country_id == cid]
        return {
            "country_id": cid,
            "total_animals": sum(x.count for x in animals),
            "exposed_animals": sum(x.exposed_count for x in animals),
            "evacuated_animals": sum(x.evacuated_count for x in animals),
            "animals": [to_dict(x) for x in animals],
        }

    return {
        "get_global_world_overview": lambda a: world.get_global_overview(),
        "get_country_list": lambda a: {"countries": world.get_global_overview()["countries"]},
        "get_country_status": lambda a: world.get_country_detail(_cid(world, a)),
        "get_country_cities": _get_country_cities,
        "get_district_details": _get_district_details,
        "get_buildings_summary": _get_buildings_summary,
        "get_road_network": _get_road_network,
        "get_population_summary": _get_population_summary,
        "get_household_statistics": _get_household_statistics,
        "get_animal_population": _get_animal_population,
        "get_simulation_clock": lambda a: world.get_clock_info(),
    }
