from __future__ import annotations
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import numpy as np
from app.core.models import (
    CityEnvironment, DroneState, DroneStatus, OptimizationResult,
    RescueTask, StrategyType, TaskStatus
)
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.feasibility import estimate_assignment_cost, is_drone_eligible_for_task
from app.optimization.route_sequencer import sequence_drone_tasks

try:
    from ortools.sat.python import cp_model
    HAS_ORTOOLS = True
except Exception:
    HAS_ORTOOLS = False

try:
    from scipy.optimize import linear_sum_assignment
    HAS_SCIPY = True
except Exception:
    HAS_SCIPY = False


def solve_classical(
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float = 0.0,
    max_tasks_per_drone: int = 4,
) -> OptimizationResult:
    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    pending = [
        t for t in tasks.values()
        if t.status in (TaskStatus.PENDING, TaskStatus.REQUIRES_REASSIGNMENT, TaskStatus.UNASSIGNED)
    ]
    eligible_drones = [
        d for d in drones.values()
        if d.status not in (
            DroneStatus.DESTROYED, DroneStatus.DAMAGED,
            DroneStatus.COMMUNICATION_LOST, DroneStatus.LOW_BATTERY
        )
    ]

    assignments: Dict[str, List[str]] = {d.id: list(d.assigned_task_ids) for d in eligible_drones}
    if not pending or not eligible_drones:
        return OptimizationResult(
            optimization_id=f"OPT-CLS-{uuid.uuid4().hex[:6].upper()}",
            algorithm=StrategyType.CLASSICAL,
            started_at_iso=started_iso,
            completed_at_iso=datetime.now(timezone.utc).isoformat(),
            solver_runtime_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            objective_value=0.0,
            feasible=True,
            assignments={k: v for k, v in assignments.items() if v},
        )

    feasible_pairs: Dict[Tuple[int, int], float] = {}
    for di, d in enumerate(eligible_drones):
        for ti, task in enumerate(pending):
            if task.payload_required_kg > d.max_payload_kg:
                continue
            if not all(c in d.capabilities for c in task.required_capabilities):
                continue
            if d.battery_percent < 24.0:
                continue
            ok, _, _ = is_drone_eligible_for_task(
                d, task, city, grid, strategy="classical",
                assigned_task_ids=list(d.assigned_task_ids) + [task.id], tasks=tasks,
            )
            if not ok:
                continue
            cost = estimate_assignment_cost(d, task, city, sim_time_s)
            if math.isfinite(cost):
                feasible_pairs[(di, ti)] = cost

    unassigned_penalty = 950.0
    total_obj = 0.0
    missed = 0
    fallback_note = None

    if HAS_ORTOOLS:
        model = cp_model.CpModel()
        x = {(di, ti): model.NewBoolVar(f"x_{di}_{ti}") for (di, ti) in feasible_pairs}
        unassigned = [model.NewBoolVar(f"u_{ti}") for ti in range(len(pending))]

        for ti in range(len(pending)):
            vars_for_t = [x[(di, ti)] for di in range(len(eligible_drones)) if (di, ti) in x]
            model.Add(sum(vars_for_t) + unassigned[ti] == 1)

        for di, d in enumerate(eligible_drones):
            vars_for_d = [x[(di, ti)] for ti in range(len(pending)) if (di, ti) in x]
            cap_left = max(0, max_tasks_per_drone - len(d.assigned_task_ids))
            if vars_for_d:
                model.Add(sum(vars_for_d) <= cap_left)

        prio_pen = {"critical": 4200, "high": 2800, "medium": 1600, "low": 900}
        obj_terms = [int(cost * 10) * x[(di, ti)] for (di, ti), cost in feasible_pairs.items()]
        obj_terms.extend(prio_pen.get(task.priority.value, 1600) * unassigned[ti] for ti, task in enumerate(pending))
        model.Minimize(sum(obj_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 1.8
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (di, ti), var in x.items():
                if solver.Value(var) == 1:
                    d = eligible_drones[di]
                    t = pending[ti]
                    ok, _, _ = is_drone_eligible_for_task(
                        d, t, city, grid, strategy="classical",
                        assigned_task_ids=list(assignments[d.id]) + [t.id], tasks=tasks,
                    )
                    if ok:
                        assignments[d.id].append(t.id)
                        total_obj += feasible_pairs[(di, ti)]
                    else:
                        missed += 1
            for uvar in unassigned:
                if solver.Value(uvar) == 1:
                    missed += 1
        else:
            fallback_note = "OR-Tools CP-SAT infeasible/timeout -> deterministic linear assignment"
    else:
        fallback_note = "OR-Tools not installed -> SciPy Hungarian multi-slot assignment"

    if fallback_note is not None:
        slots: List[Tuple[int, int]] = []
        for di, d in enumerate(eligible_drones):
            cap_left = max(0, max_tasks_per_drone - len(d.assigned_task_ids))
            for s in range(cap_left):
                slots.append((di, s))

        if slots and HAS_SCIPY:
            big_m = 1e6
            mat = np.full((len(slots), len(pending)), big_m, dtype=float)
            for row, (di, s) in enumerate(slots):
                for ti in range(len(pending)):
                    if (di, ti) in feasible_pairs:
                        mat[row, ti] = feasible_pairs[(di, ti)] + s * 65.0
            row_ind, col_ind = linear_sum_assignment(mat)
            assigned_tasks = set()
            for r, c in zip(row_ind, col_ind):
                if mat[r, c] < big_m * 0.5:
                    di, _ = slots[r]
                    d = eligible_drones[di]
                    t = pending[c]
                    ok, _, _ = is_drone_eligible_for_task(
                        d, t, city, grid, strategy="classical",
                        assigned_task_ids=list(assignments[d.id]) + [t.id], tasks=tasks,
                    )
                    if ok:
                        assignments[d.id].append(t.id)
                        total_obj += feasible_pairs[(di, c)]
                        assigned_tasks.add(c)
            missed = len(pending) - len(assigned_tasks)
        else:
            missed = len(pending)

    accepted_new_tasks = set()
    for did, tids in list(assignments.items()):
        drone = drones.get(did)
        if not drone:
            assignments[did] = []
            continue
        ordered = sequence_drone_tasks(drone, tids, tasks, sim_time_s) if len(tids) > 1 else list(tids)
        if drone.active_task_id in ordered:
            ordered.remove(drone.active_task_id)
            ordered.insert(0, drone.active_task_id)
        accepted: List[str] = []
        for tid in ordered:
            task = tasks.get(tid)
            if not task:
                continue
            ok, _, _ = is_drone_eligible_for_task(
                drone, task, city, grid, strategy="classical",
                assigned_task_ids=accepted + [tid], tasks=tasks,
            )
            if ok:
                accepted.append(tid)
                if any(task.id == pending_task.id for pending_task in pending):
                    accepted_new_tasks.add(task.id)
        assignments[did] = accepted
    missed = len(pending) - len(accepted_new_tasks)

    runtime_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return OptimizationResult(
        optimization_id=f"OPT-CLS-{uuid.uuid4().hex[:6].upper()}",
        algorithm=StrategyType.CLASSICAL,
        started_at_iso=started_iso,
        completed_at_iso=datetime.now(timezone.utc).isoformat(),
        solver_runtime_ms=runtime_ms,
        objective_value=round(total_obj + missed * unassigned_penalty, 2),
        feasible=True,
        assignments={k: v for k, v in assignments.items() if v},
        missed_tasks=missed,
        fallback_used=fallback_note,
    )
