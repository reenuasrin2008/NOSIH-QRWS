from __future__ import annotations
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import numpy as np

from app.core.config import CONFIG
from app.core.models import (
    CityEnvironment,
    DroneState,
    DroneStatus,
    OptimizationResult,
    QuantumMetrics,
    RescueTask,
    StrategyType,
    TaskStatus,
)
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.feasibility import estimate_assignment_cost, is_drone_eligible_for_task


def _fast_quantum_inspired_qubo(
    Q: np.ndarray,
    steps: int = 16,
    seed: int = 42,
) -> Tuple[str, float, List[dict], List[dict]]:
    """Classical simulated annealing with a QUBO energy/visit-distribution trace."""
    n = Q.shape[0]
    if n == 0:
        return "", 0.0, [], []
    rng = np.random.default_rng(seed)

    def energy(bits: np.ndarray) -> float:
        return float(bits @ Q @ bits)

    best_bits = np.zeros(n, dtype=float)
    best_e = energy(best_bits)
    samples: Dict[str, int] = {}
    history: List[dict] = []

    steps = max(1, int(steps))
    cur = (rng.random(n) > 0.5).astype(float)
    cur_e = energy(cur)
    for step in range(1, steps + 1):
        temp = max(0.05, 1.4 * (1.0 - step / (steps + 1)))
        cand = cur.copy()
        flip = int(rng.integers(0, n))
        cand[flip] = 1.0 - cand[flip]
        ce = energy(cand)
        if not math.isfinite(ce):
            continue
        if ce < cur_e or rng.random() < math.exp(max(-700.0, min(0.0, (cur_e - ce) / temp))):
            cur, cur_e = cand, ce
        if cur_e < best_e:
            best_bits, best_e = cur.copy(), cur_e
        bs = "".join(str(int(b)) for b in cur)
        samples[bs] = samples.get(bs, 0) + 1
        history.append({"iteration": step, "energy": round(cur_e, 4), "best_energy": round(best_e, 4)})

    best_str = "".join(str(int(b)) for b in best_bits)
    samples[best_str] = samples.get(best_str, 0) + 1
    total = max(1, sum(samples.values()))
    top_bitstrings = sorted(
        [
            {
                "bitstring": k,
                "probability": round(v / total, 4),
                "energy": round(energy(np.array([int(c) for c in k], dtype=float)), 3),
            }
            for k, v in samples.items()
        ],
        key=lambda x: x["probability"],
        reverse=True,
    )[:8]
    return best_str, best_e, history, top_bitstrings


def solve_quantum_qaoa(
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float = 0.0,
    seed: int = 42,
) -> OptimizationResult:
    """Classical simulated-annealing QUBO heuristic with routed validation.

    The public function name is retained for API compatibility. No quantum
    hardware or QAOA circuit is executed; metrics identify the actual backend.
    """
    t0 = time.perf_counter()

    avail_drones = [
        d for d in drones.values()
        if d.status in (DroneStatus.AVAILABLE, DroneStatus.ASSIGNED, DroneStatus.IN_FLIGHT)
        and d.battery_percent > 20.0
    ]
    open_tasks = [
        t for t in tasks.values()
        if t.status in (TaskStatus.PENDING, TaskStatus.REQUIRES_REASSIGNMENT, TaskStatus.UNASSIGNED)
    ]

    max_q = min(CONFIG.qaoa_max_qubits, 8)
    pair_candidates: List[Tuple[str, str, float]] = []
    for task in open_tasks:
        for dr in avail_drones:
            if task.payload_required_kg > dr.max_payload_kg:
                continue
            if not all(cap in dr.capabilities for cap in task.required_capabilities):
                continue
            elig = is_drone_eligible_for_task(
                dr, task, city, grid, strategy="quantum",
                assigned_task_ids=list(dr.assigned_task_ids) + [task.id], tasks=tasks,
            )
            ok = elig[0]
            if ok:
                c_res = estimate_assignment_cost(dr, task, city, sim_time_s)
                cost = c_res[0] if isinstance(c_res, tuple) else float(c_res)
                if math.isfinite(cost):
                    pair_candidates.append((dr.id, task.id, cost))

    pair_candidates.sort(key=lambda x: x[2])
    sub = pair_candidates[:max_q]
    n = len(sub)
    Q = np.zeros((n, n), dtype=float)
    for i in range(n):
        ci = sub[i][2] if i < len(sub) else 100.0
        Q[i, i] = (ci / 100.0) - 2.4
        for j in range(i + 1, n):
            if i < len(sub) and j < len(sub) and (sub[i][1] == sub[j][1] or sub[i][0] == sub[j][0]):
                Q[i, j] += 3.0
                Q[j, i] += 3.0

    best_bs, best_e, history, top_bs = _fast_quantum_inspired_qubo(Q, steps=16, seed=seed)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Decode the QUBO bitstring and admit only routed, conflict-free,
    # cumulative-battery-feasible assignments. Greedy output is not reused.
    assignments: Dict[str, List[str]] = {
        d.id: list(d.assigned_task_ids)
        for d in avail_drones if d.assigned_task_ids
    }
    selected_tasks: set[str] = set()
    repaired = 0
    objective = 0.0
    for idx, bit in enumerate(best_bs[:len(sub)]):
        if bit != "1":
            continue
        did, tid, cost = sub[idx]
        drone = drones[did]
        task = tasks[tid]
        if tid in selected_tasks:
            repaired += 1
            continue
        proposed = assignments.get(did, []) + [tid]
        if len(proposed) > 4:
            repaired += 1
            continue
        ok, _, _ = is_drone_eligible_for_task(
            drone, task, city, grid, strategy="quantum",
            assigned_task_ids=proposed, tasks=tasks,
        )
        if not ok:
            repaired += 1
            continue
        assignments.setdefault(did, []).append(tid)
        selected_tasks.add(tid)
        objective += cost

    q_metrics = QuantumMetrics(
        executed=n > 0,
        backend_name="classical_simulated_annealing_qubo",
        num_qubits=n,
        circuit_depth=0,
        qaoa_layers=0,
        iterations=len(history),
        shots=0,
        best_bitstring=best_bs,
        best_energy=round(best_e, 4),
        execution_time_ms=elapsed_ms,
        candidates_evaluated=len(history),
        validation_passed=repaired == 0,
        repaired_assignments=repaired,
        subproblem_tasks=sorted({x[1] for x in sub}),
        subproblem_drones=sorted({x[0] for x in sub}),
        top_samples=top_bs,
        convergence_history=history,
    )

    return OptimizationResult(
        optimization_id=f"OPT-QBI-{uuid.uuid4().hex[:6].upper()}",
        algorithm=StrategyType.QUANTUM,
        started_at_iso=datetime.now(timezone.utc).isoformat(),
        completed_at_iso=datetime.now(timezone.utc).isoformat(),
        solver_runtime_ms=elapsed_ms,
        objective_value=round(objective, 2),
        feasible=True,
        assignments=assignments,
        missed_tasks=max(0, len(open_tasks) - len(selected_tasks)),
        quantum_metrics=q_metrics,
        fallback_used="Classical quantum-inspired QUBO heuristic; no quantum hardware or QAOA circuit executed.",
    )
