"""Navigation, safe route validation, risk scoring, and charging station lookup tools."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition


def build_navigation_tools() -> List[ToolDefinition]:
    async def calculate_safe_route(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dest = [float(args["x"]), float(args.get("y", 60.0)), float(args["z"])]
        return await sim.post(f"/api/drones/{args['drone_id']}/route", json_body={"destination": dest})

    async def compare_routes(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dest = [float(args["x"]), float(args.get("y", 60.0)), float(args["z"])]
        results = []
        for did in args["drone_ids"][:6]:
            try:
                r = await sim.post(f"/api/drones/{did}/route", json_body={"destination": dest})
                rt = r.get("route", {})
                results.append({
                    "drone_id": did,
                    "overall_feasible": r.get("overall_feasible"),
                    "distance_m": rt.get("distance_m"),
                    "estimated_energy_wh": rt.get("estimated_energy_wh"),
                    "risk_score": rt.get("risk_score"),
                    "estimated_duration_s": rt.get("estimated_duration_s"),
                })
            except Exception as exc:
                results.append({"drone_id": did, "overall_feasible": False, "error": str(exc)})
        results.sort(key=lambda x: (not x.get("overall_feasible"), x.get("distance_m", 1e9)))
        return {"destination": dest, "comparisons": results}

    async def validate_route(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dest = [float(args["x"]), float(args.get("y", 60.0)), float(args["z"])]
        r = await sim.post(f"/api/drones/{args['drone_id']}/route", json_body={"destination": dest})
        return {
            "drone_id": args["drone_id"],
            "route_feasible": r.get("route", {}).get("feasible", False),
            "battery_reserve_ok": r.get("battery_reserve_ok", False),
            "overall_feasible": r.get("overall_feasible", False),
            "risk_score": r.get("route", {}).get("risk_score", 0.0),
        }

    async def calculate_route_risk(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dest = [float(args["x"]), float(args.get("y", 60.0)), float(args["z"])]
        r = await sim.post(f"/api/drones/{args['drone_id']}/route", json_body={"destination": dest})
        rt = r.get("route", {})
        return {"drone_id": args["drone_id"], "risk_score": rt.get("risk_score", 0.0), "distance_m": rt.get("distance_m", 0.0), "feasible": r.get("overall_feasible", False)}

    async def find_nearest_available_station(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tx, tz = float(args["x"]), float(args["z"])
        st_data = await sim.get("/api/world/stations")
        stations = st_data.get("stations", [])
        util = st_data.get("utilization", {})
        candidates = []
        for s in stations:
            if not s.get("active", True):
                continue
            u = util.get(s["id"], {})
            if u.get("occupied", 0) >= s.get("capacity", 10):
                continue
            dist = math.hypot(s["position"][0] - tx, s["position"][2] - tz)
            candidates.append({"station_id": s["id"], "name": s["name"], "position": s["position"], "distance_m": round(dist, 1), "utilization": u})
        candidates.sort(key=lambda c: c["distance_m"])
        return {"nearest": candidates[0] if candidates else None, "available_stations": candidates}

    async def find_alternative_station(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        exclude = args.get("exclude_station_id")
        res = await find_nearest_available_station(sim, args)
        alts = [s for s in res["available_stations"] if s["station_id"] != exclude]
        return {"alternative": alts[0] if alts else None, "alternatives": alts}

    async def calculate_area_coverage(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        drones = await sim.get("/api/drones")
        surs = await sim.get("/api/survivors")
        active_drones = [d for d in drones if d["status"] in ("IN_FLIGHT", "DELIVERING", "AVAILABLE")]
        detected_surs = [s for s in surs if s.get("detected")]
        return {
            "operational_drones": len(active_drones),
            "total_survivors": len(surs),
            "detected_survivors": len(detected_surs),
            "detection_coverage_pct": round((len(detected_surs) / len(surs)) * 100.0, 1) if surs else 100.0,
        }

    route_schema = {
        "type": "object",
        "properties": {
            "drone_id": {"type": "string"},
            "x": {"type": "number", "minimum": 0, "maximum": 4000},
            "y": {"type": "number", "minimum": 5, "maximum": 300},
            "z": {"type": "number", "minimum": 0, "maximum": 4000},
        },
        "required": ["drone_id", "x", "z"],
        "additionalProperties": False,
    }

    return [
        ToolDefinition("calculate_safe_route", "navigation", "Compute a real 3D A* hazard-avoiding route and battery reserve check for a drone.", route_schema, calculate_safe_route),
        ToolDefinition("compare_routes", "navigation", "Compare route feasibility, distance, energy, and risk across multiple drones to a target.", {
            "type": "object",
            "properties": {
                "drone_ids": {"type": "array", "items": {"type": "string"}},
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "y": {"type": "number", "minimum": 5, "maximum": 300},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
            },
            "required": ["drone_ids", "x", "z"],
            "additionalProperties": False,
        }, compare_routes),
        ToolDefinition("validate_route", "navigation", "Validate whether a drone can reach (x, y, z) while preserving the 20% battery reserve.", route_schema, validate_route),
        ToolDefinition("calculate_route_risk", "navigation", "Calculate hazard exposure risk score for a drone's planned route.", route_schema, calculate_route_risk),
        ToolDefinition("find_nearest_available_station", "navigation", "Find the nearest active charging station with free capacity.", {
            "type": "object",
            "properties": {
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
            },
            "required": ["x", "z"],
            "additionalProperties": False,
        }, find_nearest_available_station),
        ToolDefinition("find_alternative_station", "navigation", "Find an alternative active charging station excluding a given station ID.", {
            "type": "object",
            "properties": {
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
                "exclude_station_id": {"type": "string"},
            },
            "required": ["x", "z"],
            "additionalProperties": False,
        }, find_alternative_station),
        ToolDefinition("calculate_area_coverage", "navigation", "Calculate current fleet operational readiness and survivor detection coverage.", {
            "type": "object", "properties": {}, "additionalProperties": False
        }, calculate_area_coverage),
    ]
