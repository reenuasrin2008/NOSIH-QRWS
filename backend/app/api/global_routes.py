from __future__ import annotations
import json
import math
import sys
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import PLAYBOOK_CATALOG, ApprovalEngine
from app.auth.rbac import OperatorSession, auth_service, get_current_operator
from app.core.compat import to_dict
from app.database.repository import ExperimentRepository
from app.events.bus import AuthoritativeEventBus
from app.exports.global_export import build_global_experiment_zip, build_global_geojson
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import DisasterType, GeoPoint, SimulationMode, SwarmFormation, SwarmMode


APP_START_TIME = time.time()


class ResetSnapshotsReq(BaseModel):
    confirm: str


class CountryPatchReq(BaseModel):
    name: Optional[str] = None
    flag_code: Optional[str] = None
    terrain_profile: Optional[str] = None
    population_scale: Optional[int] = None
    climate_zone: Optional[str] = None


class DisasterCreateReq(BaseModel):
    country_id: str = "COUNTRY-03"
    disaster_type: DisasterType = DisasterType.FLOOD
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    severity: float = Field(default=0.75, ge=0.1, le=1.0)
    radius_km: float = Field(default=10.0, ge=1.0, le=50.0)
    wind_kph: float = Field(default=65.0, ge=0.0, le=500.0)
    rainfall_mm_hr: float = Field(default=55.0, ge=0.0, le=1000.0)


class RouteExploreReq(BaseModel):
    country_id: str = "COUNTRY-03"
    drone_id: Optional[str] = None
    destination_lat: float = Field(ge=-90.0, le=90.0)
    destination_lon: float = Field(ge=-180.0, le=180.0)
    destination_label: str = Field(default="Target Location", max_length=200)
    objective: str = "BALANCED"
    payload_kg: float = Field(default=1.0, ge=0.0, le=50.0)
    required_sensor: Optional[str] = None
    k_candidates: int = Field(default=4, ge=1, le=8)


class MultiStopReq(BaseModel):
    country_id: str = "COUNTRY-03"
    points: List[GeoPoint]
    sensor_type: str = "thermal"
    objective: str = "LOWEST_ENERGY"


class SwarmPrepareReq(BaseModel):
    country_id: str = "COUNTRY-03"
    drone_count: int = Field(default=8, ge=1, le=30)
    mode: str = "AREA_SCAN"
    formation: str = "SEARCH_GRID"
    objective: str = "Coordinated disaster scan"


class MutualAidPrepareReq(BaseModel):
    target_country_id: str = "COUNTRY-03"
    donor_country_id: str = "COUNTRY-05"
    resource_type: str = "ambulances"
    quantity: int = Field(default=6, ge=1, le=50)


class JarvisChatReq(BaseModel):
    message: str = Field(max_length=20000)
    session_id: str = Field(default="default", max_length=128)
    use_llm_polish: bool = False


class ApprovalDecisionReq(BaseModel):
    note: str = ""
    auto_execute: bool = True


class ApprovalModifyReq(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)


class FrontendAckReq(BaseModel):
    command_id: str
    frontend: str


class GlobalPlatformServices:
    def __init__(self) -> None:
        self.event_bus = AuthoritativeEventBus()
        self.world = GlobalWorldEngine(self.event_bus)
        self.route_explorer = AdvancedRouteExplorer(self.world)
        self.approval_engine = ApprovalEngine(self.world)
        self.provider_manager = AIProviderManager()
        self.jarvis = JarvisAgent(
            world=self.world,
            route_explorer=self.route_explorer,
            approval_engine=self.approval_engine,
            provider_manager=self.provider_manager,
        )


def build_global_router(services: GlobalPlatformServices, get_legacy_summary) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["quantum-rescue-global"])

    def _require_country(country_id: str) -> str:
        if country_id not in services.world.countries:
            raise HTTPException(status_code=404, detail=f"Unknown country_id: {country_id}")
        return country_id

    def _approval_http_error(exc: ValueError) -> HTTPException:
        msg = str(exc)
        status_code = 404 if "Unknown approval_id" in msg else 400
        return HTTPException(status_code=status_code, detail=msg)

    # ---------------- Auth & RBAC ----------------
    @router.get("/auth/me")
    def auth_me(op: OperatorSession = Depends(get_current_operator)):
        return to_dict(op)

    # ---------------- World & Countries ----------------
    @router.get("/world")
    @router.get("/world/overview")
    def get_world_overview():
        return services.world.get_global_overview()

    @router.get("/world/live-entities/{country_id}")
    def get_live_entities(country_id: str):
        try:
            return services.world.get_live_entities(country_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/world/save-local")
    def save_world_local():
        repo = ExperimentRepository()
        path = repo.save_local_world_snapshot(services.world.get_global_overview())
        return {"saved": True, "storage": "local_json", "path": path}

    @router.post("/world/reset-local-snapshots")
    def reset_local_snapshots(req: ResetSnapshotsReq, op: OperatorSession = Depends(get_current_operator)):
        if req.confirm != "RESET_SNAPSHOTS":
            raise HTTPException(status_code=400, detail="Confirmation must be RESET_SNAPSHOTS")
        auth_service.check_permission(op, "admin:reset")
        repo = ExperimentRepository()
        removed = repo.reset_local_snapshots()
        fresh_world = GlobalWorldEngine(services.event_bus)
        services.world = fresh_world
        services.route_explorer = AdvancedRouteExplorer(fresh_world)
        services.approval_engine = ApprovalEngine(fresh_world)
        services.jarvis = JarvisAgent(
            world=fresh_world,
            route_explorer=services.route_explorer,
            approval_engine=services.approval_engine,
            provider_manager=services.provider_manager,
        )
        services.event_bus.emit(
            "world.reset_local_snapshots",
            payload={"removed_files": removed, "seed": fresh_world.seed},
            category="world",
        )
        return {
            "reset": True,
            "removed_files": removed,
            "seed": fresh_world.seed,
            "world_version": services.event_bus.world_version,
        }

    @router.post("/world/tick")
    def tick_world(dt_seconds: float = Query(default=60.0, ge=1.0, le=3600.0), op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "execute:operations")
        return {"clock": services.world.step(dt_seconds=dt_seconds), "totals": services.world.get_global_overview()["totals"]}

    @router.post("/world/emergency-stop")
    def emergency_stop(op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "admin:emergency_stop")
        with services.world._mutation_lock:
            services.world.emergency_stopped = True
            services.world.paused = True
        services.event_bus.emit("simulation.emergency_stop", payload={"actor": op.username}, category="safety")
        return {"emergency_stopped": True, "clock": services.world.get_clock_info()}

    @router.post("/world/emergency-resume")
    def emergency_resume(op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "admin:emergency_stop")
        with services.world._mutation_lock:
            services.world.emergency_stopped = False
            services.world.paused = False
        services.event_bus.emit("simulation.emergency_resume", payload={"actor": op.username}, category="safety")
        return {"emergency_stopped": False, "clock": services.world.get_clock_info()}

    @router.post("/world/mode/{mode}")
    def set_world_mode(mode: SimulationMode, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "execute:operations")
        with services.world._mutation_lock:
            services.world.mode = mode
        services.event_bus.emit("world.mode_changed", payload={"mode": mode.value}, category="world")
        return {"mode": mode.value, "clock": services.world.get_clock_info()}

    @router.get("/countries")
    def list_countries():
        return {"countries": services.world.get_global_overview()["countries"]}

    @router.get("/countries/{country_id}")
    def get_country(country_id: str):
        try:
            return services.world.get_country_detail(country_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/countries/{country_id}")
    def update_country(country_id: str, req: CountryPatchReq, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:countries")
        _require_country(country_id)
        with services.world._mutation_lock:
            c = services.world.countries[country_id]
            if req.name:
                c.name = req.name
            if req.flag_code:
                c.flag_code = req.flag_code
            if req.terrain_profile:
                c.terrain_profile = req.terrain_profile
            if req.population_scale:
                c.population_scale = req.population_scale
            if req.climate_zone:
                c.climate_zone = req.climate_zone
        services.event_bus.emit("country.updated", payload=to_dict(c), country_id=country_id, category="world")
        return to_dict(c)

    @router.get("/countries/{country_id}/cities")
    def get_country_cities(country_id: str):
        _require_country(country_id)
        return {"cities": [to_dict(c) for c in services.world.cities.values() if c.country_id == country_id]}

    @router.get("/countries/{country_id}/population")
    def get_country_population(country_id: str):
        _require_country(country_id)
        dists = [to_dict(d) for d in services.world.districts.values() if d.country_id == country_id]
        hhs = [to_dict(h) for h in services.world.households.values() if h.country_id == country_id]
        people = [to_dict(p) for p in services.world.people.values() if p.country_id == country_id]
        animals = [to_dict(a) for a in services.world.animals.values() if a.country_id == country_id]
        return {"country_id": country_id, "districts": dists, "sample_households": hhs, "sample_people": people, "animals": animals}

    # ---------------- Disasters & Cascades ----------------
    @router.get("/disasters")
    def list_disasters(country_id: Optional[str] = None):
        evs = [to_dict(d) for d in services.world.disasters.values() if not country_id or d.country_id == country_id]
        return {"disasters": evs}

    @router.post("/disasters/prepare")
    def prepare_disaster(req: DisasterCreateReq):
        _require_country(req.country_id)
        apr = services.approval_engine.create_approval_request(
            operation_type="inject_disaster",
            title=req.name or f"Inject {req.disaster_type.value} in {req.country_id}",
            description=f"Severity {int(req.severity * 100)}%, radius {req.radius_km} km",
            country_id=req.country_id,
            parameters=to_dict(req),
        )
        return to_dict(apr)

    @router.post("/disasters")
    def create_disaster(req: DisasterCreateReq, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:disasters")
        _require_country(req.country_id)
        return prepare_disaster(req)

    @router.post("/disasters/{event_id}/stop")
    def stop_disaster(event_id: str, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:disasters")
        with services.world._mutation_lock:
            if event_id not in services.world.disasters:
                raise HTTPException(status_code=404, detail="Disaster event not found")
            services.world.disasters[event_id].status = "STOPPED"
            services.event_bus.emit("disaster.stopped", payload={"event_id": event_id}, entity_id=event_id, category="disaster")
            return to_dict(services.world.disasters[event_id])

    @router.get("/disasters/cascade/{country_id}")
    def get_cascade(country_id: str):
        _require_country(country_id)
        return services.world.get_cascade_graph(country_id)

    # ---------------- Facilities, Medical, Logistics ----------------
    @router.get("/hospitals")
    def list_hospitals(country_id: Optional[str] = None):
        items = [
            {**to_dict(h), "available_beds": h.available_beds}
            for h in services.world.hospitals.values()
            if not country_id or h.country_id == country_id
        ]
        return {"hospitals": items}

    @router.get("/fire-units")
    def list_fire_units(country_id: Optional[str] = None):
        items = [to_dict(f) for f in services.world.fire_units.values() if not country_id or f.country_id == country_id]
        return {"fire_units": items}

    @router.get("/ambulances")
    def list_ambulances(country_id: Optional[str] = None):
        items = [to_dict(a) for a in services.world.ambulances.values() if not country_id or a.country_id == country_id]
        return {"ambulances": items}

    @router.get("/ambulances/requirements/{country_id}")
    def ambulance_requirements(country_id: str, window_hours: float = Query(default=4.0, gt=0.0, le=168.0)):
        _require_country(country_id)
        return services.world.calculate_ambulance_requirements(country_id, planning_window_hours=window_hours)

    @router.get("/shelters")
    def list_shelters(country_id: Optional[str] = None):
        items = [
            {**to_dict(s), "remaining_capacity": s.remaining_capacity}
            for s in services.world.shelters.values()
            if not country_id or s.country_id == country_id
        ]
        return {"shelters": items}

    @router.get("/inventory")
    def list_inventory(country_id: Optional[str] = None):
        items = [to_dict(w) for w in services.world.warehouses.values() if not country_id or w.country_id == country_id]
        return {"warehouses": items}

    @router.get("/resources/shortages/{country_id}")
    def resource_shortages(country_id: str, horizon_hours: float = Query(default=24.0, gt=0.0, le=720.0)):
        _require_country(country_id)
        return services.world.calculate_resource_requirements(country_id, horizon_hours=horizon_hours)

    # ---------------- Global Drones, Swarms & Route Intelligence ----------------
    @router.get("/global/drones")
    def list_global_drones(country_id: Optional[str] = None):
        items = [to_dict(d) for d in services.world.drones.values() if not country_id or d.country_id == country_id]
        return {"drones": items, "count": len(items)}

    @router.post("/global/drones/{drone_id}/destroy/prepare")
    def prepare_global_drone_destroy(drone_id: str):
        if drone_id not in services.world.drones:
            raise HTTPException(status_code=404, detail="Drone not found")
        apr = services.approval_engine.create_approval_request(
            operation_type="destroy_drone",
            title=f"Simulate Destruction of {drone_id}",
            description="Virtual drone failure injection with automatic swarm recovery.",
            country_id=services.world.drones[drone_id].country_id,
            parameters={"drone_id": drone_id, "failure_type": "COMPLETE_DRONE_DESTRUCTION"},
            affected_entities=[drone_id],
        )
        return to_dict(apr)

    @router.get("/swarms")
    def list_swarms(country_id: Optional[str] = None):
        items = [to_dict(s) for s in services.world.swarms.values() if not country_id or s.country_id == country_id]
        return {"swarms": items}

    @router.post("/swarms/prepare")
    def prepare_swarm(req: SwarmPrepareReq):
        _require_country(req.country_id)
        try:
            SwarmMode(req.mode)
            SwarmFormation(req.formation)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        apr = services.approval_engine.create_approval_request(
            operation_type="deploy_swarm",
            title=f"Deploy {req.drone_count}-Drone {req.mode} Swarm ({req.country_id})",
            description=f"Formation: {req.formation}. Objective: {req.objective}",
            country_id=req.country_id,
            parameters=to_dict(req),
            required_resources={"drones": req.drone_count},
        )
        return to_dict(apr)

    @router.post("/routes/explore")
    def explore_routes(req: RouteExploreReq):
        dest = GeoPoint(lat=req.destination_lat, lon=req.destination_lon, elevation_m=90.0)
        try:
            if req.drone_id:
                return services.route_explorer.explore_routes_for_drone(
                    drone_id=req.drone_id, destination=dest, objective=req.objective,
                    k_candidates=req.k_candidates, payload_kg=req.payload_kg,
                )
            _require_country(req.country_id)
            return services.route_explorer.compare_drones_to_destination(
                country_id=req.country_id, destination=dest, destination_label=req.destination_label,
                objective=req.objective, payload_kg=req.payload_kg, required_sensor=req.required_sensor,
            )
        except ValueError as e:
            status_code = 404 if "Unknown drone_id" in str(e) else 400
            raise HTTPException(status_code=status_code, detail=str(e))

    @router.post("/routes/multistop")
    def multistop_routes(req: MultiStopReq):
        _require_country(req.country_id)
        if not req.points:
            raise HTTPException(status_code=400, detail="At least one waypoint is required")
        if len(req.points) > 50:
            raise HTTPException(status_code=422, detail="points must contain no more than 50 waypoints")
        try:
            return services.route_explorer.plan_multistop_mission(
                country_id=req.country_id, points=req.points, sensor_type=req.sensor_type, objective=req.objective
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/routes/logs")
    def get_route_logs():
        return {"logs": list(services.route_explorer.route_logs)[-100:]}

    # ---------------- Innovations: Counterfactual, Mutual Aid, Equity, Playbooks ----------------
    @router.post("/counterfactual/{country_id}")
    def run_counterfactual(country_id: str, what_if: Optional[Dict[str, Any]] = None):
        _require_country(country_id)
        try:
            return services.world.run_counterfactual_comparison(country_id, what_if_params=what_if)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/mutual-aid/{country_id}")
    def get_mutual_aid(country_id: str, resource_type: str = "ambulances", quantity: int = Query(default=8, ge=1, le=500)):
        _require_country(country_id)
        try:
            return services.world.find_mutual_aid_options(country_id, resource_type=resource_type, quantity=quantity)
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/mutual-aid/prepare")
    def prepare_mutual_aid(req: MutualAidPrepareReq):
        _require_country(req.target_country_id)
        _require_country(req.donor_country_id)
        apr = services.approval_engine.create_approval_request(
            operation_type="cross_country_aid",
            title=f"Mutual Aid Transfer: {req.quantity} {req.resource_type} ({req.donor_country_id} -> {req.target_country_id})",
            description="Seven-Country Mutual Aid Network transfer proposal.",
            country_id=req.target_country_id,
            parameters=to_dict(req),
            required_resources={req.resource_type: req.quantity},
        )
        return to_dict(apr)

    @router.get("/equity/{country_id}")
    def get_equity(country_id: str):
        _require_country(country_id)
        return services.world.evaluate_rescue_equity(country_id)

    @router.get("/playbooks")
    def list_playbooks():
        return {"playbooks": PLAYBOOK_CATALOG}

    @router.post("/playbooks/{playbook_id}/adapt/{country_id}")
    def adapt_playbook(playbook_id: str, country_id: str):
        _require_country(country_id)
        try:
            return services.approval_engine.generate_adapted_plan(country_id, playbook_id=playbook_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---------------- JARVIS AI, Voice, Tools & Approvals ----------------
    @router.post("/ai/chat")
    async def jarvis_chat(req: JarvisChatReq, op: OperatorSession = Depends(get_current_operator)):
        reply = await services.jarvis.process_command(
            req.message,
            session_id=f"{op.username}:{req.session_id}",
            use_llm_polish=req.use_llm_polish,
        )
        reply["session_id"] = req.session_id
        return reply

    @router.post("/ai/chat/stream")
    async def jarvis_chat_stream(req: JarvisChatReq, op: OperatorSession = Depends(get_current_operator)):
        async def _gen():
            try:
                res = await services.jarvis.process_command(
                    req.message,
                    session_id=f"{op.username}:{req.session_id}",
                    use_llm_polish=req.use_llm_polish,
                )
                res["session_id"] = req.session_id
                text = str(res.get("assistant_message") or "")
                if text:
                    for chunk in text.split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk + ' '}, default=str)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'payload': res}, default=str)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, default=str)}\n\n"

        return StreamingResponse(_gen(), media_type="text/event-stream")

    @router.post("/ai/voice/synthesize")
    def voice_synthesize(payload: Dict[str, Any]):
        text = str(payload.get("text", "")).strip()
        clean = text.replace("\n", ". ").replace("•", "")
        return {"status": "ok", "engine": "browser_web_speech_tts", "spoken_text": clean[:400]}

    @router.post("/ai/voice/transcribe")
    def voice_transcribe(payload: Dict[str, Any]):
        transcript = str(payload.get("transcript", "")).strip()
        return {"status": "ok", "engine": "browser_web_speech_stt", "transcript": transcript}

    @router.get("/ai/providers/status")
    def ai_providers_status():
        return services.provider_manager.get_status()

    @router.post("/ai/tools/{tool_name}")
    def execute_ai_tool(tool_name: str, args: Optional[Dict[str, Any]] = None):
        out = services.jarvis.execute_tool_direct(tool_name, args or {})
        if out.get("status") == "ERROR":
            return JSONResponse(status_code=422, content=out)
        return out

    @router.get("/ai/tools/schemas")
    def ai_tool_schemas():
        schemas = services.jarvis.get_tool_schemas()
        return {
            "count": len(schemas),
            "schemas": schemas,
            "provider_payloads": services.provider_manager.build_provider_tool_payload(schemas),
        }

    @router.get("/ai/tools")
    def ai_tools():
        return {"tools": services.jarvis.registry, "count": len(services.jarvis.registry)}

    @router.get("/ai/conversations/{session_id}")
    def ai_conversation_history(session_id: str, op: OperatorSession = Depends(get_current_operator)):
        return {"session_id": session_id, "messages": list(services.jarvis.conversations.get(f"{op.username}:{session_id}", []))}

    @router.get("/approvals")
    def list_approvals(status: Optional[str] = None):
        return {"approvals": services.approval_engine.list_approvals(status=status)}

    @router.post("/approvals/{approval_id}/approve")
    def approve_op(approval_id: str, req: ApprovalDecisionReq = ApprovalDecisionReq(), op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:approvals")
        try:
            res = services.approval_engine.approve_and_execute(approval_id, actor=op.username, auto_execute=req.auto_execute)
            return to_dict(res)
        except ValueError as e:
            raise _approval_http_error(e)

    @router.post("/approvals/{approval_id}/reject")
    def reject_op(approval_id: str, req: ApprovalDecisionReq = ApprovalDecisionReq(), op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:approvals")
        try:
            res = services.approval_engine.reject(approval_id, actor=op.username, reason=req.note or "Rejected by operator")
            return to_dict(res)
        except ValueError as e:
            raise _approval_http_error(e)

    @router.post("/approvals/{approval_id}/modify")
    def modify_op(approval_id: str, req: ApprovalModifyReq, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:approvals")
        try:
            res = services.approval_engine.modify_pending(approval_id, req.updates, actor=op.username)
            return to_dict(res)
        except ValueError as e:
            raise _approval_http_error(e)

    # ---------------- Events, Logs, Frontend Command Bus & Global Export ----------------
    @router.get("/events")
    def get_events(limit: int = Query(default=100, ge=1, le=1000), category: Optional[str] = None, country_id: Optional[str] = None):
        return {
            "world_version": services.event_bus.world_version,
            "events": services.event_bus.get_events(limit=limit, category=category, country_id=country_id),
        }

    @router.get("/audit-logs")
    def get_audit_logs():
        return {"audit_log": list(services.approval_engine.audit_log)[-200:], "tool_logs": list(services.jarvis.tool_logs)[-200:]}

    @router.get("/frontend/commands")
    def get_frontend_commands():
        return {"commands": services.event_bus.get_commands(), "frontends": services.event_bus.frontend_status()}

    @router.post("/frontend/commands/ack")
    def ack_frontend_command(req: FrontendAckReq):
        cmd = services.event_bus.acknowledge_command(req.command_id, req.frontend)
        return {"acknowledged": cmd is not None, "command": to_dict(cmd) if cmd else None}

    @router.get("/global/export/geojson")
    def export_geojson():
        return build_global_geojson(services.world)

    @router.get("/global/export/zip")
    def export_global_zip():
        data = build_global_experiment_zip(
            world=services.world,
            route_explorer=services.route_explorer,
            approval_engine=services.approval_engine,
            jarvis=services.jarvis,
            legacy_summary=get_legacy_summary(),
        )
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="quantum-rescue-global-{services.world.scenario_id}.zip"'},
        )


    # ---------------- Observability, Replay & Deterministic Reseed ----------------
    def _percentile(sorted_vals: List[float], pct: float) -> float:
        if not sorted_vals:
            return 0.0
        if len(sorted_vals) == 1:
            return round(sorted_vals[0], 2)
        k = (len(sorted_vals) - 1) * (pct / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_vals[int(k)], 2)
        return round(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f), 2)

    @router.get("/health")
    def get_health():
        return {
            "status": "ok",
            "world_version": services.event_bus.world_version,
            "uptime_seconds": round(time.time() - APP_START_TIME, 2),
            "tool_count": services.jarvis.tool_count,
            "seed": services.world.seed,
            "invariants": {
                "approval_gated": True,
                "zero_database": True,
                "tool_count": services.jarvis.tool_count,
            },
        }

    @router.get("/metrics", response_class=PlainTextResponse)
    def get_metrics():
        tool_logs = list(services.jarvis.tool_logs)
        tool_calls_total = len(tool_logs)
        tool_errors_total = sum(1 for entry in tool_logs if entry.get("status") == "ERROR")
        sessions_active = len(services.jarvis.conversations)
        disasters_active = sum(1 for d in services.world.disasters.values() if d.status == "ACTIVE")
        approvals_pending = sum(1 for a in services.approval_engine.approvals.values() if a.status == "PENDING")
        world_ver = services.event_bus.world_version
        lines = [
            "# HELP jarvis_tool_calls_total Total number of JARVIS tool invocations recorded.",
            "# TYPE jarvis_tool_calls_total counter",
            f"jarvis_tool_calls_total {tool_calls_total}",
            "# HELP jarvis_sessions_active Number of active JARVIS conversation sessions.",
            "# TYPE jarvis_sessions_active gauge",
            f"jarvis_sessions_active {sessions_active}",
            "# HELP jarvis_tool_errors_total Total number of JARVIS tool invocation errors recorded.",
            "# TYPE jarvis_tool_errors_total counter",
            f"jarvis_tool_errors_total {tool_errors_total}",
            "# HELP world_disasters_active Number of currently active disasters in the world simulation.",
            "# TYPE world_disasters_active gauge",
            f"world_disasters_active {disasters_active}",
            "# HELP world_approvals_pending Number of pending operator approval requests.",
            "# TYPE world_approvals_pending gauge",
            f"world_approvals_pending {approvals_pending}",
            "# HELP world_version Current authoritative world event bus version.",
            "# TYPE world_version gauge",
            f"world_version {world_ver}",
            "",
        ]
        return PlainTextResponse(content="\n".join(lines), media_type="text/plain; version=0.0.4; charset=utf-8")

    @router.get("/ai/latency")
    def get_ai_latency():
        latencies: List[float] = []
        for msgs in services.jarvis.conversations.values():
            for msg in msgs:
                val = msg.get("latency_ms") if isinstance(msg, dict) else None
                if isinstance(val, (int, float)) and math.isfinite(val):
                    latencies.append(float(val))
        if not latencies:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
        latencies.sort()
        return {
            "count": len(latencies),
            "p50_ms": _percentile(latencies, 50.0),
            "p95_ms": _percentile(latencies, 95.0),
            "p99_ms": _percentile(latencies, 99.0),
            "max_ms": round(latencies[-1], 2),
        }

    @router.get("/world/replay")
    def replay_world_events(
        from_version: int = Query(default=0, ge=0),
        to_version: Optional[int] = Query(default=None, ge=0),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        matched: List[Dict[str, Any]] = []
        for ev in list(services.event_bus._events):
            if ev.world_version < from_version:
                continue
            if to_version is not None and ev.world_version > to_version:
                continue
            matched.append(to_dict(ev))
            if len(matched) >= limit:
                break
        return {
            "seed": services.world.seed,
            "world_version": services.event_bus.world_version,
            "from_version": from_version,
            "to_version": to_version,
            "count": len(matched),
            "events": matched,
        }

    @router.post("/world/reseed")
    def reseed_world(seed: int = Query(default=42, ge=1, le=2147483647), op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "admin:reset")
        with services.world._mutation_lock:
            services.world.reset_to_seed(seed)
            services.jarvis._country_lookup = services.jarvis._build_country_lookup()
            services.event_bus.emit(
                "world.reseeded",
                payload={"seed": seed},
                source="global_world_engine",
                category="world",
                bump_version=True,
            )
            return {
                "reseeded": True,
                "seed": seed,
                "world_version": services.event_bus.world_version,
            }

    # Ensure /api/health from this router supersedes any legacy /api/health registered on app.main
    main_mod = sys.modules.get("app.main")
    main_app = getattr(main_mod, "app", None)
    if main_app is not None and hasattr(main_app, "router") and hasattr(main_app.router, "routes"):
        main_app.router.routes[:] = [
            r for r in main_app.router.routes if getattr(r, "path", None) != "/api/health"
        ]

    return router
