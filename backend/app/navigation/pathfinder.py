from __future__ import annotations
import heapq
import math
import uuid
from typing import Dict, List, Optional, Tuple

from app.core.config import CONFIG
from app.core.models import Building, CityEnvironment, DroneState, RoutePlan
from app.simulation.battery_model import compute_route_energy_wh


MAX_SAFE_ALTITUDE_M = 300.0
POINT = Tuple[float, float, float]


class SpatialAirspaceGrid:
    def __init__(self, city: CityEnvironment, cell_size: float = CONFIG.grid_cell_size):
        self.city = city
        self.cell_size = max(1.0, float(cell_size))
        self.grid_n = max(1, int(city.world_size // self.cell_size))
        self.obstacle_height: Dict[Tuple[int, int], float] = {}
        self.hazard_ceiling: Dict[Tuple[int, int], float] = {}
        self.risk_map: Dict[Tuple[int, int], float] = {}
        self.hard_blocked: set[Tuple[int, int]] = set()
        self.building_index: Dict[Tuple[int, int], List[Building]] = {}
        self.rebuild()

    def rebuild(self) -> None:
        self.obstacle_height.clear()
        self.hazard_ceiling.clear()
        self.risk_map.clear()
        self.hard_blocked.clear()
        self.building_index.clear()

        # Rasterize building envelopes for A*, and retain a small exact-geometry
        # index for endpoint/segment validation (the raster is conservative).
        margin = 10.0
        for b in self.city.buildings:
            min_gx = max(0, int((b.x - b.width / 2.0 - margin) // self.cell_size))
            max_gx = min(self.grid_n - 1, int((b.x + b.width / 2.0 + margin) // self.cell_size))
            min_gz = max(0, int((b.z - b.depth / 2.0 - margin) // self.cell_size))
            max_gz = min(self.grid_n - 1, int((b.z + b.depth / 2.0 + margin) // self.cell_size))
            clear_h = b.height + 14.0
            for gx in range(min_gx, max_gx + 1):
                for gz in range(min_gz, max_gz + 1):
                    cell = (gx, gz)
                    if clear_h > self.obstacle_height.get(cell, 0.0):
                        self.obstacle_height[cell] = clear_h
                    self.building_index.setdefault(cell, []).append(b)

        for gx in range(self.grid_n):
            for gz in range(self.grid_n):
                risk, ceiling, blocked = self._hazard_values(gx, gz)
                self.hazard_ceiling[(gx, gz)] = ceiling
                self.risk_map[(gx, gz)] = round(risk, 3)
                if blocked:
                    self.hard_blocked.add((gx, gz))

    def _hazard_values(self, gx: int, gz: int) -> Tuple[float, float, bool]:
        wx = (gx + 0.5) * self.cell_size
        wz = (gz + 0.5) * self.cell_size
        risk = 0.05
        ceiling = 0.0
        blocked = False
        for hz in self.city.hazards:
            if not hz.active:
                continue
            dist = math.hypot(wx - hz.x, wz - hz.z)
            if dist <= hz.radius:
                ceiling = max(ceiling, float(hz.altitude_ceiling))
                if hz.kind in ("no_fly", "blocked_area"):
                    risk = max(risk, 1.0)
                elif hz.kind == "fire":
                    risk = max(risk, 0.95)
                elif hz.kind == "flood":
                    risk = max(risk, 0.35 * hz.severity)
                # A hazard ceiling is a vertical exclusion boundary, not a
                # horizontal wall. Only ceilings beyond the operating envelope
                # make the whole cell impassable.
                if hz.altitude_ceiling >= MAX_SAFE_ALTITUDE_M:
                    blocked = True
            elif dist <= hz.radius + 35.0 and hz.kind in ("fire", "no_fly"):
                risk = max(risk, 0.45)
        return risk, ceiling, blocked

    def rebuild_region(self, cx: float, cz: float, radius: float) -> int:
        """Incrementally recompute hazard values in the affected bounding box."""
        pad = radius + 45.0
        min_gx = max(0, int((cx - pad) // self.cell_size))
        max_gx = min(self.grid_n - 1, int((cx + pad) // self.cell_size))
        min_gz = max(0, int((cz - pad) // self.cell_size))
        max_gz = min(self.grid_n - 1, int((cz + pad) // self.cell_size))
        updated = 0
        for gx in range(min_gx, max_gx + 1):
            for gz in range(min_gz, max_gz + 1):
                risk, ceiling, blocked = self._hazard_values(gx, gz)
                self.hazard_ceiling[(gx, gz)] = ceiling
                self.risk_map[(gx, gz)] = round(risk, 3)
                if blocked:
                    self.hard_blocked.add((gx, gz))
                else:
                    self.hard_blocked.discard((gx, gz))
                updated += 1
        return updated

    def world_to_grid(self, x: float, z: float) -> Tuple[int, int]:
        return (
            max(0, min(self.grid_n - 1, int(x // self.cell_size))),
            max(0, min(self.grid_n - 1, int(z // self.cell_size))),
        )

    def grid_to_world(self, gx: int, gz: int) -> Tuple[float, float]:
        return ((gx + 0.5) * self.cell_size, (gz + 0.5) * self.cell_size)

    @staticmethod
    def _valid_point(point: object) -> bool:
        return (
            isinstance(point, (tuple, list))
            and len(point) == 3
            and all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in point)
        )

    def _in_world(self, x: float, z: float) -> bool:
        return 0.0 <= x <= self.city.world_size and 0.0 <= z <= self.city.world_size

    def _point_geometry_safe(self, x: float, y: float, z: float) -> bool:
        if not self._in_world(x, z) or not (0.0 <= y <= MAX_SAFE_ALTITUDE_M):
            return False
        cell = self.world_to_grid(x, z)
        if cell in self.hard_blocked:
            return False
        for b in self.building_index.get(cell, []):
            if (
                abs(x - b.x) <= b.width / 2.0 + 4.0
                and abs(z - b.z) <= b.depth / 2.0 + 4.0
                and y < b.height + 8.0
            ):
                return False
        for hz in self.city.hazards:
            if hz.active and math.hypot(x - hz.x, z - hz.z) <= hz.radius:
                if y <= float(hz.altitude_ceiling) + 2.0:
                    return False
        return True

    def is_valid_point(self, point: object) -> bool:
        return self._valid_point(point)

    def is_point_safe(self, point: POINT) -> bool:
        return self._valid_point(point) and self._point_geometry_safe(*map(float, point))

    def minimum_safe_altitude(self, x: float, z: float, base_altitude: float = 0.0) -> float:
        cell = self.world_to_grid(x, z)
        return round(max(
            float(base_altitude),
            self.obstacle_height.get(cell, 0.0) + 10.0,
            self.hazard_ceiling.get(cell, 0.0) + 12.0,
        ), 1)

    def safe_surface_altitude(self, x: float, z: float, preferred_altitude: float = 2.0) -> float:
        """Return a safe approach/landing altitude for a known surface point."""
        altitude = max(2.0, float(preferred_altitude))
        for b in self.city.buildings:
            if abs(x - b.x) <= b.width / 2.0 + 4.0 and abs(z - b.z) <= b.depth / 2.0 + 4.0:
                altitude = max(altitude, b.height + 10.0)
        for hz in self.city.hazards:
            if hz.active and math.hypot(x - hz.x, z - hz.z) <= hz.radius:
                altitude = max(altitude, float(hz.altitude_ceiling) + 12.0)
        return round(min(MAX_SAFE_ALTITUDE_M, altitude), 1)

    def _cell_safe_at(self, cell: Tuple[int, int], altitude: float) -> bool:
        return (
            cell not in self.hard_blocked
            and altitude >= self.obstacle_height.get(cell, 0.0) - 2.0
            and altitude >= self.hazard_ceiling.get(cell, 0.0) + 2.0
        )

    def _segment_cells(self, a: POINT, b: POINT) -> List[Tuple[int, int]]:
        """Supercover grid traversal, including both cells at diagonal ties."""
        sx, sz = self.world_to_grid(a[0], a[2])
        gx, gz = self.world_to_grid(b[0], b[2])
        if (sx, sz) == (gx, gz):
            return [(sx, sz)]
        dx, dz = b[0] - a[0], b[2] - a[2]
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_z = 1 if dz > 0 else -1 if dz < 0 else 0
        delta_x = self.cell_size / abs(dx) if dx else float("inf")
        delta_z = self.cell_size / abs(dz) if dz else float("inf")
        next_x = ((sx + 1) * self.cell_size if step_x > 0 else sx * self.cell_size)
        next_z = ((gz + 1) * self.cell_size if step_z > 0 else gz * self.cell_size)
        t_max_x = (next_x - a[0]) / dx if dx else float("inf")
        t_max_z = (next_z - a[2]) / dz if dz else float("inf")
        cells: List[Tuple[int, int]] = []
        for _ in range(self.grid_n * 4 + 4):
            if (gx, gz) not in cells:
                cells.append((gx, gz))
            if (gx, gz) == (sx, sz):
                break
            eps = 1e-12
            if t_max_x < t_max_z - eps:
                gx += step_x
                t_max_x += delta_x
            elif t_max_z < t_max_x - eps:
                gz += step_z
                t_max_z += delta_z
            else:
                for cell in ((gx + step_x, gz), (gx, gz + step_z)):
                    if 0 <= cell[0] < self.grid_n and 0 <= cell[1] < self.grid_n and cell not in cells:
                        cells.append(cell)
                gx += step_x
                gz += step_z
                t_max_x += delta_x
                t_max_z += delta_z
        return cells

    def _segment_geometry_safe(self, a: POINT, b: POINT) -> bool:
        # Exact horizontal segment/circle intersections for altitude-limited
        # hazards; altitude is linear along the segment.
        for hz in self.city.hazards:
            if not hz.active:
                continue
            dx, dz = b[0] - a[0], b[2] - a[2]
            fx, fz = a[0] - hz.x, a[2] - hz.z
            qa = dx * dx + dz * dz
            if qa <= 1e-12:
                if fx * fx + fz * fz > hz.radius * hz.radius:
                    continue
                t0, t1 = 0.0, 1.0
            else:
                qb = 2.0 * (fx * dx + fz * dz)
                qc = fx * fx + fz * fz - hz.radius * hz.radius
                disc = qb * qb - 4.0 * qa * qc
                if disc < 0.0:
                    continue
                root = math.sqrt(max(0.0, disc))
                t0 = max(0.0, (-qb - root) / (2.0 * qa))
                t1 = min(1.0, (-qb + root) / (2.0 * qa))
                if t0 > t1:
                    continue
            min_alt = min(a[1] + (b[1] - a[1]) * t0, a[1] + (b[1] - a[1]) * t1)
            if min_alt <= float(hz.altitude_ceiling) + 2.0:
                return False

        # Exact segment/expanded-building-box intersections. Only buildings in
        # traversed grid cells are candidates, keeping long routes inexpensive.
        seen: set[str] = set()
        for cell in self._segment_cells(a, b):
            for building in self.building_index.get(cell, []):
                if building.id in seen:
                    continue
                seen.add(building.id)
                t0, t1 = 0.0, 1.0
                intersects = True
                for start, delta, low, high in (
                    (a[0], b[0] - a[0], building.x - building.width / 2.0 - 4.0, building.x + building.width / 2.0 + 4.0),
                    (a[2], b[2] - a[2], building.z - building.depth / 2.0 - 4.0, building.z + building.depth / 2.0 + 4.0),
                ):
                    if abs(delta) <= 1e-12:
                        if start < low or start > high:
                            intersects = False
                            break
                        continue
                    ta, tb = (low - start) / delta, (high - start) / delta
                    if ta > tb:
                        ta, tb = tb, ta
                    t0, t1 = max(t0, ta), min(t1, tb)
                    if t0 > t1:
                        intersects = False
                        break
                if intersects:
                    min_alt = min(a[1] + (b[1] - a[1]) * t0, a[1] + (b[1] - a[1]) * t1)
                    if min_alt < building.height + 8.0:
                        return False
        return True

    def is_route_valid(self, route: RoutePlan) -> bool:
        if not route or not route.feasible or len(route.waypoints) < 2:
            return False
        if not all(self._valid_point(wp) for wp in route.waypoints):
            return False
        if not self.is_point_safe(route.waypoints[0]) or not self.is_point_safe(route.waypoints[-1]):
            return False
        for wp in route.waypoints:
            if not self._point_geometry_safe(*map(float, wp)):
                return False
        return all(self._segment_geometry_safe(a, b) for a, b in zip(route.waypoints, route.waypoints[1:]))

    def _infeasible_route(
        self,
        start: object,
        goal: object,
        drone: DroneState,
        strategy: str,
        task_id: Optional[str],
    ) -> RoutePlan:
        waypoints = []
        if self._valid_point(start) and self._valid_point(goal):
            waypoints = [tuple(map(float, start)), tuple(map(float, goal))]
        return RoutePlan(
            route_id=f"RT-{uuid.uuid4().hex[:8].upper()}",
            drone_id=drone.id,
            task_id=task_id,
            strategy=strategy,
            waypoints=waypoints,
            feasible=False,
            color_tag="red",
        )

    def plan_route(
        self,
        start: POINT,
        goal: POINT,
        drone: DroneState,
        strategy: str = "hybrid",
        task_id: Optional[str] = None,
        payload_kg: float = 0.0,
        service_hover_s: float = 0.0,
        algorithm: str = "astar",
    ) -> RoutePlan:
        if not self._valid_point(start) or not self._valid_point(goal):
            return self._infeasible_route(start, goal, drone, strategy, task_id)
        start = tuple(map(float, start))
        goal = tuple(map(float, goal))
        if not self.is_point_safe(start) or not self.is_point_safe(goal):
            return self._infeasible_route(start, goal, drone, strategy, task_id)

        sg = self.world_to_grid(start[0], start[2])
        gg = self.world_to_grid(goal[0], goal[2])
        cruise_alt = float(drone.cruise_altitude)
        max_altitude = max(MAX_SAFE_ALTITUDE_M, cruise_alt)

        def traversable(cell: Tuple[int, int]) -> bool:
            return self.minimum_safe_altitude(*self.grid_to_world(*cell)) <= max_altitude

        if not traversable(sg) or not traversable(gg):
            return self._infeasible_route(start, goal, drone, strategy, task_id)

        open_heap: List[Tuple[float, Tuple[int, int]]] = [(0.0, sg)]
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {sg: 0.0}
        closed: set[Tuple[int, int]] = set()
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]

        found = False
        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            closed.add(current)
            if current == gg:
                found = True
                break
            cx, cz = current
            for dx, dz in neighbors:
                nx, nz = cx + dx, cz + dz
                if not (0 <= nx < self.grid_n and 0 <= nz < self.grid_n):
                    continue
                ncell = (nx, nz)
                if not traversable(ncell):
                    continue
                if dx and dz:
                    if not traversable((cx + dx, cz)) or not traversable((cx, cz + dz)):
                        continue
                step_dist = math.hypot(dx, dz) * self.cell_size
                wx, wz = self.grid_to_world(nx, nz)
                safe_alt = self.minimum_safe_altitude(wx, wz, cruise_alt)
                climb_pen = max(0.0, safe_alt - cruise_alt) * 1.4
                risk_pen = self.risk_map.get(ncell, 0.05) * 28.0
                tentative = g_score[current] + step_dist + climb_pen + risk_pen
                if tentative < g_score.get(ncell, float("inf")):
                    came_from[ncell] = current
                    g_score[ncell] = tentative
                    h = 0.0 if algorithm == "dijkstra" else math.hypot(gg[0] - nx, gg[1] - nz) * self.cell_size
                    heapq.heappush(open_heap, (tentative + h, ncell))

        if not found:
            return self._infeasible_route(start, goal, drone, strategy, task_id)

        grid_path: List[Tuple[int, int]] = []
        cur = gg
        while cur != sg:
            grid_path.append(cur)
            cur = came_from[cur]
        grid_path.append(sg)
        grid_path.reverse()

        start_alt = self.minimum_safe_altitude(start[0], start[2], cruise_alt)
        waypoints: List[POINT] = [start, (round(start[0], 1), start_alt, round(start[2], 1))]
        risk_acc = 0.0
        for cell in grid_path[1:-1]:
            wx, wz = self.grid_to_world(*cell)
            safe_alt = self.minimum_safe_altitude(wx, wz, cruise_alt)
            waypoints.append((round(wx, 1), safe_alt, round(wz, 1)))
            risk_acc += self.risk_map.get(cell, 0.05)

        goal_surface_alt = self.safe_surface_altitude(goal[0], goal[2], goal[1])
        goal_clear_alt = max(cruise_alt, self.minimum_safe_altitude(goal[0], goal[2]), goal_surface_alt + 8.0)
        waypoints.append((round(goal[0], 1), round(goal_clear_alt, 1), round(goal[2], 1)))
        waypoints.append((round(goal[0], 1), goal_surface_alt, round(goal[2], 1)))

        # Remove only exact duplicate points; never simplify across a potentially
        # unsafe corridor. Validation below is the final authority.
        compact: List[POINT] = []
        for wp in waypoints:
            if not compact or math.dist(compact[-1], wp) > 0.01:
                compact.append(wp)
        waypoints = compact

        total_dist = sum(math.dist(a, b) for a, b in zip(waypoints, waypoints[1:]))
        est_duration = total_dist / max(drone.cruise_speed_mps, 1.0) + service_hover_s
        est_energy = compute_route_energy_wh(
            waypoints, drone, payload_kg, self.city.weather, service_hover_s=service_hover_s
        )
        avg_risk = min(1.0, risk_acc / max(1, len(grid_path)))
        color_map = {"greedy": "slate", "classical": "blue", "quantum": "amber", "hybrid": "green"}
        color_tag = "orange" if avg_risk > 0.45 else color_map.get(strategy, "blue")

        route = RoutePlan(
            route_id=f"RT-{uuid.uuid4().hex[:8].upper()}",
            drone_id=drone.id,
            task_id=task_id,
            strategy=strategy,
            waypoints=waypoints,
            distance_m=round(total_dist, 2),
            estimated_duration_s=round(est_duration, 2),
            estimated_energy_wh=round(est_energy, 2),
            risk_score=round(avg_risk, 3),
            feasible=True,
            color_tag=color_tag,
        )
        if not self.is_route_valid(route):
            route.feasible = False
            route.color_tag = "red"
        return route
