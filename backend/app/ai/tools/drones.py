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
    def _get_drone_fleet(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        drones = [d for d in world.drones.values() if d.country_id == cid]
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
        cid = _cid(world, args)
        min_batt = float(args.get("min_battery_pct", 25.0))
        sensor = args.get("sensor")
        avail = [
            d for d in world.drones.values()
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
            to_dict(d) for d in world.drones.values()
            if d.battery_pct < threshold and (not cid or d.country_id == cid)
        ]
        return {"threshold_pct": threshold, "country_id": cid or "ALL", "count": len(drones), "drones": drones}

    def _get_swarm_status(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id")
        swarms = [to_dict(s) for s in world.swarms.values() if not cid or s.country_id == cid]
        return {
            "country_id": cid or "ALL",
            "total_swarms": len(swarms),
            "active_swarms": sum(1 for s in swarms if s["status"] == "ACTIVE"),
            "swarms": swarms,
        }

    return {
        "get_drone_fleet": _get_drone_fleet,
        "get_available_drones": _get_available_drones,
        "get_low_battery_drones": _get_low_battery_drones,
        "get_swarm_status": _get_swarm_status,
    }
