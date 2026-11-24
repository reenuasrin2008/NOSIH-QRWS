from __future__ import annotations
from typing import Dict
from app.core.config import CONFIG
from app.core.models import StrategyMetrics


def compute_objective_breakdown(m: StrategyMetrics, total_tasks: int = 50) -> Dict[str, float]:
    w = CONFIG.weights
    total = max(1, total_tasks)
    norm_time = max(0.0, min(1.0, m.avg_response_time_s / 600.0)) if m.missions_completed > 0 else 1.0
    norm_energy = max(0.0, min(1.0, m.total_energy_wh / 4500.0))
    norm_risk = max(0.0, min(1.0, m.operational_risk))
    deadline_ratio = max(0.0, min(1.0, m.deadline_violations / total))
    uncompleted_ratio = max(0.0, min(1.0, 1.0 - (m.missions_completed / total)))

    terms = {
        "rescue_time_term": round(w.w_rescue_time * norm_time, 4),
        "energy_term": round(w.w_energy * norm_energy, 4),
        "risk_term": round(w.w_risk * norm_risk, 4),
        "deadline_term": round(w.w_deadline_violations * deadline_ratio, 4),
        "uncompleted_term": round(w.w_uncompleted * uncompleted_ratio, 4),
    }
    terms["total_objective_j"] = round(sum(terms.values()), 4)
    return terms
