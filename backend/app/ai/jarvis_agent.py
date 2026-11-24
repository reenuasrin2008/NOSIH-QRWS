from __future__ import annotations
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.approvals.engine import PLAYBOOK_CATALOG, ApprovalEngine
from app.core.compat import to_dict, utc_now_iso
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import DisasterType, GeoPoint


class SessionContext:
    """Structured operational context service (tracks active country, hospital, drone, and pending approval)."""

    def __init__(self, default_country: str = "COUNTRY-03") -> None:
        self.active_country_id: str = default_country
        self.active_city_id: Optional[str] = None
        self.active_district_id: Optional[str] = None
        self.selected_hospital_id: Optional[str] = None
        self.selected_drone_id: Optional[str] = None
        self.selected_disaster_id: Optional[str] = None
        self.pending_approval_id: Optional[str] = None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active_country_id": self.active_country_id,
            "active_city_id": self.active_city_id,
            "active_district_id": self.active_district_id,
            "selected_hospital_id": self.selected_hospital_id,
            "selected_drone_id": self.selected_drone_id,
            "selected_disaster_id": self.selected_disaster_id,
            "pending_approval_id": self.pending_approval_id,
        }


class JarvisAgent:
    """Fast Universal Command Orchestrator with 100% wired callable tool handlers."""

    def __init__(
        self,
        world: GlobalWorldEngine,
        route_explorer: AdvancedRouteExplorer,
        approval_engine: ApprovalEngine,
        provider_manager: AIProviderManager,
    ) -> None:
        self.world = world
        self.route_explorer = route_explorer
        self.approval_engine = approval_engine
        self.provider_manager = provider_manager
        self.sessions: Dict[str, SessionContext] = {}
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.tool_logs: List[Dict[str, Any]] = []
        self._tool_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = self._build_tool_handlers()
        self.registry: Dict[str, Dict[str, Any]] = self._build_tool_registry()

    def _get_session(self, session_id: str) -> SessionContext:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionContext(default_country=self.world.selected_country_id)
        return self.sessions[session_id]

    def _build_tool_handlers(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        """Every registered JARVIS tool maps directly to a real, fast backend execution handler."""
        def _cid(args: Dict[str, Any]) -> str:
            return args.get("country_id") or self.world.selected_country_id

        return {
            # Navigation & World Camera
            "view_global_world": lambda a: to_dict(
                self.world.event_bus.dispatch_frontend_command("camera.focus_world", frontend="quantum-world")
            ),
            "view_country": lambda a: to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_country", target_id=_cid(a), frontend="quantum-world",
                    parameters={"transition": "smooth", "show_boundary": True, "show_city_markers": True},
                )
            ),
            "focus_hospital": lambda a: to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_hospital", target_id=a.get("hospital_id"), frontend="quantum-world"
                )
            ),
            "focus_drone": lambda a: to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.focus_drone", target_id=a.get("drone_id"), frontend="quantum-world"
                )
            ),
            # Global & Country Data
            "get_global_world_overview": lambda a: self.world.get_global_overview(),
            "get_country_list": lambda a: {"countries": self.world.get_global_overview()["countries"]},
            "get_country_status": lambda a: self.world.get_country_detail(_cid(a)),
            "get_population_summary": lambda a: {
                "country_id": _cid(a),
                "districts": [to_dict(d) for d in self.world.districts.values() if d.country_id == _cid(a)],
                "households_count": sum(1 for h in self.world.households.values() if h.country_id == _cid(a)),
                "sample_people": [to_dict(p) for p in self.world.people.values() if p.country_id == _cid(a)][:15],
            },
            "get_animal_population": lambda a: {
                "country_id": _cid(a),
                "animals": [to_dict(x) for x in self.world.animals.values() if x.country_id == _cid(a)],
            },
            # Disasters & Cascades
            "get_active_disasters": lambda a: {
                "disasters": [to_dict(d) for d in self.world.disasters.values() if d.status == "ACTIVE"]
            },
            "get_cascade_graph": lambda a: self.world.get_cascade_graph(_cid(a)),
            "analyze_disaster": lambda a: self.world.get_country_detail(_cid(a)),
            # Medical & Logistics
            "get_hospital_status": lambda a: {
                "country_id": _cid(a),
                "hospitals": [
                    {**to_dict(h), "available_beds": h.available_beds}
                    for h in self.world.hospitals.values()
                    if h.country_id == _cid(a)
                ],
            },
            "get_ambulance_fleet": lambda a: {
                "country_id": _cid(a),
                "ambulances": [to_dict(x) for x in self.world.ambulances.values() if x.country_id == _cid(a)],
            },
            "calculate_ambulance_requirements": lambda a: self.world.calculate_ambulance_requirements(
                _cid(a), planning_window_hours=float(a.get("window_hours", 4.0))
            ),
            "get_shelter_capacity": lambda a: {
                "country_id": _cid(a),
                "shelters": [
                    {**to_dict(s), "remaining_capacity": s.remaining_capacity}
                    for s in self.world.shelters.values()
                    if s.country_id == _cid(a)
                ],
            },
            "calculate_resource_requirements": lambda a: self.world.calculate_resource_requirements(
                _cid(a), horizon_hours=float(a.get("horizon_hours", 24.0))
            ),
            # Drones, Swarms & Route Intelligence
            "get_drone_fleet": lambda a: {
                "country_id": _cid(a),
                "drones": [to_dict(d) for d in self.world.drones.values() if d.country_id == _cid(a)],
            },
            "get_low_battery_drones": lambda a: {
                "threshold_pct": float(a.get("threshold", 35.0)),
                "drones": [
                    to_dict(d) for d in self.world.drones.values()
                    if d.battery_pct < float(a.get("threshold", 35.0))
                ],
            },
            "get_swarm_status": lambda a: {"swarms": [to_dict(s) for s in self.world.swarms.values()]},
            "compare_drones_to_destination": lambda a: self._handle_route_compare(a),
            "plan_multistop_mission": lambda a: self._handle_multistop(a),
            # Innovations & Playbooks
            "evaluate_rescue_equity": lambda a: self.world.evaluate_rescue_equity(_cid(a)),
            "find_mutual_aid_options": lambda a: self.world.find_mutual_aid_options(
                _cid(a), resource_type=a.get("resource_type", "ambulances"), quantity=int(a.get("quantity", 8))
            ),
            "run_counterfactual_comparison": lambda a: self.world.run_counterfactual_comparison(
                _cid(a), what_if_params=a.get("what_if")
            ),
            "list_playbooks": lambda a: {"playbooks": PLAYBOOK_CATALOG},
            "get_event_timeline": lambda a: {"events": self.world.event_bus.get_events(limit=int(a.get("limit", 40)))},
            # State-changing Action Tools (always create PENDING operator approval)
            "prepare_disaster_event": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="inject_disaster",
                    title=f"Inject Simulated {a.get('disaster_type', 'FLOOD')} in {self.world.countries[_cid(a)].name}",
                    description=f"Severity {int(float(a.get('severity', 0.78)) * 100)}% centered on capital.",
                    country_id=_cid(a),
                    parameters={"disaster_type": a.get("disaster_type", "FLOOD"), "severity": float(a.get("severity", 0.78)), "radius_km": 11.0},
                )
            ),
            "prepare_swarm_operation": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="deploy_swarm",
                    title=f"Deploy {int(a.get('drone_count', 8))}-Drone {a.get('mode', 'AREA_SCAN')} Swarm ({self.world.countries[_cid(a)].name})",
                    description=f"Formation: {a.get('formation', 'SEARCH_GRID')}.",
                    country_id=_cid(a),
                    parameters={"drone_count": int(a.get("drone_count", 8)), "mode": a.get("mode", "AREA_SCAN"), "formation": a.get("formation", "SEARCH_GRID")},
                    required_resources={"drones": int(a.get("drone_count", 8))},
                )
            ),
            "prepare_ambulance_dispatch": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="dispatch_ambulances",
                    title=f"Dispatch {int(a.get('count', 6))} Ambulances in {self.world.countries[_cid(a)].name}",
                    description="Priority medical transport dispatch.",
                    country_id=_cid(a),
                    parameters={"count": int(a.get("count", 6))},
                )
            ),
            "prepare_cross_country_aid": lambda a: to_dict(
                self.approval_engine.create_approval_request(
                    operation_type="cross_country_aid",
                    title=f"Mutual Aid Transfer: {int(a.get('quantity', 6))} {a.get('resource_type', 'ambulances')}",
                    description=f"From {a.get('donor_country_id', 'COUNTRY-05')} to {_cid(a)}.",
                    country_id=_cid(a),
                    parameters={"donor_country_id": a.get("donor_country_id", "COUNTRY-05"), "resource_type": a.get("resource_type", "ambulances"), "quantity": int(a.get("quantity", 6))},
                )
            ),
            "prepare_comprehensive_rescue_plan": lambda a: self._handle_prepare_rescue_plan(_cid(a)),
            "prepare_drone_failure": lambda a: self._handle_prepare_drone_failure(a),
        }

    def _handle_route_compare(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        hospitals = [h for h in self.world.hospitals.values() if h.country_id == cid]
        target_h = hospitals[0] if hospitals else None
        dest = GeoPoint(lat=float(args["lat"]), lon=float(args["lon"]), elevation_m=90.0) if ("lat" in args and "lon" in args) else (
            target_h.location if target_h else self.world.countries[cid].center
        )
        label = args.get("destination_label") or (target_h.name if target_h else self.world.countries[cid].capital_name)
        return self.route_explorer.compare_drones_to_destination(
            cid, dest, destination_label=label, objective=args.get("objective", "BALANCED")
        )

    def _handle_multistop(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        c = self.world.countries[cid].center
        pts = [
            GeoPoint(lat=c.lat + 0.02, lon=c.lon + 0.02, elevation_m=85.0),
            GeoPoint(lat=c.lat - 0.02, lon=c.lon + 0.03, elevation_m=90.0),
            GeoPoint(lat=c.lat + 0.03, lon=c.lon - 0.02, elevation_m=88.0),
        ]
        return self.route_explorer.plan_multistop_mission(cid, pts, sensor_type=args.get("sensor_type", "thermal"))

    def _handle_prepare_rescue_plan(self, cid: str) -> Dict[str, Any]:
        plan = self.approval_engine.generate_adapted_plan(cid, playbook_id="PB-03")
        pr = plan["proposed_resources"]
        apr = self.approval_engine.create_approval_request(
            operation_type="comprehensive_rescue_plan",
            title=f"Execute {plan['playbook']['title']} — {self.world.countries[cid].name}",
            description=f"Deploy {pr['drones']} drones, {pr['ambulances']} ambulances, and activate {pr['shelters_to_activate']} relief shelters.",
            country_id=cid,
            parameters={"drones": pr["drones"], "ambulances": pr["ambulances"], "plan_id": plan["plan_id"]},
            required_resources=pr,
            expected_outcomes=[f"Addresses {plan['population_at_risk']:,} exposed residents across {self.world.countries[cid].name}"],
            operational_risks=plan["shortages_and_risks"],
        )
        return {"plan": plan, "approval": to_dict(apr)}

    def _handle_prepare_drone_failure(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or self.world.selected_country_id
        target_d = args.get("drone_id")
        if not target_d or target_d not in self.world.drones:
            target_d = next((d.drone_id for d in self.world.drones.values() if d.country_id == cid), next(iter(self.world.drones.keys())))
        return to_dict(
            self.approval_engine.create_approval_request(
                operation_type="destroy_drone",
                title=f"Simulate Destruction of {target_d}",
                description=f"Virtual simulation failure injection on {target_d} with automatic swarm task recovery.",
                country_id=self.world.drones[target_d].country_id,
                parameters={"drone_id": target_d, "failure_type": "COMPLETE_DRONE_DESTRUCTION"},
                affected_entities=[target_d],
            )
        )

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        meta: Dict[str, Dict[str, Any]] = {}
        for name in self._tool_handlers:
            is_action = name.startswith("prepare_")
            cat = (
                "action" if is_action
                else "navigation" if name.startswith(("view_", "focus_"))
                else "routing" if "route" in name or "multistop" in name or "compare_drones" in name
                else "medical" if any(k in name for k in ("hospital", "ambulance"))
                else "logistics" if any(k in name for k in ("shelter", "resource", "mutual_aid"))
                else "drone" if any(k in name for k in ("drone", "swarm"))
                else "world"
            )
            meta[name] = {
                "tool_name": name,
                "category": cat,
                "read_only": not is_action,
                "requires_approval": is_action,
                "callable": True,
            }
        return meta

    def execute_tool_direct(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Direct fast execution endpoint for any registered JARVIS tool."""
        if tool_name not in self._tool_handlers:
            raise ValueError(f"Unknown tool: {tool_name}")
        t0 = time.perf_counter()
        result = self._tool_handlers[tool_name](args or {})
        dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        entry = {
            "timestamp": utc_now_iso(),
            "tool": tool_name,
            "arguments": args or {},
            "duration_ms": dur_ms,
            "status": "OK",
            "summary": self._summarize_result(tool_name, result),
        }
        self.tool_logs.append(entry)
        return {"tool": tool_name, "duration_ms": dur_ms, "result": result, "trace_entry": entry}

    def _run_tool(self, trace: List[Dict[str, Any]], tool_name: str, args: Dict[str, Any]) -> Any:
        t0 = time.perf_counter()
        started = utc_now_iso()
        try:
            res = self._tool_handlers[tool_name](args)
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "OK",
                "summary": self._summarize_result(tool_name, res),
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            return res
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            entry = {
                "timestamp": started,
                "tool": tool_name,
                "arguments": args,
                "duration_ms": dur_ms,
                "status": "ERROR",
                "summary": str(exc),
            }
            trace.append(entry)
            self.tool_logs.append(entry)
            raise

    def _summarize_result(self, tool_name: str, res: Any) -> str:
        if isinstance(res, dict):
            if "approval_id" in res:
                return f"Prepared approval {res['approval_id']}"
            if "approval" in res and isinstance(res["approval"], dict):
                return f"Prepared plan + approval {res['approval'].get('approval_id')}"
            if "ranked_comparison" in res:
                return f"Evaluated {res['eligible_count']} eligible drones, {len(res['all_candidate_routes'])} routes"
            if "minimum_ambulances_required" in res:
                return f"Recommended {res['recommended_operational_fleet']} ambulances ({res['available_ambulances']} avail)"
            if "command_id" in res:
                return f"Dispatched {res['command_type']} ({res['status']})"
        return "Completed"

    def _resolve_country(self, text: str, ctx: SessionContext) -> str:
        m = re.search(r"country\s*[-#]?\s*0?([1-7])\b", text, re.IGNORECASE)
        if m:
            cid = f"COUNTRY-0{m.group(1)}"
            ctx.active_country_id = cid
            self.world.selected_country_id = cid
            return cid
        low = text.lower()
        for cid, c in self.world.countries.items():
            if c.name.lower() in low or c.capital_name.lower() in low:
                ctx.active_country_id = cid
                self.world.selected_country_id = cid
                return cid
        return ctx.active_country_id

    async def process_command(self, message: str, session_id: str = "default", use_llm_polish: bool = False) -> Dict[str, Any]:
        t_start = time.perf_counter()
        ctx = self._get_session(session_id)
        trace: List[Dict[str, Any]] = []
        low = message.lower().strip()
        cid = self._resolve_country(message, ctx)
        country = self.world.countries[cid]

        structured_cards: List[Dict[str, Any]] = []
        frontend_commands: List[Dict[str, Any]] = []
        pending_approval: Optional[Dict[str, Any]] = None
        globe_state = "SUCCESS"

        if any(k in low for k in ("whole world", "global view", "all seven countries", "reset camera")):
            cmd = self._run_tool(trace, "view_global_world", {})
            frontend_commands.append(cmd)
            overview = self._run_tool(trace, "get_global_world_overview", {})
            structured_cards.append({"type": "global_overview", "data": overview["totals"]})
            answer = (
                f"Full 7-country continent active. Active disasters: {overview['totals']['active_disasters']} | "
                f"Population at risk: {overview['totals']['people_at_risk']:,} | "
                f"Drones available: {overview['totals']['drones_available']}/{overview['totals']['drones_total']}."
            )

        elif any(k in low for k in ("route", "feasible", "battery", "reach", "best drone")):
            globe_state = "OPTIMIZING"
            if any(v in low for v in ("view ", "zoom ", "go to ")):
                frontend_commands.append(self._run_tool(trace, "view_country", {"country_id": cid}))
            obj = "LOWEST_ENERGY" if ("battery" in low or "energy" in low) else ("FASTEST" if "fastest" in low else ("SAFEST" if "safe" in low else "BALANCED"))
            comp = self._run_tool(trace, "compare_drones_to_destination", {"country_id": cid, "objective": obj})
            cmd_routes = to_dict(
                self.world.event_bus.dispatch_frontend_command(
                    "camera.show_candidate_routes", target_id=cid, frontend="quantum-world",
                    parameters={"candidates": comp["all_candidate_routes"][:10], "destination": comp["destination"]},
                )
            )
            frontend_commands.append(cmd_routes)
            structured_cards.append({"type": "route_comparison", "data": comp})
            best = comp["best_recommendation"]
            answer = (
                f"Route comparison for {comp['destination_label']} ({country.name}, {obj}): "
                f"{comp['eligible_count']}/{comp['total_country_drones']} drones eligible. "
                + (
                    f"Best: {best['drone_id']} via {best['route_id']} ({best['total_distance_km']} km, "
                    f"ETA {best['estimated_duration_min']} min, battery {best['predicted_battery_used_pct']}%)."
                    if best else "No feasible routes."
                )
            )

        elif any(k in low for k in ("mutual aid", "another country", "cross-country", "spare ambulance", "additional ambulance")):
            globe_state = "AWAITING_APPROVAL"
            aid = self._run_tool(trace, "find_mutual_aid_options", {"country_id": cid, "resource_type": "ambulances"})
            structured_cards.append({"type": "mutual_aid", "data": aid})
            if aid["eligible_donors"]:
                top = aid["eligible_donors"][0]
                apr = self._run_tool(trace, "prepare_cross_country_aid", {
                    "country_id": cid, "donor_country_id": top["donor_country_id"],
                    "resource_type": "ambulances", "quantity": top["proposed_transfer"],
                })
                pending_approval = apr
                ctx.pending_approval_id = apr["approval_id"]
                answer = (
                    f"{top['donor_name']} has {top['available_surplus']} surplus ambulances ({top['distance_km']} km, ETA {top['estimated_arrival_hours']}h). "
                    f"Prepared transfer proposal {apr['approval_id']} for {top['proposed_transfer']} ambulances."
                )
            else:
                answer = f"No neighboring countries currently have surplus ambulances for {country.name}."

        elif any(k in low for k in ("swarm", "scan", "medical delivery")):
            globe_state = "AWAITING_APPROVAL"
            m_num = re.search(r"\b(\d+)\s*(?:drone|unit)", low)
            dcount = int(m_num.group(1)) if m_num else 8
            mode = "MEDICAL_DELIVERY" if "medical" in low else ("FLOOD_ASSESSMENT" if "flood" in low else "AREA_SCAN")
            formation = "GRID" if "grid" in low else "SEARCH_GRID"
            apr = self._run_tool(trace, "prepare_swarm_operation", {"country_id": cid, "drone_count": dcount, "mode": mode, "formation": formation})
            pending_approval = apr
            ctx.pending_approval_id = apr["approval_id"]
            answer = f"Prepared {dcount}-drone {mode.replace('_', ' ').lower()} swarm ({formation}) for {country.name} [{apr['approval_id']}]. Ready for your approval."

        elif any(k in low for k in ("destroy", "kill drone", "fail drone")):
            globe_state = "AWAITING_APPROVAL"
            m_dr = re.search(r"\b(D-\d{2}-\d{2}|D-\d{2})\b", message, re.IGNORECASE)
            apr = self._run_tool(trace, "prepare_drone_failure", {"country_id": cid, "drone_id": m_dr.group(1).upper() if m_dr else None})
            pending_approval = apr
            ctx.pending_approval_id = apr["approval_id"]
            answer = f"Prepared simulated drone failure ({apr['approval_id']}). Approve to trigger failure and automatic swarm recovery."

        elif any(k in low for k in ("what if", "counterfactual", "compare", "conventional")):
            globe_state = "OPTIMIZING"
            cf = self._run_tool(trace, "run_counterfactual_comparison", {"country_id": cid})
            structured_cards.append({"type": "counterfactual", "data": cf})
            s0, s3 = cf["scenarios"][0], cf["scenarios"][-1]
            answer = (
                f"Counterfactual comparison ({cf['counterfactual_id']}, seed {cf['seed']}) for {country.name}: "
                f"Conventional evacuates {s0['people_safely_evacuated']:,} in {s0['rescue_completion_min']}m vs "
                f"Swarm + Mutual Aid evacuating {s3['people_safely_evacuated']:,} in {s3['rescue_completion_min']}m."
            )

        elif any(k in low for k in ("rescue plan", "recovery plan", "complete rescue", "prepare a")):
            globe_state = "AWAITING_APPROVAL"
            res_bundle = self._run_tool(trace, "prepare_comprehensive_rescue_plan", {"country_id": cid})
            plan = res_bundle["plan"]
            apr = res_bundle["approval"]
            pr = plan["proposed_resources"]
            pending_approval = apr
            ctx.pending_approval_id = apr["approval_id"]
            structured_cards.append({"type": "rescue_plan", "data": plan})
            answer = (
                f"Prepared rescue strategy for {country.name} ({plan['plan_id']}): {pr['drones']} drones, "
                f"{pr['ambulances']} ambulances, {pr['shelters_to_activate']} shelters for {plan['population_at_risk']:,} exposed residents "
                f"(Approval {apr['approval_id']}). Shall I deploy?"
            )

        elif any(k in low for k in ("view country", "select country", "zoom into", "open country", "focus")):
            globe_state = "QUERYING"
            frontend_commands.append(self._run_tool(trace, "view_country", {"country_id": cid}))
            detail = self._run_tool(trace, "get_country_status", {"country_id": cid})
            structured_cards.append({"type": "country_status", "data": detail["profile"]})
            answer = f"{country.name} ({cid}) is now focused in World Command. Capital: {country.capital_name} | Exposed: {detail['resource_analysis']['exposed_population']:,}."

        else:
            globe_state = "QUERYING"
            detail = self._run_tool(trace, "get_country_status", {"country_id": cid})
            amb = detail["ambulance_analysis"]
            res = detail["resource_analysis"]
            active_dis = [d for d in detail["disasters"] if d["status"] == "ACTIVE"]
            hosp_op = sum(1 for h in detail["hospitals"] if h["status"] in ("OPERATIONAL", "PARTIALLY_OPERATIONAL"))
            structured_cards.append({"type": "disaster_analysis", "data": {"country": detail["profile"], "ambulance": amb, "resources": res}})
            answer = (
                f"Live Report — {country.name} ({cid}, v{self.world.event_bus.world_version}):\n"
                f"• Active disasters: {len(active_dis)} ({', '.join(d['name'] for d in active_dis) or 'None'})\n"
                f"• Exposed: {res['exposed_population']:,} | Evac demand: {res['evacuation_shelter_demand']:,}\n"
                f"• Hospitals: {hosp_op}/{len(detail['hospitals'])} online ({amb['available_hospital_beds']} beds free) | Ambulances: {amb['available_ambulances']}/{amb['recommended_operational_fleet']} needed\n"
                f"• 24h Supplies: Food {res['food_packages']['needed']:,} pkgs (stock {res['food_packages']['available']:,}), Water {res['water_liters']['needed']:,.0f} L"
            )

        # Ultra-fast grounded response by default (<10ms); optional LLM polish when requested & keys configured
        provider_used = "instant_grounded_orchestrator"
        model_used = "zero-latency-tool-engine"
        if use_llm_polish:
            llm_res = await self.provider_manager.synthesize_narrative(message, answer, answer)
            answer = llm_res["text"]
            provider_used = llm_res["provider_used"]
            model_used = llm_res["model_used"]

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        reply_record = {
            "reply_id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": utc_now_iso(),
            "session_id": session_id,
            "user_message": message,
            "assistant_message": answer,
            "spoken_summary": answer.replace("\n", " ").replace("•", "")[:280],
            "provider": provider_used,
            "model": model_used,
            "latency_ms": total_ms,
            "globe_state": globe_state,
            "context": ctx.snapshot(),
            "execution_trace": trace,
            "structured_cards": structured_cards,
            "frontend_commands": frontend_commands,
            "pending_approval": pending_approval,
        }
        self.conversations.setdefault(session_id, []).append(reply_record)
        return reply_record
