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
    def _get_active_disasters(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id")
        evs = [
            to_dict(d) for d in world.disasters.values()
            if d.status == "ACTIVE" and (not cid or d.country_id == cid)
        ]
        return {"count": len(evs), "disasters": evs}

    def _get_disaster_impact(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        ev_id = args.get("event_id")
        if ev_id and ev_id in world.disasters:
            evs = [world.disasters[ev_id]]
            cid = evs[0].country_id
        else:
            evs = [d for d in world.disasters.values() if d.country_id == cid and d.status == "ACTIVE"]
        dists = [d for d in world.districts.values() if d.country_id == cid]
        blocked = sum(1 for r in world.roads.values() if r.country_id == cid and not r.accessible)
        damaged_blds = sum(
            1 for b in world.buildings.values() if b.country_id == cid and b.structural_condition != "INTACT"
        )
        return {
            "country_id": cid,
            "country_name": world.countries[cid].name,
            "active_disaster_count": len(evs),
            "disasters": [to_dict(e) for e in evs],
            "exposed_population": sum(d.exposed_residents for d in dists),
            "evacuation_demand": sum(e.evacuation_demand for e in evs),
            "estimated_injuries": sum(d.injured_residents for d in dists),
            "blocked_roads": blocked,
            "damaged_buildings": damaged_blds,
            "power_outage_districts": sum(1 for d in dists if not d.power_available),
        }

    return {
        "get_active_disasters": _get_active_disasters,
        "get_disaster_impact": _get_disaster_impact,
        "get_cascade_graph": lambda a: world.get_cascade_graph(_cid(world, a)),
        "analyze_disaster": lambda a: world.get_country_detail(_cid(world, a)),
    }
