"""Synchronized 3D camera, layer, and replay control tools operating through /api/ui/sync."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def build_visual_tools() -> List[ToolDefinition]:
    async def focus_camera(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        pt = [float(args["x"]), float(args.get("y", 25.0)), float(args["z"])]
        return await sim.post("/api/ui/sync", json_body={"action": "focus_point", "payload": {"point": pt}})

    async def focus_camera_on_drone(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/drones/{args['drone_id']}")
        await sim.post("/api/ui/sync", json_body={"action": "select_drone", "payload": {"id": d["id"]}})
        await sim.post("/api/ui/sync", json_body={"action": "camera_mode", "payload": {"mode": "follow"}})
        return await sim.post("/api/ui/sync", json_body={"action": "focus_point", "payload": {"point": d["position"]}})

    async def focus_camera_on_survivor(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        s = await sim.get(f"/api/survivors/{args['survivor_id']}")
        return await sim.post("/api/ui/sync", json_body={"action": "focus_point", "payload": {"point": s["position"]}})

    async def focus_camera_on_building(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        dmg = await sim.get("/api/world/buildings/damage")
        target = next((b for b in dmg.get("damaged_buildings", []) if b["id"] == args["building_id"]), None)
        if target:
            pt = [target["x"], 30.0, target["z"]]
            return await sim.post("/api/ui/sync", json_body={"action": "focus_point", "payload": {"point": pt}})
        return {"ok": False, "error": f"Building {args['building_id']} not found in damaged buildings index."}

    async def focus_camera_on_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        d = await sim.get(f"/api/disasters/{args['event_id']}")
        ep = d["epicentre"]
        await sim.post("/api/ui/sync", json_body={"action": "camera_mode", "payload": {"mode": "disaster_focus"}})
        return await sim.post("/api/ui/sync", json_body={"action": "focus_point", "payload": {"point": [ep["x"], ep.get("y", 20.0), ep["z"]]}})

    async def change_camera_mode(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "camera_mode", "payload": {"mode": args["mode"]}})

    async def set_visual_layer(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "set_layer", "payload": {"key": args["layer"], "value": bool(args["enabled"])}})

    async def show_disaster_boundaries(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "set_layer", "payload": {"key": "showHazards", "value": bool(args.get("enabled", True))}})

    async def show_all_drone_routes(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "set_layer", "payload": {"key": "showRoutes", "value": bool(args.get("enabled", True))}})

    async def show_survivor_markers(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "set_layer", "payload": {"key": "showSurvivors", "value": bool(args.get("enabled", True))}})

    async def start_replay(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        rep = await sim.get("/api/experiments/current/replay")
        return await sim.post("/api/ui/sync", json_body={"action": "start_replay", "payload": {"runId": rep.get("run_id", "REPLAY"), "frames": rep.get("frames", [])}})

    async def stop_replay(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/ui/sync", json_body={"action": "stop_replay", "payload": {}})

    bool_opt = {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "additionalProperties": False}

    return [
        ToolDefinition("focus_camera", "visual", "Focus the 3D scene camera on (x, y, z) coordinates.", {
            "type": "object",
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
            "required": ["x", "z"],
            "additionalProperties": False,
        }, focus_camera, PermissionLevel.OPERATIONAL),
        ToolDefinition("focus_camera_on_drone", "visual", "Select and focus the 3D camera on a specific drone.", {
            "type": "object", "properties": {"drone_id": {"type": "string"}}, "required": ["drone_id"], "additionalProperties": False
        }, focus_camera_on_drone, PermissionLevel.OPERATIONAL),
        ToolDefinition("focus_camera_on_survivor", "visual", "Focus the 3D camera on a specific simulated survivor.", {
            "type": "object", "properties": {"survivor_id": {"type": "string"}}, "required": ["survivor_id"], "additionalProperties": False
        }, focus_camera_on_survivor, PermissionLevel.OPERATIONAL),
        ToolDefinition("focus_camera_on_building", "visual", "Focus the 3D camera on a specific damaged building.", {
            "type": "object", "properties": {"building_id": {"type": "string"}}, "required": ["building_id"], "additionalProperties": False
        }, focus_camera_on_building, PermissionLevel.OPERATIONAL),
        ToolDefinition("focus_camera_on_disaster", "visual", "Focus the 3D camera on a specific disaster epicentre.", {
            "type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"], "additionalProperties": False
        }, focus_camera_on_disaster, PermissionLevel.OPERATIONAL),
        ToolDefinition("change_camera_mode", "visual", "Switch 3D camera mode (orbit, free, topdown, fpv, follow, disaster_focus).", {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["orbit", "free", "topdown", "fpv", "follow", "disaster_focus"]}},
            "required": ["mode"],
            "additionalProperties": False,
        }, change_camera_mode, PermissionLevel.OPERATIONAL),
        ToolDefinition("set_visual_layer", "visual", "Toggle a visual layer in the 3D scene.", {
            "type": "object",
            "properties": {"layer": {"type": "string"}, "enabled": {"type": "boolean"}},
            "required": ["layer", "enabled"],
            "additionalProperties": False,
        }, set_visual_layer, PermissionLevel.OPERATIONAL),
        ToolDefinition("show_disaster_boundaries", "visual", "Show or hide disaster hazard boundaries in 3D.", bool_opt, show_disaster_boundaries, PermissionLevel.OPERATIONAL),
        ToolDefinition("show_all_drone_routes", "visual", "Show or hide all drone flight paths in 3D.", bool_opt, show_all_drone_routes, PermissionLevel.OPERATIONAL),
        ToolDefinition("show_survivor_markers", "visual", "Show or hide simulated survivor markers in 3D.", bool_opt, show_survivor_markers, PermissionLevel.OPERATIONAL),
        ToolDefinition("start_replay", "visual", "Start 3D experiment replay playback.", _EMPTY, start_replay, PermissionLevel.OPERATIONAL),
        ToolDefinition("stop_replay", "visual", "Stop 3D experiment replay playback.", _EMPTY, stop_replay, PermissionLevel.OPERATIONAL),
    ]
