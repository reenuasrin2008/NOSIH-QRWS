from __future__ import annotations
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import numpy as np
from scipy.optimize import minimize
from app.core.config import CONFIG
from app.core.models import (
    CityEnvironment, DroneState, DroneStatus, OptimizationResult,
    QuantumMetrics, RescueTask, StrategyType, TaskStatus
)
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.optimization.feasibility import estimate_assignment_cost, is_drone_eligible_for_task
from app.optimization.greedy_solver import solve_greedy

try:
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator
    HAS_QISKIT = True
except Exception:
    HAS_QISKIT = False


def _qubo_energy(bitstring: str, Q: np.ndarray) -> float:
    x = np.array([int(b) for b in bitstring], dtype=float)
    return float(x @ Q @ x)


def _run_qaoa_qiskit(Q: np.ndarray, p_layers: int, shots: int, max_iter: int) -> Tuple[str, float, int, int, List[dict], List[dict]]:
    n = Q.shape[0]
    sim = AerSimulator()
    h = np.zeros(n)
    J = np.zeros((n, n))
    for i in range(n):
        h[i] += 0.5 * Q[i, i]
        for j in range(i + 1, n):
            coeff = Q[i, j] + Q[j, i]
            if abs(coeff) > 1e-9:
                h[i] += 0.25 * coeff
                h[j] += 0.25 * coeff
                J[i, j] += 0.25 * coeff

    def build_circuit(params: np.ndarray) -> QuantumCircuit:
        gammas, betas = params[:p_layers], params[p_layers:]
        qc = QuantumCircuit(n)
        qc.h(range(n))
        for layer in range(p_layers):
            g, b = float(gammas[layer]), float(betas[layer])
            for i in range(n):
                if abs(h[i]) > 1e-9:
                    qc.rz(2.0 * g * h[i], i)
            for i in range(n):
                for j in range(i + 1, n):
                    if abs(J[i, j]) > 1e-9:
                        qc.rzz(2.0 * g * J[i, j], i, j)
            for i in range(n):
                qc.rx(2.0 * b, i)
        qc.measure_all()
        return qc

    iter_count = 0
    history: List[dict] = []

    def objective(params: np.ndarray) -> float:
        nonlocal iter_count
        iter_count += 1
        counts = sim.run(build_circuit(params), shots=shots).result().get_counts()
        val = sum((cnt / shots) * _qubo_energy(bs[::-1], Q) for bs, cnt in counts.items())
        history.append({'iter': float(iter_count), 'energy': round(float(val), 2)})
        return val

    init_params = np.concatenate([np.linspace(0.2, 0.7, p_layers), np.linspace(0.3, 0.6, p_layers)])
    res = minimize(objective, init_params, method="COBYLA", options={"maxiter": max_iter})
    final_qc = build_circuit(res.x)
    depth = final_qc.depth()
    final_counts = sim.run(final_qc, shots=shots).result().get_counts()

    ranked = sorted(
        [(bs[::-1], cnt, round(_qubo_energy(bs[::-1], Q), 3)) for bs, cnt in final_counts.items()],
        key=lambda item: (item[2], -item[1]),
    )
    best_bs, _, best_e = ranked[0]
    top_samples = [{"bitstring": r[0], "count": r[1], "energy": r[2]} for r in ranked[:5]]
    return best_bs, best_e, depth, iter_count, top_samples, history


def _run_qaoa_statevector_numpy(Q: np.ndarray, p_layers: int, shots: int, max_iter: int, seed: int = 42) -> Tuple[str, float, int, int, List[dict], List[dict]]:
    n = Q.shape[0]
    dim = 1 << n
    basis_bits = ((np.arange(dim)[:, None] >> np.arange(n - 1, -1, -1)) & 1).astype(float)
    energies = np.einsum("bi,ij,bj->b", basis_bits, Q, basis_bits)
    scale = max(1.0, float(np.max(np.abs(energies))))
    norm_energies = energies / scale

    def evolve_state(params: np.ndarray) -> np.ndarray:
        gammas, betas = params[:p_layers], params[p_layers:]
        psi = np.full(dim, 1.0 / math.sqrt(dim), dtype=np.complex128)
        for layer in range(p_layers):
            g, b = float(gammas[layer]), float(betas[layer])
            psi *= np.exp(-1j * g * norm_energies)
            cb, sb = math.cos(b), -1j * math.sin(b)
            for k in range(n):
                bit = 1 << (n - 1 - k)
                psi_r = psi.reshape(-1, 2, bit)
                p0, p1 = psi_r[:, 0, :].copy(), psi_r[:, 1, :].copy()
                psi_r[:, 0, :] = cb * p0 + sb * p1
                psi_r[:, 1, :] = sb * p0 + cb * p1
                psi = psi_r.reshape(dim)
        return psi

    iter_count = 0
    history: List[dict] = []

    def expectation(params: np.ndarray) -> float:
        nonlocal iter_count
        iter_count += 1
        probs = np.abs(evolve_state(params)) ** 2
        val = float(np.dot(probs, energies))
        history.append({'iter': float(iter_count), 'energy': round(val, 2)})
        return val

    init_params = np.concatenate([np.linspace(0.25, 0.8, p_layers), np.linspace(0.35, 0.7, p_layers)])
    res = minimize(expectation, init_params, method="COBYLA", options={"maxiter": max_iter})
    probs = np.abs(evolve_state(res.x)) ** 2
    probs /= probs.sum()

    rng = np.random.default_rng(seed)
    samples = rng.choice(dim, size=shots, p=probs)
    unique, counts = np.unique(samples, return_counts=True)
    ranked = sorted(
        [(format(int(u), f"0{n}b"), int(c), round(float(energies[int(u)]), 3)) for u, c in zip(unique, counts)],
        key=lambda item: (item[2], -item[1]),
    )
    best_bs, _, best_e = ranked[0]
    depth = p_layers * (n + 3) + 2
    top_samples = [{"bitstring": r[0], "count": r[1], "energy": r[2]} for r in ranked[:5]]
    return best_bs, best_e, depth, iter_count, top_samples, history


def solve_quantum_qaoa(
    drones: Dict[str, DroneState],
    tasks: Dict[str, RescueTask],
    city: CityEnvironment,
    grid: SpatialAirspaceGrid,
    sim_time_s: float = 0.0,
    seed: int = 20261121,
) -> OptimizationResult:
    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    pending = [
        t for t in tasks.values()
        if t.status in (TaskStatus.PENDING, TaskStatus.REQUIRES_REASSIGNMENT, TaskStatus.UNASSIGNED)
    ]
    prio_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending.sort(key=lambda t: (prio_rank[t.priority.value], t.deadline_seconds, t.id))

    eligible_drones = [
        d for d in drones.values()
        if d.status not in (
            DroneStatus.DESTROYED, DroneStatus.DAMAGED,
            DroneStatus.COMMUNICATION_LOST, DroneStatus.LOW_BATTERY
        )
    ]

    max_qubits = min(CONFIG.qaoa_max_qubits, 8)
    sub_vars: List[Tuple[DroneState, RescueTask, float]] = []
    selected_task_ids: List[str] = []
    selected_drone_ids: set[str] = set()

    for task in pending:
        if len(sub_vars) + 2 > max_qubits:
            break
        candidates = []
        for d in eligible_drones:
            if task.payload_required_kg > d.max_payload_kg:
                continue
            if not all(c in d.capabilities for c in task.required_capabilities):
                continue
            candidates.append((estimate_assignment_cost(d, task, city, sim_time_s), d))
        candidates.sort(key=lambda x: x[0])
        if len(candidates) >= 2:
            for cost, d in candidates[:2]:
                sub_vars.append((d, task, cost))
                selected_drone_ids.add(d.id)
            selected_task_ids.append(task.id)

    n_qubits = len(sub_vars)
    assignments: Dict[str, List[str]] = {d.id: list(d.assigned_task_ids) for d in eligible_drones}
    repaired = 0
    backend_label = (
        "QAOA — Classical quantum-circuit simulation (Qiskit Aer)"
        if HAS_QISKIT
        else "QAOA — Classical quantum-circuit simulation (Exact Statevector)"
    )
    q_metrics = QuantumMetrics(executed=False, backend_name=backend_label)

    assigned_in_qaoa: set[str] = set()
    qaoa_obj = 0.0

    if n_qubits >= 4:
        qt0 = time.perf_counter()
        Q = np.zeros((n_qubits, n_qubits), dtype=float)
        penalty_one_hot = 420.0
        penalty_conflict = 180.0

        for idx, (_, _, cost) in enumerate(sub_vars):
            Q[idx, idx] += cost - penalty_one_hot

        task_groups: Dict[str, List[int]] = {}
        drone_groups: Dict[str, List[int]] = {}
        for idx, (d, t, _) in enumerate(sub_vars):
            task_groups.setdefault(t.id, []).append(idx)
            drone_groups.setdefault(d.id, []).append(idx)

        for indices in task_groups.values():
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    Q[indices[i], indices[j]] += 2.0 * penalty_one_hot

        for indices in drone_groups.values():
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    Q[indices[i], indices[j]] += penalty_conflict

        if HAS_QISKIT:
            best_bs, best_e, depth, iters, top_samples, conv_hist = _run_qaoa_qiskit(Q, CONFIG.qaoa_layers, CONFIG.qaoa_shots, CONFIG.qaoa_max_iter)
        else:
            best_bs, best_e, depth, iters, top_samples, conv_hist = _run_qaoa_statevector_numpy(Q, CONFIG.qaoa_layers, CONFIG.qaoa_shots, CONFIG.qaoa_max_iter, seed=seed)

        q_time_ms = round((time.perf_counter() - qt0) * 1000.0, 2)

        chosen_per_task: Dict[str, List[Tuple[DroneState, RescueTask, float]]] = {}
        for idx, bit in enumerate(best_bs):
            if bit == "1":
                d, t, cost = sub_vars[idx]
                chosen_per_task.setdefault(t.id, []).append((d, t, cost))

        all_valid = True
        for tid in selected_task_ids:
            picks = chosen_per_task.get(tid, [])
            if len(picks) == 1:
                d, t, cost = picks[0]
                ok, _, _ = is_drone_eligible_for_task(d, t, city, grid, strategy="quantum")
                if ok:
                    assignments[d.id].append(t.id)
                    assigned_in_qaoa.add(t.id)
                    qaoa_obj += cost
                    continue
            all_valid = False
            repaired += 1
            group = sorted([sub_vars[i] for i in task_groups[tid]], key=lambda item: item[2])
            for d, t, cost in group:
                ok, _, _ = is_drone_eligible_for_task(d, t, city, grid, strategy="quantum")
                if ok:
                    assignments[d.id].append(t.id)
                    assigned_in_qaoa.add(t.id)
                    qaoa_obj += cost
                    break

        q_metrics = QuantumMetrics(
            executed=True,
            backend_name=backend_label,
            num_qubits=n_qubits,
            circuit_depth=depth,
            qaoa_layers=CONFIG.qaoa_layers,
            iterations=iters,
            shots=CONFIG.qaoa_shots,
            best_bitstring=best_bs,
            best_energy=round(best_e, 3),
            execution_time_ms=q_time_ms,
            candidates_evaluated=len(top_samples),
            validation_passed=all_valid,
            repaired_assignments=repaired,
            subproblem_tasks=selected_task_ids,
            subproblem_drones=sorted(list(selected_drone_ids)),
            top_samples=top_samples,
            convergence_history=conv_hist,
        )

    remaining_tasks = {t.id: t for t in pending if t.id not in assigned_in_qaoa}
    temp_drones = {d.id: d.model_copy(deep=True) for d in drones.values()}
    for did, tids in assignments.items():
        if did in temp_drones:
            temp_drones[did].assigned_task_ids = list(tids)

    rest_res = solve_greedy(temp_drones, remaining_tasks, city, grid, sim_time_s)
    for did, tids in rest_res.assignments.items():
        assignments.setdefault(did, [])
        for tid in tids:
            if tid not in assignments[did]:
                assignments[did].append(tid)

    runtime_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return OptimizationResult(
        optimization_id=f"OPT-QAOA-{uuid.uuid4().hex[:6].upper()}",
        algorithm=StrategyType.QUANTUM,
        started_at_iso=started_iso,
        completed_at_iso=datetime.now(timezone.utc).isoformat(),
        solver_runtime_ms=runtime_ms,
        objective_value=round(qaoa_obj + rest_res.objective_value, 2),
        feasible=True,
        assignments={k: v for k, v in assignments.items() if v},
        missed_tasks=rest_res.missed_tasks,
        quantum_metrics=q_metrics,
    )
