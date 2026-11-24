from __future__ import annotations
import copy
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import CONFIG, DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_NAME, DEFAULT_SEED
from app.core.models import (
    CityEnvironment, DroneState, DroneStatus, FailureType, HazardZone,
    OptimizationResult, QuantumMetrics, RescueTask,
    SimulationEvent, SimulationStatus, StrategyMetrics, StrategyType, TaskPriority, TaskStatus
)
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
from app.simulation.collision_manager import assign_corridor_altitude, resolve_airspace_conflicts
from app.recovery.failure_detector import scan_fleet_anomalies
from app.recovery.fallback_manager import execute_with_failover
from app.recovery.task_reallocator import release_incomplete_tasks
from app.simulation.drone_manager import find_nearest_charging_station, generate_fleet
from app.simulation.task_manager import generate_tasks


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
    ):
        self.run_id: str = run_id or f"RUN-{uuid.uuid4().hex[:6].upper()}"
        self.strategy: StrategyType = strategy
        self.seed: int = seed
        self.status: SimulationStatus = SimulationStatus.READY
        self.sim_time_s: float = 0.0
        self.speed_multiplier: float = 1.0
        self.started_at_iso: str = datetime.now(timezone.utc).isoformat()
        self.wall_start_ts: float = time.perf_counter()

        self.city: CityEnvironment = generate_city(
            seed=seed, scenario_id=scenario_id, scenario_name=scenario_name,
            city_density=city_density, building_density=building_density,
        )
        self.grid: SpatialAirspaceGrid = SpatialAirspaceGrid(self.city)
        self.charging: ChargingPadManager = ChargingPadManager(self.city)
        self.drones: Dict[str, DroneState] = generate_fleet(self.city, seed)
        self.tasks: Dict[str, RescueTask] = generate_tasks(self.city, seed, count=50)

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

    def clone_for_strategy(self, strategy: StrategyType, run_id: str) -> "SimulationWorld":
        cloned = copy.deepcopy(self)
        cloned.run_id = run_id
        cloned.strategy = strategy
        cloned.wall_start_ts = time.perf_counter()
        cloned.log_event("system", "snapshot_cloned", f"Isolated benchmark instance created for strategy '{strategy.value.upper()}'.")
        return cloned

    def log_event(self, category: str, event_type: str, message: str, entity_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> SimulationEvent:
        ev = SimulationEvent(
            id=f"EV-{uuid.uuid4().hex[:8].upper()}",
            run_id=self.run_id,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            sim_time_s=round(self.sim_time_s, 1),
            category=category,
            event_type=event_type,
            message=message,
            entity_id=entity_id,
            payload=payload or {},
        )
        self.events.append(ev)
        if len(self.events) > 1500:
            self.events = self.events[-1500:]
        return ev

    def run_optimizer(self, trigger_reason: str = "initial_plan") -> OptimizationResult:
        prev_status = self.status
        self.status = SimulationStatus.OPTIMIZING if trigger_reason == "initial_plan" else SimulationStatus.REPLANNING
        self.log_event("solver", "optimizer_started", f"{self.strategy.value.upper()} optimizer started ({trigger_reason}).")

        try:
            if self.strategy == StrategyType.GREEDY:
                res = solve_greedy(self.drones, self.tasks, self.city, self.grid, self.sim_time_s)
            elif self.strategy == StrategyType.CLASSICAL:
                res = solve_classical(self.drones, self.tasks, self.city, self.grid, self.sim_time_s)
            elif self.strategy == StrategyType.QUANTUM:
                res = solve_quantum_qaoa(self.drones, self.tasks, self.city, self.grid, self.sim_time_s, seed=self.seed)
            else:
                res = solve_hybrid(self.drones, self.tasks, self.city, self.grid, self.sim_time_s, seed=self.seed)
        except Exception as exc:
            self.last_error = str(exc)
            self.log_event("solver", "optimizer_error", f"{self.strategy.value.upper()} failed ({exc}); engaging feasibility-checked greedy fallback.")
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
                            "strategy": self.strategy.value,
                            "reason": trigger_reason,
                        })
                    if drone.status == DroneStatus.AVAILABLE:
                        self._dispatch_next_task(drone)

        for task in self.tasks.values():
            if task.status == TaskStatus.REQUIRES_REASSIGNMENT:
                task.status = TaskStatus.UNASSIGNED
                task.unassigned_reason = "No eligible drone met capability, payload, and 20% battery reserve constraints."

        self.log_event("solver", "optimizer_completed", f"{self.strategy.value.upper()} completed in {res.solver_runtime_ms:.1f}ms ({newly_assigned} assignments, obj={res.objective_value:.1f}).")
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

        if int(self.sim_time_s) % 5 == 0:
            self._record_snapshot()

        all_done = all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) for t in self.tasks.values())
        no_active_flight = all(d.status not in (DroneStatus.IN_FLIGHT, DroneStatus.DELIVERING, DroneStatus.TAKING_OFF) for d in self.drones.values())
        if all_done and no_active_flight:
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

        # Wind-coupled effective cruise speed (headwind slows groundspeed, tailwind boosts)
        wind_effect = 0.0
        if horiz_dist > 0.2:
            wind_rad = math.radians(self.city.weather.wind_direction_deg)
            dot = (dx / horiz_dist) * math.cos(wind_rad) + (dz / horiz_dist) * math.sin(wind_rad)
            wind_effect = dot * self.city.weather.wind_speed_mps * 0.22

        target_speed = max(3.5, min(drone.max_speed_mps, drone.cruise_speed_mps + wind_effect))
        # Smooth deceleration when approaching final waypoint
        if drone.waypoint_index == len(route.waypoints) - 1 and dist < 24.0:
            target_speed = max(2.8, target_speed * (dist / 24.0))

        # Smooth acceleration/deceleration ramp (4.5 m/s^2)
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

        # Compute remaining ETA along waypoints
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

        # Instantaneous power draw (Watts = Wh * 3600 / dt) & battery thermal response
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
    ) -> RescueTask:
        tid = f"T-{len(self.tasks) + 1:03d}"
        task = RescueTask(
            id=tid, name=name, task_type=task_type,
            location=(round(location[0], 1), round(max(2.0, location[1]), 1), round(location[2], 1)),
            priority=priority, deadline_seconds=self.sim_time_s + deadline_seconds,
            payload_required_kg=payload_required_kg, required_capabilities=required_capabilities,
            service_time_seconds=service_time_seconds, risk_level=risk_level, description=description,
            status=TaskStatus.PENDING, created_at_sim_s=self.sim_time_s,
        )
        self.tasks[tid] = task
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
        self.log_event("drone", "custom_waypoint_set", f"Drone {drone.id} redirected to ({destination[0]:.0f}, {destination[2]:.0f}), dist={route.distance_m:.0f}m.", entity_id=drone.id)
        return {"ok": True, "route": route.model_dump()}

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
        return {"ok": True, "failure": failure_record}

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

        self.log_event("environment", event_kind, msg or f"Environment event '{event_kind}' applied.")

        rerouted = 0
        if replan_needed:
            if event_kind in ('expand_fire', 'new_fire', 'new_flood', 'close_airspace') and self.city.hazards:
                hz_ref = self.city.hazards[-1] if event_kind != 'expand_fire' else next((h for h in self.city.hazards if h.kind == 'fire' and h.active), self.city.hazards[-1])
                self.grid.rebuild_region(hz_ref.x, hz_ref.z, hz_ref.radius)
            else:
                self.grid.rebuild()
            for d in self.drones.values():
                if d.status == DroneStatus.IN_FLIGHT and d.current_route and not self.grid.is_route_valid(d.current_route):
                    goal = d.current_route.waypoints[-1]
                    new_rt = self.grid.plan_route(start=d.position, goal=goal, drone=d, strategy=self.strategy.value, task_id=d.active_task_id, payload_kg=d.current_payload_kg)
                    new_rt.replan_count = d.current_route.replan_count + 1
                    d.current_route = new_rt
                    d.waypoint_index = 1
                    rerouted += 1
                    self.route_history.append(new_rt.model_dump())
            if rerouted > 0:
                self.replanning_count += 1
                self.log_event("replanning", "hazard_reroute", f"Hazard invalidated {rerouted} active flight path(s); safe detours computed.")

        return {"ok": True, "message": msg, "rerouted_drones": rerouted}

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
        })
        if len(self.replay_frames) > 400:
            self.replay_frames = self.replay_frames[-400:]

    def serialize_state(self, include_city: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "run_id": self.run_id, "strategy": self.strategy.value, "status": self.status.value,
            "seed": self.seed, "sim_time_s": self.sim_time_s, "speed_multiplier": self.speed_multiplier,
            "weather": self.city.weather.model_dump(),
            "hazards": [h.model_dump() for h in self.city.hazards],
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
