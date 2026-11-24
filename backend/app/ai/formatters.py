from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

from app.ai.session import SessionContext
from app.core.compat import to_dict
from app.world.global_engine import GlobalWorldEngine


class _ToolTraceEntryOptional(TypedDict, total=False):
    category: str


class ToolTraceEntry(_ToolTraceEntryOptional):
    timestamp: str
    tool: str
    arguments: Dict[str, Any]
    duration_ms: float
    status: str
    summary: str


class JarvisReply(TypedDict):
    reply_id: str
    timestamp: str
    session_id: str
    user_message: str
    assistant_message: str
    spoken_summary: str
    provider: str
    model: str
    latency_ms: float
    globe_state: str
    intent: str
    intents: List[str]
    intents_succeeded: int
    intents_failed: int
    entities: Dict[str, Any]
    kpis: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    tools_called: List[str]
    context: Dict[str, Any]
    execution_trace: List[ToolTraceEntry]
    structured_cards: List[Dict[str, Any]]
    frontend_commands: List[Dict[str, Any]]
    pending_approval: Optional[Dict[str, Any]]


def summarize_result(tool_name: str, res: Any) -> str:
    if isinstance(res, dict):
        if "approval_id" in res:
            return f"Prepared approval {res.get('approval_id')}"
        if "approval" in res and isinstance(res["approval"], dict):
            return f"Prepared plan + approval {res['approval'].get('approval_id')}"
        if "ranked_comparison" in res:
            return f"Evaluated {res.get('eligible_count', 0)} eligible drones, {len(res.get('all_candidate_routes') or [])} routes"
        if "minimum_ambulances_required" in res:
            return f"Recommended {res.get('recommended_operational_fleet', 0)} ambulances ({res.get('available_ambulances', 0)} avail)"
        if "command_id" in res:
            return f"Dispatched {res.get('command_type', 'command')} ({res.get('status', 'OK')})"
        if "blocked_count" in res:
            return f"Found {res.get('blocked_count', 0)}/{res.get('total_roads', 0)} blocked roads"
        if "total_available_beds" in res:
            return f"{res.get('total_available_beds', 0)}/{res.get('total_beds', 0)} beds available"
        if "saved" in res and res.get("saved"):
            return f"Saved local world snapshot to {res.get('path')}"
        if "count" in res:
            return f"Returned {res.get('count', 0)} records"
    return "Completed"


def execute_intent(
    intent: str,
    *,
    intents_count: int,
    cid: str,
    country: Any,
    low: str,
    entities: Dict[str, Any],
    ctx: SessionContext,
    world: GlobalWorldEngine,
    run_tool: Callable[[str, Dict[str, Any]], Any],
    is_tool_error: Callable[[Any], bool],
    structured_cards: List[Dict[str, Any]],
    frontend_commands: List[Dict[str, Any]],
    kpis: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    answer_sections: List[str],
    globe_state: str,
    pending_approval: Optional[Dict[str, Any]],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Execute a single recognized intent, appending cards/KPIs/tables/text.

    Returns (succeeded, updated_globe_state, updated_pending_approval).
    """

    def _note_err(res: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        answer_sections.append(
            f"Afraid we hit a snag on {res.get('tool', 'that subsystem')}, Sir: {res.get('error', 'unknown error')}."
        )
        return False, globe_state, pending_approval

    if intent == "global_world":
        cmd = run_tool("view_global_world", {})
        if is_tool_error(cmd):
            return _note_err(cmd)
        frontend_commands.append(cmd)
        overview = run_tool("get_global_world_overview", {})
        if is_tool_error(overview):
            return _note_err(overview)
        t = overview["totals"]
        structured_cards.append({"type": "global_overview", "data": t})
        kpis.extend([
            {"label": "Active Disasters", "value": t["active_disasters"]},
            {"label": "Population at Risk", "value": t["people_at_risk"]},
            {"label": "Drones Available", "value": f"{t['drones_available']}/{t['drones_total']}"},
        ])
        tables.append({
            "title": "Seven-Country Continental Status",
            "columns": ["Country", "Capital", "Active Disasters", "Exposed", "Drones Avail", "Readiness"],
            "rows": [
                [c["name"], c["capital_name"], c["active_disasters"], c["exposed_population"], f"{c['drones_available']}/{c['drones_total']}", f"{c['readiness_score']}%"]
                for c in overview["countries"]
            ],
        })
        answer_sections.append(
            f"Right away, Sir. Full 7-country continental telemetry is live: {t['active_disasters']} active disasters, "
            f"{t['people_at_risk']:,} residents at risk, and {t['drones_available']}/{t['drones_total']} drones flight-ready."
        )

    elif intent == "view_country":
        vcmd = run_tool("view_country", {"country_id": cid})
        if is_tool_error(vcmd):
            return _note_err(vcmd)
        globe_state = "QUERYING" if globe_state == "SUCCESS" else globe_state
        frontend_commands.append(vcmd)
        if intents_count == 1:
            detail = run_tool("get_country_status", {"country_id": cid})
            if is_tool_error(detail):
                return _note_err(detail)
            structured_cards.append({"type": "country_status", "data": detail["profile"]})
            kpis.extend([
                {"label": "Country", "value": country.name},
                {"label": "Exposed Population", "value": detail["resource_analysis"]["exposed_population"]},
                {"label": "Readiness", "value": f"{country.readiness_score}%"},
            ])
            answer_sections.append(
                f"Right away, Sir. {country.name} ({cid}) telemetry is up in World Command—capital {country.capital_name}, "
                f"{detail['resource_analysis']['exposed_population']:,} exposed, readiness holding at {country.readiness_score}%."
            )
        else:
            answer_sections.append(
                f"Right away, Sir. World Command camera is locked onto {country.name} ({cid}, capital {country.capital_name})."
            )

    elif intent == "focus_hospital":
        cmd = run_tool("focus_hospital", {"country_id": cid, "hospital_id": entities["hospital_id"]})
        if is_tool_error(cmd):
            return _note_err(cmd)
        frontend_commands.append(cmd)
        answer_sections.append(f"Visual locked onto hospital {cmd.get('target_id')}, Sir.")

    elif intent == "focus_drone":
        cmd = run_tool("focus_drone", {"country_id": cid, "drone_id": entities["drone_id"]})
        if is_tool_error(cmd):
            return _note_err(cmd)
        frontend_commands.append(cmd)
        answer_sections.append(f"Tracking feed locked onto drone {cmd.get('target_id')}, Sir.")

    elif intent == "blocked_roads":
        res = run_tool("get_blocked_roads", {"country_id": cid})
        if is_tool_error(res):
            return _note_err(res)
        globe_state = "QUERYING" if globe_state == "SUCCESS" else globe_state
        structured_cards.append({"type": "blocked_roads", "data": res})
        kpis.append({"label": "Blocked Roads", "value": f"{res['blocked_count']}/{res['total_roads']}"})
        if res["blocked_roads"]:
            tables.append({
                "title": f"Blocked Roads — {country.name}",
                "columns": ["Road ID", "Name", "Category", "Flood Depth (m)", "Reason"],
                "rows": [
                    [r["road_id"], r["name"], r["category"], r["flood_depth_m"], r.get("blocked_reason") or "Blocked"]
                    for r in res["blocked_roads"]
                ],
            })
        answer_sections.append(
            f"Ground corridors in {country.name}, Sir: {res['blocked_count']}/{res['total_roads']} roads blocked "
            f"({res['accessible_count']} still passable)."
        )

    elif intent == "road_network":
        res = run_tool("get_road_network", {"country_id": cid})
        if is_tool_error(res):
            return _note_err(res)
        structured_cards.append({"type": "road_network", "data": res})
        kpis.extend([
            {"label": "Accessible Roads", "value": f"{res['accessible_roads']}/{res['total_roads']}"},
            {"label": "Blocked Bridges", "value": f"{res['bridges_blocked']}/{res['bridges_total']}"},
        ])
        answer_sections.append(
            f"Road grid telemetry for {country.name}, Sir: {res['accessible_roads']}/{res['total_roads']} open, "
            f"{res['blocked_roads']} blocked ({res['bridges_blocked']} bridges compromised)."
        )

    elif intent == "route_comparison":
        obj = entities["objective"]
        comp = run_tool(
            "compare_drones_to_destination",
            {"country_id": cid, "hospital_id": entities["hospital_id"], "objective": obj},
        )
        if is_tool_error(comp):
            return _note_err(comp)
        globe_state = "OPTIMIZING"
        cmd_routes = to_dict(
            world.event_bus.dispatch_frontend_command(
                "camera.show_candidate_routes",
                target_id=cid,
                frontend="quantum-world",
                parameters={"candidates": comp["all_candidate_routes"][:10], "destination": comp["destination"]},
            )
        )
        frontend_commands.append(cmd_routes)
        structured_cards.append({"type": "route_comparison", "data": comp})
        best = comp["best_recommendation"]
        kpis.extend([
            {"label": "Eligible Drones", "value": f"{comp['eligible_count']}/{comp['total_country_drones']}"},
            {"label": "Best Drone", "value": best["drone_id"] if best else "None"},
        ])
        if comp["ranked_comparison"]:
            tables.append({
                "title": f"Top Drone Routes to {comp['destination_label']} ({obj})",
                "columns": ["Rank", "Drone", "Route", "Distance (km)", "ETA (min)", "Battery Used (%)", "Feasible"],
                "rows": [
                    [r["rank"], r["drone_id"], r["route_id"], r["total_distance_km"], r["estimated_duration_min"], r["predicted_battery_used_pct"], "Yes" if r["feasible"] else "No"]
                    for r in comp["ranked_comparison"][:5]
                ],
            })
        answer_sections.append(
            f"Three steps ahead as usual, Sir—route matrix locked for {comp['destination_label']} ({country.name}, {obj}). "
            f"{comp['eligible_count']}/{comp['total_country_drones']} drones qualify. "
            + (
                f"Optimal pick: {best['drone_id']} via {best['route_id']} ({best['total_distance_km']} km, "
                f"ETA {best['estimated_duration_min']} min, {best['predicted_battery_used_pct']}% battery draw)."
                if best else "No feasible air corridors under current constraints."
            )
        )

    elif intent == "multistop_mission":
        ms = run_tool("plan_multistop_mission", {"country_id": cid, "sensor_type": entities["sensor_type"]})
        if is_tool_error(ms):
            return _note_err(ms)
        globe_state = "OPTIMIZING"
        structured_cards.append({"type": "multistop_mission", "data": ms})
        rec = ms.get("recommended")
        kpis.append({"label": "Eligible Sensor Drones", "value": ms.get("eligible_drones", 0)})
        answer_sections.append(
            f"Multi-stop {entities['sensor_type']} sweep plotted for {country.name}, Sir: "
            + (
                f"assigning {rec['drone_id']} ({rec['total_distance_km']} km round-trip, {rec['estimated_duration_min']} min, {rec['predicted_battery_used_pct']}% battery)."
                if rec else ms.get("reason", "No feasible flight plan available.")
            )
        )

    elif intent == "route_logs":
        logs = run_tool("get_route_logs", {"limit": 20})
        if is_tool_error(logs):
            return _note_err(logs)
        structured_cards.append({"type": "route_logs", "data": logs})
        answer_sections.append(f"Pulled the latest {logs['count']} 3D route solver telemetry logs, Sir.")

    elif intent == "mutual_aid":
        rtype = entities["resource_type"]
        qty = entities["counts"].get("ambulance_count") or entities["counts"].get("quantity") or 8
        aid = run_tool("find_mutual_aid_options", {"country_id": cid, "resource_type": rtype, "quantity": qty})
        if is_tool_error(aid):
            return _note_err(aid)
        structured_cards.append({"type": "mutual_aid", "data": aid})
        kpis.append({"label": "Eligible Donors", "value": len(aid["eligible_donors"])})
        if aid["eligible_donors"]:
            top = aid["eligible_donors"][0]
            apr = run_tool("prepare_cross_country_aid", {
                "country_id": cid,
                "donor_country_id": top["donor_country_id"],
                "resource_type": rtype,
                "quantity": top["proposed_transfer"],
            })
            if is_tool_error(apr):
                return _note_err(apr)
            globe_state = "AWAITING_APPROVAL"
            pending_approval = apr
            ctx.pending_approval_id = apr["approval_id"]
            tables.append({
                "title": f"Mutual Aid Donors ({rtype})",
                "columns": ["Donor", "Distance (km)", "Surplus", "Proposed", "ETA (h)"],
                "rows": [
                    [d["donor_name"], d["distance_km"], d["available_surplus"], d["proposed_transfer"], d["estimated_arrival_hours"]]
                    for d in aid["eligible_donors"]
                ],
            })
            answer_sections.append(
                f"{top['donor_name']} can spare {top['available_surplus']} {rtype} ({top['distance_km']} km out, ETA {top['estimated_arrival_hours']}h). "
                f"I've queued transfer proposal {apr['approval_id']} for {top['proposed_transfer']} {rtype}—standing by for your green light, Sir."
            )
        else:
            answer_sections.append(f"No neighboring nations currently hold surplus {rtype} to spare for {country.name}, Sir.")

    elif intent == "prepare_swarm":
        dcount = entities["counts"].get("drone_count", 8)
        mode = (
            "MEDICAL_DELIVERY" if "medical" in low
            else "FLOOD_ASSESSMENT" if "flood" in low
            else "FIRE_PERIMETER" if "fire" in low
            else "SURVIVOR_SEARCH" if "survivor" in low
            else "AREA_SCAN"
        )
        formation = "GRID" if "grid" in low and "search grid" not in low else "SEARCH_GRID"
        apr = run_tool("prepare_swarm_operation", {
            "country_id": cid, "drone_count": dcount, "mode": mode, "formation": formation,
        })
        if is_tool_error(apr):
            return _note_err(apr)
        globe_state = "AWAITING_APPROVAL"
        pending_approval = apr
        ctx.pending_approval_id = apr["approval_id"]
        kpis.extend([
            {"label": "Swarm Size", "value": dcount},
            {"label": "Approval ID", "value": apr["approval_id"]},
        ])
        answer_sections.append(
            f"Staged a {dcount}-drone {mode.replace('_', ' ').lower()} swarm ({formation}) for {country.name} "
            f"[{apr['approval_id']}]. Standing by for your green light, Sir."
        )

    elif intent == "prepare_drone_failure":
        apr = run_tool("prepare_drone_failure", {"country_id": cid, "drone_id": entities["drone_id"]})
        if is_tool_error(apr):
            return _note_err(apr)
        globe_state = "AWAITING_APPROVAL"
        pending_approval = apr
        ctx.pending_approval_id = apr["approval_id"]
        answer_sections.append(
            f"Simulated drone failure injection queued [{apr['approval_id']}] with automatic swarm failover armed. "
            f"Standing by for your green light, Sir."
        )

    elif intent == "prepare_ambulance_dispatch":
        cnt = entities["counts"].get("ambulance_count", 6)
        apr = run_tool("prepare_ambulance_dispatch", {"country_id": cid, "count": cnt})
        if is_tool_error(apr):
            return _note_err(apr)
        globe_state = "AWAITING_APPROVAL"
        pending_approval = apr
        ctx.pending_approval_id = apr["approval_id"]
        answer_sections.append(
            f"Dispatch order staged for {cnt} ambulances in {country.name} [{apr['approval_id']}]. "
            f"Standing by for your green light, Sir."
        )

    elif intent == "prepare_disaster":
        dtype = entities["disaster_type"] or "FLOOD"
        sev = entities["counts"].get("severity", 0.78)
        apr = run_tool("prepare_disaster_event", {"country_id": cid, "disaster_type": dtype, "severity": sev})
        if is_tool_error(apr):
            return _note_err(apr)
        globe_state = "AWAITING_APPROVAL"
        pending_approval = apr
        ctx.pending_approval_id = apr["approval_id"]
        answer_sections.append(
            f"Simulated {dtype} event queued for {country.name} at {int(sev * 100)}% severity [{apr['approval_id']}]. "
            f"Standing by for your green light, Sir."
        )

    elif intent == "prepare_rescue_plan":
        res_bundle = run_tool("prepare_comprehensive_rescue_plan", {"country_id": cid})
        if is_tool_error(res_bundle):
            return _note_err(res_bundle)
        globe_state = "AWAITING_APPROVAL"
        plan = res_bundle["plan"]
        apr = res_bundle["approval"]
        pr = plan["proposed_resources"]
        pending_approval = apr
        ctx.pending_approval_id = apr["approval_id"]
        structured_cards.append({"type": "rescue_plan", "data": plan})
        kpis.extend([
            {"label": "Proposed Drones", "value": pr["drones"]},
            {"label": "Proposed Ambulances", "value": pr["ambulances"]},
            {"label": "Shelters to Activate", "value": pr["shelters_to_activate"]},
        ])
        answer_sections.append(
            f"I've assembled the full rescue playbook for {country.name} ({plan['plan_id']}), Sir: {pr['drones']} drones, "
            f"{pr['ambulances']} ambulances, and {pr['shelters_to_activate']} shelters covering {plan['population_at_risk']:,} exposed residents "
            f"[{apr['approval_id']}]. Standing by for your green light, Sir."
        )

    elif intent == "counterfactual":
        cf = run_tool("run_counterfactual_comparison", {"country_id": cid})
        if is_tool_error(cf):
            return _note_err(cf)
        globe_state = "OPTIMIZING"
        structured_cards.append({"type": "counterfactual", "data": cf})
        scenarios = cf.get("scenarios") or []
        if scenarios:
            s0, s3 = scenarios[0], scenarios[-1]
            tables.append({
                "title": f"Counterfactual Comparison — {country.name}",
                "columns": ["Strategy", "Evacuated", "First Response (m)", "Completion (m)", "Failures"],
                "rows": [
                    [s["label"], s["people_safely_evacuated"], s["time_to_first_response_min"], s["rescue_completion_min"], s["mission_failures"]]
                    for s in scenarios
                ],
            })
            answer_sections.append(
                f"Ran the numbers across all four counterfactual scenarios ({cf['counterfactual_id']}, seed {cf['seed']}) for {country.name}, Sir: "
                f"Conventional evacuates {s0['people_safely_evacuated']:,} in {s0['rescue_completion_min']}m, whereas "
                f"Swarm + Mutual Aid evacuates {s3['people_safely_evacuated']:,} in {s3['rescue_completion_min']}m."
            )
        else:
            answer_sections.append(f"Counterfactual analysis for {country.name} returned no scenarios, Sir.")

    elif intent == "rescue_equity":
        eq = run_tool("evaluate_rescue_equity", {"country_id": cid})
        if is_tool_error(eq):
            return _note_err(eq)
        structured_cards.append({"type": "rescue_equity", "data": eq})
        kpis.append({"label": "Underserved Districts", "value": eq["underserved_count"]})
        tables.append({
            "title": f"Rescue Equity Priority — {country.name}",
            "columns": ["District", "Exposed", "Vulnerable", "Road Access", "Equity Score", "Underserved"],
            "rows": [
                [d["name"], d["exposed_residents"], d["vulnerable_residents"], f"{int(d['road_accessibility'] * 100)}%", d["equity_priority_score"], "Yes" if d["underserved_flag"] else "No"]
                for d in eq["districts"][:6]
            ],
        })
        answer_sections.append(
            f"Equity sweep complete for {country.name}, Sir: {eq['underserved_count']} underserved districts flagged for priority attention."
        )

    elif intent == "cascade_graph":
        cg = run_tool("get_cascade_graph", {"country_id": cid})
        if is_tool_error(cg):
            return _note_err(cg)
        structured_cards.append({"type": "cascade_graph", "data": cg})
        answer_sections.append(
            f"Cascade model for {country.name} is up, Sir: {len(cg['nodes'])} hazard and infrastructure nodes mapped across {len(cg['edges'])} causal links."
        )

    elif intent == "hospital_status":
        hs = run_tool("get_hospital_status", {"country_id": cid})
        if is_tool_error(hs):
            return _note_err(hs)
        structured_cards.append({"type": "hospital_status", "data": hs})
        kpis.extend([
            {"label": "Hospitals Online", "value": f"{hs['operational_count']}/{hs['total_hospitals']}"},
            {"label": "Available Beds", "value": f"{hs['available_beds']}/{hs['total_beds']}"},
        ])
        tables.append({
            "title": f"Hospitals — {country.name}",
            "columns": ["ID", "Name", "Status", "Available Beds", "Total Beds", "Triage Load"],
            "rows": [[h["hospital_id"], h["name"], h["status"], h["available_beds"], h["total_beds"], h["triage_load"]] for h in hs["hospitals"]],
        })
        answer_sections.append(
            f"Medical grid in {country.name}, Sir: {hs['operational_count']}/{hs['total_hospitals']} hospitals online with {hs['available_beds']}/{hs['total_beds']} beds open."
        )

    elif intent == "available_beds":
        ab = run_tool("get_available_beds", {"country_id": cid})
        if is_tool_error(ab):
            return _note_err(ab)
        structured_cards.append({"type": "available_beds", "data": ab})
        kpis.append({"label": "Available Beds", "value": f"{ab['total_available_beds']}/{ab['total_beds']}"})
        answer_sections.append(
            f"Hospital bed capacity in {country.name}, Sir: {ab['total_available_beds']}/{ab['total_beds']} beds open across {len(ab['hospitals'])} active facilities."
        )

    elif intent == "ambulance_requirements":
        amb = run_tool("calculate_ambulance_requirements", {"country_id": cid, "window_hours": entities["counts"].get("hours", 4.0)})
        if is_tool_error(amb):
            return _note_err(amb)
        structured_cards.append({"type": "ambulance_requirements", "data": amb})
        kpis.extend([
            {"label": "Ambulances Available", "value": f"{amb['available_ambulances']}/{amb['recommended_operational_fleet']}"},
            {"label": "Ambulance Deficit", "value": amb["ambulance_deficit"]},
        ])
        answer_sections.append(f"Medical transport math for {country.name}, Sir: {amb['explanation']}")

    elif intent == "ambulance_fleet":
        af = run_tool("get_ambulance_fleet", {"country_id": cid})
        if is_tool_error(af):
            return _note_err(af)
        structured_cards.append({"type": "ambulance_fleet", "data": af})
        kpis.append({"label": "Ambulances Ready", "value": f"{af['available_count']}/{af['total_ambulances']}"})
        answer_sections.append(f"EMS fleet in {country.name}, Sir: {af['available_count']}/{af['total_ambulances']} ambulances standing by.")

    elif intent == "fire_units":
        fu = run_tool("get_fire_units", {"country_id": cid})
        if is_tool_error(fu):
            return _note_err(fu)
        structured_cards.append({"type": "fire_units", "data": fu})
        kpis.append({"label": "Fire Units Available", "value": f"{fu['available_count']}/{fu['total_units']}"})
        answer_sections.append(
            f"Fire and rescue units in {country.name}, Sir: {fu['available_count']} available, {fu['on_scene_count']} on scene ({fu['total_units']} total)."
        )

    elif intent == "shelter_capacity":
        sc = run_tool("get_shelter_capacity", {"country_id": cid})
        if is_tool_error(sc):
            return _note_err(sc)
        structured_cards.append({"type": "shelter_capacity", "data": sc})
        kpis.append({"label": "Shelter Capacity Remaining", "value": f"{sc['total_remaining_capacity']:,}"})
        answer_sections.append(
            f"Relief shelters in {country.name}, Sir: {sc['accessible_shelters']}/{sc['total_shelters']} accessible, "
            f"{sc['total_remaining_capacity']:,}/{sc['total_max_occupancy']:,} capacity remaining."
        )

    elif intent == "warehouse_inventory":
        wi = run_tool("get_warehouse_inventory", {"country_id": cid})
        if is_tool_error(wi):
            return _note_err(wi)
        structured_cards.append({"type": "warehouse_inventory", "data": wi})
        wt = wi["totals"]
        kpis.extend([
            {"label": "Warehouse Food", "value": f"{wt['food_packages']:,} pkgs"},
            {"label": "Warehouse Water", "value": f"{wt['water_liters']:,.0f} L"},
        ])
        answer_sections.append(
            f"Depot stock across {wi['warehouse_count']} warehouses in {country.name}, Sir: {wt['food_packages']:,} food pkgs, "
            f"{wt['water_liters']:,.0f} L water, {wt['medical_kits']:,} medical kits, and {wt['generators']} generators."
        )

    elif intent == "resource_shortages":
        rs = run_tool("get_resource_shortages", {"country_id": cid, "horizon_hours": entities["counts"].get("hours", 24.0)})
        if is_tool_error(rs):
            return _note_err(rs)
        structured_cards.append({"type": "resource_shortages", "data": rs})
        kpis.append({"label": "Shortage Alerts", "value": len(rs["shortage_warnings"])})
        answer_sections.append(
            f"Supply risk scan for {country.name}, Sir: "
            + ("; ".join(rs["shortage_warnings"]) if rs["shortage_warnings"] else "No critical shortages projected.")
        )

    elif intent == "resource_requirements":
        rr = run_tool("calculate_resource_requirements", {"country_id": cid, "horizon_hours": entities["counts"].get("hours", 24.0)})
        if is_tool_error(rr):
            return _note_err(rr)
        structured_cards.append({"type": "resource_requirements", "data": rr})
        answer_sections.append(
            f"24h logistics forecast for {country.name}, Sir: Food {rr['food_packages']['needed']:,} pkgs (stock {rr['food_packages']['available']:,}), "
            f"Water {rr['water_liters']['needed']:,.0f} L (stock {rr['water_liters']['available']:,.0f} L)."
        )

    elif intent == "low_battery_drones":
        thresh = entities["counts"].get("battery_threshold", 35.0)
        lb = run_tool("get_low_battery_drones", {"threshold": thresh})
        if is_tool_error(lb):
            return _note_err(lb)
        structured_cards.append({"type": "low_battery_drones", "data": lb})
        kpis.append({"label": f"Drones < {int(thresh)}%", "value": lb["count"]})
        answer_sections.append(f"Power check complete, Sir: {lb['count']} drones currently below {int(thresh)}% charge.")

    elif intent == "available_drones":
        ad = run_tool("get_available_drones", {"country_id": cid})
        if is_tool_error(ad):
            return _note_err(ad)
        structured_cards.append({"type": "available_drones", "data": ad})
        kpis.append({"label": "Available Drones", "value": ad["count"]})
        answer_sections.append(f"Air wing in {country.name}, Sir: {ad['count']} drones charged and cleared for launch.")

    elif intent == "drone_fleet":
        df = run_tool("get_drone_fleet", {"country_id": cid})
        if is_tool_error(df):
            return _note_err(df)
        structured_cards.append({"type": "drone_fleet", "data": df})
        kpis.append({"label": "Drone Fleet", "value": f"{df['available_count']}/{df['total_drones']} avail"})
        answer_sections.append(f"Drone roster for {country.name}, Sir: {df['available_count']}/{df['total_drones']} flight-ready.")

    elif intent == "swarm_status":
        sw = run_tool("get_swarm_status", {})
        if is_tool_error(sw):
            return _note_err(sw)
        structured_cards.append({"type": "swarm_status", "data": sw})
        kpis.append({"label": "Active Swarms", "value": sw["active_swarms"]})
        answer_sections.append(f"Swarm telemetry, Sir: {sw['active_swarms']} active formations ({sw['total_swarms']} total logged).")

    elif intent == "active_disasters":
        ad = run_tool("get_active_disasters", {})
        if is_tool_error(ad):
            return _note_err(ad)
        structured_cards.append({"type": "active_disasters", "data": ad})
        kpis.append({"label": "Active Disasters", "value": ad["count"]})
        answer_sections.append(f"Global hazard board, Sir: {ad['count']} active disaster events under live tracking.")

    elif intent == "disaster_impact":
        di = run_tool("get_disaster_impact", {"country_id": cid})
        if is_tool_error(di):
            return _note_err(di)
        structured_cards.append({"type": "disaster_impact", "data": di})
        kpis.extend([
            {"label": "Exposed Population", "value": di["exposed_population"]},
            {"label": "Blocked Roads", "value": di["blocked_roads"]},
        ])
        answer_sections.append(
            f"Impact readout for {country.name}, Sir: {di['exposed_population']:,} exposed, {di['estimated_injuries']:,} estimated injuries, "
            f"{di['blocked_roads']} blocked roads, and {di['damaged_buildings']} damaged structures."
        )

    elif intent == "country_cities":
        cc = run_tool("get_country_cities", {"country_id": cid})
        if is_tool_error(cc):
            return _note_err(cc)
        structured_cards.append({"type": "country_cities", "data": cc})
        answer_sections.append(f"Urban centers in {country.name}, Sir: {', '.join(c['name'] for c in cc['cities'])}.")

    elif intent == "district_details":
        dd = run_tool("get_district_details", {"country_id": cid, "district_id": entities["district_id"]})
        if is_tool_error(dd):
            return _note_err(dd)
        structured_cards.append({"type": "district_details", "data": dd})
        answer_sections.append(f"Pulled {dd['count']} district telemetry records for {country.name}, Sir.")

    elif intent == "buildings_summary":
        bs = run_tool("get_buildings_summary", {"country_id": cid})
        if is_tool_error(bs):
            return _note_err(bs)
        structured_cards.append({"type": "buildings_summary", "data": bs})
        answer_sections.append(
            f"Structural scan for {country.name}, Sir: {bs['total_buildings']} buildings tracked "
            f"({bs['damaged_count']} damaged, {bs['inaccessible_count']} cut off)."
        )

    elif intent == "population_summary":
        ps = run_tool("get_population_summary", {"country_id": cid})
        if is_tool_error(ps):
            return _note_err(ps)
        structured_cards.append({"type": "population_summary", "data": ps})
        kpis.extend([
            {"label": "Total Residents", "value": ps["total_residents"]},
            {"label": "Exposed Residents", "value": ps["exposed_residents"]},
        ])
        answer_sections.append(
            f"Civilian headcount for {country.name}, Sir: {ps['total_residents']:,} total, "
            f"{ps['exposed_residents']:,} exposed, {ps['vulnerable_residents']:,} vulnerable."
        )

    elif intent == "household_statistics":
        hh = run_tool("get_household_statistics", {"country_id": cid})
        if is_tool_error(hh):
            return _note_err(hh)
        structured_cards.append({"type": "household_statistics", "data": hh})
        answer_sections.append(
            f"Household breakdown for {country.name}, Sir: ~{hh['district_estimated_households']:,} estimated "
            f"({hh['tracked_households']} tracked, {hh['needs_assisted_transport']} requiring assisted transport)."
        )

    elif intent == "animal_population":
        ap = run_tool("get_animal_population", {"country_id": cid})
        if is_tool_error(ap):
            return _note_err(ap)
        structured_cards.append({"type": "animal_population", "data": ap})
        answer_sections.append(
            f"Animal populations in {country.name}, Sir: {ap['total_animals']:,} total ({ap['exposed_animals']:,} exposed)."
        )

    elif intent == "list_playbooks":
        pb = run_tool("list_playbooks", {})
        if is_tool_error(pb):
            return _note_err(pb)
        structured_cards.append({"type": "playbooks", "data": pb})
        answer_sections.append(f"All {pb['count']} disaster response playbooks (PB-01 through PB-24) are loaded and on deck, Sir.")

    elif intent == "event_timeline":
        et = run_tool("get_event_timeline", {"limit": 25})
        if is_tool_error(et):
            return _note_err(et)
        structured_cards.append({"type": "event_timeline", "data": et})
        answer_sections.append(f"Event bus readout (world v{et['world_version']}), Sir: {len(et['events'])} recent events retrieved.")

    elif intent == "audit_logs":
        al = run_tool("get_audit_logs", {"limit": 25})
        if is_tool_error(al):
            return _note_err(al)
        structured_cards.append({"type": "audit_logs", "data": al})
        answer_sections.append(
            f"Audit trail is spotless, Sir: {al['audit_count']} approval records and {al['tool_log_count']} tool executions logged."
        )

    elif intent == "pending_approvals":
        pa = run_tool("list_pending_approvals", {"status": "PENDING"})
        if is_tool_error(pa):
            return _note_err(pa)
        structured_cards.append({"type": "pending_approvals", "data": pa})
        answer_sections.append(
            f"You have {len(pa['approvals'])} pending operator approvals awaiting your sign-off, Sir."
        )

    elif intent == "save_world_local":
        sv = run_tool("save_world_local", {})
        if is_tool_error(sv):
            return _note_err(sv)
        structured_cards.append({"type": "save_world_local", "data": sv})
        answer_sections.append(f"Local snapshot saved (world v{sv['world_version']}) to {sv['path']}, Sir.")

    elif intent == "country_list":
        cl = run_tool("get_country_list", {})
        if is_tool_error(cl):
            return _note_err(cl)
        structured_cards.append({"type": "country_list", "data": cl})
        answer_sections.append(f"All 7 nations online, Sir: {', '.join(c['name'] for c in cl['countries'])}.")

    else:
        detail = run_tool("get_country_status", {"country_id": cid})
        if is_tool_error(detail):
            return _note_err(detail)
        globe_state = "QUERYING"
        amb = detail["ambulance_analysis"]
        res = detail["resource_analysis"]
        active_dis = [d for d in detail["disasters"] if d["status"] == "ACTIVE"]
        hosp_op = sum(1 for h in detail["hospitals"] if h["status"] in ("OPERATIONAL", "PARTIALLY_OPERATIONAL"))
        structured_cards.append({"type": "disaster_analysis", "data": {"country": detail["profile"], "ambulance": amb, "resources": res}})
        kpis.extend([
            {"label": "Active Disasters", "value": len(active_dis)},
            {"label": "Exposed Population", "value": res["exposed_population"]},
            {"label": "Available Beds", "value": amb["available_hospital_beds"]},
            {"label": "Ambulances Ready", "value": f"{amb['available_ambulances']}/{amb['recommended_operational_fleet']}"},
        ])
        answer_sections.append(
            f"Right away, Sir. Live briefing for {country.name} ({cid}, v{world.event_bus.world_version}):\n"
            f"• Active disasters: {len(active_dis)} ({', '.join(d['name'] for d in active_dis) or 'None'})\n"
            f"• Exposed: {res['exposed_population']:,} | Evac demand: {res['evacuation_shelter_demand']:,}\n"
            f"• Hospitals: {hosp_op}/{len(detail['hospitals'])} online ({amb['available_hospital_beds']} beds free) | Ambulances: {amb['available_ambulances']}/{amb['recommended_operational_fleet']} needed\n"
            f"• 24h Supplies: Food {res['food_packages']['needed']:,} pkgs (stock {res['food_packages']['available']:,}), Water {res['water_liters']['needed']:,.0f} L"
        )

    return True, globe_state, pending_approval
