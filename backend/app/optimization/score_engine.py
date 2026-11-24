from __future__ import annotations
from typing import List
from app.core.config import CONFIG
from app.core.models import StrategyMetrics


def compute_strategy_score(m: StrategyMetrics, total_tasks: int = 50) -> float:
    w = CONFIG.weights
    total = max(1, total_tasks)
    completion_ratio = max(0.0, min(1.0, m.missions_completed / total))
    uncompleted_ratio = 1.0 - completion_ratio
    deadline_ratio = max(0.0, min(1.0, m.deadline_violations / total))
    norm_time = max(0.0, min(1.0, m.avg_response_time_s / 600.0)) if m.missions_completed > 0 else 1.0
    norm_energy = max(0.0, min(1.0, m.total_energy_wh / 4500.0))
    norm_risk = max(0.0, min(1.0, m.operational_risk))

    objective_j = (
        w.w_rescue_time * norm_time
        + w.w_energy * norm_energy
        + w.w_risk * norm_risk
        + w.w_deadline_violations * deadline_ratio
        + w.w_uncompleted * uncompleted_ratio
    )
    raw_score = max(0.0, min(100.0, (1.0 - objective_j) * 100.0))
    if not m.feasible or m.error:
        raw_score = min(raw_score * 0.4, 35.0)
    return round(raw_score, 2)


def rank_leaderboard(metrics_list: List[StrategyMetrics], total_tasks: int = 50) -> List[StrategyMetrics]:
    for m in metrics_list:
        m.score = compute_strategy_score(m, total_tasks=total_tasks)
        m.solution_quality = m.score

    ordered = sorted(
        metrics_list,
        key=lambda x: (1 if (x.feasible and not x.error) else 0, x.score, x.missions_completed, -x.total_energy_wh),
        reverse=True,
    )
    for idx, item in enumerate(ordered):
        if idx > 0 and ordered[idx - 1].score == item.score and ordered[idx - 1].feasible == item.feasible:
            item.rank = ordered[idx - 1].rank
        else:
            item.rank = idx + 1
    return ordered
