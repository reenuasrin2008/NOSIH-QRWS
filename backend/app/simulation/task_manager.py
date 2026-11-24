from __future__ import annotations
import math
import random
from typing import Dict, List
from app.core.config import TASK_TYPE_SPECS
from app.core.models import CityEnvironment, RescueTask, TaskPriority, TaskStatus


def generate_tasks(city: CityEnvironment, seed: int, count: int = 50) -> Dict[str, RescueTask]:
    rng = random.Random(seed + 202)
    priorities: List[TaskPriority] = (
        [TaskPriority.CRITICAL] * 12
        + [TaskPriority.HIGH] * 15
        + [TaskPriority.MEDIUM] * 15
        + [TaskPriority.LOW] * 8
    )
    if count != 50:
        priorities = [priorities[i % len(priorities)] for i in range(count)]
    rng.shuffle(priorities)

    task_types = list(TASK_TYPE_SPECS.keys())
    tasks: Dict[str, RescueTask] = {}

    def is_valid_spawn(x: float, z: float) -> bool:
        for hz in city.hazards:
            if hz.kind == "no_fly" and math.hypot(x - hz.x, z - hz.z) < hz.radius + 12.0:
                return False
        for b in city.buildings:
            if abs(x - b.x) < b.width / 2.0 + 4.0 and abs(z - b.z) < b.depth / 2.0 + 4.0:
                return False
        return True

    deadline_ranges = {
        TaskPriority.CRITICAL: (240.0, 420.0),
        TaskPriority.HIGH: (420.0, 680.0),
        TaskPriority.MEDIUM: (680.0, 960.0),
        TaskPriority.LOW: (900.0, 1250.0),
    }

    for i in range(count):
        tid = f"T-{i+1:03d}"
        prio = priorities[i]
        if prio == TaskPriority.CRITICAL:
            ttype = rng.choice(["medical_delivery", "missing_person", "survivor_search", "fire_monitoring"])
        elif prio == TaskPriority.HIGH:
            ttype = rng.choice(["medical_delivery", "water_supply", "survivor_search", "equipment_delivery", "flood_inspection"])
        else:
            ttype = rng.choice(task_types)

        spec = TASK_TYPE_SPECS[ttype]
        x, z = 500.0, 500.0
        for _ in range(40):
            cx = rng.uniform(220.0, city.world_size - 220.0)
            cz = rng.uniform(220.0, city.world_size - 220.0)
            if is_valid_spawn(cx, cz):
                x, z = cx, cz
                break

        d_min, d_max = deadline_ranges[prio]
        deadline = round(rng.uniform(d_min, d_max), 0)
        risk = round(rng.uniform(0.55, 0.92) if prio == TaskPriority.CRITICAL else rng.uniform(0.15, 0.65), 2)

        tasks[tid] = RescueTask(
            id=tid,
            name=f"{ttype.replace('_', ' ').title()} #{i+1:02d}",
            task_type=ttype,
            location=(round(x, 1), 2.0, round(z, 1)),
            priority=prio,
            deadline_seconds=deadline,
            payload_required_kg=spec["payload_kg"],
            required_capabilities=list(spec["required_capabilities"]),
            service_time_seconds=spec["service_time"],
            risk_level=risk,
            description=f"Seeded {prio.value} disaster response mission ({ttype}).",
            status=TaskStatus.PENDING,
            created_at_sim_s=0.0,
        )
    return tasks
