from __future__ import annotations
import heapq
import math
import uuid
from typing import Dict, List, Optional, Tuple
from app.core.config import CONFIG
from app.core.models import CityEnvironment, DroneState, RoutePlan
from app.simulation.battery_model import compute_route_energy_wh


class SpatialAirspaceGrid:
    def __init__(self, city: CityEnvironment, cell_size: float = CONFIG.grid_cell_size):
        self.city = city
        self.cell_size = cell_size
        self.grid_n = int(city.world_size // cell_size)
        self.obstacle_height: Dict[Tuple[int, int], float] = {}
        self.risk_map: Dict[Tuple[int, int], float] = {}
        self.hard_blocked: set[Tuple[int, int]] = set()
        self.rebuild()

    def rebuild(self) -> None:
        self.obstacle_height.clear()
        self.risk_map.clear()
        self.hard_blocked.clear()

        # Fast O(B) building height rasterization for 1,600+ building cities
        margin = 10.0
        for b in self.city.buildings:
            min_gx = max(0, int((b.x - b.width / 2.0 - margin) // self.cell_size))
            max_gx = min(self.grid_n - 1, int((b.x + b.width / 2.0 + margin) // self.cell_size))
            min_gz = max(0, int((b.z - b.depth / 2.0 - margin) // self.cell_size))
            max_gz = min(self.grid_n - 1, int((b.z + b.depth / 2.0 + margin) // self.cell_size))
            clear_h = b.height + 14.0
            for gx in range(min_gx, max_gx + 1):
                for gz in range(min_gz, max_gz + 1):
                    if clear_h > self.obstacle_height.get((gx, gz), 0.0):
                        self.obstacle_height[(gx, gz)] = clear_h

        for gx in range(self.grid_n):
            for gz in range(self.grid_n):
                wx = (gx + 0.5) * self.cell_size
                wz = (gz + 0.5) * self.cell_size

                risk = 0.05
                blocked = False
                for hz in self.city.hazards:
                    if not hz.active:
                        continue
                    dist = math.hypot(wx - hz.x, wz - hz.z)
                    if dist <= hz.radius:
                        if hz.kind in ("no_fly", "blocked_area"):
                            blocked = True
                            risk = 1.0
                        elif hz.kind == "fire":
                            blocked = True
                            risk = max(risk, 0.95)
                        elif hz.kind == "flood":
                            risk = max(risk, 0.35 * hz.severity)
                    elif dist <= hz.radius + 35.0:
                        if hz.kind in ("fire", "no_fly"):
                            risk = max(risk, 0.45)

                if blocked:
                    self.hard_blocked.add((gx, gz))
                self.risk_map[(gx, gz)] = round(risk, 3)


    def rebuild_region(self, cx: float, cz: float, radius: float) -> int:
        """Incrementally recompute only grid cells intersecting the affected hazard bounding box."""
        pad = radius + 45.0
        min_gx = max(0, int((cx - pad) // self.cell_size))
        max_gx = min(self.grid_n - 1, int((cx + pad) // self.cell_size))
        min_gz = max(0, int((cz - pad) // self.cell_size))
        max_gz = min(self.grid_n - 1, int((cz + pad) // self.cell_size))
        updated = 0
        for gx in range(min_gx, max_gx + 1):
            for gz in range(min_gz, max_gz + 1):
                wx = (gx + 0.5) * self.cell_size
                wz = (gz + 0.5) * self.cell_size
                risk = 0.05
                blocked = False
                for hz in self.city.hazards:
                    if not hz.active:
                        continue
                    dist = math.hypot(wx - hz.x, wz - hz.z)
                    if dist <= hz.radius:
                        if hz.kind in ("no_fly", "blocked_area"):
                            blocked = True
                            risk = 1.0
                        elif hz.kind == "fire":
                            blocked = True
                            risk = max(risk, 0.95)
                        elif hz.kind == "flood":
                            risk = max(risk, 0.35 * hz.severity)
                    elif dist <= hz.radius + 35.0:
                        if hz.kind in ("fire", "no_fly"):
                            risk = max(risk, 0.45)
                if blocked:
                    self.hard_blocked.add((gx, gz))
                else:
                    self.hard_blocked.discard((gx, gz))
                self.risk_map[(gx, gz)] = round(risk, 3)
                updated += 1
        return updated

    def world_to_grid(self, x: float, z: float) -> Tuple[int, int]:
        return (
            max(0, min(self.grid_n - 1, int(x // self.cell_size))),
            max(0, min(self.grid_n - 1, int(z // self.cell_size))),
        )

    def grid_to_world(self, gx: int, gz: int) -> Tuple[float, float]:
        return ((gx + 0.5) * self.cell_size, (gz + 0.5) * self.cell_size)

    def is_route_valid(self, route: RoutePlan) -> bool:
        if not route or len(route.waypoints) < 2:
            return True
        for wp in route.waypoints[1:-1]:
            cell = self.world_to_grid(wp[0], wp[2])
            if cell in self.hard_blocked:
                return False
            if wp[1] < self.obstacle_height.get(cell, 0.0) - 2.0:
                return False
        return True

    def plan_route(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        drone: DroneState,
        strategy: str = "hybrid",
        task_id: Optional[str] = None,
        payload_kg: float = 0.0,
        service_hover_s: float = 0.0,
        algorithm: str = "astar",
    ) -> RoutePlan:
        sg = self.world_to_grid(start[0], start[2])
        gg = self.world_to_grid(goal[0], goal[2])
        cruise_alt = drone.cruise_altitude

        open_heap: List[Tuple[float, Tuple[int, int]]] = [(0.0, sg)]
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {sg: 0.0}
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]

        found = False
        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current == gg:
                found = True
                break
            cx, cz = current
            for dx, dz in neighbors:
                nx, nz = cx + dx, cz + dz
                if not (0 <= nx < self.grid_n and 0 <= nz < self.grid_n):
                    continue
                ncell = (nx, nz)
                if ncell in self.hard_blocked and ncell != gg:
                    continue
                step_dist = math.hypot(dx, dz) * self.cell_size
                obs_h = self.obstacle_height.get(ncell, 0.0)
                climb_pen = max(0.0, obs_h - cruise_alt) * 1.4
                risk_pen = self.risk_map.get(ncell, 0.05) * 28.0
                tentative = g_score[current] + step_dist + climb_pen + risk_pen
                if tentative < g_score.get(ncell, float("inf")):
                    came_from[ncell] = current
                    g_score[ncell] = tentative
                    h = 0.0 if algorithm == "dijkstra" else math.hypot(gg[0] - nx, gg[1] - nz) * self.cell_size
                    heapq.heappush(open_heap, (tentative + h, ncell))

        grid_path: List[Tuple[int, int]] = []
        if found:
            cur = gg
            while cur != sg:
                grid_path.append(cur)
                cur = came_from[cur]
            grid_path.append(sg)
            grid_path.reverse()
        else:
            grid_path = [sg, gg]

        waypoints: List[Tuple[float, float, float]] = [
            (round(start[0], 1), round(max(start[1], 4.0), 1), round(start[2], 1)),
            (round(start[0], 1), round(max(cruise_alt, self.obstacle_height.get(sg, 0.0) + 8.0), 1), round(start[2], 1)),
        ]

        risk_acc = 0.0
        for idx, cell in enumerate(grid_path):
            if idx == 0 or idx == len(grid_path) - 1:
                continue
            if 0 < idx < len(grid_path) - 1:
                px, pz = grid_path[idx - 1]
                nx, nz = grid_path[idx + 1]
                if (cell[0] - px == nx - cell[0]) and (cell[1] - pz == nz - cell[1]):
                    if self.obstacle_height.get(cell, 0.0) <= cruise_alt:
                        risk_acc += self.risk_map.get(cell, 0.05)
                        continue
            wx, wz = self.grid_to_world(cell[0], cell[1])
            safe_alt = max(cruise_alt, self.obstacle_height.get(cell, 0.0) + 10.0)
            waypoints.append((round(wx, 1), round(safe_alt, 1), round(wz, 1)))
            risk_acc += self.risk_map.get(cell, 0.05)

        goal_clear_alt = max(cruise_alt, self.obstacle_height.get(gg, 0.0) + 10.0)
        waypoints.append((round(goal[0], 1), round(goal_clear_alt, 1), round(goal[2], 1)))
        waypoints.append((round(goal[0], 1), round(max(goal[1], 6.0), 1), round(goal[2], 1)))

        total_dist = 0.0
        for i in range(len(waypoints) - 1):
            a, b = waypoints[i], waypoints[i + 1]
            total_dist += math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)

        est_duration = total_dist / max(drone.cruise_speed_mps, 1.0) + service_hover_s
        est_energy = compute_route_energy_wh(
            waypoints, drone, payload_kg, self.city.weather, service_hover_s=service_hover_s
        )
        avg_risk = min(1.0, risk_acc / max(1, len(grid_path)))

        color_map = {"greedy": "slate", "classical": "blue", "quantum": "amber", "hybrid": "green"}
        color_tag = "orange" if avg_risk > 0.45 else color_map.get(strategy, "blue")

        return RoutePlan(
            route_id=f"RT-{uuid.uuid4().hex[:8].upper()}",
            drone_id=drone.id,
            task_id=task_id,
            strategy=strategy,
            waypoints=waypoints,
            distance_m=round(total_dist, 2),
            estimated_duration_s=round(est_duration, 2),
            estimated_energy_wh=round(est_energy, 2),
            risk_score=round(avg_risk, 3),
            feasible=found,
            color_tag=color_tag,
        )
