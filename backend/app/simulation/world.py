from __future__ import annotations
import copy
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import CONFIG, DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_NAME, DEFAULT_SEED
from app.core.models import (
    BuildingDamageState, CityEnvironment, DisasterEvent, DisasterStatus, DisasterType,
    DroneState, DroneStatus, FailureType, HazardZone,
    OptimizationResult, QuantumMetrics, RescueTask, SimulatedSurvivor,
    SimulationEvent, SimulationStatus, StrategyMetrics, StrategyType,
    SurvivorStatus, TaskPriority, TaskStatus
)
from app.disasters.manager import DisasterLifecycleManager
from app.disasters.survivor_generator import update_survivors_health
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.classical_solver import solve_classical
from app.optimization.feasibility import is_drone_eligible_for_task
from app.optimization.greedy_solver import solve_greedy
from app.optimization.hybrid_solver import solve_hybrid
from app.optimization.quantum_solver import solve_quantum_qaoa
from app.optimization.score_engine import compute_strategy_score
from app.simulation.battery_model import compute_segment_energy_wh
from app.simulation.city_generator import generate_city
from app.simulation.charging_manager import ChargingPadManager
from app.simulation.collision_manager import resolve_airspace_conflicts
from app.recovery.failure_detector import scan_fleet_anomalies
from app.simulation.drone_manager import generate_fleet
from app.simulation.serializers import (
    deserialize_world as _deserialize_world,
    serialize_city as _serialize_city,
    serialize_disaster as _serialize_disaster,
    serialize_drone as _serialize_drone,
    serialize_event as _serialize_event,
    serialize_experiment as _serialize_experiment,
    serialize_task as _serialize_task,
    serialize_world as _serialize_world,
)
from app.simulation.task_manager import generate_tasks
from app.storage.event_journal import EventJournal


class SimulationWorld:
    def __init__(
        self,
        run_id: Optional[str] = None,
        strategy: StrategyType = StrategyType.HYBRID,
        seed: int = DEFAULT_SEED,
        scenario_id: str = DEFAULT_SCENARIO_ID,
        scenario_name: str = DEFAULT_SCENARIO_NAME,
        city_density: float = 1.0,
        building_density: float = 1.0,
        journal: Optional[EventJournal] = None,
    ):
        self.run_id: str = run_id or f"RUN-{uuid.uuid4().hex[:6].upper()}"
        self.strategy: StrategyType = strategy
        self.seed: int = seed
        self.status: SimulationStatus = SimulationStatus.READY
        self.state_version: int = 1
        self.sim_time_s: float = 0.0
        self.speed_multiplier: float = 1.0
        self.started_at_iso: str = datetime.now(timezone.utc).isoformat()
        self.wall_start_ts: float = time.perf_counter()
        self.journal: Optional[EventJournal] = journal

        self.city: CityEnvironment = generate_city(
            seed=seed, scenario_id=scenario_id, scenario_name=scenario_name,
            city_density=city_density, building_density=building_density,
        )
        self.grid: SpatialAirspaceGrid = SpatialAirspaceGrid(self.city)
        self.charging: ChargingPadManager = ChargingPadManager(self.city)
        self.drones: Dict[str, DroneState] = generate_fleet(self.city, seed)
        self.tasks: Dict[str, RescueTask] = generate_tasks(self.city, seed, count=50)
        self.disasters: DisasterLifecycleManager = DisasterLifecycleManager(seed=seed)
        self.survivors: Dict[str, SimulatedSurvivor] = {}

        self.events: List[SimulationEvent] = []
        self.optimization_history: List[OptimizationResult] = []
        self.route_history: List[Dict[str, Any]] = []
        self.failure_logs: List[Dict[str, Any]] = []
        self.reassignment_logs: List[Dict[str, Any]] = []
        self.recovery_arcs: List[Dict[str, Any]] = []
        self.replay_frames: List[Dict[str, Any]] = []
        self.analytics_series: List[Dict[str, Any]] = []

        self.planning_complete: bool = False
        self.replanning_count: int = 0
        self.tasks_recovered: int = 0
        self.tasks_needing_recovery_total: int = 0
        self.airspace_conflicts_total: int = 0
        self.last_solver_runtime_ms: float = 0.0
        self.last_quantum_metrics: Optional[QuantumMetrics] = None
        self.last_error: Optional[str] = None
        self.feasible: bool = True

        self.log_event("system", "world_initialized", f"Disaster environment '{scenario_name}' initialized (seed={seed}).")
        self.log_event("drone", "fleet_registered", f"{len(self.drones)} autonomous rescue drones registered across 4 classes.")
        self.log_event("task", "tasks_generated", f"{len(self.tasks)} rescue tasks generated (12 critical, 15 high, 15 medium, 8 low).")

    def bump_version(self) -> int:
        self.state_version += 1
        return self.state_version

    def clone_for_strategy(self, strategy: StrategyType, run_id: str) -> "SimulationWorld":
        saved_journal = self.journal
        self.journal = None
        try:
            cloned = copy.deepcopy(self)
        finally:
            self.journal = saved_journal
        cloned.run_id = run_id
        cloned.strategy = strategy
        cloned.wall_start_ts = time.perf_counter()
        cloned.journal = None
        cloned.log_event("system", "snapshot_cloned", f"Isolated benchmark instance created for strategy '{strategy.value.upper()}'.")
        return cloned

    def log_event(
        self,
        category: str,
        event_type: str,
        message: str,
        entity_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        operation_id: Optional[str] = None,
    ) -> SimulationEvent:
        ev = SimulationEvent(
            id=f"EV-{uuid.uuid4().hex[:8].upper()}",
            run_id=self.run_id,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            sim_time_s=round(self.sim_time_s, 1),
            category=category,
            event_type=event_type,
            message=message,
            entity_id=entity_id,
            state_version=self.state_version,
            operation_id=operation_id,
            payload=payload or {},
        )
        self.events.append(ev)
        if len(self.events) > 1500:
            self.events = self.events[-1500:]
        if self.journal is not None:
            try:
                self.journal.record(category, ev.model_dump())
            except Exception:
                pass
        return ev

    # ── Serialization Methods ─────────────────────────────────────────
    def serialize_world(self) -> Dict[str, Any]:
        return _serialize_world(self)

    @classmethod
    def deserialize_world(cls, snapshot: Dict[str, Any]) -> "SimulationWorld":
        return _deserialize_world(snapshot, cls)

    def serialize_city(self) -> Dict[str, Any]:
        return _serialize_city(self)

    def serialize_drone(self, drone_id: str) -> Optional[Dict[str, Any]]:
        d = self.drones.get(drone_id)
        return _serialize_drone(d) if d else None

    def serialize_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        t = self.tasks.get(task_id)
        return _serialize_task(t) if t else None

    def serialize_disaster(self, event_id: str) -> Optional[Dict[str, Any]]:
        ev = self.disasters.events.get(event_id)
        return _serialize_disaster(ev) if ev else None

    def serialize_event(self, ev: SimulationEvent) -> Dict[str, Any]:
        return _serialize_event(ev)

    def serialize_experiment(self, leaderboard: Optional[List[StrategyMetrics]] = None) -> Dict[str, Any]:
        return _serialize_experiment(self, leaderboard)

    # ── Disaster Lifecycle API ────────────────────────────────────────
    def _revalidate_routes_for_region(self, x: float, z: float, radius: float) -> int:
        self.grid.rebuild_region(x, z, radius)
        rerouted = 0
        for d in self.drones.values():
            if d.status == DroneStatus.IN_FLIGHT and d.current_route and not self.grid.is_route_valid(d.current_route):
                goal = d.current_route.waypoints[-1]
                new_rt = self.grid.plan_route(
                    start=d.position, goal=goal, drone=d,
                    strategy=self.strategy.value, task_id=d.active_task_id, payload_kg=d.current_payload_kg,
                )
                new_rt.replan_count = d.current_route.replan_count + 1
                d.current_route = new_rt
                d.waypoint_index = 1
                rerouted += 1
                self.route_history.append(new_rt.model_dump())
        if rerouted > 0:
            self.replanning_count += 1
            self.log_event("replanning", "hazard_reroute", f"Disaster hazard invalidated {rerouted} flight path(s); safe detours computed.")
        return rerouted

    def create_disaster(
        self,
        disaster_type: DisasterType,
        x: float,
        z: float,
        *,
        y: float = 0.0,
        severity: float = 0.75,
        affected_radius: float = 260.0,
        duration: float = 900.0,
        propagation_speed: float = 1.0,
        start_delay: float = 0.0,
        auto_start: bool = True,
        seed: Optional[int] = None,
        magnitude: float = 0.0,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ver = self.bump_version()
        ev, new_survivors = self.disasters.create_disaster(
            self.city,
            self.survivors,
            disaster_type=disaster_type,
            x=x,
            z=z,
            y=y,
            severity=severity,
            affected_radius=affected_radius,
            duration=duration,
            propagation_speed=propagation_speed,
            start_delay=start_delay,
            sim_time_s=self.sim_time_s,
            auto_start=auto_start,
            seed=seed,
            magnitude=magnitude,
            state_version=ver,
        )
        rerouted = 0
        if ev.status == DisasterStatus.ACTIVE:
            rerouted = self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event(
            "disaster",
            f"disaster_{ev.type.value}_created",
            f"Disaster {ev.event_id} ({ev.type.value}) created at ({ev.epicentre.x:.0f}, {ev.epicentre.z:.0f}) with severity {ev.severity}. {len(new_survivors)} simulated survivor(s) identified in zone.",
            entity_id=ev.event_id,
            operation_id=operation_id,
            payload={"event_id": ev.event_id, "type": ev.type.value, "severity": ev.severity, "survivors_generated": len(new_survivors)},
        )
        return {
            "disaster": ev.model_dump(),
            "new_survivors": [s.model_dump() for s in new_survivors],
            "rerouted_drones": rerouted,
            "state_version": self.state_version,
            "run_id": self.run_id,
            "simulation_time": self.sim_time_s,
            "event_id": log.id,
            "operation_id": operation_id,
        }

    def start_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev, new_survivors = self.disasters.start_disaster(self.city, self.survivors, event_id, self.sim_time_s)
        ev.state_version = self.state_version
        rerouted = self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_started", f"Disaster {event_id} started.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "new_survivors": [s.model_dump() for s in new_survivors], "rerouted_drones": rerouted, "state_version": self.state_version, "event_id": log.id}

    def pause_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.pause_disaster(event_id, self.sim_time_s)
        ev.state_version = self.state_version
        log = self.log_event("disaster", "disaster_paused", f"Disaster {event_id} paused.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "state_version": self.state_version, "event_id": log.id}

    def resume_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.resume_disaster(self.city, event_id, self.sim_time_s)
        ev.state_version = self.state_version
        log = self.log_event("disaster", "disaster_resumed", f"Disaster {event_id} resumed.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "state_version": self.state_version, "event_id": log.id}

    def stop_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.stop_disaster(self.city, event_id, self.sim_time_s)
        ev.state_version = self.state_version
        self.grid.rebuild_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_stopped", f"Disaster {event_id} stopped and resolved.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "state_version": self.state_version, "event_id": log.id}

    def remove_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        ev = self.disasters.events.get(event_id)
        ok = self.disasters.remove_disaster(self.city, event_id, self.sim_time_s)
        if not ok:
            raise KeyError(f"Disaster {event_id} not found")
        self.bump_version()
        if ev:
            self.grid.rebuild_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_removed", f"Disaster {event_id} removed.", entity_id=event_id, operation_id=operation_id)
        return {"removed": True, "disaster_id": event_id, "state_version": self.state_version, "event_id": log.id}

    def reset_disaster(self, event_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.reset_disaster(self.city, event_id, self.sim_time_s)
        ev.state_version = self.state_version
        self.grid.rebuild_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_reset", f"Disaster {event_id} reset.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "state_version": self.state_version, "event_id": log.id}

    def adjust_disaster_severity(self, event_id: str, delta: float, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.adjust_severity(self.city, event_id, delta, self.sim_time_s)
        ev.state_version = self.state_version
        log = self.log_event("disaster", "disaster_severity_changed", f"Disaster {event_id} severity changed to {ev.severity}.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "state_version": self.state_version, "event_id": log.id}

    def expand_disaster_radius(self, event_id: str, delta_radius: float, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.expand_radius(self.city, event_id, delta_radius, self.sim_time_s)
        ev.state_version = self.state_version
        rerouted = self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_radius_expanded", f"Disaster {event_id} radius expanded to {ev.affected_radius}m.", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "rerouted_drones": rerouted, "state_version": self.state_version, "event_id": log.id}

    def move_disaster_epicentre(self, event_id: str, x: float, z: float, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        ev = self.disasters.move_epicentre(self.city, event_id, x, z, self.sim_time_s)
        ev.state_version = self.state_version
        rerouted = self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "disaster_moved", f"Disaster {event_id} moved to ({x:.0f}, {z:.0f}).", entity_id=event_id, operation_id=operation_id)
        return {"disaster": ev.model_dump(), "rerouted_drones": rerouted, "state_version": self.state_version, "event_id": log.id}

    def trigger_aftershock(self, event_id: str, scale: float = 0.65, operation_id: Optional[str] = None) -> Dict[str, Any]:
        self.bump_version()
        res = self.disasters.trigger_aftershock(self.city, self.survivors, event_id, self.sim_time_s, scale=scale)
        ev = res["event"]
        ev.state_version = self.state_version
        rerouted = self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "aftershock_triggered", f"Aftershock #{ev.aftershock_count} triggered on {event_id}.", entity_id=event_id, operation_id=operation_id)
        return {
            "disaster": ev.model_dump(),
            "cascades": [c.model_dump() for c in res["cascades"]],
            "rerouted_drones": rerouted,
            "state_version": self.state_version,
            "event_id": log.id,
        }

    def load_disaster_preset(self, preset_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        ver = self.bump_version()
        events, surs = self.disasters.load_preset(self.city, self.survivors, preset_id, self.sim_time_s, state_version=ver)
        rerouted = 0
        for ev in events:
            if ev.status == DisasterStatus.ACTIVE:
                rerouted += self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "preset_loaded", f"Disaster preset '{preset_id}' activated ({len(events)} hazard(s), {len(surs)} simulated survivor(s)).", operation_id=operation_id)
        return {
            "preset_id": preset_id,
            "disasters": [e.model_dump() for e in events],
            "new_survivors": [s.model_dump() for s in surs],
            "rerouted_drones": rerouted,
            "state_version": self.state_version,
            "event_id": log.id,
        }

    def create_random_disaster_scenario(self, seed: Optional[int] = None, operation_id: Optional[str] = None) -> Dict[str, Any]:
        ver = self.bump_version()
        events, surs = self.disasters.create_random_scenario(self.city, self.survivors, self.sim_time_s, seed=seed, state_version=ver)
        for ev in events:
            if ev.status == DisasterStatus.ACTIVE:
                self._revalidate_routes_for_region(ev.epicentre.x, ev.epicentre.z, ev.affected_radius)
        log = self.log_event("disaster", "random_scenario_created", f"Random multi-hazard scenario triggered ({len(events)} event(s)).", operation_id=operation_id)
        return {
            "disasters": [e.model_dump() for e in events],
            "new_survivors": [s.model_dump() for s in surs],
            "state_version": self.state_version,
            "event_id": log.id,
        }

    # ── Survivor Operations ───────────────────────────────────────────
    def search_area_for_survivors(self, x: float, z: float, radius: float = 400.0) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        changed = False
        for s in self.survivors.values():
            dist = math.hypot(s.position[0] - x, s.position[2] - z)
            if dist <= radius:
                if not s.detected:
                    s.detected = True
                    changed = True
                if s.status == SurvivorStatus.UNCONFIRMED:
                    s.status = SurvivorStatus.DETECTED
                    changed = True
                s.last_updated_sim_time = round(self.sim_time_s, 1)
                found.append(s.model_dump())
        if changed:
            self.bump_version()
            self.log_event("survivor", "area_search_completed", f"Thermal scan around ({x:.0f}, {z:.0f}, r={radius:.0f}m) detected {len(found)} simulated survivor(s).")
        return found

    def verify_survivor_location(self, survivor_id: str) -> Dict[str, Any]:
        s = self.survivors.get(survivor_id)
        if not s:
            raise KeyError(f"Survivor {survivor_id} not found")
        s.detected = True
        if s.status in (SurvivorStatus.UNCONFIRMED, SurvivorStatus.DETECTED):
            s.status = SurvivorStatus.LOCATED
        s.last_updated_sim_time = round(self.sim_time_s, 1)
        self.bump_version()
        self.log_event("survivor", "survivor_verified", f"Simulated survivor {survivor_id} location verified at {s.position}.", entity_id=survivor_id)
        return s.model_dump()

    def prioritize_survivors(self) -> List[Dict[str, Any]]:
        order = {TaskPriority.CRITICAL: 0, TaskPriority.HIGH: 1, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 3}
        ranked = sorted(
            self.survivors.values(),
            key=lambda s: (
                s.status in (SurvivorStatus.EVACUATED, SurvivorStatus.MEDICAL_ASSISTANCE),
                order.get(s.priority, 4),
                s.health_level,
                -s.exposure_level,
            ),
        )
        return [s.model_dump() for s in ranked]

    # ── Explicit Drone & Route Operations ─────────────────────────────
    def assign_drone_to_task(self, drone_id: str, task_id: str, operation_id: Optional[str] = None) -> Dict[str, Any]:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"ok": False, "error": f"Drone {drone_id} not found.", "state_version": self.state_version}
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": f"Task {task_id} not found.", "state_version": self.state_version}
        if task.status == TaskStatus.COMPLETED:
            return {"ok": False, "error": f"Task {task_id} is already completed.", "state_version": self.state_version}
        ok, reason, route = is_drone_eligible_for_task(drone, task, self.city, self.grid, strategy=self.strategy.value)
        if not ok or route is None:
            return {"ok": False, "error": reason, "drone_id": drone_id, "task_id": task_id, "route_feasible": False, "state_version": self.state_version}

        if task.assigned_drone_id and task.assigned_drone_id != drone_id:
            prev = self.drones.get(task.assigned_drone_id)
            if prev and task_id in prev.assigned_task_ids:
                prev.assigned_task_ids.remove(task_id)

        self.bump_version()
        task.assigned_drone_id = drone_id
        task.status = TaskStatus.ASSIGNED
        task.assigned_at_sim_s = self.sim_time_s
        task.unassigned_reason = None
        if task_id not in drone.assigned_task_ids:
            drone.assigned_task_ids.insert(0, task_id)
        if task.survivor_id and task.survivor_id in self.survivors:
            self.survivors[task.survivor_id].assigned_task_id = task_id
            self.survivors[task.survivor_id].status = SurvivorStatus.RESCUE_PENDING
        if drone.status == DroneStatus.AVAILABLE:
            self._dispatch_next_task(drone)
        self.log_event("drone", "drone_assigned_to_task", f"Drone {drone_id} assigned to {task_id} ({route.distance_m:.0f}m, {route.estimated_energy_wh:.1f}Wh).", entity_id=drone_id, operation_id=operation_id)
        return {
            "ok": True,
            "drone_id": drone_id,
            "task_id": task_id,
            "assignment_status": task.status.value.upper(),
            "route_feasible": True,
            "distance_m": route.distance_m,
            "estimated_energy_wh": route.estimated_energy_wh,
            "battery_percent": drone.battery_percent,
            "state_version": self.state_version,
        }

    def find_best_drone_for_task(self, task_id: str) -> Dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": f"Task {task_id} not found."}
        candidates: List[Dict[str, Any]] = []
        for d in self.drones.values():
            ok, reason, route = is_drone_eligible_for_task(d, task, self.city, self.grid, strategy=self.strategy.value)
            if ok and route is not None:
                score = route.distance_m + route.risk_score * 400.0 + len(d.assigned_task_ids) * 250.0 - d.battery_percent * 2.0
                candidates.append({
                    "drone_id": d.id,
                    "drone_type": d.drone_type,
                    "status": d.status.value,
                    "battery_percent": d.battery_percent,
                    "distance_m": route.distance_m,
                    "estimated_duration_s": route.estimated_duration_s,
                    "estimated_energy_wh": route.estimated_energy_wh,
                    "risk_score": route.risk_score,
                    "suitability_cost": round(score, 2),
                })
        candidates.sort(key=lambda c: c["suitability_cost"])
        return {
            "ok": True,
            "task_id": task_id,
            "best_drone": candidates[0] if candidates else None,
            "candidates": candidates[:5],
        }

    def calculate_safe_route(self, drone_id: str, destination: Tuple[float, float, float]) -> Dict[str, Any]:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"ok": False, "error": f"Drone {drone_id} not found."}
        route = self.grid.plan_route(
            start=drone.position,
            goal=(destination[0], max(6.0, destination[1]), destination[2]),
            drone=drone,
            strategy=self.strategy.value,
            payload_kg=drone.current_payload_kg,
        )
        st = self.charging.select_available_station(drone, self.city)
        rtb_pos = st.position if st else drone.home_position
        rtb_e = compute_segment_energy_wh(destination, rtb_pos, drone, 0.0, self.city.weather, 5.0)
        battery_ok = (drone.remaining_battery_wh - (route.estimated_energy_wh + rtb_e)) >= drone.battery_capacity_wh * CONFIG.safety_reserve_ratio
        return {
            "ok": True,
            "route": route.model_dump(),
            "rtb_energy_wh": round(rtb_e, 2),
            "battery_reserve_ok": battery_ok,
            "overall_feasible": bool(route.feasible and battery_ok),
        }

    def run_optimizer(self, trigger_reason: str = "initial_plan", strategy_override: Optional[StrategyType] = None) -> OptimizationResult:
        prev_status = self.status
        active_strategy = strategy_override or self.strategy
        self.status = SimulationStatus.OPTIMIZING if trigger_reason == "initial_plan" else SimulationStatus.REPLANNING
        self.log_event("solver", "optimizer_started", f"{active_strategy.value.upper()} optimizer started ({trigger_reason}).")

        try:
            if active_strategy == StrategyType.GREEDY:
                res = solve_greedy(self.drones, self.tasks, self.city, self.grid, self.sim_time_s)
            elif active_strategy == StrategyType.CLASSICAL:
                res = solve_classical(self.drones, self.tasks, self.city, self.grid, self.sim_time_s)
            elif active_strategy == StrategyType.QUANTUM:
                res = solve_quantum_qaoa(self.drones, self.tasks, self.city, self.grid, self.sim_time_s, seed=self.seed)
            else:
                res = solve_hybrid(self.drones, self.tasks, self.city, self.grid, self.sim_time_s, seed=self.seed)
        except Exception as exc:
            self.last_error = str(exc)
            self.log_event("solver", "optimizer_error", f"{active_strategy.value.upper()} failed ({exc}); engaging feasibility-checked greedy fallback.")
            res = solve_greedy(self.drones, self.tasks, self.city, self.grid, self.sim_time_s)
            res.fallback_used = f"Greedy failover after error: {exc}"
            res.errors.append(str(exc))

        self.optimization_history.append(res)
        self.last_solver_runtime_ms = res.solver_runtime_ms
        if res.quantum_metrics:
            self.last_quantum_metrics = res.quantum_metrics
        self.planning_complete = True
        if trigger_reason != "initial_plan":
            self.replanning_count += 1

        newly_assigned = 0
        for did, task_ids in res.assignments.items():
            drone = self.drones.get(did)
            if not drone or drone.status in (DroneStatus.DESTROYED, DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST):
                continue
            for tid in task_ids:
                task = self.tasks.get(tid)
                if not task or task.status == TaskStatus.COMPLETED:
                    continue
                if task.assigned_drone_id == did and tid in drone.assigned_task_ids:
                    continue
                if task.status in (TaskStatus.PENDING, TaskStatus.REQUIRES_REASSIGNMENT, TaskStatus.UNASSIGNED):
                    was_recovery = task.status == TaskStatus.REQUIRES_REASSIGNMENT
                    task.assigned_drone_id = did
                    task.status = TaskStatus.ASSIGNED
                    task.assigned_at_sim_s = self.sim_time_s
                    task.unassigned_reason = None
                    if tid not in drone.assigned_task_ids:
                        drone.assigned_task_ids.append(tid)
                    newly_assigned += 1
                    if was_recovery:
                        task.reassignment_count += 1
                        self.tasks_recovered += 1
                        self.reassignment_logs.append({
                            "sim_time_s": round(self.sim_time_s, 1),
                            "task_id": tid,
                            "new_drone_id": did,
                            "strategy": active_strategy.value,
                            "reason": trigger_reason,
                        })
                    if drone.status == DroneStatus.AVAILABLE:
                        self._dispatch_next_task(drone)

        for task in self.tasks.values():
            if task.status == TaskStatus.REQUIRES_REASSIGNMENT:
                task.status = TaskStatus.UNASSIGNED
                task.unassigned_reason = "No eligible drone met capability, payload, and 20% battery reserve constraints."

        self.bump_version()
        self.log_event("solver", "optimizer_completed", f"{active_strategy.value.upper()} completed in {res.solver_runtime_ms:.1f}ms ({newly_assigned} assignments, obj={res.objective_value:.1f}).")
        self.status = SimulationStatus.RUNNING if prev_status in (SimulationStatus.RUNNING, SimulationStatus.READY, SimulationStatus.OPTIMIZING, SimulationStatus.REPLANNING) else prev_status
        return res

    def _dispatch_next_task(self, drone: DroneState) -> None:
        if drone.status in (DroneStatus.DESTROYED, DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST, DroneStatus.LOW_BATTERY):
            return
        while drone.assigned_task_ids:
            tid = drone.assigned_task_ids[0]
            task = self.tasks.get(tid)
            if not task or task.status == TaskStatus.COMPLETED:
                drone.assigned_task_ids.pop(0)
                continue
            ok, reason, route = is_drone_eligible_for_task(drone, task, self.city, self.grid, strategy=self.strategy.value)
            if not ok or route is None:
                drone.assigned_task_ids.pop(0)
                task.assigned_drone_id = None
                task.status = TaskStatus.REQUIRES_REASSIGNMENT
                task.unassigned_reason = reason
                if "Battery reserve" in reason:
                    self._send_drone_to_charge(drone)
                    return
                continue

            drone.active_task_id = tid
            drone.current_payload_kg = task.payload_required_kg
            drone.current_route = route
            drone.waypoint_index = 1
            drone.status = DroneStatus.IN_FLIGHT
            task.status = TaskStatus.IN_PROGRESS
            task.started_at_sim_s = self.sim_time_s
            if task.survivor_id and task.survivor_id in self.survivors:
                self.survivors[task.survivor_id].status = SurvivorStatus.RESCUE_IN_PROGRESS
                self.survivors[task.survivor_id].assigned_task_id = tid
            self.route_history.append(route.model_dump())
            self.log_event("drone", "task_dispatched", f"Drone {drone.id} dispatched to {task.id} ({task.priority.value}, {route.distance_m:.0f}m).", entity_id=drone.id)
            return

        dist_home = math.hypot(drone.position[0] - drone.home_position[0], drone.position[2] - drone.home_position[2])
        if dist_home > 15.0:
            self._send_drone_to_charge(drone, rtb_only=True)
        else:
            drone.status = DroneStatus.AVAILABLE
            drone.current_route = None
            drone.active_task_id = None

    def _send_drone_to_charge(self, drone: DroneState, rtb_only: bool = False) -> None:
        st = self.charging.select_available_station(drone, self.city)
        target = st.position if st else drone.home_position
        route = self.grid.plan_route(
            start=drone.position, goal=(target[0], 2.0, target[2]),
            drone=drone, strategy=self.strategy.value, task_id=None, payload_kg=0.0,
        )
        drone.current_route = route
        drone.waypoint_index = 1
        drone.active_task_id = None
        drone.current_payload_kg = 0.0
        drone.status = DroneStatus.RETURNING
        if not rtb_only:
            self.log_event("drone", "low_battery_rtb", f"Drone {drone.id} battery at {drone.battery_percent:.1f}% — returning to {st.name if st else 'home'}.", entity_id=drone.id)

    def step(self, dt: float = CONFIG.tick_dt) -> None:
        if self.status not in (SimulationStatus.RUNNING, SimulationStatus.READY):
            return
        if self.status == SimulationStatus.READY:
            self.status = SimulationStatus.RUNNING
        if not self.planning_complete:
            self.run_optimizer("initial_plan")

        self.sim_time_s = round(self.sim_time_s + dt, 2)

        # Advance dynamic disasters & survivor health
        if self.disasters.events:
            d_step = self.disasters.step(self.city, self.survivors, dt, self.sim_time_s)
            for rx, rz, rr in d_step.get("changed_regions", []):
                self._revalidate_routes_for_region(rx, rz, rr)
        if self.survivors:
            update_survivors_health(self.survivors, dt, self.sim_time_s)

        for drone in self.drones.values():
            drone.last_telemetry_ts = self.sim_time_s
            if drone.status in (DroneStatus.DESTROYED, DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST):
                if drone.status == DroneStatus.DESTROYED and drone.position[1] > 1.5:
                    drone.position = (drone.position[0], round(max(1.0, drone.position[1] - 14.0 * dt), 1), drone.position[2])
                continue

            if drone.status == DroneStatus.CHARGING:
                charge_rate_wh_s = drone.battery_capacity_wh / 45.0
                drone.remaining_battery_wh = min(drone.battery_capacity_wh, drone.remaining_battery_wh + charge_rate_wh_s * dt)
                drone.battery_percent = round((drone.remaining_battery_wh / drone.battery_capacity_wh) * 100.0, 1)
                if drone.battery_percent >= 96.0:
                    self.charging.release_pad(drone.id)
                    drone.status = DroneStatus.AVAILABLE
                    self.log_event("drone", "charging_complete", f"Drone {drone.id} recharged to {drone.battery_percent:.0f}%.", entity_id=drone.id)
                    if drone.assigned_task_ids:
                        self._dispatch_next_task(drone)
                continue

            if drone.status == DroneStatus.DELIVERING:
                hover_e = compute_segment_energy_wh(drone.position, drone.position, drone, drone.current_payload_kg, self.city.weather, hover_seconds=dt)
                self._consume_battery(drone, hover_e, dt)
                drone.service_timer_s -= dt
                if drone.service_timer_s <= 0.0:
                    tid = drone.active_task_id
                    if tid and tid in self.tasks:
                        task = self.tasks[tid]
                        task.status = TaskStatus.COMPLETED
                        task.completed_at_sim_s = self.sim_time_s
                        if self.sim_time_s > task.deadline_seconds:
                            task.deadline_violated = True
                        drone.tasks_completed += 1
                        if tid in drone.assigned_task_ids:
                            drone.assigned_task_ids.remove(tid)
                        if task.survivor_id and task.survivor_id in self.survivors:
                            surv = self.survivors[task.survivor_id]
                            surv.status = (
                                SurvivorStatus.MEDICAL_ASSISTANCE
                                if task.task_type == "medical_delivery"
                                else SurvivorStatus.EVACUATED
                            )
                            surv.detected = True
                            surv.last_updated_sim_time = round(self.sim_time_s, 1)
                        self.log_event("task", "task_completed", f"Task {task.id} completed by {drone.id} at t={self.sim_time_s:.0f}s.", entity_id=task.id)
                    drone.active_task_id = None
                    drone.current_payload_kg = 0.0
                    if drone.battery_percent <= 24.0:
                        self._send_drone_to_charge(drone)
                    else:
                        self._dispatch_next_task(drone)
                continue

            if drone.status in (DroneStatus.IN_FLIGHT, DroneStatus.RETURNING, DroneStatus.TAKING_OFF):
                self._advance_drone_along_route(drone, dt)
                continue

            if drone.status == DroneStatus.AVAILABLE and drone.assigned_task_ids:
                self._dispatch_next_task(drone)

        conflicts = resolve_airspace_conflicts(self.drones)
        if conflicts:
            self.airspace_conflicts_total += len(conflicts)

        for task in self.tasks.values():
            if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED) and self.sim_time_s > task.deadline_seconds:
                task.deadline_violated = True

        self.bump_version()

        if int(self.sim_time_s) % 5 == 0:
            self._record_snapshot()

        all_done = all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in self.tasks.values())
        no_active_flight = all(d.status not in (DroneStatus.IN_FLIGHT, DroneStatus.DELIVERING, DroneStatus.TAKING_OFF) for d in self.drones.values())
        no_active_disasters = all(
            ev.status in (DisasterStatus.RESOLVED, DisasterStatus.CONTAINED, DisasterStatus.PAUSED)
            for ev in self.disasters.events.values()
        )
        if all_done and no_active_flight and no_active_disasters:
            self.status = SimulationStatus.COMPLETED
            self._record_snapshot()
            self.log_event("system", "simulation_completed", f"All rescue tasks resolved at t={self.sim_time_s:.0f}s.")

    def _advance_drone_along_route(self, drone: DroneState, dt: float) -> None:
        route = drone.current_route
        if not route or drone.waypoint_index >= len(route.waypoints):
            drone.groundspeed_mps = 0.0
            drone.pitch_rad = 0.0
            drone.bank_rad = 0.0
            if drone.status == DroneStatus.RETURNING:
                drone.status = DroneStatus.CHARGING
                drone.current_route = None
            elif drone.active_task_id and drone.active_task_id in self.tasks:
                drone.status = DroneStatus.DELIVERING
                drone.service_timer_s = self.tasks[drone.active_task_id].service_time_seconds
            else:
                drone.status = DroneStatus.AVAILABLE
            return

        target = route.waypoints[drone.waypoint_index]
        px, py, pz = drone.position
        dx, dy, dz = target[0] - px, target[1] - py, target[2] - pz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        horiz_dist = math.hypot(dx, dz)

        wind_effect = 0.0
        if horiz_dist > 0.2:
            wind_rad = math.radians(self.city.weather.wind_direction_deg)
            dot = (dx / horiz_dist) * math.cos(wind_rad) + (dz / horiz_dist) * math.sin(wind_rad)
            wind_effect = dot * self.city.weather.wind_speed_mps * 0.22

        target_speed = max(3.5, min(drone.max_speed_mps, drone.cruise_speed_mps + wind_effect))
        if drone.waypoint_index == len(route.waypoints) - 1 and dist < 24.0:
            target_speed = max(2.8, target_speed * (dist / 24.0))

        max_dv = 4.5 * dt
        if drone.groundspeed_mps < target_speed:
            drone.groundspeed_mps = round(min(target_speed, drone.groundspeed_mps + max_dv), 2)
        else:
            drone.groundspeed_mps = round(max(target_speed, drone.groundspeed_mps - max_dv), 2)

        step_dist = drone.groundspeed_mps * dt

        if dist <= step_dist or dist < 0.5:
            new_pos = target
            drone.waypoint_index += 1
        else:
            ratio = step_dist / dist
            new_pos = (round(px + dx * ratio, 2), round(py + dy * ratio, 2), round(pz + dz * ratio, 2))

        seg_dist = math.sqrt((new_pos[0] - px) ** 2 + (new_pos[1] - py) ** 2 + (new_pos[2] - pz) ** 2)
        seg_energy = compute_segment_energy_wh(drone.position, new_pos, drone, drone.current_payload_kg, self.city.weather, 0.0)

        new_heading = math.atan2(dx, dz) if horiz_dist > 0.1 else drone.heading_rad
        delta_h = (new_heading - drone.heading_rad + math.pi) % (2 * math.pi) - math.pi
        drone.bank_rad = round(max(-0.38, min(0.38, delta_h * 0.65)), 3)
        drone.pitch_rad = round(min(0.26, (drone.groundspeed_mps / max(drone.max_speed_mps, 1.0)) * 0.22), 3)
        drone.heading_rad = round(new_heading, 3)
        drone.velocity = (round((new_pos[0] - px) / dt, 2), round((new_pos[1] - py) / dt, 2), round((new_pos[2] - pz) / dt, 2))
        drone.position = new_pos
        drone.total_distance_m = round(drone.total_distance_m + seg_dist, 2)

        rem_dist = dist
        for wi in range(drone.waypoint_index, len(route.waypoints) - 1):
            a, b = route.waypoints[wi], route.waypoints[wi + 1]
            rem_dist += math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)
        drone.eta_seconds = round(rem_dist / max(drone.groundspeed_mps, 1.0), 1)

        self._consume_battery(drone, seg_energy, dt)

        if drone.waypoint_index >= len(route.waypoints):
            drone.groundspeed_mps = 0.0
            drone.pitch_rad = 0.0
            drone.eta_seconds = 0.0
            if drone.status == DroneStatus.RETURNING:
                drone.status = DroneStatus.CHARGING
                drone.current_route = None
            elif drone.active_task_id and drone.active_task_id in self.tasks:
                drone.status = DroneStatus.DELIVERING
                drone.service_timer_s = self.tasks[drone.active_task_id].service_time_seconds
            else:
                drone.status = DroneStatus.AVAILABLE
                drone.current_route = None

    def _consume_battery(self, drone: DroneState, energy_wh: float, dt: float) -> None:
        drone.remaining_battery_wh = max(0.0, round(drone.remaining_battery_wh - energy_wh, 3))
        drone.total_energy_used_wh = round(drone.total_energy_used_wh + energy_wh, 3)
        drone.total_flight_time_s = round(drone.total_flight_time_s + dt, 1)
        drone.battery_percent = round((drone.remaining_battery_wh / drone.battery_capacity_wh) * 100.0, 1)

        power_w = (energy_wh * 3600.0) / max(dt, 0.1)
        drone.power_draw_w = round(power_w, 1)
        ambient_c = 28.0
        target_temp = ambient_c + min(26.0, power_w * 0.032)
        drone.battery_temp_c = round(drone.battery_temp_c + (target_temp - drone.battery_temp_c) * 0.08 * dt, 1)

        burn_rate = max(0.05, energy_wh / max(dt, 0.1))
        drone.estimated_remaining_flight_s = round(drone.remaining_battery_wh / burn_rate, 1)

        if drone.battery_percent <= 19.0 and drone.status == DroneStatus.IN_FLIGHT:
            self._release_drone_tasks(drone, reason="LOW_BATTERY_RESERVE")
            self._send_drone_to_charge(drone)
            self.run_optimizer("low_battery_recovery")

    def _release_drone_tasks(self, drone: DroneState, reason: str) -> List[str]:
        released: List[str] = []
        to_release = list(drone.assigned_task_ids)
        if drone.active_task_id and drone.active_task_id not in to_release:
            to_release.append(drone.active_task_id)
        for tid in to_release:
            t = self.tasks.get(tid)
            if t and t.status != TaskStatus.COMPLETED:
                t.assigned_drone_id = None
                t.status = TaskStatus.REQUIRES_REASSIGNMENT
                released.append(tid)
        drone.assigned_task_ids.clear()
        drone.active_task_id = None
        drone.current_route = None
        drone.current_payload_kg = 0.0
        self.tasks_needing_recovery_total += len(released)
        return released

    def add_task(
        self, name: str, task_type: str, location: Tuple[float, float, float],
        priority: TaskPriority, payload_required_kg: float, required_capabilities: List[str],
        deadline_seconds: float, service_time_seconds: float, risk_level: float,
        description: str = "", assign_drone_id: Optional[str] = None, auto_assign: bool = True,
        survivor_id: Optional[str] = None, disaster_event_id: Optional[str] = None,
    ) -> RescueTask:
        tid = f"T-{len(self.tasks) + 1:03d}"
        task = RescueTask(
            id=tid, name=name, task_type=task_type,
            location=(round(location[0], 1), round(max(2.0, location[1]), 1), round(location[2], 1)),
            priority=priority, deadline_seconds=self.sim_time_s + deadline_seconds,
            payload_required_kg=payload_required_kg, required_capabilities=required_capabilities,
            service_time_seconds=service_time_seconds, risk_level=risk_level, description=description,
            status=TaskStatus.PENDING, created_at_sim_s=self.sim_time_s,
            survivor_id=survivor_id, disaster_event_id=disaster_event_id,
        )
        self.tasks[tid] = task
        if survivor_id and survivor_id in self.survivors:
            self.survivors[survivor_id].assigned_task_id = tid
            self.survivors[survivor_id].status = SurvivorStatus.RESCUE_PENDING
        if disaster_event_id and disaster_event_id in self.disasters.events:
            self.disasters.events[disaster_event_id].related_tasks.append(tid)
        self.bump_version()
        self.log_event("task", "target_injected", f"New rescue task {tid} ({priority.value} {task_type}) injected at ({location[0]:.0f}, {location[2]:.0f}).", entity_id=tid)

        if assign_drone_id and assign_drone_id in self.drones:
            d = self.drones[assign_drone_id]
            ok, reason, _ = is_drone_eligible_for_task(d, task, self.city, self.grid, strategy=self.strategy.value)
            if ok:
                task.assigned_drone_id = d.id
                task.status = TaskStatus.ASSIGNED
                task.assigned_at_sim_s = self.sim_time_s
                d.assigned_task_ids.insert(0, tid)
                if d.status == DroneStatus.AVAILABLE:
                    self._dispatch_next_task(d)
                self.log_event("drone", "manual_task_assigned", f"Operator assigned {tid} directly to {d.id}.", entity_id=d.id)
            else:
                task.unassigned_reason = reason
                self.log_event("task", "manual_assign_rejected", f"Manual assignment of {tid} to {d.id} rejected: {reason}", entity_id=tid)
                if auto_assign:
                    self.run_optimizer("new_task_injected")
        elif auto_assign:
            self.run_optimizer("new_task_injected")
        return task

    def set_drone_waypoint(self, drone_id: str, destination: Tuple[float, float, float]) -> Dict[str, Any]:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"ok": False, "error": f"Drone {drone_id} not found."}
        if drone.status in (DroneStatus.DESTROYED, DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST):
            return {"ok": False, "error": f"Drone {drone_id} is {drone.status.value} and cannot accept waypoints."}

        route = self.grid.plan_route(
            start=drone.position, goal=(destination[0], max(6.0, destination[1]), destination[2]),
            drone=drone, strategy=self.strategy.value, payload_kg=drone.current_payload_kg,
        )
        if not route.feasible:
            return {"ok": False, "error": "Destination is blocked by hazards or no-fly zones.", "route": route.model_dump()}

        st = self.charging.select_available_station(drone, self.city)
        rtb_pos = st.position if st else drone.home_position
        rtb_e = compute_segment_energy_wh(destination, rtb_pos, drone, 0.0, self.city.weather, 5.0)
        if drone.remaining_battery_wh - (route.estimated_energy_wh + rtb_e) < drone.battery_capacity_wh * CONFIG.safety_reserve_ratio:
            return {"ok": False, "error": "Route violates 20% mandatory battery safety reserve.", "route": route.model_dump()}

        drone.current_route = route
        drone.waypoint_index = 1
        drone.status = DroneStatus.IN_FLIGHT
        self.route_history.append(route.model_dump())
        self.bump_version()
        self.log_event("drone", "custom_waypoint_set", f"Drone {drone.id} redirected to ({destination[0]:.0f}, {destination[2]:.0f}), dist={route.distance_m:.0f}m.", entity_id=drone.id)
        return {"ok": True, "route": route.model_dump(), "state_version": self.state_version}

    def inject_failure(self, drone_id: str, failure_type: FailureType) -> Dict[str, Any]:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"ok": False, "error": f"Drone {drone_id} not found."}

        t0 = time.perf_counter()
        released = self._release_drone_tasks(drone, reason=failure_type.value)

        if failure_type == FailureType.COMPLETE_DRONE_DESTRUCTION:
            drone.status = DroneStatus.DESTROYED
            drone.health = 0.0
        elif failure_type == FailureType.COMMUNICATION_LOSS:
            drone.status = DroneStatus.COMMUNICATION_LOST
            drone.health = min(drone.health, 50.0)
        elif failure_type in (FailureType.LOW_BATTERY, FailureType.BATTERY_FAILURE):
            drone.remaining_battery_wh = round(drone.battery_capacity_wh * 0.12, 2)
            drone.battery_percent = 12.0
            drone.status = DroneStatus.LOW_BATTERY
            drone.health = min(drone.health, 60.0)
        else:
            drone.status = DroneStatus.DAMAGED
            drone.health = min(drone.health, 25.0)

        drone.tasks_failed += len(released)
        failure_record = {
            "sim_time_s": round(self.sim_time_s, 1),
            "drone_id": drone.id,
            "failure_type": failure_type.value,
            "position": list(drone.position),
            "tasks_affected": released,
            "strategy": self.strategy.value,
        }
        drone.failure_history.append(failure_record)
        self.bump_version()
        self.log_event("failure", "drone_failed", f"Drone {drone.id} suffered {failure_type.value} at ({drone.position[0]:.0f}, {drone.position[2]:.0f}). {len(released)} task(s) queued for recovery.", entity_id=drone.id, payload=failure_record)

        reassigned = []
        if released:
            self.run_optimizer(f"recovery_{failure_type.value.lower()}")
            for tid in released:
                t = self.tasks.get(tid)
                if t and t.assigned_drone_id:
                    reassigned.append({"task_id": tid, "new_drone_id": t.assigned_drone_id})
                    self.recovery_arcs.append({"from_pos": list(drone.position), "to_drone_id": t.assigned_drone_id, "task_id": tid, "created_at_s": self.sim_time_s})

        rec_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        failure_record["new_assignments"] = reassigned
        failure_record["recovery_duration_ms"] = rec_ms
        failure_record["recovery_success"] = len(reassigned) == len(released)
        self.failure_logs.append(failure_record)

        if released:
            self.log_event("replanning", "task_recovery_complete", f"Recovery complete in {rec_ms:.1f}ms: {len(reassigned)}/{len(released)} tasks reassigned.", entity_id=drone.id, payload={"reassigned": reassigned})
        return {"ok": True, "failure": failure_record, "state_version": self.state_version}

    def inject_environment_event(self, event_kind: str, params: Dict[str, Any]) -> Dict[str, Any]:
        replan_needed = False
        msg = ""
        if event_kind == "expand_fire":
            fires = [h for h in self.city.hazards if h.kind == "fire" and h.active]
            if fires:
                fires[0].radius = round(fires[0].radius + float(params.get("delta_radius", 75.0)), 1)
                msg = f"Fire zone {fires[0].id} expanded to radius {fires[0].radius:.0f}m."
                replan_needed = True
        elif event_kind == "new_fire":
            hz = HazardZone(id=f"HZ-FIRE-{len(self.city.hazards)+1}", kind="fire", x=float(params.get("x", 1920.0)), z=float(params.get("z", 1620.0)), radius=float(params.get("radius", 145.0)), severity=0.92, altitude_ceiling=85.0)
            self.city.hazards.append(hz)
            msg = f"New fire zone {hz.id} erupted at ({hz.x:.0f}, {hz.z:.0f})."
            replan_needed = True
        elif event_kind == "new_flood":
            hz = HazardZone(id=f"HZ-FLOOD-{len(self.city.hazards)+1}", kind="flood", x=float(params.get("x", 1650.0)), z=float(params.get("z", 2750.0)), radius=float(params.get("radius", 260.0)), severity=0.85, altitude_ceiling=18.0)
            self.city.hazards.append(hz)
            msg = f"Flood zone {hz.id} introduced at ({hz.x:.0f}, {hz.z:.0f})."
            replan_needed = True
        elif event_kind == "close_airspace":
            hz = HazardZone(id=f"HZ-NFZ-{len(self.city.hazards)+1}", kind="no_fly", x=float(params.get("x", 2050.0)), z=float(params.get("z", 1900.0)), radius=float(params.get("radius", 160.0)), severity=1.0, altitude_ceiling=140.0)
            self.city.hazards.append(hz)
            msg = f"Airspace closed ({hz.id}) at ({hz.x:.0f}, {hz.z:.0f})."
            replan_needed = True
        elif event_kind == "increase_wind":
            self.city.weather.wind_speed_mps = round(min(22.0, self.city.weather.wind_speed_mps + float(params.get("delta", 4.5))), 1)
            msg = f"Wind speed increased to {self.city.weather.wind_speed_mps} m/s."
        elif event_kind == "heavy_rain":
            self.city.weather.condition = "storm"
            self.city.weather.rain_intensity = 0.9
            self.city.weather.fog_density = 0.35
            msg = "Heavy rainstorm active; aerodynamic energy penalty elevated."
        elif event_kind == "change_wind_direction":
            self.city.weather.wind_direction_deg = (self.city.weather.wind_direction_deg + 75.0) % 360.0
            msg = f"Wind direction shifted to {self.city.weather.wind_direction_deg:.0f} deg."
        elif event_kind == "toggle_day_night":
            self.city.weather.day_mode = not self.city.weather.day_mode
            msg = f"Lighting switched to {'DAY' if self.city.weather.day_mode else 'NIGHT'} mode."
        elif event_kind == "disable_station":
            active_st = [s for s in self.city.stations if s.active]
            if len(active_st) > 1:
                active_st[-1].active = False
                msg = f"Landing/charging station {active_st[-1].name} disabled."
                replan_needed = True

        self.bump_version()
        self.log_event("environment", event_kind, msg or f"Environment event '{event_kind}' applied.")

        rerouted = 0
        if replan_needed:
            if event_kind in ("expand_fire", "new_fire", "new_flood", "close_airspace") and self.city.hazards:
                hz_ref = self.city.hazards[-1] if event_kind != "expand_fire" else next((h for h in self.city.hazards if h.kind == "fire" and h.active), self.city.hazards[-1])
                rerouted = self._revalidate_routes_for_region(hz_ref.x, hz_ref.z, hz_ref.radius)
            else:
                self.grid.rebuild()

        return {"ok": True, "message": msg, "rerouted_drones": rerouted, "state_version": self.state_version}

    def get_building_damage_summary(self) -> Dict[str, Any]:
        counts = {s.value: 0 for s in BuildingDamageState}
        damaged_list = []
        for b in self.city.buildings:
            counts[b.damage_state.value] = counts.get(b.damage_state.value, 0) + 1
            if b.damage_state != BuildingDamageState.INTACT or b.flood_depth_m > 0 or b.on_fire:
                damaged_list.append({
                    "id": b.id,
                    "x": b.x,
                    "z": b.z,
                    "integrity": b.integrity,
                    "damage_state": b.damage_state.value,
                    "flood_depth_m": b.flood_depth_m,
                    "on_fire": b.on_fire,
                })
        return {"counts": counts, "total_damaged": len(damaged_list), "damaged_buildings": damaged_list[:100]}

    def get_metrics(self) -> StrategyMetrics:
        completed = [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]
        pending = [t for t in self.tasks.values() if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        failed_tasks = [t for t in self.tasks.values() if t.status in (TaskStatus.FAILED, TaskStatus.UNASSIGNED)]
        failed_drones = [d for d in self.drones.values() if d.status in (DroneStatus.DESTROYED, DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST)]
        total_energy = round(sum(d.total_energy_used_wh for d in self.drones.values()), 2)
        resp_times = [(t.completed_at_sim_s - t.created_at_sim_s) for t in completed if t.completed_at_sim_s is not None]
        avg_resp = round(sum(resp_times) / len(resp_times), 1) if resp_times else 0.0
        deadlines_violated = sum(1 for t in self.tasks.values() if t.deadline_violated)
        route_risks = [d.current_route.risk_score for d in self.drones.values() if d.current_route]
        avg_risk = round(sum(route_risks) / len(route_risks), 3) if route_risks else 0.12
        rec_rate = 100.0 if self.tasks_needing_recovery_total == 0 else round((self.tasks_recovered / self.tasks_needing_recovery_total) * 100.0, 1)

        m = StrategyMetrics(
            strategy=self.strategy, status=self.status, planning_complete=self.planning_complete,
            missions_completed=len(completed), missions_pending=len(pending), missions_failed=len(failed_tasks),
            failed_drones=len(failed_drones), total_mission_time_s=round(self.sim_time_s, 1),
            total_energy_wh=total_energy, avg_response_time_s=avg_resp, operational_risk=avg_risk,
            solver_runtime_ms=self.last_solver_runtime_ms, replanning_count=self.replanning_count,
            tasks_recovered=self.tasks_recovered, recovery_rate_pct=rec_rate,
            deadline_violations=deadlines_violated, airspace_conflicts=self.airspace_conflicts_total,
            feasible=self.feasible, error=self.last_error,
        )
        m.score = compute_strategy_score(m, total_tasks=len(self.tasks))
        m.solution_quality = m.score
        return m

    def _record_snapshot(self) -> None:
        m = self.get_metrics()
        self.analytics_series.append({
            "t": self.sim_time_s, "completed": m.missions_completed, "energy_wh": m.total_energy_wh,
            "avg_response_s": m.avg_response_time_s,
            "avg_battery_pct": round(sum(d.battery_percent for d in self.drones.values()) / max(1, len(self.drones)), 1),
            "distance_m": round(sum(d.total_distance_m for d in self.drones.values()), 1),
            "score": m.score,
        })
        if len(self.analytics_series) > 300:
            self.analytics_series = self.analytics_series[-300:]

        self.replay_frames.append({
            "t": self.sim_time_s,
            "drones": {did: {"pos": d.position, "status": d.status.value, "bat": d.battery_percent, "hdg": d.heading_rad} for did, d in self.drones.items()},
            "tasks": {tid: t.status.value for tid, t in self.tasks.items()},
            "disasters": {eid: {"r": ev.affected_radius, "sev": ev.severity, "st": ev.status.value, "wl": ev.water_level_m} for eid, ev in self.disasters.events.items()},
        })
        if len(self.replay_frames) > 400:
            self.replay_frames = self.replay_frames[-400:]

    def serialize_state(self, include_city: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "run_id": self.run_id, "strategy": self.strategy.value, "status": self.status.value,
            "state_version": self.state_version,
            "seed": self.seed, "sim_time_s": self.sim_time_s, "speed_multiplier": self.speed_multiplier,
            "weather": self.city.weather.model_dump(),
            "hazards": [h.model_dump() for h in self.city.hazards],
            "disasters": [ev.model_dump() for ev in self.disasters.events.values()],
            "disaster_timeline": self.disasters.timeline[-60:],
            "survivors": [s.model_dump() for s in self.survivors.values()],
            "building_damage_summary": self.get_building_damage_summary(),
            "stations": [s.model_dump() for s in self.city.stations],
            "drones": [d.model_dump() for d in self.drones.values()],
            "tasks": [t.model_dump() for t in self.tasks.values()],
            "metrics": self.get_metrics().model_dump(),
            "quantum_metrics": self.last_quantum_metrics.model_dump() if self.last_quantum_metrics else None,
            "analytics": self.analytics_series[-80:],
            "station_utilization": self.charging.get_utilization(self.city),
            "fleet_alerts": scan_fleet_anomalies(self.drones),
            "recovery_arcs": [a for a in self.recovery_arcs if self.sim_time_s - a["created_at_s"] <= 45.0][-12:],
            "events": [e.model_dump() for e in self.events[-80:]],
        }
        if include_city:
            payload["city"] = self.city.model_dump()
        return payload
