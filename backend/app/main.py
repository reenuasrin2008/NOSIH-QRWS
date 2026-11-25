from __future__ import annotations
import asyncio
import math
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from app.core.models import BaseModel

from app.benchmark.runner import BenchmarkArena
from app.benchmark.leaderboard import sort_leaderboard
from app.core.config import CONFIG, DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_NAME, DEFAULT_SEED
from app.core.models import (
    DisasterType, DroneStatus, FailureType, SimulationStatus, StrategyType,
    SurvivorStatus, TaskPriority, TaskStatus,
)
from app.disasters.disaster_presets import load_disaster_presets
from app.logging.export_manager import build_experiment_zip, build_replay_payload, build_summary_payload
from app.simulation.world import SimulationWorld
from app.storage.event_journal import EventJournal
from app.storage.experiment_repository import JsonExperimentRepository
from app.websocket.manager import ConnectionManager


class GenerateScenarioReq(BaseModel):
    seed: int = DEFAULT_SEED
    scenario_id: str = DEFAULT_SCENARIO_ID
    scenario_name: str = DEFAULT_SCENARIO_NAME
    city_density: float = Field(default=1.0, ge=0.3, le=1.5)
    building_density: float = Field(default=1.0, ge=0.3, le=1.5)
    strategy: StrategyType = StrategyType.HYBRID


class SpeedReq(BaseModel):
    speed: float = Field(default=1.0, ge=0.5, le=8.0)


class CreateTaskReq(BaseModel):
    name: str
    task_type: str = "medical_delivery"
    location: Tuple[float, float, float]
    priority: TaskPriority = TaskPriority.CRITICAL
    payload_required_kg: float = 1.2
    required_capabilities: List[str] = Field(default_factory=lambda: ["medical_payload"])
    deadline_seconds: float = 420.0
    service_time_seconds: float = 20.0
    risk_level: float = 0.7
    description: str = ""
    assign_drone_id: Optional[str] = None
    auto_assign: bool = True
    survivor_id: Optional[str] = None
    disaster_event_id: Optional[str] = None


class WaypointReq(BaseModel):
    destination: Tuple[float, float, float]


class AssignTaskReq(BaseModel):
    task_id: str
    operation_id: Optional[str] = None


class FailureReq(BaseModel):
    failure_type: FailureType = FailureType.COMPLETE_DRONE_DESTRUCTION
    scope: str = "all"


class EnvEventReq(BaseModel):
    event_kind: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ViewSwitchReq(BaseModel):
    strategy: StrategyType


class UiSyncReq(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class CreateDisasterReq(BaseModel):
    type: DisasterType
    x: float
    z: float
    y: float = 0.0
    severity: float = Field(default=0.75, ge=0.05, le=1.0)
    affected_radius: float = Field(default=260.0, ge=30.0, le=2000.0)
    duration: float = Field(default=900.0, ge=30.0, le=7200.0)
    propagation_speed: float = Field(default=1.0, ge=0.1, le=5.0)
    start_delay: float = Field(default=0.0, ge=0.0, le=600.0)
    auto_start: bool = True
    seed: Optional[int] = None
    magnitude: float = Field(default=0.0, ge=0.0, le=9.5)
    operation_id: Optional[str] = None


class SeverityDeltaReq(BaseModel):
    delta: float = Field(default=0.15, ge=-0.95, le=0.95)
    operation_id: Optional[str] = None


class RadiusDeltaReq(BaseModel):
    delta_radius: float = Field(default=80.0, ge=-500.0, le=1000.0)
    operation_id: Optional[str] = None


class MoveEpicentreReq(BaseModel):
    x: float
    z: float
    operation_id: Optional[str] = None


class AftershockReq(BaseModel):
    scale: float = Field(default=0.65, ge=0.1, le=1.5)
    operation_id: Optional[str] = None


class PresetReq(BaseModel):
    preset_id: str
    operation_id: Optional[str] = None


class RandomScenarioReq(BaseModel):
    seed: Optional[int] = None
    operation_id: Optional[str] = None


class SurvivorSearchReq(BaseModel):
    x: float
    z: float
    radius: float = Field(default=400.0, ge=20.0, le=2500.0)


class OptimizerRunReq(BaseModel):
    strategy: Optional[StrategyType] = None
    reason: str = "operator_request"


class UpdateConfigReq(BaseModel):
    w_rescue_time: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    w_energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    w_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    w_deadline_violations: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    w_uncompleted: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    qaoa_max_qubits: Optional[int] = Field(default=None, ge=4, le=10)
    qaoa_layers: Optional[int] = Field(default=None, ge=1, le=4)
    qaoa_shots: Optional[int] = Field(default=None, ge=128, le=2048)


class AppRuntime:
    def __init__(self):
        self.journal: EventJournal = EventJournal()
        self.repo: JsonExperimentRepository = JsonExperimentRepository()
        self.world: SimulationWorld = SimulationWorld(seed=DEFAULT_SEED, journal=self.journal)
        self.benchmark: Optional[BenchmarkArena] = None
        self.ws_manager: ConnectionManager = ConnectionManager()
        self.state_lock: asyncio.Lock = asyncio.Lock()
        self.tick_task: Optional[asyncio.Task] = None
        self._last_snapshot_sim_s: float = -100.0

    def active_world(self) -> SimulationWorld:
        return self.benchmark.worlds[self.benchmark.active_view] if self.benchmark is not None else self.world

    async def broadcast_state(self, include_city: bool = False) -> None:
        if self.ws_manager.active:
            await self.ws_manager.broadcast(self.current_payload(include_city=include_city))

    async def broadcast_meaningful_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.ws_manager.active:
            w = self.active_world()
            await self.ws_manager.broadcast({
                "type": "meaningful_event",
                "event_type": event_type,
                "run_id": w.run_id,
                "state_version": w.state_version,
                "sim_time_s": w.sim_time_s,
                "data": data,
            })

    def current_payload(self, include_city: bool = False) -> Dict[str, Any]:
        if self.benchmark is not None:
            return {"mode": "benchmark", "benchmark": self.benchmark.serialize(include_city=include_city)}
        w = self.world
        return {
            "mode": "single",
            "benchmark": {
                "benchmark_id": None,
                "active_view": w.strategy.value,
                "leaderboard": [w.get_metrics().model_dump()],
                "active_state": w.serialize_state(include_city=include_city),
                "ghost_routes": {},
            },
        }


runtime = AppRuntime()


async def simulation_loop():
    while True:
        await asyncio.sleep(0.25)
        w = runtime.active_world()
        ticks = max(1, int(round(w.speed_multiplier)))
        advanced = False
        async with runtime.state_lock:
            if runtime.benchmark is not None:
                if any(bw.status == SimulationStatus.RUNNING for bw in runtime.benchmark.worlds.values()):
                    for _ in range(ticks):
                        runtime.benchmark.step_all(dt=1.0)
                    advanced = True
            elif runtime.world.status == SimulationStatus.RUNNING:
                for _ in range(ticks):
                    runtime.world.step(dt=1.0)
                advanced = True

        if advanced:
            if runtime.ws_manager.active:
                await runtime.ws_manager.broadcast(runtime.current_payload(include_city=False))
            cur_w = runtime.active_world()
            if cur_w.sim_time_s - runtime._last_snapshot_sim_s >= 30.0:
                runtime._last_snapshot_sim_s = cur_w.sim_time_s
                snap = cur_w.serialize_world()
                asyncio.create_task(asyncio.to_thread(runtime.journal.save_world_snapshot, snap))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.tick_task = asyncio.create_task(simulation_loop())
    try:
        yield
    finally:
        if runtime.tick_task:
            runtime.tick_task.cancel()


app = FastAPI(title="QUANTUM RESCUE V2 — Autonomous Disaster Response Digital Twin API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Health & World Authoritative Endpoints ────────────────────────────
@app.get("/api/health")
def health():
    w = runtime.active_world()
    return {
        "status": "ok",
        "version": "2.0.0",
        "storage": "json_only",
        "run_id": w.run_id,
        "state_version": w.state_version,
        "sim_time_s": w.sim_time_s,
        "ws_clients": len(runtime.ws_manager.active),
    }


@app.get("/api/world/state")
def get_world_state(include_city: bool = Query(default=False)):
    return runtime.active_world().serialize_state(include_city=include_city)


@app.get("/api/world/version")
def get_world_version():
    w = runtime.active_world()
    return {
        "run_id": w.run_id,
        "state_version": w.state_version,
        "sim_time_s": w.sim_time_s,
        "status": w.status.value,
        "strategy": w.strategy.value,
    }


@app.get("/api/world/events")
def get_world_events(limit: int = Query(default=100, ge=1, le=500), category: Optional[str] = None):
    w = runtime.active_world()
    evs = w.events
    if category:
        evs = [e for e in evs if e.category == category]
    return {"run_id": w.run_id, "state_version": w.state_version, "events": [e.model_dump() for e in evs[-limit:]]}


@app.get("/api/world/snapshot")
def get_world_snapshot(save_to_disk: bool = Query(default=False)):
    w = runtime.active_world()
    snap = w.serialize_world()
    if save_to_disk:
        runtime.journal.save_world_snapshot(snap)
    return snap


@app.post("/api/world/snapshot/restore")
async def restore_world_snapshot():
    snap = runtime.journal.load_world_snapshot()
    if not snap:
        raise HTTPException(404, "No saved latest_world.json snapshot available")
    async with runtime.state_lock:
        restored = SimulationWorld.deserialize_world(snap)
        restored.journal = runtime.journal
        runtime.benchmark = None
        runtime.world = restored
    payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return {"restored": True, "run_id": restored.run_id, "state_version": restored.state_version, "sim_time_s": restored.sim_time_s}


@app.get("/api/world/city")
def get_world_city():
    w = runtime.active_world()
    return {
        "scenario_id": w.city.scenario_id,
        "scenario_name": w.city.scenario_name,
        "seed": w.city.seed,
        "world_size": w.city.world_size,
        "river_z": w.city.river_z,
        "river_width": w.city.river_width,
        "building_count": len(w.city.buildings),
        "road_count": len(w.city.roads),
        "station_count": len(w.city.stations),
        "hazard_count": len(w.city.hazards),
        "weather": w.city.weather.model_dump(),
    }


@app.get("/api/world/buildings/damage")
def get_building_damage():
    return runtime.active_world().get_building_damage_summary()


@app.get("/api/world/roads")
def get_road_conditions():
    roads = runtime.active_world().city.roads
    blocked = [r.model_dump() for r in roads if r.blocked or r.flood_depth_m > 0 or r.fractured or r.obstructed_by_debris]
    return {"total_roads": len(roads), "affected_count": len(blocked), "affected_roads": blocked[:120]}


@app.get("/api/world/weather")
def get_weather():
    return runtime.active_world().city.weather.model_dump()


@app.get("/api/world/hazards")
def get_hazards():
    return [h.model_dump() for h in runtime.active_world().city.hazards]


@app.get("/api/world/stations")
def get_stations():
    w = runtime.active_world()
    return {"stations": [s.model_dump() for s in w.city.stations], "utilization": w.charging.get_utilization(w.city)}


@app.get("/api/world/metrics")
def get_metrics():
    w = runtime.active_world()
    return {"run_id": w.run_id, "state_version": w.state_version, "metrics": w.get_metrics().model_dump()}


# ── UI Sync Relay ─────────────────────────────────────────────────────
@app.post("/api/ui/sync")
async def ui_sync(req: UiSyncReq):
    """Relay UI/camera/selection/layer commands across 3D Scene (:5173), Control Panel (:5174), and AI Console (:5175)."""
    msg = {"type": "ui_command", "action": req.action, "payload": req.payload}
    if runtime.ws_manager.active:
        await runtime.ws_manager.broadcast(msg)
    return {"ok": True, "action": req.action, "relayed_to": len(runtime.ws_manager.active)}


# ── Disaster Lifecycle Endpoints ──────────────────────────────────────
@app.get("/api/disasters")
def list_disasters():
    w = runtime.active_world()
    return [ev.model_dump() for ev in w.disasters.events.values()]


@app.get("/api/disasters/presets")
def list_disaster_presets():
    return load_disaster_presets()


@app.get("/api/disasters/timeline")
def get_disaster_timeline():
    return runtime.active_world().disasters.timeline[-100:]


@app.get("/api/disasters/{event_id}")
def get_disaster(event_id: str):
    ev = runtime.active_world().disasters.events.get(event_id)
    if not ev:
        raise HTTPException(404, f"Disaster {event_id} not found")
    return ev.model_dump()


@app.post("/api/disasters")
async def create_disaster(req: CreateDisasterReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().create_disaster(
                disaster_type=req.type,
                x=req.x,
                z=req.z,
                y=req.y,
                severity=req.severity,
                affected_radius=req.affected_radius,
                duration=req.duration,
                propagation_speed=req.propagation_speed,
                start_delay=req.start_delay,
                auto_start=req.auto_start,
                seed=req.seed,
                magnitude=req.magnitude,
                operation_id=req.operation_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    await runtime.broadcast_state(include_city=False)
    await runtime.broadcast_meaningful_event("disaster_created", res["disaster"])
    return res


@app.post("/api/disasters/preset")
async def load_disaster_preset(req: PresetReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().load_disaster_preset(req.preset_id, operation_id=req.operation_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    await runtime.broadcast_meaningful_event("disaster_preset_loaded", res)
    return res


@app.post("/api/disasters/random")
async def trigger_random_disaster(req: RandomScenarioReq):
    async with runtime.state_lock:
        res = runtime.active_world().create_random_disaster_scenario(seed=req.seed, operation_id=req.operation_id)
    await runtime.broadcast_state(include_city=False)
    await runtime.broadcast_meaningful_event("disaster_random_created", res)
    return res


@app.post("/api/disasters/{event_id}/start")
async def start_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().start_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    await runtime.broadcast_meaningful_event("disaster_started", res["disaster"])
    return res


@app.post("/api/disasters/{event_id}/pause")
async def pause_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().pause_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/resume")
async def resume_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().resume_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/stop")
async def stop_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().stop_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.delete("/api/disasters/{event_id}")
async def remove_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().remove_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/reset")
async def reset_disaster(event_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().reset_disaster(event_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/severity")
async def adjust_disaster_severity(event_id: str, req: SeverityDeltaReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().adjust_disaster_severity(event_id, req.delta, operation_id=req.operation_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/radius")
async def expand_disaster_radius(event_id: str, req: RadiusDeltaReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().expand_disaster_radius(event_id, req.delta_radius, operation_id=req.operation_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/move")
async def move_disaster_epicentre(event_id: str, req: MoveEpicentreReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().move_disaster_epicentre(event_id, req.x, req.z, operation_id=req.operation_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/disasters/{event_id}/aftershock")
async def trigger_aftershock(event_id: str, req: AftershockReq):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().trigger_aftershock(event_id, scale=req.scale, operation_id=req.operation_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    await runtime.broadcast_state(include_city=False)
    await runtime.broadcast_meaningful_event("aftershock_triggered", res["disaster"])
    return res


# ── Survivor Endpoints ────────────────────────────────────────────────
@app.get("/api/survivors")
def list_survivors(
    disaster_event_id: Optional[str] = None,
    x: Optional[float] = None,
    z: Optional[float] = None,
    radius: Optional[float] = None,
):
    surs = list(runtime.active_world().survivors.values())
    if disaster_event_id:
        surs = [s for s in surs if s.disaster_event_id == disaster_event_id]
    if x is not None and z is not None and radius is not None:
        surs = [s for s in surs if math.hypot(s.position[0] - x, s.position[2] - z) <= radius]
    return [s.model_dump() for s in surs]


@app.get("/api/survivors/prioritized")
def list_prioritized_survivors():
    return runtime.active_world().prioritize_survivors()


@app.get("/api/survivors/{survivor_id}")
def get_survivor(survivor_id: str):
    s = runtime.active_world().survivors.get(survivor_id)
    if not s:
        raise HTTPException(404, f"Survivor {survivor_id} not found")
    return s.model_dump()


@app.post("/api/survivors/search")
async def search_survivors(req: SurvivorSearchReq):
    async with runtime.state_lock:
        found = runtime.active_world().search_area_for_survivors(req.x, req.z, req.radius)
    await runtime.broadcast_state(include_city=False)
    return {"found_count": len(found), "survivors": found, "state_version": runtime.active_world().state_version}


@app.post("/api/survivors/{survivor_id}/verify")
async def verify_survivor(survivor_id: str):
    async with runtime.state_lock:
        try:
            res = runtime.active_world().verify_survivor_location(survivor_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
    await runtime.broadcast_state(include_city=False)
    return {"survivor": res, "state_version": runtime.active_world().state_version}


# ── Scenario & Simulation Lifecycle Endpoints ─────────────────────────
@app.post("/api/scenarios/generate")
async def generate_scenario(req: GenerateScenarioReq):
    async with runtime.state_lock:
        runtime.benchmark = None
        runtime.world = SimulationWorld(
            strategy=req.strategy, seed=req.seed, scenario_id=req.scenario_id,
            scenario_name=req.scenario_name, city_density=req.city_density, building_density=req.building_density,
            journal=runtime.journal,
        )
        payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.get("/api/scenarios")
def get_current_scenario():
    return runtime.current_payload(include_city=True)


@app.post("/api/simulation/start")
async def start_simulation():
    async with runtime.state_lock:
        if runtime.benchmark is not None:
            runtime.benchmark.start_all()
        else:
            runtime.world.run_optimizer("initial_plan")
            runtime.world.status = SimulationStatus.RUNNING
        payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/pause")
async def pause_simulation():
    async with runtime.state_lock:
        if runtime.benchmark is not None:
            runtime.benchmark.pause_all()
        else:
            runtime.world.status = SimulationStatus.PAUSED
        payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/resume")
async def resume_simulation():
    async with runtime.state_lock:
        if runtime.benchmark is not None:
            runtime.benchmark.resume_all()
        else:
            runtime.world.status = SimulationStatus.RUNNING
        payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/step")
async def step_simulation():
    async with runtime.state_lock:
        if runtime.benchmark is not None:
            for w in runtime.benchmark.worlds.values():
                w.status = SimulationStatus.RUNNING
                w.step(dt=1.0)
                w.status = SimulationStatus.PAUSED
        else:
            runtime.world.status = SimulationStatus.RUNNING
            runtime.world.step(dt=1.0)
            runtime.world.status = SimulationStatus.PAUSED
        payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/speed")
def set_speed(req: SpeedReq):
    if runtime.benchmark is not None:
        runtime.benchmark.set_speed(req.speed)
    runtime.world.speed_multiplier = req.speed
    return {"speed": req.speed}


@app.post("/api/simulation/reset")
async def reset_simulation():
    async with runtime.state_lock:
        seed, city = runtime.world.seed, runtime.world.city
        runtime.benchmark = None
        runtime.world = SimulationWorld(
            strategy=runtime.world.strategy, seed=seed, scenario_id=city.scenario_id,
            scenario_name=city.scenario_name, city_density=city.city_density, building_density=city.building_density,
            journal=runtime.journal,
        )
        payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return payload


# ── Drone, Task & Optimizer Endpoints ─────────────────────────────────
@app.get("/api/drones")
def list_drones(status: Optional[str] = None):
    drones = list(runtime.active_world().drones.values())
    if status:
        drones = [d for d in drones if d.status.value.lower() == status.lower()]
    return [d.model_dump() for d in drones]


@app.get("/api/drones/{drone_id}")
def get_drone(drone_id: str):
    d = runtime.active_world().drones.get(drone_id)
    if not d:
        raise HTTPException(404, f"Drone {drone_id} not found")
    return d.model_dump()


@app.post("/api/drones/{drone_id}/assign")
async def assign_drone_to_task(drone_id: str, req: AssignTaskReq):
    async with runtime.state_lock:
        res = runtime.active_world().assign_drone_to_task(drone_id, req.task_id, operation_id=req.operation_id)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Assignment rejected"))
    await runtime.broadcast_state(include_city=False)
    return res


@app.post("/api/drones/{drone_id}/route")
def calculate_drone_route(drone_id: str, req: WaypointReq):
    res = runtime.active_world().calculate_safe_route(drone_id, req.destination)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Route calculation failed"))
    return res


@app.get("/api/tasks")
def list_tasks(status: Optional[str] = None, priority: Optional[str] = None):
    tasks = list(runtime.active_world().tasks.values())
    if status:
        tasks = [t for t in tasks if t.status.value.lower() == status.lower()]
    if priority:
        tasks = [t for t in tasks if t.priority.value.lower() == priority.lower()]
    return [t.model_dump() for t in tasks]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    t = runtime.active_world().tasks.get(task_id)
    if not t:
        raise HTTPException(404, f"Task {task_id} not found")
    return t.model_dump()


@app.get("/api/tasks/{task_id}/best-drone")
def get_best_drone_for_task(task_id: str):
    res = runtime.active_world().find_best_drone_for_task(task_id)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Task not found"))
    return res


@app.post("/api/tasks")
async def create_task(req: CreateTaskReq):
    kwargs = req.model_dump()
    async with runtime.state_lock:
        if runtime.benchmark is not None:
            bm_kwargs = {k: v for k, v in kwargs.items() if k not in ("survivor_id", "disaster_event_id")}
            created = runtime.benchmark.broadcast_task(**bm_kwargs)
            state = runtime.current_payload(include_city=False)
        else:
            task = runtime.world.add_task(**kwargs)
            created = task.id
            state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"created": created, "task": runtime.active_world().tasks[created].model_dump() if isinstance(created, str) and created in runtime.active_world().tasks else None, "state_version": runtime.active_world().state_version, "state": state}


@app.post("/api/drones/{drone_id}/waypoint")
async def set_drone_waypoint(drone_id: str, req: WaypointReq):
    async with runtime.state_lock:
        res = runtime.active_world().set_drone_waypoint(drone_id, req.destination)
        if not res.get("ok"):
            raise HTTPException(400, res.get("error", "Infeasible waypoint"))
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/drones/{drone_id}/failure")
async def inject_drone_failure(drone_id: str, req: FailureReq):
    async with runtime.state_lock:
        res = runtime.benchmark.inject_failure(drone_id, req.failure_type, scope=req.scope) if runtime.benchmark else runtime.world.inject_failure(drone_id, req.failure_type)
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    await runtime.broadcast_meaningful_event("drone_failure", {"drone_id": drone_id, "failure_type": req.failure_type.value})
    return {"result": res, "state": state}


@app.post("/api/drones/{drone_id}/destroy")
async def destroy_drone(drone_id: str, scope: str = Query(default="all")):
    async with runtime.state_lock:
        res = runtime.benchmark.inject_failure(drone_id, FailureType.COMPLETE_DRONE_DESTRUCTION, scope=scope) if runtime.benchmark else runtime.world.inject_failure(drone_id, FailureType.COMPLETE_DRONE_DESTRUCTION)
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/drones/{drone_id}/rtb")
async def return_drone_to_base(drone_id: str):
    async with runtime.state_lock:
        w = runtime.active_world()
        d = w.drones.get(drone_id)
        if not d:
            raise HTTPException(404, f"Drone {drone_id} not found")
        w._send_drone_to_charge(d, rtb_only=True)
        w.bump_version()
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return state


@app.post("/api/environment/events")
async def inject_env_event(req: EnvEventReq):
    async with runtime.state_lock:
        res = runtime.benchmark.broadcast_environment_event(req.event_kind, req.params) if runtime.benchmark else runtime.world.inject_environment_event(req.event_kind, req.params)
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/optimizer/run")
async def run_optimizer(req: OptimizerRunReq):
    async with runtime.state_lock:
        w = runtime.active_world()
        res = w.run_optimizer(trigger_reason=req.reason, strategy_override=req.strategy)
        state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res.model_dump(), "state_version": w.state_version}


@app.get("/api/optimizer/history")
def get_optimizer_history():
    w = runtime.active_world()
    return [o.model_dump() for o in w.optimization_history[-30:]]


@app.post("/api/benchmarks/start")
async def start_benchmark():
    async with runtime.state_lock:
        base = SimulationWorld(
            seed=runtime.world.seed, scenario_id=runtime.world.city.scenario_id,
            scenario_name=runtime.world.city.scenario_name,
            city_density=runtime.world.city.city_density, building_density=runtime.world.city.building_density,
            journal=runtime.journal,
        )
        runtime.world = base
        runtime.benchmark = BenchmarkArena(base)
    await asyncio.to_thread(runtime.benchmark.start_all)
    payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/benchmarks/view")
async def switch_benchmark_view(req: ViewSwitchReq):
    if runtime.benchmark is None:
        runtime.world.strategy = req.strategy
    else:
        runtime.benchmark.active_view = req.strategy
    payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.get("/api/leaderboard")
def get_leaderboard(sort_by: str = Query(default="score")):
    raw = runtime.benchmark.get_leaderboard() if runtime.benchmark else [runtime.world.get_metrics()]
    total_tasks = len(runtime.active_world().tasks)
    return [m.model_dump() for m in sort_leaderboard(raw, sort_by=sort_by, total_tasks=total_tasks)]


@app.get("/api/config")
def get_config():
    return {
        "weights": {
            "w_rescue_time": CONFIG.weights.w_rescue_time,
            "w_energy": CONFIG.weights.w_energy,
            "w_risk": CONFIG.weights.w_risk,
            "w_deadline_violations": CONFIG.weights.w_deadline_violations,
            "w_uncompleted": CONFIG.weights.w_uncompleted,
        },
        "qaoa": {
            "qaoa_max_qubits": CONFIG.qaoa_max_qubits,
            "qaoa_layers": CONFIG.qaoa_layers,
            "qaoa_shots": CONFIG.qaoa_shots,
        },
    }


@app.post("/api/config")
def update_config(req: UpdateConfigReq):
    if req.w_rescue_time is not None: CONFIG.weights.w_rescue_time = req.w_rescue_time
    if req.w_energy is not None: CONFIG.weights.w_energy = req.w_energy
    if req.w_risk is not None: CONFIG.weights.w_risk = req.w_risk
    if req.w_deadline_violations is not None: CONFIG.weights.w_deadline_violations = req.w_deadline_violations
    if req.w_uncompleted is not None: CONFIG.weights.w_uncompleted = req.w_uncompleted
    if req.qaoa_max_qubits is not None: CONFIG.qaoa_max_qubits = req.qaoa_max_qubits
    if req.qaoa_layers is not None: CONFIG.qaoa_layers = req.qaoa_layers
    if req.qaoa_shots is not None: CONFIG.qaoa_shots = req.qaoa_shots
    return get_config()


# ── JSON-Only Experiments & Export Endpoints ──────────────────────────
@app.get("/api/experiments")
def list_experiments():
    return runtime.repo.list_experiments()


@app.post("/api/experiments/save")
def save_current_experiment():
    w = runtime.active_world()
    lb = runtime.benchmark.get_leaderboard() if runtime.benchmark else [w.get_metrics()]
    summary = build_summary_payload(w, lb)
    replay = build_replay_payload(w)
    runtime.repo.save_experiment(
        w.run_id, w.city.scenario_id, w.seed, w.strategy.value, w.status.value,
        w.sim_time_s, summary["metrics"]["score"], summary, replay,
        events=[e.model_dump() for e in w.events],
        drones=[d.model_dump() for d in w.drones.values()],
        tasks=[t.model_dump() for t in w.tasks.values()],
        optimizer=[o.model_dump() for o in w.optimization_history],
    )
    runtime.journal.save_world_snapshot(w.serialize_world())
    return {"saved": True, "storage": "json", "run_id": w.run_id}


@app.get("/api/experiments/current/export")
def export_current_experiment(fmt: str = Query(default="zip", pattern="^(zip|json)$")):
    w = runtime.active_world()
    lb = runtime.benchmark.get_leaderboard() if runtime.benchmark else [w.get_metrics()]
    if fmt == "json":
        return JSONResponse(build_summary_payload(w, lb))
    return Response(
        content=build_experiment_zip(w, lb),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="QUANTUM_RESCUE_{w.run_id}.zip"'},
    )


@app.get("/api/experiments/current/replay")
def get_current_replay():
    return build_replay_payload(runtime.active_world())


@app.get("/api/experiments/{run_id}")
def get_saved_experiment(run_id: str):
    exp = runtime.repo.get_experiment(run_id)
    if not exp:
        raise HTTPException(404, f"Experiment {run_id} not found")
    return exp


@app.get("/api/experiments/{run_id}/replay")
def get_saved_experiment_replay(run_id: str):
    exp = runtime.repo.get_experiment(run_id)
    if not exp:
        raise HTTPException(404, f"Experiment {run_id} not found")
    return exp["replay"]


@app.get("/api/logs/journal")
def get_event_journal(stream: str = Query(default="simulation"), limit: int = Query(default=200, ge=1, le=1000)):
    return {"stream": stream, "entries": runtime.journal.read_events(stream=stream, limit=limit)}


@app.websocket("/ws/simulation")
async def ws_simulation(ws: WebSocket):
    await runtime.ws_manager.connect(ws)
    try:
        await ws.send_json(runtime.current_payload(include_city=True))
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        runtime.ws_manager.disconnect(ws)
