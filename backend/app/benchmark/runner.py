from __future__ import annotations
import uuid
from typing import Any, Dict, List
from app.core.models import FailureType, SimulationStatus, StrategyMetrics, StrategyType
from app.optimization.score_engine import rank_leaderboard
from app.simulation.world import SimulationWorld


class BenchmarkArena:
    def __init__(self, base_world: SimulationWorld):
        self.benchmark_id: str = f"BMK-{uuid.uuid4().hex[:6].upper()}"
        self.seed: int = base_world.seed
        self.active_view: StrategyType = StrategyType.HYBRID
        self.worlds: Dict[StrategyType, SimulationWorld] = {}
        for strat in (StrategyType.GREEDY, StrategyType.CLASSICAL, StrategyType.QUANTUM, StrategyType.HYBRID):
            self.worlds[strat] = base_world.clone_for_strategy(strat, run_id=f"{self.benchmark_id}-{strat.value.upper()}")

    def start_all(self) -> None:
        for w in self.worlds.values():
            w.run_optimizer("initial_plan")
            w.status = SimulationStatus.RUNNING

    def pause_all(self) -> None:
        for w in self.worlds.values():
            if w.status == SimulationStatus.RUNNING:
                w.status = SimulationStatus.PAUSED

    def resume_all(self) -> None:
        for w in self.worlds.values():
            if w.status == SimulationStatus.PAUSED:
                w.status = SimulationStatus.RUNNING

    def step_all(self, dt: float = 1.0) -> None:
        for w in self.worlds.values():
            if w.status == SimulationStatus.RUNNING:
                w.step(dt)

    def set_speed(self, speed: float) -> None:
        for w in self.worlds.values():
            w.speed_multiplier = speed

    def broadcast_task(self, **task_kwargs) -> Dict[str, str]:
        return {strat.value: w.add_task(**task_kwargs).id for strat, w in self.worlds.items()}

    def inject_failure(self, drone_id: str, failure_type: FailureType, scope: str = "all") -> Dict[str, Any]:
        targets = self.worlds.items() if scope == "all" else [(self.active_view, self.worlds[self.active_view])]
        return {strat.value: w.inject_failure(drone_id, failure_type) for strat, w in targets}

    def broadcast_environment_event(self, event_kind: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {strat.value: w.inject_environment_event(event_kind, params) for strat, w in self.worlds.items()}

    def get_leaderboard(self) -> List[StrategyMetrics]:
        raw = [w.get_metrics() for w in self.worlds.values()]
        return rank_leaderboard(raw, total_tasks=len(self.worlds[self.active_view].tasks))

    def get_ghost_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for strat, w in self.worlds.items():
            out[strat.value] = [
                {"drone_id": d.id, "strategy": strat.value, "waypoints": d.current_route.waypoints, "color_tag": d.current_route.color_tag}
                for d in w.drones.values() if d.current_route
            ]
        return out

    def serialize(self, include_city: bool = False) -> Dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "active_view": self.active_view.value,
            "leaderboard": [m.model_dump() for m in self.get_leaderboard()],
            "active_state": self.worlds[self.active_view].serialize_state(include_city=include_city),
            "ghost_routes": self.get_ghost_routes(),
        }
