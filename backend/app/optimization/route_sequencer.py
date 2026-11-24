from __future__ import annotations
import itertools
import math
from typing import Dict, List
from app.core.models import DroneState, RescueTask

PRIO_PENALTY = {"critical": 5.0, "high": 3.0, "medium": 1.6, "low": 1.0}


def sequence_drone_tasks(
    drone: DroneState,
    task_ids: List[str],
    tasks: Dict[str, RescueTask],
    sim_time_s: float = 0.0,
) -> List[str]:
    """
    CVRPTW multi-stop route sequencer for an individual drone's assigned tasks.
    Finds the exact minimum-cost visit order minimizing travel time + priority-weighted
    lateness across all permutations (for <= 6 stops) or greedy nearest-deadline insertion.
    """
    valid = list(dict.fromkeys(tid for tid in task_ids if tid in tasks))
    if len(valid) <= 1:
        return valid

    speed = max(drone.cruise_speed_mps, 1.0)

    def eval_order(order: tuple[str, ...]) -> float:
        cur_x, cur_z = drone.position[0], drone.position[2]
        t_cur = sim_time_s
        cost = 0.0
        for tid in order:
            task = tasks[tid]
            dist = math.hypot(task.location[0] - cur_x, task.location[2] - cur_z)
            travel_s = dist / speed
            t_cur += travel_s + task.service_time_seconds
            lateness = max(0.0, t_cur - task.deadline_seconds)
            w = PRIO_PENALTY.get(task.priority.value, 1.0)
            cost += travel_s + (lateness * 3.5 * w) + (t_cur * 0.12 * w)
            cur_x, cur_z = task.location[0], task.location[2]
        return cost

    if len(valid) <= 6:
        best = min(itertools.permutations(valid), key=eval_order)
        return list(best)

    # Greedy earliest-weighted-arrival heuristic for > 6 tasks
    remaining = list(valid)
    ordered: List[str] = []
    cur_x, cur_z = drone.position[0], drone.position[2]
    t_cur = sim_time_s
    while remaining:
        nxt = min(
            remaining,
            key=lambda tid: (
                math.hypot(tasks[tid].location[0] - cur_x, tasks[tid].location[2] - cur_z) / speed
                + max(0.0, tasks[tid].deadline_seconds - t_cur) * 0.35
            ) / PRIO_PENALTY.get(tasks[tid].priority.value, 1.0),
        )
        ordered.append(nxt)
        remaining.remove(nxt)
        t_cur += math.hypot(tasks[nxt].location[0] - cur_x, tasks[nxt].location[2] - cur_z) / speed + tasks[nxt].service_time_seconds
        cur_x, cur_z = tasks[nxt].location[0], tasks[nxt].location[2]
    return ordered
