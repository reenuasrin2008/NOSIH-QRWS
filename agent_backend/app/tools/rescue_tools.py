"""Survivor observation and rescue task creation/verification tools."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def build_rescue_tools() -> List[ToolDefinition]:
    async def get_all_survivors(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        surs = await sim.get("/api/survivors")
        return {"count": len(surs), "survivors": surs}

    async def get_survivors_in_region(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if args.get("disaster_event_id"):
            params["disaster_event_id"] = args["disaster_event_id"]
        if args.get("x") is not None and args.get("z") is not None:
            params["x"] = args["x"]
            params["z"] = args["z"]
            params["radius"] = args.get("radius", 450.0)
        surs = await sim.get("/api/survivors", params=params)
        return {"count": len(surs), "survivors": surs}

    async def get_survivor_details(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get(f"/api/survivors/{args['survivor_id']}")

    async def search_area_for_survivors(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/survivors/search", json_body={
            "x": float(args["x"]),
            "z": float(args["z"]),
            "radius": float(args.get("radius", 400.0)),
        })

    async def verify_survivor_location(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post(f"/api/survivors/{args['survivor_id']}/verify")

    async def prioritize_survivors(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        ranked = await sim.get("/api/survivors/prioritized")
        return {"count": len(ranked), "prioritized_survivors": ranked}

    async def get_all_tasks(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks")
        return {"count": len(tasks), "tasks": tasks[:60]}

    async def get_task_details(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.get(f"/api/tasks/{args['task_id']}")

    async def get_pending_tasks(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks", params={"status": "pending"})
        return {"count": len(tasks), "tasks": tasks}

    async def get_critical_tasks(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks", params={"priority": "critical"})
        return {"count": len(tasks), "tasks": tasks}

    async def get_active_missions(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks")
        active = [t for t in tasks if t["status"] in ("assigned", "in_progress")]
        return {"count": len(active), "active_missions": active}

    async def get_mission_history(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks")
        done = [t for t in tasks if t["status"] in ("completed", "failed")]
        return {"count": len(done), "history": done}

    async def prioritize_tasks(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tasks = await sim.get("/api/tasks")
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        pending = [t for t in tasks if t["status"] not in ("completed", "failed")]
        pending.sort(key=lambda t: (order.get(t["priority"], 4), t["deadline_seconds"]))
        return {"count": len(pending), "prioritized_tasks": pending[:30]}

    def _task_creator(default_type: str, default_caps: List[str], default_payload: float):
        async def _fn(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
            body = {
                "name": args.get("name", f"{default_type.replace('_', ' ').title()} Mission"),
                "task_type": args.get("task_type", default_type),
                "location": [float(args["x"]), float(args.get("y", 18.0)), float(args["z"])],
                "priority": args.get("priority", "critical"),
                "payload_required_kg": float(args.get("payload_required_kg", default_payload)),
                "required_capabilities": args.get("required_capabilities", default_caps),
                "deadline_seconds": float(args.get("deadline_seconds", 420.0)),
                "service_time_seconds": float(args.get("service_time_seconds", 20.0)),
                "risk_level": float(args.get("risk_level", 0.7)),
                "description": args.get("description", ""),
                "assign_drone_id": args.get("assign_drone_id"),
                "auto_assign": bool(args.get("auto_assign", True)),
                "survivor_id": args.get("survivor_id"),
                "disaster_event_id": args.get("disaster_event_id"),
            }
            res = await sim.post("/api/tasks", json_body=body)
            return {"task_id": res.get("created"), "task": res.get("task"), "state_version": res.get("state_version")}
        return _fn

    async def assign_rescue_resources(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/optimizer/run", json_body={"strategy": args.get("strategy"), "reason": "agent_assign_rescue_resources"})

    async def optimize_rescue_operations(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/optimizer/run", json_body={"strategy": args.get("strategy", "hybrid"), "reason": "agent_optimize_rescue"})

    async def reallocate_failed_missions(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/optimizer/run", json_body={"reason": "agent_reallocate_failed_missions"})

    async def verify_rescue_completion(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        tid = args.get("task_id")
        sid = args.get("survivor_id")
        out: Dict[str, Any] = {}
        if tid:
            t = await sim.get(f"/api/tasks/{tid}")
            out["task"] = {"id": t["id"], "status": t["status"], "assigned_drone_id": t["assigned_drone_id"], "completed_at_sim_s": t["completed_at_sim_s"]}
        if sid:
            s = await sim.get(f"/api/survivors/{sid}")
            out["survivor"] = {"survivor_id": s["survivor_id"], "status": s["status"], "assigned_task_id": s["assigned_task_id"]}
        if not tid and not sid:
            m = await sim.get("/api/world/metrics")
            out["metrics"] = m
        return out


    async def get_tactical_situation_brief(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        disasters = await sim.get("/api/disasters")
        survivors = await sim.get("/api/survivors/prioritized")
        drones = await sim.get("/api/drones")
        weather = await sim.get("/api/world/weather")
        metrics = await sim.get("/api/world/metrics")
        avail = [d for d in drones if d["status"] == "AVAILABLE"]
        unrescued = [s for s in survivors if s["status"] not in ("EVACUATED", "MEDICAL_ASSISTANCE")]
        return {
            "active_disasters": disasters,
            "unrescued_survivors_count": len(unrescued),
            "top_priority_survivors": unrescued[:8],
            "available_drones_count": len(avail),
            "available_drones_sample": [{"id": d["id"], "type": d["drone_type"], "battery": d["battery_percent"], "capabilities": d["capabilities"]} for d in avail[:10]],
            "weather": weather,
            "metrics": metrics.get("metrics", {}),
        }

    async def plan_and_dispatch_disaster_response(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        event_id = args.get("event_id")
        max_drones = max(1, min(8, int(args.get("max_drones", 3))))
        if event_id:
            dis = await sim.get(f"/api/disasters/{event_id}")
            surs = await sim.get("/api/survivors", params={"disaster_event_id": event_id})
        else:
            dis_list = await sim.get("/api/disasters")
            dis = dis_list[-1] if dis_list else None
            surs = await sim.get("/api/survivors/prioritized")

        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        targets = [s for s in surs if s["status"] not in ("EVACUATED", "MEDICAL_ASSISTANCE", "RESCUE_IN_PROGRESS")]
        targets.sort(key=lambda s: (order.get(s.get("priority", "medium"), 3), s.get("health_level", 1.0)))

        dispatched = []
        rejected = []
        used_drones = set()

        for surv in targets[:max_drones]:
            sid = surv["survivor_id"]
            pos = surv["position"]
            # Create linked rescue task (auto_assign=False so we explicitly validate & assign)
            t_res = await sim.post("/api/tasks", json_body={
                "name": f"AI Rescue {sid}",
                "task_type": "medical_delivery" if surv.get("health_level", 1.0) < 0.55 else "survivor_search",
                "location": pos,
                "priority": surv.get("priority", "critical"),
                "payload_required_kg": 1.2 if surv.get("health_level", 1.0) < 0.55 else 0.5,
                "required_capabilities": ["medical_payload"] if surv.get("health_level", 1.0) < 0.55 else ["survivor_search"],
                "deadline_seconds": 420.0,
                "service_time_seconds": 20.0,
                "risk_level": 0.75,
                "auto_assign": False,
                "survivor_id": sid,
                "disaster_event_id": surv.get("disaster_event_id") or (dis["event_id"] if dis else None),
            })
            tid = t_res.get("created")
            best = await sim.get(f"/api/tasks/{tid}/best-drone")
            chosen = next((c for c in best.get("candidates", []) if c["drone_id"] not in used_drones), None)
            if not chosen:
                rejected.append({"survivor_id": sid, "task_id": tid, "reason": "No eligible available drone met capability & 20% battery reserve."})
                continue
            try:
                asgn = await sim.post(f"/api/drones/{chosen['drone_id']}/assign", json_body={"task_id": tid})
                used_drones.add(chosen["drone_id"])
                dispatched.append({
                    "survivor_id": sid,
                    "task_id": tid,
                    "drone_id": chosen["drone_id"],
                    "distance_m": asgn.get("distance_m"),
                    "battery_percent": asgn.get("battery_percent"),
                    "target_position": pos,
                })
                # Broadcast 3D dispatch beam visualization
                drone_detail = await sim.get(f"/api/drones/{chosen['drone_id']}")
                await sim.post("/api/ui/sync", json_body={
                    "action": "ai_dispatch_beam",
                    "payload": {"from": drone_detail["position"], "to": pos, "drone_id": chosen["drone_id"], "survivor_id": sid},
                })
            except Exception as exc:
                rejected.append({"survivor_id": sid, "task_id": tid, "drone_id": chosen["drone_id"], "reason": str(exc)})

        if dis:
            ep = dis["epicentre"]
            await sim.post("/api/ui/sync", json_body={
                "action": "ai_scan_pulse",
                "payload": {"point": [ep["x"], 8, ep["z"]], "radius": dis["affected_radius"], "label": f"AI RESPONSE {dis['event_id']}"},
            })

        return {
            "event_id": dis["event_id"] if dis else None,
            "dispatched_count": len(dispatched),
            "dispatched": dispatched,
            "rejected_count": len(rejected),
            "rejected": rejected,
        }

    create_task_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "task_type": {"type": "string"},
            "x": {"type": "number", "minimum": 0, "maximum": 4000},
            "y": {"type": "number", "minimum": 0, "maximum": 300},
            "z": {"type": "number", "minimum": 0, "maximum": 4000},
            "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            "payload_required_kg": {"type": "number", "minimum": 0, "maximum": 10},
            "assign_drone_id": {"type": "string"},
            "auto_assign": {"type": "boolean"},
            "survivor_id": {"type": "string"},
            "disaster_event_id": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["x", "z"],
        "additionalProperties": False,
    }

    return [
        ToolDefinition("get_all_survivors", "rescue", "List all simulated survivors currently tracked in the world.", _EMPTY, get_all_survivors),
        ToolDefinition("get_survivors_in_region", "rescue", "List simulated survivors linked to a disaster_event_id or within (x, z, radius).", {
            "type": "object",
            "properties": {
                "disaster_event_id": {"type": "string"},
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
                "radius": {"type": "number", "minimum": 20, "maximum": 2500},
            },
            "additionalProperties": False,
        }, get_survivors_in_region),
        ToolDefinition("get_survivor_details", "rescue", "Retrieve authoritative state of a simulated survivor.", {
            "type": "object",
            "properties": {"survivor_id": {"type": "string"}},
            "required": ["survivor_id"],
            "additionalProperties": False,
        }, get_survivor_details),
        ToolDefinition("get_all_tasks", "rescue", "List rescue tasks in the simulation.", _EMPTY, get_all_tasks),
        ToolDefinition("get_task_details", "rescue", "Retrieve full details of a specific rescue task.", {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        }, get_task_details),
        ToolDefinition("get_pending_tasks", "rescue", "List all pending rescue tasks.", _EMPTY, get_pending_tasks),
        ToolDefinition("get_critical_tasks", "rescue", "List all critical-priority rescue tasks.", _EMPTY, get_critical_tasks),
        ToolDefinition("get_active_missions", "rescue", "List currently assigned or in-progress rescue missions.", _EMPTY, get_active_missions),
        ToolDefinition("get_mission_history", "rescue", "List completed and failed rescue missions.", _EMPTY, get_mission_history),
        ToolDefinition("create_rescue_task", "rescue", "Create a rescue task at (x, z) and optionally assign a drone.", create_task_schema, _task_creator("survivor_search", ["survivor_search"], 0.5), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_search_task", "rescue", "Create a thermal/aerial survivor search task at (x, z).", create_task_schema, _task_creator("survivor_search", ["survivor_search"], 0.4), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_medical_delivery", "rescue", "Create a rapid medical supply delivery task at (x, z).", create_task_schema, _task_creator("medical_delivery", ["medical_payload"], 1.2), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_water_delivery", "rescue", "Create a heavy-lift emergency water delivery task at (x, z).", create_task_schema, _task_creator("water_supply", ["water_supply"], 4.5), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("create_equipment_delivery", "rescue", "Create a rescue equipment delivery task at (x, z).", create_task_schema, _task_creator("equipment_delivery", ["equipment_delivery"], 5.5), PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("search_area_for_survivors", "rescue", "Perform simulated thermal scan around (x, z, radius) to detect simulated survivors.", {
            "type": "object",
            "properties": {
                "x": {"type": "number", "minimum": 0, "maximum": 4000},
                "z": {"type": "number", "minimum": 0, "maximum": 4000},
                "radius": {"type": "number", "minimum": 20, "maximum": 2500},
            },
            "required": ["x", "z"],
            "additionalProperties": False,
        }, search_area_for_survivors, PermissionLevel.OPERATIONAL),
        ToolDefinition("verify_survivor_location", "rescue", "Verify and lock in a simulated survivor's location status.", {
            "type": "object",
            "properties": {"survivor_id": {"type": "string"}},
            "required": ["survivor_id"],
            "additionalProperties": False,
        }, verify_survivor_location, PermissionLevel.OPERATIONAL),
        ToolDefinition("prioritize_survivors", "rescue", "Rank all simulated survivors by urgency, health level, and hazard exposure.", _EMPTY, prioritize_survivors),
        ToolDefinition("prioritize_tasks", "rescue", "Rank pending rescue tasks by priority and deadline.", _EMPTY, prioritize_tasks),
        ToolDefinition("assign_rescue_resources", "rescue", "Run resource assignment optimization across available drones and pending rescue tasks.", {
            "type": "object",
            "properties": {"strategy": {"type": "string", "enum": ["greedy", "classical", "quantum", "hybrid"]}},
            "additionalProperties": False,
        }, assign_rescue_resources, PermissionLevel.OPERATIONAL),
        ToolDefinition("optimize_rescue_operations", "rescue", "Run the hybrid/quantum rescue optimizer to plan fleet assignments.", {
            "type": "object",
            "properties": {"strategy": {"type": "string", "enum": ["greedy", "classical", "quantum", "hybrid"]}},
            "additionalProperties": False,
        }, optimize_rescue_operations, PermissionLevel.OPERATIONAL),
        ToolDefinition("reallocate_failed_missions", "rescue", "Reallocate tasks released by failed or low-battery drones.", _EMPTY, reallocate_failed_missions, PermissionLevel.OPERATIONAL),
        ToolDefinition("get_tactical_situation_brief", "rescue", "Fetch a consolidated tactical brief of active disasters, top priority unrescued survivors, available drones, weather, and KPIs in one fast call.", _EMPTY, get_tactical_situation_brief),
        ToolDefinition("plan_and_dispatch_disaster_response", "rescue", "Tactical macro-tool: prioritize unrescued survivors in a disaster zone, create validated rescue tasks, assign the best feasible drones (3D A* + 20% battery reserve), and broadcast 3D dispatch beams.", {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "max_drones": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "additionalProperties": False,
        }, plan_and_dispatch_disaster_response, PermissionLevel.OPERATIONAL, idempotent=False),
        ToolDefinition("verify_rescue_completion", "rescue", "Verify the real authoritative status of a rescue task, survivor, or overall mission metrics.", {
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "survivor_id": {"type": "string"}},
            "additionalProperties": False,
        }, verify_rescue_completion),
    ]
