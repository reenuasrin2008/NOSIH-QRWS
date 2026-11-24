from __future__ import annotations

from typing import Any, Callable, Dict

from app.approvals.engine import ApprovalEngine
from app.core.compat import to_dict
from app.world.global_engine import GlobalWorldEngine


def _cid(world: GlobalWorldEngine, args: Dict[str, Any]) -> str:
    cid = args.get("country_id") or world.selected_country_id
    if cid not in world.countries:
        cid = world.selected_country_id
    return cid


def build_handlers(
    world: GlobalWorldEngine,
    approval_engine: ApprovalEngine,
) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _prepare_rescue_plan(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        plan = approval_engine.generate_adapted_plan(cid, playbook_id="PB-03")
        pr = plan["proposed_resources"]
        apr = approval_engine.create_approval_request(
            operation_type="comprehensive_rescue_plan",
            title=f"Execute {plan['playbook']['title']} — {world.countries[cid].name}",
            description=f"Deploy {pr['drones']} drones, {pr['ambulances']} ambulances, and activate {pr['shelters_to_activate']} relief shelters.",
            country_id=cid,
            parameters={"drones": pr["drones"], "ambulances": pr["ambulances"], "plan_id": plan["plan_id"]},
            required_resources=pr,
            expected_outcomes=[f"Addresses {plan['population_at_risk']:,} exposed residents across {world.countries[cid].name}"],
            operational_risks=plan["shortages_and_risks"],
        )
        return {"plan": plan, "approval": to_dict(apr)}

    def _prepare_drone_failure(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = args.get("country_id") or world.selected_country_id
        target_d = args.get("drone_id")
        if target_d and target_d not in world.drones:
            return {
                "status": "ERROR",
                "tool": "prepare_drone_failure",
                "error": f"Unknown drone_id: {target_d}",
                "category": "action",
            }
        if target_d and args.get("country_id") and world.drones[target_d].country_id != args["country_id"]:
            return {
                "status": "ERROR",
                "tool": "prepare_drone_failure",
                "error": "drone_id does not belong to country_id",
                "category": "action",
            }
        if not target_d:
            target_d = next(
                (d.drone_id for d in world.drones.values() if d.country_id == cid),
                next(iter(world.drones.keys()), None),
            )
        if not target_d:
            return {
                "status": "ERROR",
                "tool": "prepare_drone_failure",
                "error": "No drones available in the world for failure injection.",
                "category": "action",
            }
        return to_dict(
            approval_engine.create_approval_request(
                operation_type="destroy_drone",
                title=f"Simulate Destruction of {target_d}",
                description=f"Virtual simulation failure injection on {target_d} with automatic swarm task recovery.",
                country_id=world.drones[target_d].country_id,
                parameters={"drone_id": target_d, "failure_type": "COMPLETE_DRONE_DESTRUCTION"},
                affected_entities=[target_d],
            )
        )

    return {
        "prepare_disaster_event": lambda a: to_dict(
            approval_engine.create_approval_request(
                operation_type="inject_disaster",
                title=f"Inject Simulated {a.get('disaster_type', 'FLOOD')} in {world.countries[_cid(world, a)].name}",
                description=f"Severity {int(float(a.get('severity', 0.78)) * 100)}% centered on capital.",
                country_id=_cid(world, a),
                parameters={
                    "disaster_type": a.get("disaster_type", "FLOOD"),
                    "severity": float(a.get("severity", 0.78)),
                    "radius_km": float(a.get("radius_km", 11.0)),
                },
            )
        ),
        "prepare_swarm_operation": lambda a: to_dict(
            approval_engine.create_approval_request(
                operation_type="deploy_swarm",
                title=f"Deploy {int(a.get('drone_count', 8))}-Drone {a.get('mode', 'AREA_SCAN')} Swarm ({world.countries[_cid(world, a)].name})",
                description=f"Formation: {a.get('formation', 'SEARCH_GRID')}.",
                country_id=_cid(world, a),
                parameters={
                    "drone_count": int(a.get("drone_count", 8)),
                    "mode": a.get("mode", "AREA_SCAN"),
                    "formation": a.get("formation", "SEARCH_GRID"),
                },
                required_resources={"drones": int(a.get("drone_count", 8))},
            )
        ),
        "prepare_ambulance_dispatch": lambda a: to_dict(
            approval_engine.create_approval_request(
                operation_type="dispatch_ambulances",
                title=f"Dispatch {int(a.get('count', 6))} Ambulances in {world.countries[_cid(world, a)].name}",
                description="Priority medical transport dispatch.",
                country_id=_cid(world, a),
                parameters={"count": int(a.get("count", 6))},
            )
        ),
        "prepare_cross_country_aid": lambda a: to_dict(
            approval_engine.create_approval_request(
                operation_type="cross_country_aid",
                title=f"Mutual Aid Transfer: {int(a.get('quantity', 6))} {a.get('resource_type', 'ambulances')}",
                description=f"From {a.get('donor_country_id', 'COUNTRY-05')} to {_cid(world, a)}.",
                country_id=_cid(world, a),
                parameters={
                    "donor_country_id": a.get("donor_country_id", "COUNTRY-05"),
                    "resource_type": a.get("resource_type", "ambulances"),
                    "quantity": int(a.get("quantity", 6)),
                },
            )
        ),
        "prepare_comprehensive_rescue_plan": _prepare_rescue_plan,
        "prepare_drone_failure": _prepare_drone_failure,
    }
