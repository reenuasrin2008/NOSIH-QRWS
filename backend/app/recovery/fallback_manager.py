from __future__ import annotations
from typing import Dict
from app.core.models import CityEnvironment, DroneState, OptimizationResult, RescueTask, StrategyType
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.classical_solver import solve_classical
from app.optimization.greedy_solver import solve_greedy
from app.optimization.hybrid_solver import solve_hybrid
from app.optimization.quantum_solver import solve_quantum_qaoa


def execute_with_failover(
    strategy: StrategyType,
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float,
    seed: int,
) -> OptimizationResult:
    """
    Enforces the 4-tier failover hierarchy:
    Hybrid -> Classical OR-Tools -> Feasibility-checked Greedy -> Safe empty plan.
    Never crashes the simulation if a solver times out or fails.
    """
    try:
        if strategy == StrategyType.GREEDY:
            return solve_greedy(drones, tasks, city, grid, sim_time_s)
        if strategy == StrategyType.CLASSICAL:
            return solve_classical(drones, tasks, city, grid, sim_time_s)
        if strategy == StrategyType.QUANTUM:
            return solve_quantum_qaoa(drones, tasks, city, grid, sim_time_s, seed=seed)
        return solve_hybrid(drones, tasks, city, grid, sim_time_s, seed=seed)
    except Exception as primary_exc:
        try:
            res = solve_classical(drones, tasks, city, grid, sim_time_s)
            res.fallback_used = f"Classical failover after {strategy.value} error: {primary_exc}"
            res.errors.append(str(primary_exc))
            return res
        except Exception as secondary_exc:
            res = solve_greedy(drones, tasks, city, grid, sim_time_s)
            res.fallback_used = f"Greedy failover after {strategy.value}/{secondary_exc}"
            res.errors.extend([str(primary_exc), str(secondary_exc)])
            return res
