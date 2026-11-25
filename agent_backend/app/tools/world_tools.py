"""World observation and simulation lifecycle tools calling authoritative port 8000."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def build_world_tools() -> List[ToolDefinition]:
    async def get_world_state(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        st = await sim.get("/api/world/state", params={"include_city": "false"})
        return {
            "run_id": st.get("run_id"),
            "state_version": st.get("state_version"),
            "status": st.get("status"),
            "strategy": st.get("strategy"),
            "sim_time_s": st.get("sim_time_s"),
            "active_disasters": len(st.get("disasters", [])),
            "survivors_count": len(st.get("survivors", [])),
            "drones_count": len(st.get("drones", [])),
            "tasks_count": len(st.get("tasks", [])),
            "weather": st.get("weather"),
            "metrics": st.get("metrics"),
        }

    async def get_world_version(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/version")

    async def get_city_details(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/city")

    async def get_city_coordinates(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        c = await sim.get("/api/world/city")
        ws = float(c.get("world_size", 4000.0))
        return {
            "world_size_m": ws,
            "bounds": {"x_min": 0, "x_max": ws, "z_min": 0, "z_max": ws},
            "center": {"x": ws / 2, "z": ws / 2},
            "regions": {
                "north": {"x": ws * 0.5, "z": ws * 0.2},
                "south": {"x": ws * 0.5, "z": ws * 0.8},
                "east": {"x": ws * 0.8, "z": ws * 0.5},
                "west": {"x": ws * 0.2, "z": ws * 0.5},
                "river_corridor": {"x": ws * 0.5, "z": c.get("river_z", ws * 0.5)},
            },
        }

    async def get_simulation_time(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        v = await sim.get("/api/world/version")
        return {"sim_time_s": v.get("sim_time_s"), "status": v.get("status"), "state_version": v.get("state_version")}

    async def get_simulation_status(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/version")

    async def get_all_hazards(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        hz = await sim.get("/api/world/hazards")
        return {"count": len(hz), "hazards": hz}

    async def get_affected_regions(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        disasters = await sim.get("/api/disasters")
        regions = [
            {
                "event_id": d["event_id"],
                "type": d["type"],
                "status": d["status"],
                "epicentre": d["epicentre"],
                "affected_radius": d["affected_radius"],
                "severity": d["severity"],
                "affected_buildings_count": len(d.get("affected_buildings", [])),
                "affected_roads_count": len(d.get("affected_roads", [])),
                "survivors_count": len(d.get("related_survivors", [])),
            }
            for d in disasters
        ]
        return {"count": len(regions), "regions": regions}

    async def get_building_damage(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/buildings/damage")

    async def get_road_conditions(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/roads")

    async def get_weather(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/weather")

    async def get_all_stations(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/stations")

    async def get_station_utilization(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        st = await sim.get("/api/world/stations")
        return {"utilization": st.get("utilization", {})}

    async def get_simulation_metrics(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get("/api/world/metrics")

    async def get_simulation_event_log(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = int(args.get("limit", 40))
        return await sim.get("/api/world/events", params={"limit": limit})

    # Lifecycle operations
    async def start_simulation(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post("/api/simulation/start")
        st = res.get("benchmark", {}).get("active_state", {})
        return {"status": st.get("status"), "state_version": st.get("state_version"), "sim_time_s": st.get("sim_time_s")}

    async def pause_simulation(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post("/api/simulation/pause")
        st = res.get("benchmark", {}).get("active_state", {})
        return {"status": st.get("status"), "state_version": st.get("state_version")}

    async def resume_simulation(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post("/api/simulation/resume")
        st = res.get("benchmark", {}).get("active_state", {})
        return {"status": st.get("status"), "state_version": st.get("state_version")}

    async def step_simulation(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        steps = max(1, min(20, int(args.get("steps", 1))))
        last = {}
        for _ in range(steps):
            last = await sim.post("/api/simulation/step")
        st = last.get("benchmark", {}).get("active_state", {})
        return {"steps": steps, "sim_time_s": st.get("sim_time_s"), "state_version": st.get("state_version")}

    async def set_simulation_speed(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/simulation/speed", json_body={"speed": float(args["speed"])})

    async def generate_scenario(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        body = {
            "seed": int(args.get("seed", 20261121)),
            "strategy": args.get("strategy", "hybrid"),
            "city_density": float(args.get("city_density", 1.0)),
            "building_density": float(args.get("building_density", 1.0)),
        }
        res = await sim.post("/api/scenarios/generate", json_body=body)
        st = res.get("benchmark", {}).get("active_state", {})
        return {"run_id": st.get("run_id"), "seed": st.get("seed"), "state_version": st.get("state_version")}

    async def reset_simulation(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        res = await sim.post("/api/simulation/reset")
        st = res.get("benchmark", {}).get("active_state", {})
        return {"reset": True, "run_id": st.get("run_id"), "state_version": st.get("state_version")}

    async def save_experiment(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/experiments/save")

    async def export_experiment(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        fmt = args.get("format", "json")
        if fmt == "json":
            return await sim.get("/api/experiments/current/export", params={"fmt": "json"})
        return await sim.get("/api/experiments/current/export", params={"fmt": "zip"})

    return [
        ToolDefinition("get_world_state", "observation", "Retrieve a concise authoritative summary of the current simulation world.", _EMPTY, get_world_state),
        ToolDefinition("get_world_version", "observation", "Retrieve the current run_id, state_version, simulation time, and status.", _EMPTY, get_world_version),
        ToolDefinition("get_city_details", "observation", "Retrieve city metadata, bounds, building/road/station counts, and weather.", _EMPTY, get_city_details),
        ToolDefinition("get_city_coordinates", "observation", "Retrieve valid world coordinate bounds and named metropolitan regions (north, south, east, west, center, river).", _EMPTY, get_city_coordinates),
        ToolDefinition("get_simulation_time", "observation", "Retrieve the current simulation clock time in seconds.", _EMPTY, get_simulation_time),
        ToolDefinition("get_simulation_status", "observation", "Retrieve current simulation status (READY, RUNNING, PAUSED, COMPLETED).", _EMPTY, get_simulation_status),
        ToolDefinition("get_all_hazards", "observation", "List all active and inactive hazard zones in the metropolitan area.", _EMPTY, get_all_hazards),
        ToolDefinition("get_affected_regions", "observation", "List all disaster-affected regions with epicentres, radii, and impact counts.", _EMPTY, get_affected_regions),
        ToolDefinition("get_building_damage", "observation", "Retrieve structural integrity and damage counts across metropolitan buildings.", _EMPTY, get_building_damage),
        ToolDefinition("get_road_conditions", "observation", "Retrieve flooded, fractured, or debris-obstructed roads and bridges.", _EMPTY, get_road_conditions),
        ToolDefinition("get_weather", "observation", "Retrieve live weather conditions (wind, rain, fog, visibility, lightning).", _EMPTY, get_weather),
        ToolDefinition("get_all_stations", "observation", "List all charging/landing stations and current utilization.", _EMPTY, get_all_stations),
        ToolDefinition("get_station_utilization", "observation", "Retrieve charging pad occupancy and queue counts per station.", _EMPTY, get_station_utilization),
        ToolDefinition("get_simulation_metrics", "observation", "Retrieve live mission KPIs, score, energy usage, and recovery rate.", _EMPTY, get_simulation_metrics),
        ToolDefinition("get_simulation_event_log", "observation", "Retrieve recent authoritative simulation events.", {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            "additionalProperties": False,
        }, get_simulation_event_log),
        ToolDefinition("start_simulation", "lifecycle", "Start the simulation engine.", _EMPTY, start_simulation, PermissionLevel.OPERATIONAL),
        ToolDefinition("pause_simulation", "lifecycle", "Pause the simulation engine.", _EMPTY, pause_simulation, PermissionLevel.OPERATIONAL),
        ToolDefinition("resume_simulation", "lifecycle", "Resume a paused simulation.", _EMPTY, resume_simulation, PermissionLevel.OPERATIONAL),
        ToolDefinition("step_simulation", "lifecycle", "Advance the simulation by a fixed number of 1-second steps.", {
            "type": "object",
            "properties": {"steps": {"type": "integer", "minimum": 1, "maximum": 20}},
            "additionalProperties": False,
        }, step_simulation, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("set_simulation_speed", "lifecycle", "Set simulation time scaling multiplier (0.5 to 8.0).", {
            "type": "object",
            "properties": {"speed": {"type": "number", "minimum": 0.5, "maximum": 8.0}},
            "required": ["speed"],
            "additionalProperties": False,
        }, set_simulation_speed, PermissionLevel.OPERATIONAL),
        ToolDefinition("generate_scenario", "lifecycle", "Generate a fresh seeded metropolitan disaster scenario.", {
            "type": "object",
            "properties": {
                "seed": {"type": "integer"},
                "strategy": {"type": "string", "enum": ["greedy", "classical", "quantum", "hybrid"]},
                "city_density": {"type": "number", "minimum": 0.3, "maximum": 1.5},
                "building_density": {"type": "number", "minimum": 0.3, "maximum": 1.5},
            },
            "additionalProperties": False,
        }, generate_scenario, PermissionLevel.DESTRUCTIVE, idempotent=False),
        ToolDefinition("reset_simulation", "lifecycle", "Reset the entire simulation world to initial state (destructive).", _EMPTY, reset_simulation, PermissionLevel.DESTRUCTIVE, idempotent=False),
        ToolDefinition("save_experiment", "lifecycle", "Save the current experiment run and replay as JSON files.", _EMPTY, save_experiment, PermissionLevel.OPERATIONAL),
        ToolDefinition("export_experiment", "lifecycle", "Export the current experiment summary as JSON or ZIP.", {
            "type": "object",
            "properties": {"format": {"type": "string", "enum": ["json", "zip"]}},
            "additionalProperties": False,
        }, export_experiment, PermissionLevel.READ_ONLY),
    ]
