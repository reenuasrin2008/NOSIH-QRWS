from __future__ import annotations
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List
from app.core.models import CityEnvironment, DroneState, OptimizationResult, RescueTask, StrategyType
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.classical_solver import solve_classical
from app.optimization.greedy_solver import solve_greedy
from app.optimization.quantum_solver import solve_quantum_qaoa


def solve_hybrid(
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float = 0.0,
    seed: int = 20261121,
) -> OptimizationResult:
    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()
    errors: List[str] = []
    fallback_used = None

    try:
        classical_res = solve_classical(drones, tasks, city, grid, sim_time_s)
    except Exception as exc:
        errors.append(f"Classical baseline error: {exc}")
        classical_res = solve_greedy(drones, tasks, city, grid, sim_time_s)
        fallback_used = "Greedy fallback (classical error)"

    q_res = None
    try:
        q_res = solve_quantum_qaoa(drones, tasks, city, grid, sim_time_s, seed=seed)
    except Exception as exc:
        errors.append(f"QAOA refinement error: {exc}")
        fallback_used = "Retained classical baseline (QAOA unavailable)"

    chosen = classical_res
    if q_res is not None and q_res.feasible:
        if q_res.missed_tasks < classical_res.missed_tasks or (
            q_res.missed_tasks == classical_res.missed_tasks
            and q_res.objective_value < classical_res.objective_value
        ):
            chosen = q_res

    runtime_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return OptimizationResult(
        optimization_id=f"OPT-HYB-{uuid.uuid4().hex[:6].upper()}",
        algorithm=StrategyType.HYBRID,
        started_at_iso=started_iso,
        completed_at_iso=datetime.now(timezone.utc).isoformat(),
        solver_runtime_ms=runtime_ms,
        objective_value=chosen.objective_value,
        feasible=chosen.feasible,
        assignments=chosen.assignments,
        missed_tasks=chosen.missed_tasks,
        quantum_metrics=q_res.quantum_metrics if q_res else None,
        fallback_used=fallback_used,
        errors=errors,
    )
