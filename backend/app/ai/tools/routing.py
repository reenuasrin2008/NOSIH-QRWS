from __future__ import annotations

from typing import Any, Callable, Dict

from app.core.compat import to_dict
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import GeoPoint


def _cid(world: GlobalWorldEngine, args: Dict[str, Any]) -> str:
    cid = args.get("country_id") or world.selected_country_id
    if cid not in world.countries:
        cid = world.selected_country_id
    return cid


def build_handlers(
    world: GlobalWorldEngine,
    route_explorer: AdvancedRouteExplorer,
) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _get_blocked_roads(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        all_countries = bool(args.get("all_countries", False))
        roads = [
            r for r in world.roads.values()
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

    def _compare_drones_to_destination(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        if args.get("hospital_id") and args["hospital_id"] not in world.hospitals:
            return {"status": "ERROR", "tool": "compare_drones_to_destination", "error": f"Unknown hospital_id: {args['hospital_id']}", "category": "routing"}
        if args.get("hospital_id") and args.get("country_id") and world.hospitals[args["hospital_id"]].country_id != args["country_id"]:
            return {"status": "ERROR", "tool": "compare_drones_to_destination", "error": "hospital_id does not belong to country_id", "category": "routing"}
        target_h = None
        if args.get("hospital_id"):
            target_h = world.hospitals[args["hospital_id"]]
        else:
            hospitals = [h for h in world.hospitals.values() if h.country_id == cid]
            target_h = hospitals[0] if hospitals else None
        dest = (
            GeoPoint(lat=float(args["lat"]), lon=float(args["lon"]), elevation_m=90.0)
            if (args.get("lat") is not None and args.get("lon") is not None)
            else (target_h.location if target_h else world.countries[cid].center)
        )
        label = args.get("destination_label") or (target_h.name if target_h else world.countries[cid].capital_name)
        return route_explorer.compare_drones_to_destination(
            cid,
            dest,
            destination_label=label,
            objective=args.get("objective", "BALANCED"),
            payload_kg=float(args.get("payload_kg", 1.0)),
            required_sensor=args.get("required_sensor"),
        )

    def _plan_multistop_mission(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        c = world.countries[cid].center
        raw_pts = args.get("points")
        if raw_pts is not None and (not isinstance(raw_pts, list) or not 1 <= len(raw_pts) <= 50):
            return {"status": "ERROR", "tool": "plan_multistop_mission", "error": "points must contain between 1 and 50 waypoints", "category": "routing"}
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
        return route_explorer.plan_multistop_mission(
            cid, pts, sensor_type=args.get("sensor_type", "thermal"), objective=args.get("objective", "LOWEST_ENERGY")
        )

    def _get_route_logs(args: Dict[str, Any]) -> Dict[str, Any]:
        limit = max(1, int(args.get("limit", 50)))
        logs = list(route_explorer.route_logs)[-limit:]
        return {"count": len(logs), "logs": logs}

    return {
        "compare_drones_to_destination": _compare_drones_to_destination,
        "plan_multistop_mission": _plan_multistop_mission,
        "get_route_logs": _get_route_logs,
        "get_blocked_roads": _get_blocked_roads,
        "run_counterfactual_comparison": lambda a: world.run_counterfactual_comparison(
            _cid(world, a),
            what_if_params=(
                {k: v for k, v in a["what_if"].items() if v is not None}
                if isinstance(a.get("what_if"), dict)
                else None
            ),
        ),
    }
