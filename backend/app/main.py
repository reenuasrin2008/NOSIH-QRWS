from __future__ import annotations
import app.core.compat  # noqa: F401
import asyncio
import logging

logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.benchmark.runner import BenchmarkArena
from app.core.config import CONFIG, DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_NAME, DEFAULT_SEED
from app.benchmark.leaderboard import sort_leaderboard
from app.core.models import FailureType, SimulationStatus, StrategyType, TaskPriority
from app.database.repository import ExperimentRepository
from app.logging.export_manager import build_experiment_zip, build_replay_payload, build_summary_payload
from app.simulation.world import SimulationWorld
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


class WaypointReq(BaseModel):
    destination: Tuple[float, float, float]


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
        self.world: SimulationWorld = SimulationWorld(seed=DEFAULT_SEED)
        self.benchmark: Optional[BenchmarkArena] = None
        self.repo: ExperimentRepository = ExperimentRepository()
        self.ws_manager: ConnectionManager = ConnectionManager()
        self.tick_task: Optional[asyncio.Task] = None

    def active_world(self) -> SimulationWorld:
        return self.benchmark.worlds[self.benchmark.active_view] if self.benchmark is not None else self.world

    async def broadcast_state(self, include_city: bool = False) -> None:
        if self.ws_manager.active:
            await self.ws_manager.broadcast(self.current_payload(include_city=include_city))

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
        if runtime.benchmark is not None:
            if any(bw.status == SimulationStatus.RUNNING for bw in runtime.benchmark.worlds.values()):
                for _ in range(ticks):
                    runtime.benchmark.step_all(dt=1.0)
                advanced = True
        elif runtime.world.status == SimulationStatus.RUNNING:
            for _ in range(ticks):
                runtime.world.step(dt=1.0)
            advanced = True
        if advanced and runtime.ws_manager.active:
            await runtime.ws_manager.broadcast(runtime.current_payload(include_city=False))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.tick_task = asyncio.create_task(simulation_loop())
    global_tick_task = asyncio.create_task(global_simulation_loop())
    try:
        yield
    finally:
        if runtime.tick_task:
            runtime.tick_task.cancel()


app = FastAPI(title="QUANTUM RESCUE — 3D Autonomous Drone Simulation & Optimization API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"status": "ok", "run_id": runtime.active_world().run_id, "ws_clients": len(runtime.ws_manager.active)}


@app.post("/api/ui/sync")
async def ui_sync(req: UiSyncReq):
    """Relay UI/camera/selection/layer commands between Control Panel (:5174) and 3D Scene (:5173)."""
    msg = {"type": "ui_command", "action": req.action, "payload": req.payload}
    if runtime.ws_manager.active:
        await runtime.ws_manager.broadcast(msg)
    return {"ok": True, "relayed_to": len(runtime.ws_manager.active)}


@app.post("/api/scenarios/generate")
async def generate_scenario(req: GenerateScenarioReq):
    runtime.benchmark = None
    runtime.world = SimulationWorld(
        strategy=req.strategy, seed=req.seed, scenario_id=req.scenario_id,
        scenario_name=req.scenario_name, city_density=req.city_density, building_density=req.building_density,
    )
    payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.get("/api/scenarios")
def get_current_scenario():
    return runtime.current_payload(include_city=True)


@app.post("/api/simulation/start")
async def start_simulation():
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
    if runtime.benchmark is not None:
        runtime.benchmark.pause_all()
    else:
        runtime.world.status = SimulationStatus.PAUSED
    payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/resume")
async def resume_simulation():
    if runtime.benchmark is not None:
        runtime.benchmark.resume_all()
    else:
        runtime.world.status = SimulationStatus.RUNNING
    payload = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.post("/api/simulation/step")
async def step_simulation():
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
    seed, city = runtime.world.seed, runtime.world.city
    runtime.benchmark = None
    runtime.world = SimulationWorld(
        strategy=runtime.world.strategy, seed=seed, scenario_id=city.scenario_id,
        scenario_name=city.scenario_name, city_density=city.city_density, building_density=city.building_density,
    )
    payload = runtime.current_payload(include_city=True)
    await runtime.ws_manager.broadcast(payload)
    return payload


@app.get("/api/drones")
def list_drones():
    return [d.model_dump() for d in runtime.active_world().drones.values()]


@app.get("/api/drones/{drone_id}")
def get_drone(drone_id: str):
    d = runtime.active_world().drones.get(drone_id)
    if not d:
        raise HTTPException(404, f"Drone {drone_id} not found")
    return d.model_dump()


@app.post("/api/tasks")
async def create_task(req: CreateTaskReq):
    kwargs = req.model_dump()
    if runtime.benchmark is not None:
        created = runtime.benchmark.broadcast_task(**kwargs)
        state = runtime.current_payload(include_city=False)
        await runtime.ws_manager.broadcast(state)
        return {"created": created, "state": state}
    task = runtime.world.add_task(**kwargs)
    state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"created": task.id, "state": state}


@app.post("/api/drones/{drone_id}/waypoint")
async def set_drone_waypoint(drone_id: str, req: WaypointReq):
    res = runtime.active_world().set_drone_waypoint(drone_id, req.destination)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Infeasible waypoint"))
    state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/drones/{drone_id}/failure")
async def inject_drone_failure(drone_id: str, req: FailureReq):
    res = runtime.benchmark.inject_failure(drone_id, req.failure_type, scope=req.scope) if runtime.benchmark else runtime.world.inject_failure(drone_id, req.failure_type)
    state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/drones/{drone_id}/destroy")
def destroy_drone(drone_id: str, scope: str = Query(default="all")):
    res = runtime.benchmark.inject_failure(drone_id, FailureType.COMPLETE_DRONE_DESTRUCTION, scope=scope) if runtime.benchmark else runtime.world.inject_failure(drone_id, FailureType.COMPLETE_DRONE_DESTRUCTION)
    return {"result": res, "state": runtime.current_payload(include_city=False)}


@app.post("/api/drones/{drone_id}/rtb")
async def return_drone_to_base(drone_id: str):
    w = runtime.active_world()
    d = w.drones.get(drone_id)
    if not d:
        raise HTTPException(404, f"Drone {drone_id} not found")
    w._send_drone_to_charge(d, rtb_only=True)
    state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return state


@app.post("/api/environment/events")
async def inject_env_event(req: EnvEventReq):
    res = runtime.benchmark.broadcast_environment_event(req.event_kind, req.params) if runtime.benchmark else runtime.world.inject_environment_event(req.event_kind, req.params)
    state = runtime.current_payload(include_city=False)
    await runtime.ws_manager.broadcast(state)
    return {"result": res, "state": state}


@app.post("/api/benchmarks/start")
async def start_benchmark():
    base = SimulationWorld(
        seed=runtime.world.seed, scenario_id=runtime.world.city.scenario_id,
        scenario_name=runtime.world.city.scenario_name,
        city_density=runtime.world.city.city_density, building_density=runtime.world.city.building_density,
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


@app.get("/api/experiments")
def list_experiments():
    return runtime.repo.list_experiments()


@app.post("/api/experiments/save")
def save_current_experiment():
    w = runtime.active_world()
    lb = runtime.benchmark.get_leaderboard() if runtime.benchmark else [w.get_metrics()]
    summary = build_summary_payload(w, lb)
    runtime.repo.save_experiment(w.run_id, w.city.scenario_id, w.seed, w.strategy.value, w.status.value, w.sim_time_s, summary["metrics"]["score"], summary, build_replay_payload(w))
    return {"saved": True, "run_id": w.run_id}


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


@app.websocket("/ws/simulation")
async def ws_simulation(ws: WebSocket):
    await runtime.ws_manager.connect(ws)
    try:
        await ws.send_json(runtime.current_payload(include_city=True))
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        runtime.ws_manager.disconnect(ws)


# ==============================================================================
# QUANTUM RESCUE v2 — GLOBAL 7-COUNTRY LIVING WORLD, ROUTE INTELLIGENCE & JARVIS
# ==============================================================================
from app.api.global_routes import GlobalPlatformServices, build_global_router

global_services = GlobalPlatformServices()
global_ws_manager = ConnectionManager()


def _schedule_global_broadcast(msg: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
        if global_ws_manager.active:
            loop.create_task(global_ws_manager.broadcast(msg))
        if runtime.ws_manager.active and msg.get("type") == "frontend_command":
            loop.create_task(runtime.ws_manager.broadcast({
                "type": "ui_sync",
                "action": msg["command"]["command_type"],
                "payload": msg["command"],
            }))
    except RuntimeError as exc:
        logger.debug("No running event loop for broadcast: %s", exc)


global_services.event_bus.subscribe(_schedule_global_broadcast)
app.include_router(
    build_global_router(
        global_services,
        get_legacy_summary=lambda: build_summary_payload(runtime.active_world()),
    )
)


@app.websocket("/ws/global")
async def ws_global(ws: WebSocket, client: str = Query(default="quantum-world")):
    await global_ws_manager.connect(ws)
    global_services.event_bus.register_frontend(client)
    try:
        await ws.send_json({
            "type": "global_snapshot",
            "overview": global_services.world.get_global_overview(),
            "approvals": global_services.approval_engine.list_approvals(),
            "providers": global_services.provider_manager.get_status(),
        })
        while True:
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        global_ws_manager.disconnect(ws)
        global_services.event_bus.unregister_frontend(client)


async def global_simulation_loop():
    """Continuous real-time background physics & living-world tick broadcaster."""
    while True:
        await asyncio.sleep(2.5)
        if not global_services.world.paused and not global_services.world.emergency_stopped:
            global_services.world.step(dt_seconds=15.0)
            if global_ws_manager.active:
                await global_ws_manager.broadcast({
                    "type": "global_snapshot",
                    "overview": global_services.world.get_global_overview(),
                    "approvals": global_services.approval_engine.list_approvals(),
                    "providers": global_services.provider_manager.get_status(),
                })
