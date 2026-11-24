from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.ai.entities import _RE_HOSPITAL_ID, extract_disaster_type, extract_drone_id


def recognize_intents(message: str, entities: Optional[Dict[str, Any]] = None) -> List[str]:
    """Fast multi-intent classifier supporting compound commands in <1 ms."""
    low = (message or "").lower()
    if entities is None:
        m_hosp = _RE_HOSPITAL_ID.search(message or "")
        entities = {
            "hospital_id": m_hosp.group(1).upper() if m_hosp else None,
            "drone_id": extract_drone_id(message or ""),
            "disaster_type": extract_disaster_type(low),
        }

    intents: List[str] = []

    # 1. Navigation intents (can combine with any read or routing intent)
    if any(k in low for k in ("whole world", "global view", "all seven countries", "reset camera", "global overview")):
        intents.append("global_world")
    elif any(k in low for k in ("view country", "select country", "zoom into", "open country", "go to country", "focus country")):
        intents.append("view_country")
    elif re.search(r"\b(?:view|zoom|go to|focus on)\s+(?:country|aurelia|valtoria|veridia|solara|ferros|kalahar|sylva)\b", low):
        intents.append("view_country")

    if entities.get("hospital_id") and any(k in low for k in ("focus", "zoom", "view", "locate")):
        intents.append("focus_hospital")
    if entities.get("drone_id") and any(k in low for k in ("focus", "zoom", "track", "locate")) and not any(k in low for k in ("destroy", "kill", "fail")):
        intents.append("focus_drone")

    # 2. Approval-gated action intents (high priority, compound-capable)
    is_action = False
    if any(k in low for k in ("destroy", "kill drone", "fail drone", "drone failure")):
        intents.append("prepare_drone_failure")
        is_action = True
    if any(k in low for k in ("inject", "trigger", "simulate")) and entities.get("disaster_type") and not any(k in low for k in ("what if", "counterfactual")):
        intents.append("prepare_disaster")
        is_action = True
    if any(k in low for k in ("rescue plan", "recovery plan", "complete rescue", "comprehensive rescue")):
        intents.append("prepare_rescue_plan")
        is_action = True
    if any(k in low for k in ("swarm", "medical delivery", "area scan", "deploy drone")) and any(
        k in low for k in ("prepare", "deploy", "launch", "start", "swarm", "scan", "delivery")
    ):
        if "swarm status" in low or "active swarm" in low or "list swarm" in low:
            intents.append("swarm_status")
        else:
            intents.append("prepare_swarm")
            is_action = True
    if any(k in low for k in ("dispatch ambulance", "send ambulance", "prepare ambulance")):
        intents.append("prepare_ambulance_dispatch")
        is_action = True
    if any(k in low for k in ("mutual aid", "another country", "cross-country", "spare ambulance", "additional ambulance")):
        intents.append("mutual_aid")
        is_action = True

    # 3. Granular analytical & read-only intents (compound-capable!)
    if not is_action:
        if any(k in low for k in ("blocked road", "road blockage", "closed road", "flooded road", "blocked bridge")):
            intents.append("blocked_roads")
        elif any(k in low for k in ("road network", "all roads", "road status", "bridges")):
            intents.append("road_network")

        if any(k in low for k in ("multistop", "multi-stop", "multi stop", "survey mission")):
            intents.append("multistop_mission")
        elif any(k in low for k in ("route log", "routing log")):
            intents.append("route_logs")
        elif any(k in low for k in ("best drone", "compare drone", "feasible route", "drone route", "drones to reach", "reach the hospital", "route to")):
            intents.append("route_comparison")
        elif any(k in low for k in ("route", "feasible", "reach")) and "road" not in low:
            intents.append("route_comparison")

        if any(k in low for k in ("low battery", "low-battery", "battery below", "battery under")):
            intents.append("low_battery_drones")
        elif any(k in low for k in ("available drone", "ready drone", "idle drone")):
            intents.append("available_drones")
        elif any(k in low for k in ("drone fleet", "all drones", "list drones")):
            intents.append("drone_fleet")

        if any(k in low for k in ("swarm status", "active swarm", "list swarm")) and "swarm_status" not in intents:
            intents.append("swarm_status")

        if any(k in low for k in ("available bed", "free bed", "bed capacity", "hospital bed")):
            intents.append("available_beds")
        elif any(k in low for k in ("hospital status", "hospitals", "medical facility")) and "reach the hospital" not in low:
            intents.append("hospital_status")

        if any(k in low for k in ("ambulance requirement", "how many ambulance", "ambulances needed", "ambulance deficit")):
            intents.append("ambulance_requirements")
        elif any(k in low for k in ("ambulance fleet", "list ambulance", "ambulance status")):
            intents.append("ambulance_fleet")

        if any(k in low for k in ("fire unit", "fire truck", "firefighter", "rescue boat")):
            intents.append("fire_units")

        if any(k in low for k in ("shelter capacity", "shelters", "relief shelter")):
            intents.append("shelter_capacity")
        if any(k in low for k in ("warehouse", "inventory", "depot stock", "supply stock")):
            intents.append("warehouse_inventory")
        if any(k in low for k in ("shortage", "depletion", "deficit")) and "ambulance deficit" not in low:
            intents.append("resource_shortages")
        elif any(k in low for k in ("resource requirement", "food and water", "supply requirement", "supplies needed")):
            intents.append("resource_requirements")

        if any(k in low for k in ("what if", "counterfactual", "conventional")):
            intents.append("counterfactual")
        if any(k in low for k in ("equity", "underserved", "vulnerable priority")):
            intents.append("rescue_equity")
        if any(k in low for k in ("cascade", "chain reaction", "secondary hazard")):
            intents.append("cascade_graph")
        if any(k in low for k in ("disaster impact", "damage assessment")):
            intents.append("disaster_impact")
        elif any(k in low for k in ("active disaster", "list disaster", "current disaster")):
            intents.append("active_disasters")

        if any(k in low for k in ("cities", "city list")):
            intents.append("country_cities")
        if any(k in low for k in ("district", "sector")):
            intents.append("district_details")
        if any(k in low for k in ("building", "structural damage")):
            intents.append("buildings_summary")
        if any(k in low for k in ("household", "families", "pets", "assisted transport")):
            intents.append("household_statistics")
        elif any(k in low for k in ("population", "residents", "demographics")):
            intents.append("population_summary")
        if any(k in low for k in ("animal", "livestock", "wildlife")):
            intents.append("animal_population")

        if any(k in low for k in ("playbook", "sop", "protocol")):
            intents.append("list_playbooks")
        if any(k in low for k in ("event timeline", "recent events", "event log")):
            intents.append("event_timeline")
        if any(k in low for k in ("audit log", "tool log")):
            intents.append("audit_logs")
        if any(k in low for k in ("pending approval", "list approval")):
            intents.append("pending_approvals")
        if any(k in low for k in ("save world", "save snapshot", "save local")):
            intents.append("save_world_local")
        if any(k in low for k in ("list countries", "all countries", "country list")):
            intents.append("country_list")

    if not intents:
        intents.append("country_report")
    return intents
