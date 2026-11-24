from __future__ import annotations
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List
from app.core.models import (
    CityEnvironment, DroneState, DroneStatus, OptimizationResult,
    RescueTask, StrategyType, TaskStatus
)
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.feasibility import estimate_assignment_cost, is_drone_eligible_for_task

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def solve_greedy(
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float = 0.0,
) -> OptimizationResult:
    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    pending = [
        t for t in tasks.values()
        if t.status in (TaskStatus.PENDING, TaskStatus.REQUIRES_REASSIGNMENT, TaskStatus.UNASSIGNED)
    ]
    pending.sort(key=lambda t: (PRIORITY_ORDER[t.priority.value], t.deadline_seconds, t.id))

    eligible_drones = [
        d for d in drones.values()
        if d.status not in (
            DroneStatus.DESTROYED, DroneStatus.DAMAGED,
            DroneStatus.COMMUNICATION_LOST, DroneStatus.LOW_BATTERY
        )
    ]

    assignments: Dict[str, List[str]] = {d.id: list(d.assigned_task_ids) for d in eligible_drones}
    drone_load: Dict[str, int] = {d.id: len(assignments[d.id]) for d in eligible_drones}
    total_obj = 0.0
    missed = 0

    for task in pending:
        best_drone = None
        best_dist = float("inf")
        for d in eligible_drones:
            if drone_load[d.id] >= 4:
                continue
            if task.payload_required_kg > d.max_payload_kg:
                continue
            if not all(c in d.capabilities for c in task.required_capabilities):
                continue
            dist = math.hypot(d.position[0] - task.location[0], d.position[2] - task.location[2]) + drone_load[d.id] * 140.0
            if dist < best_dist:
                ok, _, _ = is_drone_eligible_for_task(d, task, city, grid, strategy="greedy")
                if ok:
                    best_dist = dist
                    best_drone = d

        if best_drone is not None:
            assignments[best_drone.id].append(task.id)
            drone_load[best_drone.id] += 1
            total_obj += estimate_assignment_cost(best_drone, task, city, sim_time_s)
        else:
            missed += 1

    runtime_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return OptimizationResult(
        optimization_id=f"OPT-GRD-{uuid.uuid4().hex[:6].upper()}",
        algorithm=StrategyType.GREEDY,
        started_at_iso=started_iso,
        completed_at_iso=datetime.now(timezone.utc).isoformat(),
        solver_runtime_ms=runtime_ms,
        objective_value=round(total_obj, 2),
        feasible=True,
        assignments={k: v for k, v in assignments.items() if v},
        missed_tasks=missed,
    )
