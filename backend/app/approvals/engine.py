from __future__ import annotations
import math
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.compat import to_dict, utc_now_iso
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import (
    AmbulanceStatus,
    ApprovalRequest,
    DisasterType,
    GeoPoint,
    SwarmFormation,
    SwarmMode,
    SwarmOperation,
)


MAX_APPROVAL_WORLD_VERSION_DRIFT = max(50, int(os.getenv("QR_APPROVAL_MAX_VERSION_DRIFT", "500")))
MAX_APPROVALS = max(100, int(os.getenv("QR_MAX_APPROVALS", "2000")))


PLAYBOOK_CATALOG: List[Dict[str, str]] = [
    {"id": "PB-01", "title": "Severe Flood Response", "category": "flood"},
    {"id": "PB-02", "title": "Urban Flood Evacuation", "category": "flood"},
    {"id": "PB-03", "title": "Coastal Cyclone Response", "category": "cyclone"},
    {"id": "PB-04", "title": "Mountain Rescue", "category": "terrain"},
    {"id": "PB-05", "title": "Industrial Fire Response", "category": "fire"},
    {"id": "PB-06", "title": "Forest Fire Response", "category": "fire"},
    {"id": "PB-07", "title": "Hospital Surge Management", "category": "medical"},
    {"id": "PB-08", "title": "Mass Medical Transport", "category": "medical"},
    {"id": "PB-09", "title": "Drinking Water Distribution", "category": "logistics"},
    {"id": "PB-10", "title": "Food Relief Distribution", "category": "logistics"},
    {"id": "PB-11", "title": "Shelter Activation", "category": "shelter"},
    {"id": "PB-12", "title": "Drone-Assisted Search", "category": "drone"},
    {"id": "PB-13", "title": "Drone Medical Delivery", "category": "drone"},
    {"id": "PB-14", "title": "Drone Swarm Area Scan", "category": "swarm"},
    {"id": "PB-15", "title": "Communication Relay Deployment", "category": "comms"},
    {"id": "PB-16", "title": "Bridge Failure Response", "category": "infrastructure"},
    {"id": "PB-17", "title": "Power Grid Failure Response", "category": "infrastructure"},
    {"id": "PB-18", "title": "Communication Blackout Response", "category": "comms"},
    {"id": "PB-19", "title": "Multi-Country Humanitarian Assistance", "category": "mutual_aid"},
    {"id": "PB-20", "title": "Post-Disaster Recovery", "category": "recovery"},
    {"id": "PB-21", "title": "Emergency Resource Reallocation", "category": "logistics"},
    {"id": "PB-22", "title": "Drone Fleet Recovery", "category": "drone"},
    {"id": "PB-23", "title": "Mass Evacuation", "category": "evacuation"},
    {"id": "PB-24", "title": "Flood-to-Hospital Logistics Recovery", "category": "medical"},
]


class ApprovalEngine:
    """Permission-aware operational approval, staleness validation, execution, and audit log."""

    def __init__(self, world: GlobalWorldEngine) -> None:
        self.world = world
        self.approvals: Dict[str, ApprovalRequest] = {}
        self.audit_log: deque = deque(maxlen=5000)
        self._approval_lock = threading.RLock()

    def _log_audit(self, action: str, actor: str, details: Dict[str, Any]) -> None:
        self.audit_log.append({
            "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": utc_now_iso(),
            "world_version": self.world.event_bus.world_version,
            "action": action,
            "actor": actor,
            "details": details,
        })

    def _validate_parameters(self, operation_type: str, parameters: Dict[str, Any]) -> None:
        allowed = {
            "inject_disaster": {"country_id", "disaster_type", "name", "lat", "lon", "severity", "radius_km", "wind_kph", "rainfall_mm_hr", "require_approval"},
            "deploy_swarm": {"country_id", "drone_count", "mode", "formation", "objective", "name", "lat", "lon", "coverage_radius_km"},
            "dispatch_ambulances": {"count"},
            "cross_country_aid": {"target_country_id", "donor_country_id", "resource_type", "quantity"},
            "destroy_drone": {"drone_id", "failure_type"},
            "comprehensive_rescue_plan": {"drones", "ambulances", "plan_id"},
        }.get(operation_type, set())
        unknown = set(parameters) - allowed
        if unknown:
            raise ValueError(f"Unsupported approval parameters: {', '.join(sorted(unknown))}")

        def number(name: str, low: float, high: float) -> None:
            if name not in parameters:
                return
            value = float(parameters[name])
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")

        def integer(name: str, low: int, high: int) -> None:
            if name not in parameters:
                return
            value = int(parameters[name])
            if not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")

        if operation_type == "inject_disaster":
            DisasterType(parameters.get("disaster_type", "FLOOD"))
            number("severity", 0.1, 1.0)
            number("radius_km", 1.0, 50.0)
            number("wind_kph", 0.0, 500.0)
            number("rainfall_mm_hr", 0.0, 1000.0)
        elif operation_type == "deploy_swarm":
            integer("drone_count", 1, 30)
            SwarmMode(parameters.get("mode", "AREA_SCAN"))
            SwarmFormation(parameters.get("formation", "SEARCH_GRID"))
            number("coverage_radius_km", 0.5, 50.0)
        elif operation_type == "dispatch_ambulances":
            integer("count", 1, 50)
        elif operation_type == "cross_country_aid":
            integer("quantity", 1, 50)
            if parameters.get("resource_type", "ambulances") not in {"ambulances", "drones", "food"}:
                raise ValueError("resource_type must be ambulances, drones, or food")
        elif operation_type == "comprehensive_rescue_plan":
            integer("drones", 1, 30)
            integer("ambulances", 1, 50)

    def _validate_approval(self, req: ApprovalRequest) -> None:
        expires_at = datetime.fromisoformat(req.expires_at)
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError(f"Approval {req.approval_id} has expired")
        drift = self.world.event_bus.world_version - req.world_version_at_proposal
        if drift > MAX_APPROVAL_WORLD_VERSION_DRIFT:
            raise ValueError(f"Approval {req.approval_id} is stale; prepare a new request")
        self._validate_parameters(req.operation_type, req.parameters or {})

    def _prune_approvals(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            aid for aid, req in self.approvals.items()
            if datetime.fromisoformat(req.expires_at) <= now
        ]
        for aid in expired:
            self.approvals.pop(aid, None)
        while len(self.approvals) >= MAX_APPROVALS:
            self.approvals.pop(next(iter(self.approvals)), None)

    def create_approval_request(
        self,
        operation_type: str,
        title: str,
        description: str,
        country_id: Optional[str],
        parameters: Dict[str, Any],
        required_resources: Optional[Dict[str, Any]] = None,
        affected_locations: Optional[List[str]] = None,
        affected_entities: Optional[List[str]] = None,
        expected_outcomes: Optional[List[str]] = None,
        operational_risks: Optional[List[str]] = None,
    ) -> ApprovalRequest:
        aid = f"APR-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        self._prune_approvals()
        self._validate_parameters(operation_type, parameters or {})
        req = ApprovalRequest(
            approval_id=aid,
            operation_type=operation_type,
            title=title,
            description=description,
            country_id=country_id,
            affected_locations=affected_locations or [],
            affected_entities=affected_entities or [],
            required_resources=required_resources or {},
            expected_outcomes=expected_outcomes or [],
            operational_risks=operational_risks or [],
            safety_checks={"authorization_required": True, "simulation_only_verified": True, "resource_bounds_checked": True},
            parameters=dict(parameters or {}),
            world_version_at_proposal=self.world.event_bus.world_version,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=30)).isoformat(),
            status="PENDING",
        )
        self.approvals[aid] = req
        self._log_audit("approval.requested", "jarvis_orchestrator", {"approval_id": aid, "operation_type": operation_type})
        self.world.event_bus.emit(
            "approval.requested",
            payload=to_dict(req),
            country_id=country_id,
            entity_id=aid,
            source="approval_engine",
            category="approval",
            bump_version=False,
        )
        return req

    def list_approvals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        items = list(self.approvals.values())
        if status:
            items = [a for a in items if a.status == status.upper()]
        return [to_dict(a) for a in reversed(items)]

    def modify_pending(self, approval_id: str, updates: Dict[str, Any], actor: str = "operator") -> ApprovalRequest:
        with self._approval_lock:
            if not approval_id or approval_id not in self.approvals:
                raise ValueError(f"Unknown approval_id: {approval_id}")
            if not isinstance(updates, dict):
                raise ValueError("updates must be a JSON object")
            req = self.approvals[approval_id]
            if req.status not in ("PENDING", "MODIFIED"):
                raise ValueError(f"Cannot modify approval {approval_id} in status {req.status}")
            merged = {**(req.parameters or {}), **updates}
            self._validate_parameters(req.operation_type, merged)
            req.parameters = merged
            req.status = "PENDING"
            req.world_version_at_proposal = self.world.event_bus.world_version
            req.decision_note = f"Modified by {actor}"
            self._log_audit("approval.modified", actor, {"approval_id": approval_id, "updates": updates})
            return req

    def reject(self, approval_id: str, actor: str = "operator", reason: str = "Rejected by operator") -> ApprovalRequest:
        if not approval_id or approval_id not in self.approvals:
            raise ValueError(f"Unknown approval_id: {approval_id}")
        req = self.approvals[approval_id]
        if req.status not in ("PENDING", "MODIFIED", "APPROVED"):
            raise ValueError(f"Cannot reject approval {approval_id} in status {req.status}")
        req.status = "REJECTED"
        req.decided_by = actor
        req.decision_note = reason
        self._log_audit("approval.rejected", actor, {"approval_id": approval_id, "reason": reason})
        self.world.event_bus.emit("approval.rejected", payload=to_dict(req), country_id=req.country_id, entity_id=approval_id, category="approval", bump_version=False)
        return req

    def approve_and_execute(self, approval_id: str, actor: str = "operator", auto_execute: bool = True) -> ApprovalRequest:
        with self._approval_lock:
            if not approval_id or approval_id not in self.approvals:
                raise ValueError(f"Unknown approval_id: {approval_id}")
            req = self.approvals[approval_id]
            if req.status not in ("PENDING", "APPROVED"):
                raise ValueError(f"Approval {approval_id} cannot be approved from status {req.status}")
            if req.status == "APPROVED" and not auto_execute:
                raise ValueError(f"Approval {approval_id} is already APPROVED")
            self._validate_approval(req)

            if req.status == "PENDING":
                req.status = "APPROVED"
                req.decided_by = actor
                self._log_audit("approval.granted", actor, {"approval_id": approval_id, "operation_type": req.operation_type})
                self.world.event_bus.emit("approval.granted", payload=to_dict(req), country_id=req.country_id, entity_id=approval_id, category="approval", bump_version=False)

            if auto_execute:
                return self._execute_approved_locked(approval_id, actor=actor)
            return req

    def execute_approved(self, approval_id: str, actor: str = "operator") -> ApprovalRequest:
        with self._approval_lock:
            return self._execute_approved_locked(approval_id, actor=actor)

    def _execute_approved_locked(self, approval_id: str, actor: str = "operator") -> ApprovalRequest:
        if not approval_id or approval_id not in self.approvals:
            raise ValueError(f"Unknown approval_id: {approval_id}")
        req = self.approvals[approval_id]
        if req.status != "APPROVED":
            raise ValueError(f"Operation {approval_id} must be APPROVED before execution (current: {req.status})")

        op = req.operation_type
        p = req.parameters or {}
        cid = req.country_id or p.get("country_id") or self.world.selected_country_id
        if cid not in self.world.countries:
            raise ValueError(f"Unknown country_id: {cid}")
        self._validate_approval(req)
        req.status = "EXECUTING"

        with self.world._mutation_lock:
            result: Dict[str, Any] = {}
            try:
                if op == "inject_disaster":
                    dtype = DisasterType(p.get("disaster_type", "FLOOD"))
                    ev = self.world.inject_disaster(
                        country_id=cid,
                        disaster_type=dtype,
                        name=p.get("name"),
                        severity=float(p.get("severity", 0.75)),
                        radius_km=float(p.get("radius_km", 10.0)),
                        wind_kph=float(p.get("wind_kph", 65.0)),
                        rainfall_mm_hr=float(p.get("rainfall_mm_hr", 50.0)),
                    )
                    result = {"disaster_event": to_dict(ev)}

                elif op == "deploy_swarm":
                    count = max(1, int(p.get("drone_count", 6)))
                    mode = SwarmMode(p.get("mode", "AREA_SCAN"))
                    formation = SwarmFormation(p.get("formation", "SEARCH_GRID"))
                    avail = [
                        d for d in self.world.drones.values()
                        if d.country_id == cid and d.status == "AVAILABLE" and d.battery_pct >= 35.0
                    ]
                    avail.sort(key=lambda d: d.battery_pct, reverse=True)
                    chosen = avail[:count]
                    if not chosen:
                        raise ValueError("No available drones meet the swarm battery requirement")
                    sw_id = f"SWARM-{uuid.uuid4().hex[:6].upper()}"
                    c_center = self.world.countries[cid].center
                    t_loc = GeoPoint(lat=float(p.get("lat", c_center.lat)), lon=float(p.get("lon", c_center.lon)), elevation_m=95.0)
                    swarm = SwarmOperation(
                        swarm_id=sw_id,
                        country_id=cid,
                        name=p.get("name", f"{mode.value} Swarm ({cid})"),
                        mode=mode,
                        formation=formation,
                        drone_ids=[d.drone_id for d in chosen],
                        target_center=t_loc,
                        coverage_radius_km=float(p.get("coverage_radius_km", 4.0)),
                        status="ACTIVE",
                        created_at=utc_now_iso(),
                        objective=p.get("objective", "Authorized disaster response swarm"),
                    )
                    self.world.swarms[sw_id] = swarm
                    for d in chosen:
                        d.status = "IN_FLIGHT"
                        d.swarm_id = sw_id
                        d.assigned_mission_id = sw_id
                        d.altitude_m = 95.0
                    self.world.event_bus.emit("swarm.started", payload=to_dict(swarm), country_id=cid, entity_id=sw_id, category="swarm")
                    result = {"swarm": to_dict(swarm), "deployed_drones": len(chosen)}

                elif op == "dispatch_ambulances":
                    count = max(1, int(p.get("count", 6)))
                    avail = [a for a in self.world.ambulances.values() if a.country_id == cid and a.status == AmbulanceStatus.AVAILABLE]
                    hospitals = [h for h in self.world.hospitals.values() if h.country_id == cid and h.available_beds > 0]
                    if not hospitals:
                        raise ValueError("No hospital with available beds can receive ambulances")
                    if not avail:
                        raise ValueError("No available ambulances for dispatch")
                    hospitals.sort(key=lambda h: h.available_beds, reverse=True)
                    dispatched_ids = []
                    for idx, amb in enumerate(avail[:count]):
                        amb.status = AmbulanceStatus.DISPATCHED
                        if hospitals:
                            amb.destination_hospital_id = hospitals[idx % len(hospitals)].hospital_id
                        dispatched_ids.append(amb.ambulance_id)
                    self.world.event_bus.emit("ambulance.dispatched", payload={"count": len(dispatched_ids), "ambulance_ids": dispatched_ids}, country_id=cid, category="medical")
                    result = {"dispatched_ambulances": dispatched_ids, "count": len(dispatched_ids)}

                elif op == "cross_country_aid":
                    donor_id = p.get("donor_country_id")
                    if not donor_id or donor_id not in self.world.countries:
                        raise ValueError(f"Unknown donor_country_id: {donor_id}")
                    res_type = p.get("resource_type", "ambulances")
                    qty = max(1, int(p.get("quantity", 4)))
                    transferred = []
                    if res_type == "ambulances":
                        avail = [a for a in self.world.ambulances.values() if a.country_id == donor_id and a.status == AmbulanceStatus.AVAILABLE]
                        for amb in avail[:qty]:
                            amb.country_id = cid
                            amb.home_station = f"Mutual Aid from {donor_id}"
                            transferred.append(amb.ambulance_id)
                    elif res_type == "drones":
                        avail = [d for d in self.world.drones.values() if d.country_id == donor_id and d.status == "AVAILABLE"]
                        for dr in avail[:qty]:
                            dr.country_id = cid
                            transferred.append(dr.drone_id)
                    else:
                        # Food package transfer with strict inventory check
                        donor_whs = [w for w in self.world.warehouses.values() if w.country_id == donor_id]
                        recv_whs = [w for w in self.world.warehouses.values() if w.country_id == cid]
                        if donor_whs and recv_whs:
                            amt = min(qty, donor_whs[0].food_packages)
                            donor_whs[0].food_packages -= amt
                            recv_whs[0].food_packages += amt
                            transferred.append(f"{amt}_food_packages")
                    if not transferred:
                        raise ValueError("No requested resources are available for transfer")
                    self.world.event_bus.emit("mutual_aid.executed", payload={"from": donor_id, "to": cid, "resource_type": res_type, "transferred": transferred}, country_id=cid, category="logistics")
                    result = {"donor_country_id": donor_id, "recipient_country_id": cid, "resource_type": res_type, "transferred": transferred}

                elif op == "destroy_drone":
                    drone_id = p.get("drone_id")
                    if not drone_id or drone_id not in self.world.drones:
                        raise ValueError(f"Unknown drone_id: {drone_id}")
                    result = self.world.inject_drone_failure(drone_id, p.get("failure_type", "COMPLETE_DRONE_DESTRUCTION"))

                elif op == "comprehensive_rescue_plan":
                    drone_count = int(p.get("drones", 8))
                    ambulance_count = int(p.get("ambulances", 10))
                    if not any(d.country_id == cid and d.status == "AVAILABLE" and d.battery_pct >= 35.0 for d in self.world.drones.values()):
                        raise ValueError("No available drones meet the rescue-plan battery requirement")
                    if not any(a.country_id == cid and a.status == AmbulanceStatus.AVAILABLE for a in self.world.ambulances.values()):
                        raise ValueError("No available ambulances for the rescue plan")
                    if not any(h.country_id == cid and h.available_beds > 0 for h in self.world.hospitals.values()):
                        raise ValueError("No hospital with available beds for the rescue plan")
                    # Execute coordinated multi-subsystem rescue plan (swarm + ambulances + shelter activation)
                    sw_res = self.approve_and_execute(
                        self.create_approval_request("deploy_swarm", "Sub-Op: Swarm", "Swarm", cid, {"drone_count": drone_count, "mode": "COORDINATED_RESCUE", "formation": "SEARCH_GRID"}).approval_id,
                        actor=actor,
                    )
                    amb_res = self.approve_and_execute(
                        self.create_approval_request("dispatch_ambulances", "Sub-Op: Ambulances", "Ambulances", cid, {"count": ambulance_count}).approval_id,
                        actor=actor,
                    )
                    activated_shelters = []
                    for s in self.world.shelters.values():
                        if s.country_id == cid and s.status == "STANDBY":
                            s.status = "ACTIVE"
                            activated_shelters.append(s.shelter_id)
                    result = {
                        "swarm": sw_res.execution_result,
                        "ambulances": amb_res.execution_result,
                        "activated_shelters": activated_shelters,
                    }

                else:
                    result = {"status": "executed_generic", "parameters": p}
            except Exception:
                req.status = "APPROVED"
                raise

        req.status = "EXECUTED"
        req.execution_result = result
        self._log_audit("operation.executed", actor, {"approval_id": approval_id, "operation_type": op, "result": result})
        self.world.event_bus.emit(
            "operation.executed",
            payload={"approval_id": approval_id, "operation_type": op, "result": result},
            country_id=cid,
            entity_id=approval_id,
            category="execution",
            bump_version=True,
        )
        return req

    def generate_adapted_plan(self, country_id: str, playbook_id: str = "PB-03") -> Dict[str, Any]:
        if country_id not in self.world.countries:
            raise ValueError(f"Unknown country_id: {country_id}")
        pb = next((x for x in PLAYBOOK_CATALOG if x["id"] == playbook_id), PLAYBOOK_CATALOG[0])
        amb = self.world.calculate_ambulance_requirements(country_id)
        res = self.world.calculate_resource_requirements(country_id)
        avail_drones = [d for d in self.world.drones.values() if d.country_id == country_id and d.status == "AVAILABLE"]
        shelters = [s for s in self.world.shelters.values() if s.country_id == country_id]

        proposed_drones = min(len(avail_drones), max(4, min(12, len(avail_drones))))
        proposed_amb = min(amb["available_ambulances"], max(2, amb["recommended_operational_fleet"]))

        return {
            "plan_id": f"PLAN-{uuid.uuid4().hex[:6].upper()}",
            "playbook": pb,
            "country_id": country_id,
            "country_name": self.world.countries[country_id].name,
            "world_version": self.world.event_bus.world_version,
            "sim_time_s": round(self.world.sim_time_s, 1),
            "population_at_risk": res["exposed_population"],
            "evacuation_demand": res["evacuation_shelter_demand"],
            "proposed_resources": {
                "drones": proposed_drones,
                "ambulances": proposed_amb,
                "ambulance_deficit": amb["ambulance_deficit"],
                "hospitals_available_beds": amb["available_hospital_beds"],
                "shelters_to_activate": len([s for s in shelters if s.accessible]),
                "food_packages_24h": res["food_packages"]["needed"],
                "water_liters_24h": res["water_liters"]["needed"],
            },
            "staged_timeline": [
                {"t": "T+00", "action": "Activate emergency coordination & alert exposed districts"},
                {"t": "T+05", "action": f"Deploy {proposed_drones} drones in SEARCH_GRID & medical delivery modes"},
                {"t": "T+10", "action": f"Dispatch {proposed_amb} ambulances to priority triage sectors"},
                {"t": "T+15", "action": f"Activate {len(shelters)} relief shelters & reserve warehouse food/water stock"},
                {"t": "T+30", "action": "Re-evaluate hospital bed load, drone battery reserves, and mutual aid deficits"},
            ],
            "shortages_and_risks": res["shortage_warnings"] + (
                [f"Ambulance deficit of {amb['ambulance_deficit']} units — consider Seven-Country Mutual Aid."]
                if amb["ambulance_deficit"] > 0 else []
            ),
            "requires_operator_approval": True,
        }
