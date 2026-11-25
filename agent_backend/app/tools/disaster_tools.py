"""Disaster observation and lifecycle control tools calling port 8000."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
_EID = {
    "type": "object",
    "properties": {"event_id": {"type": "string"}},
    "required": ["event_id"],
    "additionalProperties": False,
}
_DISASTER_CREATE_PROPS = {
    "x": {"type": "number", "minimum": 0, "maximum": 4000},
    "z": {"type": "number", "minimum": 0, "maximum": 4000},
    "severity": {"type": "number", "minimum": 0.05, "maximum": 1.0},
    "affected_radius": {"type": "number", "minimum": 30, "maximum": 2000},
    "duration": {"type": "number", "minimum": 30, "maximum": 7200},
    "propagation_speed": {"type": "number", "minimum": 0.1, "maximum": 5.0},
    "start_delay": {"type": "number", "minimum": 0, "maximum": 600},
    "auto_start": {"type": "boolean"},
    "magnitude": {"type": "number", "minimum": 0, "maximum": 9.5},
}


def build_disaster_tools() -> List[ToolDefinition]:
    async def get_all_disasters(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        items = await sim.get("/api/disasters")
        return {"count": len(items), "disasters": items}

    async def get_disaster_details(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get(f"/api/disasters/{args['event_id']}")

    async def get_disaster_timeline(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tl = await sim.get("/api/disasters/timeline")
        return {"count": len(tl), "timeline": tl}

    async def create_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/disasters", json_body=args)

    def _typed_creator(dtype: str):
        async def _fn(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
            body = {"type": dtype, **args}
            return await sim.post("/api/disasters", json_body=body)
        return _fn

    async def create_multi_hazard_scenario(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        preset_id = args.get("preset_id")
        if preset_id:
            return await sim.post("/api/disasters/preset", json_body={"preset_id": preset_id})
        return await sim.post("/api/disasters/random", json_body={"seed": args.get("seed")})

    async def start_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/start")

    async def pause_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/pause")

    async def resume_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/resume")

    async def stop_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/stop")

    async def remove_disaster(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.delete(f"/api/disasters/{args['event_id']}")

    async def increase_disaster_severity(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        delta = abs(float(args.get("delta", 0.15)))
        return await sim.post(f"/api/disasters/{args['event_id']}/severity", json_body={"delta": delta})

    async def decrease_disaster_severity(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        delta = -abs(float(args.get("delta", 0.15)))
        return await sim.post(f"/api/disasters/{args['event_id']}/severity", json_body={"delta": delta})

    async def expand_disaster_radius(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        delta = float(args.get("delta_radius", 80.0))
        return await sim.post(f"/api/disasters/{args['event_id']}/radius", json_body={"delta_radius": delta})

    async def move_disaster_epicentre(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/move", json_body={"x": float(args["x"]), "z": float(args["z"])})

    async def trigger_aftershock(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/disasters/{args['event_id']}/aftershock", json_body={"scale": float(args.get("scale", 0.65))})

    typed_schema = {
        "type": "object",
        "properties": _DISASTER_CREATE_PROPS,
        "required": ["x", "z"],
        "additionalProperties": False,
    }

    return [
        ToolDefinition("get_all_disasters", "disaster", "List all disaster events in the authoritative simulation.", _EMPTY, get_all_disasters),
        ToolDefinition("get_disaster_details", "disaster", "Retrieve detailed state for a specific disaster event ID.", _EID, get_disaster_details),
        ToolDefinition("get_disaster_timeline", "disaster", "Retrieve the chronological disaster lifecycle timeline.", _EMPTY, get_disaster_timeline),
        ToolDefinition("create_disaster", "disaster", "Create a new disaster event of any supported type at valid world coordinates.", {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["flood", "earthquake", "fire", "cyclone", "building_collapse", "landslide"]},
                **_DISASTER_CREATE_PROPS,
            },
            "required": ["type", "x", "z"],
            "additionalProperties": False,
        }, create_disaster, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_flood", "disaster", "Create a flood disaster at (x, z) in world coordinates.", typed_schema, _typed_creator("flood"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_earthquake", "disaster", "Create an earthquake disaster at (x, z) with structural damage and potential collapses.", typed_schema, _typed_creator("earthquake"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_fire", "disaster", "Create a fire disaster at (x, z) with wind-coupled spread.", typed_schema, _typed_creator("fire"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_cyclone", "disaster", "Create a cyclone disaster at (x, z) updating wind, rain, visibility, and lightning.", typed_schema, _typed_creator("cyclone"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_landslide", "disaster", "Create a landslide disaster at (x, z) blocking roads and damaging slope buildings.", typed_schema, _typed_creator("landslide"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_building_collapse", "disaster", "Create a building collapse event at (x, z) with debris and trapped simulated survivors.", typed_schema, _typed_creator("building_collapse"), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_multi_hazard_scenario", "disaster", "Trigger a preset or random multi-hazard disaster scenario.", {
            "type": "object",
            "properties": {
                "preset_id": {"type": "string"},
                "seed": {"type": "integer"},
            },
            "additionalProperties": False,
        }, create_multi_hazard_scenario, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("start_disaster", "disaster", "Activate a created or scheduled disaster event.", _EID, start_disaster, PermissionLevel.OPERATIONAL),
        ToolDefinition("pause_disaster", "disaster", "Pause an active disaster event.", _EID, pause_disaster, PermissionLevel.OPERATIONAL),
        ToolDefinition("resume_disaster", "disaster", "Resume a paused disaster event.", _EID, resume_disaster, PermissionLevel.OPERATIONAL),
        ToolDefinition("stop_disaster", "disaster", "Stop and resolve an active disaster event.", _EID, stop_disaster, PermissionLevel.OPERATIONAL),
        ToolDefinition("remove_disaster", "disaster", "Remove a disaster event and its hazard zone from the simulation.", _EID, remove_disaster, PermissionLevel.DESTRUCTIVE),
        ToolDefinition("increase_disaster_severity", "disaster", "Increase the severity of a disaster event.", {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, "delta": {"type": "number", "minimum": 0.05, "maximum": 0.9}},
            "required": ["event_id"],
            "additionalProperties": False,
        }, increase_disaster_severity, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("decrease_disaster_severity", "disaster", "Decrease the severity of a disaster event.", {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, "delta": {"type": "number", "minimum": 0.05, "maximum": 0.9}},
            "required": ["event_id"],
            "additionalProperties": False,
        }, decrease_disaster_severity, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("expand_disaster_radius", "disaster", "Expand the affected radius of a disaster event in meters.", {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, "delta_radius": {"type": "number", "minimum": 10, "maximum": 1000}},
            "required": ["event_id"],
            "additionalProperties": False,
        }, expand_disaster_radius, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("move_disaster_epicentre", "disaster", "Relocate a disaster epicentre to new valid (x, z) coordinates.", {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
            },
            "required": ["event_id", "x", "z"],
            "additionalProperties": False,
        }, move_disaster_epicentre, PermissionLevel.OPERATIONAL),
        ToolDefinition("trigger_aftershock", "disaster", "Trigger a seismic aftershock on an existing earthquake event.", {
            "type": "object",
            "properties": {"event_id": {"type": "string"}, "scale": {"type": "number", "minimum": 0.1, "maximum": 1.5}},
            "required": ["event_id"],
            "additionalProperties": False,
        }, trigger_aftershock, PermissionLevel.OPERATIONAL, idempotent=False),
    ]
