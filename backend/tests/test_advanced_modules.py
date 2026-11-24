from app.benchmark.leaderboard import sort_leaderboard
from app.core.models import StrategyType
from app.optimization.objective import compute_objective_breakdown
from app.optimization.route_sequencer import sequence_drone_tasks
from app.recovery.failure_detector import scan_fleet_anomalies
from app.simulation.charging_manager import ChargingPadManager
from app.simulation.collision_manager import assign_corridor_altitude
from app.simulation.world import SimulationWorld


def test_charging_pad_capacity_and_diversion():
    w = SimulationWorld(seed=20261121)
    mgr = ChargingPadManager(w.city)
    st0 = w.city.stations[0]
    st0.capacity = 1
    assert mgr.request_pad("D-01", st0) is True
    assert mgr.request_pad("D-02", st0) is False
    alt = mgr.select_available_station(w.drones["D-02"], w.city)
    assert alt is not None and alt.id != st0.id
    mgr.release_pad("D-01")
    assert "D-02" in mgr.slots[st0.id]


def test_cvrptw_route_sequencer_and_corridors():
    w = SimulationWorld(seed=20261121)
    d = w.drones["D-01"]
    ordered = sequence_drone_tasks(d, ["T-001", "T-002", "T-003", "T-004"], w.tasks, 0.0)
    assert len(ordered) == 4 and set(ordered) == {"T-001", "T-002", "T-003", "T-004"}
    crit_alt = assign_corridor_altitude(d, is_critical=True)
    norm_alt = assign_corridor_altitude(d, is_critical=False)
    assert crit_alt > norm_alt


def test_qaoa_convergence_history_and_objective_breakdown():
    w = SimulationWorld(seed=20261121, strategy=StrategyType.QUANTUM)
    w.run_optimizer("initial_plan")
    assert w.last_quantum_metrics is not None
    assert len(w.last_quantum_metrics.convergence_history) >= 5
    breakdown = compute_objective_breakdown(w.get_metrics(), total_tasks=len(w.tasks))
    assert "total_objective_j" in breakdown
    sorted_lb = sort_leaderboard([w.get_metrics()], sort_by="energy")
    assert len(sorted_lb) == 1
    alerts = scan_fleet_anomalies(w.drones)
    assert isinstance(alerts, list)
