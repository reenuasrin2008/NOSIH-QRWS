from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Dict

from app.core.models import CityEnvironment, DroneState, OptimizationResult, RescueTask, StrategyType
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.classical_solver import solve_classical
from app.optimization.greedy_solver import solve_greedy
from app.optimization.hybrid_solver import solve_hybrid
from app.optimization.quantum_solver import solve_quantum_qaoa


def _empty_result(strategy: StrategyType, task_count: int, errors: list[str]) -> OptimizationResult:
    now = datetime.now(timezone.utc).isoformat()
    return OptimizationResult(
        optimization_id=f"OPT-EMPTY-{uuid.uuid4().hex[:6].upper()}",
        algorithm=strategy,
        started_at_iso=now,
        completed_at_iso=now,
        solver_runtime_ms=0.0,
        objective_value=0.0,
        feasible=False,
        assignments={},
        missed_tasks=task_count,
        fallback_used="Safe empty plan: all solver tiers failed",
        errors=errors,
    )


def _checked_result(result: OptimizationResult, strategy: StrategyType) -> OptimizationResult:
    if not isinstance(result, OptimizationResult):
        raise TypeError("Solver returned an invalid result")
    if not result.feasible:
        raise ValueError("Solver returned an infeasible plan")
    return result


def execute_with_failover(
    strategy: StrategyType,
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float,
    seed: int,
) -> OptimizationResult:
    """Run solver tiers and always return a safe, serializable result."""
    errors: list[str] = []
    try:
        if strategy == StrategyType.GREEDY:
            result = solve_greedy(drones, tasks, city, grid, sim_time_s)
        elif strategy == StrategyType.CLASSICAL:
            result = solve_classical(drones, tasks, city, grid, sim_time_s)
        elif strategy == StrategyType.QUANTUM:
            result = solve_quantum_qaoa(drones, tasks, city, grid, sim_time_s, seed=seed)
        else:
            result = solve_hybrid(drones, tasks, city, grid, sim_time_s, seed=seed)
        return _checked_result(result, strategy)
    except Exception as primary_exc:
        errors.append(f"{strategy.value} primary solver failed: {primary_exc}")

    try:
        result = solve_classical(drones, tasks, city, grid, sim_time_s)
        result = _checked_result(result, strategy)
        result.fallback_used = f"Classical failover after {strategy.value} error: {errors[0]}"
        result.errors.extend(errors)
        return result
    except Exception as secondary_exc:
        errors.append(f"Classical failover failed: {secondary_exc}")

    try:
        result = solve_greedy(drones, tasks, city, grid, sim_time_s)
        result = _checked_result(result, strategy)
        result.fallback_used = "Greedy failover after classical failure"
        result.errors.extend(errors)
        return result
    except Exception as tertiary_exc:
        errors.append(f"Greedy failover failed: {tertiary_exc}")

    return _empty_result(strategy, len(tasks), errors)
