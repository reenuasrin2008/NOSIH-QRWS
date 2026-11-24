import io
import zipfile
from app.benchmark.runner import BenchmarkArena
from app.core.models import DroneStatus, FailureType, StrategyType, TaskPriority
from app.logging.export_manager import build_experiment_zip
from app.simulation.world import SimulationWorld


def test_seeded_city_fleet_and_tasks():
    w1 = SimulationWorld(seed=20261121)
    w2 = SimulationWorld(seed=20261121)
    assert len(w1.drones) == 30 and len(w1.tasks) == 50
    assert len(w1.city.buildings) == len(w2.city.buildings)
    assert w1.tasks["T-001"].location == w2.tasks["T-001"].location


def test_astar_route_avoids_buildings_and_hazards():
    w = SimulationWorld(seed=20261121)
    route = w.grid.plan_route(w.drones["D-01"].position, w.tasks["T-001"].location, w.drones["D-01"], strategy="hybrid", task_id="T-001")
    assert route.feasible and len(route.waypoints) >= 3 and w.grid.is_route_valid(route)


def test_all_four_strategies_and_isolated_benchmark():
    arena = BenchmarkArena(SimulationWorld(seed=20261121))
    arena.start_all()
    q_world = arena.worlds[StrategyType.QUANTUM]
    assert q_world.last_quantum_metrics and q_world.last_quantum_metrics.executed is True
    for _ in range(20):
        arena.step_all(dt=1.0)
    lb = arena.get_leaderboard()
    assert len(lb) == 4 and all(m.total_energy_wh > 0 for m in lb)


def test_drone_destruction_and_automatic_task_recovery():
    w = SimulationWorld(seed=20261121, strategy=StrategyType.HYBRID)
    w.run_optimizer("initial_plan")
    for _ in range(5):
        w.step(dt=1.0)
    target = w.drones["D-04"] if w.drones["D-04"].assigned_task_ids else next(d for d in w.drones.values() if d.assigned_task_ids)
    had = list(target.assigned_task_ids)
    assert w.inject_failure(target.id, FailureType.COMPLETE_DRONE_DESTRUCTION)["ok"] is True
    assert target.status == DroneStatus.DESTROYED
    for tid in had:
        assert w.tasks[tid].assigned_drone_id != target.id


def test_hazard_expansion_and_zip_export():
    w = SimulationWorld(seed=20261121, strategy=StrategyType.HYBRID)
    w.run_optimizer("initial_plan")
    for _ in range(12):
        w.step(dt=1.0)
    assert w.inject_environment_event("expand_fire", {"delta_radius": 35.0})["ok"] is True
    with zipfile.ZipFile(io.BytesIO(build_experiment_zip(w)), "r") as zf:
        assert {"summary.json", "drones.csv", "tasks.csv", "leaderboard.csv", "replay.json", "experiment_report.html"}.issubset(set(zf.namelist()))
