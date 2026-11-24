from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
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
from app.world.global_models import DisasterType, GeoPoint, SimulationMode


class LoginReq(BaseModel):
    username: str
    password: str


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
    wind_kph: float = 65.0
    rainfall_mm_hr: float = 55.0
    require_approval: bool = False


class RouteExploreReq(BaseModel):
    country_id: str = "COUNTRY-03"
    drone_id: Optional[str] = None
    destination_lat: float
    destination_lon: float
    destination_label: str = "Target Location"
    objective: str = "BALANCED"
    payload_kg: float = 1.0
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
    message: str
    session_id: str = "default"


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

    # ---------------- Auth & RBAC ----------------
    @router.post("/auth/login")
    def login(req: LoginReq):
        res = auth_service.login(req.username, req.password)
        return {"token": res["token"], "session": to_dict(res["session"])}

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

    @router.post("/world/tick")
    def tick_world(dt_seconds: float = Query(default=60.0, ge=1.0, le=3600.0)):
        return {"clock": services.world.step(dt_seconds=dt_seconds), "totals": services.world.get_global_overview()["totals"]}

    @router.post("/world/emergency-stop")
    def emergency_stop(op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "admin:emergency_stop")
        services.world.emergency_stopped = True
        services.world.paused = True
        services.event_bus.emit("simulation.emergency_stop", payload={"actor": op.username}, category="safety")
        return {"emergency_stopped": True, "clock": services.world.get_clock_info()}

    @router.post("/world/emergency-resume")
    def emergency_resume(op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "admin:emergency_stop")
        services.world.emergency_stopped = False
        services.world.paused = False
        services.event_bus.emit("simulation.emergency_resume", payload={"actor": op.username}, category="safety")
        return {"emergency_stopped": False, "clock": services.world.get_clock_info()}

    @router.post("/world/mode/{mode}")
    def set_world_mode(mode: SimulationMode):
        services.world.mode = mode
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
        if country_id not in services.world.countries:
            raise HTTPException(status_code=404, detail="Country not found")
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
        return {"cities": [to_dict(c) for c in services.world.cities.values() if c.country_id == country_id]}

    @router.get("/countries/{country_id}/population")
    def get_country_population(country_id: str):
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
        if req.require_approval:
            return prepare_disaster(req)
        origin = GeoPoint(lat=req.lat, lon=req.lon) if (req.lat is not None and req.lon is not None) else None
        ev = services.world.inject_disaster(
            country_id=req.country_id,
            disaster_type=req.disaster_type,
            name=req.name,
            origin=origin,
            severity=req.severity,
            radius_km=req.radius_km,
            wind_kph=req.wind_kph,
            rainfall_mm_hr=req.rainfall_mm_hr,
        )
        return to_dict(ev)

    @router.post("/disasters/{event_id}/stop")
    def stop_disaster(event_id: str, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:disasters")
        if event_id not in services.world.disasters:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        services.world.disasters[event_id].status = "STOPPED"
        services.event_bus.emit("disaster.stopped", payload={"event_id": event_id}, entity_id=event_id, category="disaster")
        return to_dict(services.world.disasters[event_id])

    @router.get("/disasters/cascade/{country_id}")
    def get_cascade(country_id: str):
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
    def ambulance_requirements(country_id: str, window_hours: float = 4.0):
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
    def resource_shortages(country_id: str, horizon_hours: float = 24.0):
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
        if req.drone_id:
            return services.route_explorer.explore_routes_for_drone(
                drone_id=req.drone_id, destination=dest, objective=req.objective,
                k_candidates=req.k_candidates, payload_kg=req.payload_kg,
            )
        return services.route_explorer.compare_drones_to_destination(
            country_id=req.country_id, destination=dest, destination_label=req.destination_label,
            objective=req.objective, payload_kg=req.payload_kg, required_sensor=req.required_sensor,
        )

    @router.post("/routes/multistop")
    def multistop_routes(req: MultiStopReq):
        return services.route_explorer.plan_multistop_mission(
            country_id=req.country_id, points=req.points, sensor_type=req.sensor_type, objective=req.objective
        )

    @router.get("/routes/logs")
    def get_route_logs():
        return {"logs": services.route_explorer.route_logs[-100:]}

    # ---------------- Innovations: Counterfactual, Mutual Aid, Equity, Playbooks ----------------
    @router.post("/counterfactual/{country_id}")
    def run_counterfactual(country_id: str, what_if: Optional[Dict[str, Any]] = None):
        return services.world.run_counterfactual_comparison(country_id, what_if_params=what_if)

    @router.get("/mutual-aid/{country_id}")
    def get_mutual_aid(country_id: str, resource_type: str = "ambulances", quantity: int = 8):
        return services.world.find_mutual_aid_options(country_id, resource_type=resource_type, quantity=quantity)

    @router.post("/mutual-aid/prepare")
    def prepare_mutual_aid(req: MutualAidPrepareReq):
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
        return services.world.evaluate_rescue_equity(country_id)

    @router.get("/playbooks")
    def list_playbooks():
        return {"playbooks": PLAYBOOK_CATALOG}

    @router.post("/playbooks/{playbook_id}/adapt/{country_id}")
    def adapt_playbook(playbook_id: str, country_id: str):
        return services.approval_engine.generate_adapted_plan(country_id, playbook_id=playbook_id)

    # ---------------- JARVIS AI, Voice, Tools & Approvals ----------------
    @router.post("/ai/chat")
    async def jarvis_chat(req: JarvisChatReq):
        return await services.jarvis.process_command(req.message, session_id=req.session_id)

    @router.post("/ai/chat/stream")
    async def jarvis_chat_stream(req: JarvisChatReq):
        res = await services.jarvis.process_command(req.message, session_id=req.session_id)

        async def _gen():
            for chunk in res["assistant_message"].split(" "):
                yield f"data: {json.dumps({'type': 'token', 'text': chunk + ' '})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'payload': res})}\n\n"

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
        try:
            return services.jarvis.execute_tool_direct(tool_name, args or {})
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/ai/tools")
    def ai_tools():
        return {"tools": services.jarvis.registry, "count": len(services.jarvis.registry)}

    @router.get("/ai/conversations/{session_id}")
    def ai_conversation_history(session_id: str):
        return {"session_id": session_id, "messages": services.jarvis.conversations.get(session_id, [])}

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
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/approvals/{approval_id}/reject")
    def reject_op(approval_id: str, req: ApprovalDecisionReq = ApprovalDecisionReq(), op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:approvals")
        try:
            res = services.approval_engine.reject(approval_id, actor=op.username, reason=req.note or "Rejected by operator")
            return to_dict(res)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/approvals/{approval_id}/modify")
    def modify_op(approval_id: str, req: ApprovalModifyReq, op: OperatorSession = Depends(get_current_operator)):
        auth_service.check_permission(op, "write:approvals")
        try:
            res = services.approval_engine.modify_pending(approval_id, req.updates, actor=op.username)
            return to_dict(res)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---------------- Events, Logs, Frontend Command Bus & Global Export ----------------
    @router.get("/events")
    def get_events(limit: int = 100, category: Optional[str] = None, country_id: Optional[str] = None):
        return {
            "world_version": services.event_bus.world_version,
            "events": services.event_bus.get_events(limit=limit, category=category, country_id=country_id),
        }

    @router.get("/audit-logs")
    def get_audit_logs():
        return {"audit_log": services.approval_engine.audit_log[-200:], "tool_logs": services.jarvis.tool_logs[-200:]}

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

    return router
