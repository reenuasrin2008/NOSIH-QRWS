from __future__ import annotations
from typing import Dict, List
from app.core.models import DroneState, RescueTask, TaskStatus


def release_incomplete_tasks(drone: DroneState, tasks: Dict[str, RescueTask]) -> List[str]:
    released: List[str] = []
    candidates = list(drone.assigned_task_ids)
    if drone.active_task_id and drone.active_task_id not in candidates:
        candidates.append(drone.active_task_id)
    for tid in candidates:
        t = tasks.get(tid)
        if t and t.status != TaskStatus.COMPLETED:
            t.assigned_drone_id = None
            t.status = TaskStatus.REQUIRES_REASSIGNMENT
            released.append(tid)
    drone.assigned_task_ids.clear()
    drone.active_task_id = None
    drone.current_route = None
    drone.current_payload_kg = 0.0
    return released
