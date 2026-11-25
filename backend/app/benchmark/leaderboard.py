from __future__ import annotations
from typing import List
from app.core.models import StrategyMetrics
from app.optimization.score_engine import rank_leaderboard


def sort_leaderboard(metrics: List[StrategyMetrics], sort_by: str = "score", total_tasks: int = 50) -> List[StrategyMetrics]:
    ranked = rank_leaderboard(metrics, total_tasks=total_tasks)
    if sort_by == "rescue_time":
        return sorted(ranked, key=lambda m: (0 if m.missions_completed > 0 else 1, m.avg_response_time_s))
    if sort_by == "energy":
        return sorted(ranked, key=lambda m: m.total_energy_wh)
    if sort_by == "risk":
        return sorted(ranked, key=lambda m: m.operational_risk)
    if sort_by == "completed":
        return sorted(ranked, key=lambda m: (-m.missions_completed, -m.score))
    if sort_by == "runtime":
        return sorted(ranked, key=lambda m: m.solver_runtime_ms)
    return ranked
