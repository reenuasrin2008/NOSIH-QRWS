"""Drone inspection, dispatch, waypoint, RTB, and failure recovery tools."""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
_DID = {
    "type": "object",
    "properties": {"drone_id": {"type": "string"}},
    "required": ["drone_id"],
    "additionalProperties": False,
}


def build_drone_tools() -> List[ToolDefinition]:
    async def get_all_drones(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        drones = await sim.get("/api/drones")
        compact = [
            {
                "id": d["id"], "drone_type": d["drone_type"], "status": d["status"],
                "battery_percent": d["battery_percent"], "health": d["health"],
                "position": d["position"], "active_task_id": d["active_task_id"],
                "assigned_task_ids": d["assigned_task_ids"], "capabilities": d["capabilities"],
            }
            for d in drones
        ]
        return {"count": len(compact), "drones": compact}

    async def get_drone_details(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get(f"/api/drones/{args['drone_id']}")

    async def get_available_drones(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        drones = await sim.get("/api/drones", params={"status": "AVAILABLE"})
        return {"count": len(drones), "drones": [{"id": d["id"], "drone_type": d["drone_type"], "battery_percent": d["battery_percent"], "position": d["position"], "capabilities": d["capabilities"]} for d in drones]}

    async def get_failed_drones(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        drones = await sim.get("/api/drones")
        failed = [d for d in drones if d["status"] in ("DESTROYED", "DAMAGED", "COMMUNICATION_LOST")]
        return {"count": len(failed), "drones": [{"id": d["id"], "status": d["status"], "health": d["health"], "position": d["position"]} for d in failed]}

    async def get_low_battery_drones(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        threshold = float(args.get("threshold_percent", 30.0))
        drones = await sim.get("/api/drones")
        low = [d for d in drones if float(d["battery_percent"]) <= threshold]
        return {"count": len(low), "threshold_percent": threshold, "drones": [{"id": d["id"], "battery_percent": d["battery_percent"], "status": d["status"]} for d in low]}

    async def select_drone(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/drones/{args['drone_id']}")
        await sim.post("/api/ui/sync", json_body={"action": "select_drone", "payload": {"id": d["id"]}})
        return {"selected": d["id"], "status": d["status"], "battery_percent": d["battery_percent"]}

    async def inspect_battery(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/drones/{args['drone_id']}")
        return {
            "drone_id": d["id"],
            "battery_percent": d["battery_percent"],
            "remaining_battery_wh": d["remaining_battery_wh"],
            "battery_capacity_wh": d["battery_capacity_wh"],
            "battery_temp_c": d["battery_temp_c"],
            "power_draw_w": d["power_draw_w"],
            "estimated_remaining_flight_s": d["estimated_remaining_flight_s"],
        }

    async def inspect_health(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/drones/{args['drone_id']}")
        return {
            "drone_id": d["id"],
            "status": d["status"],
            "health": d["health"],
            "failure_history": d.get("failure_history", []),
        }

    async def assign_drone_to_task(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/drones/{args['drone_id']}/assign", json_body={"task_id": args["task_id"]})

    async def set_drone_waypoint(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dest = [float(args["x"]), float(args.get("y", 60.0)), float(args["z"])]
        res = await sim.post(f"/api/drones/{args['drone_id']}/waypoint", json_body={"destination": dest})
        return res.get("result", res)

    async def return_drone_to_base(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post(f"/api/drones/{args['drone_id']}/rtb")
        st = res.get("benchmark", {}).get("active_state", {})
        return {"drone_id": args["drone_id"], "status": "RETURNING", "state_version": st.get("state_version")}

    async def find_nearest_drone(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tx, tz = float(args["x"]), float(args["z"])
        only_avail = bool(args.get("only_available", True))
        req_cap = args.get("required_capability")
        drones = await sim.get("/api/drones")
        candidates = []
        for d in drones:
            if only_avail and d["status"] != "AVAILABLE":
                continue
            if d["status"] in ("DESTROYED", "DAMAGED", "COMMUNICATION_LOST"):
                continue
            if req_cap and req_cap not in d.get("capabilities", []):
                continue
            dist = math.hypot(d["position"][0] - tx, d["position"][2] - tz)
            candidates.append({"drone_id": d["id"], "drone_type": d["drone_type"], "status": d["status"], "battery_percent": d["battery_percent"], "distance_m": round(dist, 1), "capabilities": d["capabilities"]})
        candidates.sort(key=lambda c: c["distance_m"])
        return {"target": [tx, tz], "nearest": candidates[0] if candidates else None, "top_candidates": candidates[:5]}

    async def find_best_drone_for_task(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get(f"/api/tasks/{args['task_id']}/best-drone")

    async def get_drone_route(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/drones/{args['drone_id']}")
        return {"drone_id": d["id"], "status": d["status"], "current_route": d.get("current_route")}

    async def inject_simulated_failure(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post(
            f"/api/drones/{args['drone_id']}/failure",
            json_body={"failure_type": args.get("failure_type", "MOTOR_FAILURE"), "scope": "all"},
        )
        return res.get("result", res)

    async def reassign_drone_tasks(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/optimizer/run", json_body={"reason": f"reassign_from_{args.get('drone_id', 'fleet')}"})

    wp_schema = {
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
        ToolDefinition("get_all_drones", "drone", "List all drones in the fleet with status, battery, health, and capabilities.", _EMPTY, get_all_drones),
        ToolDefinition("get_drone_details", "drone", "Retrieve the full authoritative state of a specific drone.", _DID, get_drone_details),
        ToolDefinition("get_available_drones", "drone", "List all drones currently in AVAILABLE status.", _EMPTY, get_available_drones),
        ToolDefinition("get_failed_drones", "drone", "List all damaged, destroyed, or communication-lost drones.", _EMPTY, get_failed_drones),
        ToolDefinition("get_low_battery_drones", "drone", "List drones at or below a battery percentage threshold.", {
            "type": "object",
            "properties": {"threshold_percent": {"type": "number", "minimum": 5, "maximum": 80}},
            "additionalProperties": False,
        }, get_low_battery_drones),
        ToolDefinition("select_drone", "drone", "Select a drone in the synchronized 3D and control panel UI.", _DID, select_drone, PermissionLevel.OPERATIONAL),
        ToolDefinition("inspect_drone", "drone", "Inspect a drone's full authoritative telemetry.", _DID, get_drone_details),
        ToolDefinition("inspect_battery", "drone", "Inspect a drone's battery level, temperature, power draw, and remaining flight time.", _DID, inspect_battery),
        ToolDefinition("inspect_health", "drone", "Inspect a drone's health score and failure history.", _DID, inspect_health),
        ToolDefinition("assign_drone_to_task", "drone", "Validate eligibility/battery/route and assign a specific drone to a rescue task.", {
            "type": "object",
            "properties": {"drone_id": {"type": "string"}, "task_id": {"type": "string"}},
            "required": ["drone_id", "task_id"],
            "additionalProperties": False,
        }, assign_drone_to_task, PermissionLevel.OPERATIONAL),
        ToolDefinition("send_drone_to_location", "drone", "Send a drone to specific (x, y, z) world coordinates after feasibility validation.", wp_schema, set_drone_waypoint, PermissionLevel.OPERATIONAL),
        ToolDefinition("set_drone_waypoint", "drone", "Set a custom validated waypoint for a drone.", wp_schema, set_drone_waypoint, PermissionLevel.OPERATIONAL),
        ToolDefinition("return_drone_to_base", "drone", "Command a drone to return to the nearest available charging station or home base.", _DID, return_drone_to_base, PermissionLevel.OPERATIONAL),
        ToolDefinition("find_nearest_drone", "drone", "Find the nearest eligible drone to (x, z) coordinates.", {
            "type": "object",
            "properties": {
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
                "only_available": {"type": "boolean"},
                "required_capability": {"type": "string"},
            },
            "required": ["x", "z"],
            "additionalProperties": False,
        }, find_nearest_drone),
        ToolDefinition("find_best_drone_for_task", "drone", "Evaluate all eligible drones for a task using real 3D route, battery reserve, and risk scoring.", {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        }, find_best_drone_for_task),
        ToolDefinition("get_drone_route", "drone", "Retrieve a drone's current planned 3D route.", _DID, get_drone_route),
        ToolDefinition("inject_simulated_failure", "drone", "Inject a simulated fault into a drone (destructive — requires confirmation).", {
            "type": "object",
            "properties": {
                "drone_id": {"type": "string"},
                "failure_type": {
                    "type": "string",
                    "enum": ["MOTOR_FAILURE", "BATTERY_FAILURE", "GPS_FAILURE", "COMMUNICATION_LOSS", "LOW_BATTERY", "SENSOR_FAILURE", "FLIGHT_CONTROL_FAILURE", "COMPLETE_DRONE_DESTRUCTION"],
                },
            },
            "required": ["drone_id"],
            "additionalProperties": False,
        }, inject_simulated_failure, PermissionLevel.DESTRUCTIVE, idempotent=False),
        ToolDefinition("reassign_drone_tasks", "drone", "Trigger fleet-wide optimization to reallocate unassigned or recovered tasks.", {
            "type": "object",
            "properties": {"drone_id": {"type": "string"}},
            "additionalProperties": False,
        }, reassign_drone_tasks, PermissionLevel.OPERATIONAL),
    ]
