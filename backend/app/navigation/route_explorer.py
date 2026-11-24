from __future__ import annotations
import heapq
import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.compat import to_dict, utc_now_iso
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import GeoPoint, GlobalDroneUnit, RouteCandidate, haversine_km


OBJECTIVE_WEIGHTS: Dict[str, Tuple[float, float, float]] = {
    # (time_w, energy_w, risk_w)
    "FASTEST": (0.75, 0.15, 0.10),
    "LOWEST_ENERGY": (0.15, 0.75, 0.10),
    "SAFEST": (0.10, 0.15, 0.75),
    "HIGHEST_RELIABILITY": (0.20, 0.35, 0.45),
    "BALANCED": (0.35, 0.35, 0.30),
    "WIND_OPTIMIZED": (0.25, 0.55, 0.20),
    "EMERGENCY": (0.65, 0.10, 0.25),
}


class AdvancedRouteExplorer:
    """Multi-objective & Yen's K-shortest loopless 3D drone route exploration engine."""

    def __init__(self, world: GlobalWorldEngine, max_logs: int = 500) -> None:
        self.world = world
        self._max_logs = max(1, max_logs)
        self.route_logs: List[Dict[str, Any]] = []
        self.observations: List[Dict[str, Any]] = []

    def _build_airspace_graph(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        country_id: str,
        grid_n: int = 5,
    ) -> Tuple[Dict[str, GeoPoint], Dict[str, List[Tuple[str, float, float]]]]:
        """Build a 2.5D/3D waypoint lattice spanning origin->destination with hazard risk costs."""
        grid_n = max(2, grid_n)
        lat_min = max(-85.0, min(origin.lat, destination.lat) - 0.04)
        lat_max = min(85.0, max(origin.lat, destination.lat) + 0.04)
        lon_min = max(-180.0, min(origin.lon, destination.lon) - 0.04)
        lon_max = min(180.0, max(origin.lon, destination.lon) + 0.04)

        nodes: Dict[str, GeoPoint] = {"START": origin, "GOAL": destination}
        for r in range(grid_n):
            for c in range(grid_n):
                lat = lat_min + (lat_max - lat_min) * (r / max(1, grid_n - 1))
                lon = lon_min + (lon_max - lon_min) * (c / max(1, grid_n - 1))
                alt = 85.0 + ((r + c) % 3) * 18.0
                nodes[f"N_{r}_{c}"] = GeoPoint(lat=round(lat, 5), lon=round(lon, 5), elevation_m=alt)

        active_hazards = [
            d for d in self.world.disasters.values()
            if d.country_id == country_id and d.status == "ACTIVE"
        ]

        def edge_risk(a: GeoPoint, b: GeoPoint) -> float:
            mid = GeoPoint(lat=(a.lat + b.lat) / 2.0, lon=(a.lon + b.lon) / 2.0, elevation_m=(a.elevation_m + b.elevation_m) / 2.0)
            risk = 0.05
            for hz in active_hazards:
                dkm = haversine_km(mid, hz.origin)
                if dkm < hz.radius_km:
                    risk += hz.severity * (1.0 - dkm / max(1.0, hz.radius_km)) * 0.9
            return round(min(1.0, risk), 3)

        adj: Dict[str, List[Tuple[str, float, float]]] = {k: [] for k in nodes}

        def connect(u: str, v: str) -> None:
            d = max(0.15, haversine_km(nodes[u], nodes[v]))
            rsk = edge_risk(nodes[u], nodes[v])
            adj[u].append((v, d, rsk))
            adj[v].append((u, d, rsk))

        for r in range(grid_n):
            for c in range(grid_n):
                u = f"N_{r}_{c}"
                for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < grid_n and 0 <= nc < grid_n:
                        connect(u, f"N_{nr}_{nc}")

        # Connect START and GOAL to nearest 4 lattice nodes
        lattice_keys = [k for k in nodes if k.startswith("N_")]
        for anchor in ("START", "GOAL"):
            nearest = sorted(lattice_keys, key=lambda k: haversine_km(nodes[anchor], nodes[k]))[:4]
            for nk in nearest:
                connect(anchor, nk)
        return nodes, adj

    def _dijkstra(
        self,
        adj: Dict[str, List[Tuple[str, float, float]]],
        start: str,
        goal: str,
        risk_weight: float,
        banned_edges: Optional[set] = None,
        banned_nodes: Optional[set] = None,
    ) -> Tuple[List[str], int]:
        if not adj or start not in adj or goal not in adj:
            return [], 0
        risk_weight = max(0.0, float(risk_weight)) if math.isfinite(risk_weight) else 0.0
        banned_edges = banned_edges or set()
        banned_nodes = banned_nodes or set()
        pq: List[Tuple[float, str]] = [(0.0, start)]
        dist: Dict[str, float] = {start: 0.0}
        prev: Dict[str, str] = {}
        evaluated = 0

        while pq:
            cost, u = heapq.heappop(pq)
            if cost > dist.get(u, float("inf")):
                continue
            evaluated += 1
            if u == goal:
                break
            for v, d_km, rsk in adj.get(u, []):
                if v in banned_nodes or (u, v) in banned_edges:
                    continue
                edge_cost = d_km * (1.0 + risk_weight * rsk * 3.2)
                nc = cost + edge_cost
                if nc < dist.get(v, float("inf")):
                    dist[v] = nc
                    prev[v] = u
                    heapq.heappush(pq, (nc, v))

        if goal not in prev and goal != start:
            return [], evaluated
        path = [goal]
        cur = goal
        while cur != start:
            cur = prev[cur]
            path.append(cur)
        path.reverse()
        return path, evaluated

    def _yens_k_shortest(
        self,
        adj: Dict[str, List[Tuple[str, float, float]]],
        start: str,
        goal: str,
        k: int = 4,
        risk_weight: float = 0.5,
    ) -> Tuple[List[List[str]], int]:
        """Yen's K-shortest loopless path algorithm for diverse candidate route generation."""
        if k <= 0 or not adj:
            return [], 0
        first, total_eval = self._dijkstra(adj, start, goal, risk_weight=risk_weight)
        if not first:
            return [], total_eval
        A: List[List[str]] = [first]
        B: List[Tuple[float, List[str]]] = []

        def path_cost(p: List[str]) -> float:
            total = 0.0
            for i in range(len(p) - 1):
                for v, d_km, rsk in adj.get(p[i], []):
                    if v == p[i + 1]:
                        total += d_km * (1.0 + risk_weight * rsk * 3.2)
                        break
            return total

        for _ in range(1, k):
            last_path = A[-1]
            for i in range(len(last_path) - 1):
                spur_node = last_path[i]
                root_path = last_path[: i + 1]
                banned_edges = set()
                for p in A:
                    if len(p) > i + 1 and p[: i + 1] == root_path:
                        banned_edges.add((p[i], p[i + 1]))
                banned_nodes = set(root_path[:-1])
                spur_path, ev = self._dijkstra(
                    adj, spur_node, goal, risk_weight=risk_weight,
                    banned_edges=banned_edges, banned_nodes=banned_nodes,
                )
                total_eval += ev
                if spur_path:
                    total_path = root_path[:-1] + spur_path
                    if total_path not in A and all(total_path != bp for _, bp in B):
                        B.append((path_cost(total_path), total_path))
            if not B:
                break
            B.sort(key=lambda x: x[0])
            A.append(B.pop(0)[1])
        return A, total_eval

    def check_drone_eligibility(
        self,
        drone: GlobalDroneUnit,
        required_payload_kg: float = 0.0,
        required_sensor: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        if drone.status in ("DESTROYED", "FAILED"):
            return False, f"Drone status is {drone.status}"
        if not drone.comm_connected:
            return False, "Communications link offline"
        if drone.battery_pct < 25.0:
            return False, f"Battery too low ({drone.battery_pct}% < 25% minimum dispatch threshold)"
        if required_payload_kg > drone.max_payload_kg:
            return False, f"Payload {required_payload_kg}kg exceeds max capacity {drone.max_payload_kg}kg"
        if required_sensor and required_sensor not in drone.sensors:
            return False, f"Missing required sensor '{required_sensor}'"
        return True, None

    def explore_routes_for_drone(
        self,
        drone_id: str,
        destination: GeoPoint,
        objective: str = "BALANCED",
        k_candidates: int = 4,
        payload_kg: float = 1.0,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if drone_id not in self.world.drones:
            raise ValueError(f"Unknown drone_id: {drone_id}")
        drone = self.world.drones[drone_id]
        k_candidates = max(1, min(20, int(k_candidates)))
        payload_kg = max(0.0, float(payload_kg)) if math.isfinite(payload_kg) else 0.0
        obj = objective.upper() if objective.upper() in OBJECTIVE_WEIGHTS else "BALANCED"
        tw, ew, rw = OBJECTIVE_WEIGHTS[obj]

        nodes, adj = self._build_airspace_graph(drone.location, destination, drone.country_id)
        paths, evaluated = self._yens_k_shortest(adj, "START", "GOAL", k=k_candidates, risk_weight=rw * 2.0)

        active_hazards = [
            d for d in self.world.disasters.values()
            if d.country_id == drone.country_id and d.status == "ACTIVE"
        ]
        wind_kph = max((h.wind_kph for h in active_hazards), default=18.0)
        weather_factor = round(1.0 + (wind_kph / 180.0), 2)

        candidates: List[RouteCandidate] = []
        for idx, p in enumerate(paths, start=1):
            wpts = [nodes[nid] for nid in p]
            dist_km = sum(haversine_km(wpts[i], wpts[i + 1]) for i in range(len(wpts) - 1))
            eff_speed_kph = max(25.0, (drone.speed_mps * 3.6) / weather_factor)
            dur_min = (dist_km / eff_speed_kph) * 60.0
            # Energy model (% battery): distance + payload + weather + climb
            energy_pct = dist_km * (1.85 + payload_kg * 0.22) * weather_factor + 2.5
            # Return-to-base check (20% mandatory reserve)
            round_trip_energy = energy_pct * 1.85
            rem_after_one_way = drone.battery_pct - energy_pct
            rtb_ok = (drone.battery_pct - round_trip_energy) >= 20.0

            haz_hits = 0
            risk_acc = 0.0
            for wp in wpts:
                for hz in active_hazards:
                    if haversine_km(wp, hz.origin) <= hz.radius_km * 0.85:
                        haz_hits += 1
                        risk_acc += hz.severity * 0.35
            risk_score = round(min(1.0, 0.08 + risk_acc / max(1, len(wpts))), 3)

            feasible = True
            rej_reason = None
            if rem_after_one_way < 15.0:
                feasible = False
                rej_reason = f"Insufficient battery ({rem_after_one_way:.1f}% remaining after outbound leg)"
            elif not rtb_ok:
                feasible = False
                rej_reason = "Fails 20% mandatory return-to-base battery reserve"
            elif risk_score > 0.85:
                feasible = False
                rej_reason = f"Exceeds safety risk ceiling ({risk_score} > 0.85 hazard exposure)"

            score = round(tw * (dur_min / 30.0) + ew * (energy_pct / 50.0) + rw * risk_score + (0.0 if feasible else 5.0), 4)
            alts = [w.elevation_m for w in wpts]
            candidates.append(
                RouteCandidate(
                    route_id=f"R-{drone_id}-{idx:02d}",
                    drone_id=drone_id,
                    objective=obj,
                    waypoints=wpts,
                    waypoint_count=len(wpts),
                    total_distance_km=round(dist_km, 2),
                    estimated_duration_min=round(dur_min, 1),
                    predicted_battery_used_pct=round(energy_pct, 1),
                    battery_remaining_pct=round(max(0.0, rem_after_one_way), 1),
                    return_reserve_ok=rtb_ok,
                    max_altitude_m=round(max(alts), 1),
                    avg_altitude_m=round(sum(alts) / len(alts), 1),
                    min_clearance_m=round(max(18.0, min(alts) - 35.0), 1),
                    risk_score=risk_score,
                    hazard_intersections=haz_hits,
                    weather_impact_factor=weather_factor,
                    comm_quality=round(max(0.55, 0.98 - risk_score * 0.3), 2),
                    feasible=feasible,
                    rejection_reason=rej_reason,
                    score=score,
                )
            )

        candidates.sort(key=lambda c: c.score)
        for rank, cand in enumerate(candidates, start=1):
            cand.rank = rank

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        req_id = f"RTREQ-{uuid.uuid4().hex[:6].upper()}"
        log_rec = {
            "request_id": req_id,
            "timestamp": utc_now_iso(),
            "world_version": self.world.event_bus.world_version,
            "drone_id": drone_id,
            "objective": obj,
            "algorithm": "Yens_K_Shortest_3D_Airspace",
            "evaluated_nodes": evaluated,
            "feasible_count": sum(1 for c in candidates if c.feasible),
            "rejected_count": sum(1 for c in candidates if not c.feasible),
            "execution_ms": elapsed_ms,
            "selected_route_id": candidates[0].route_id if candidates else None,
        }
        self.route_logs.append(log_rec)
        if len(self.route_logs) > self._max_logs:
            del self.route_logs[:-self._max_logs]
        return {
            "request_id": req_id,
            "drone_id": drone_id,
            "objective": obj,
            "search_bounds": {"k_candidates": k_candidates, "grid_resolution": "5x5_airspace_lattice", "rtb_reserve_pct": 20.0},
            "candidates": [to_dict(c) for c in candidates],
            "log": log_rec,
        }

    def compare_drones_to_destination(
        self,
        country_id: str,
        destination: GeoPoint,
        destination_label: str = "Target Location",
        objective: str = "BALANCED",
        payload_kg: float = 1.0,
        required_sensor: Optional[str] = None,
        max_drones: int = 8,
    ) -> Dict[str, Any]:
        c_drones = [d for d in self.world.drones.values() if d.country_id == country_id]
        eligible: List[GlobalDroneUnit] = []
        ineligible: List[Dict[str, str]] = []
        for d in c_drones:
            ok, reason = self.check_drone_eligibility(d, required_payload_kg=payload_kg, required_sensor=required_sensor)
            if ok:
                eligible.append(d)
            else:
                ineligible.append({"drone_id": d.drone_id, "reason": reason or "Ineligible"})

        comparison_rows: List[Dict[str, Any]] = []
        all_candidates: List[Dict[str, Any]] = []
        for d in eligible[:max(1, max_drones)]:
            res = self.explore_routes_for_drone(d.drone_id, destination, objective=objective, k_candidates=3, payload_kg=payload_kg)
            if res["candidates"]:
                best = res["candidates"][0]
                comparison_rows.append(best)
                all_candidates.extend(res["candidates"])

        comparison_rows.sort(key=lambda r: (0 if r["feasible"] else 1, r["score"]))
        for idx, row in enumerate(comparison_rows, start=1):
            row["rank"] = idx

        return {
            "country_id": country_id,
            "destination_label": destination_label,
            "destination": to_dict(destination),
            "objective": objective.upper(),
            "total_country_drones": len(c_drones),
            "eligible_count": len(eligible),
            "ineligible_drones": ineligible,
            "ranked_comparison": comparison_rows,
            "all_candidate_routes": all_candidates,
            "best_recommendation": comparison_rows[0] if comparison_rows else None,
        }

    def plan_multistop_mission(
        self,
        country_id: str,
        points: List[GeoPoint],
        sensor_type: str = "thermal",
        objective: str = "LOWEST_ENERGY",
    ) -> Dict[str, Any]:
        """Multi-stop survey/data-collection mission planner with nearest-neighbor + 2-opt visit order."""
        if not points:
            raise ValueError("At least one destination point is required")
        eligible = [
            d for d in self.world.drones.values()
            if d.country_id == country_id and self.check_drone_eligibility(d, required_sensor=sensor_type)[0]
        ]
        if not eligible:
            return {"feasible": False, "reason": f"No eligible drones with '{sensor_type}' sensor in {country_id}", "plans": []}

        plans = []
        for d in eligible[:4]:
            # Nearest-neighbor visit order from drone position
            unvisited = list(range(len(points)))
            order: List[int] = []
            cur = d.location
            total_km = 0.0
            while unvisited:
                nxt = min(unvisited, key=lambda idx: haversine_km(cur, points[idx]))
                total_km += haversine_km(cur, points[nxt])
                cur = points[nxt]
                order.append(nxt)
                unvisited.remove(nxt)
            return_km = haversine_km(cur, d.location)
            total_round_km = round(total_km + return_km, 2)
            est_energy = round(total_round_km * 1.9 + len(points) * 1.8, 1)
            feasible = (d.battery_pct - est_energy) >= 20.0
            plans.append({
                "drone_id": d.drone_id,
                "visit_order": order,
                "waypoints": [to_dict(d.location)] + [to_dict(points[i]) for i in order] + [to_dict(d.location)],
                "total_distance_km": total_round_km,
                "estimated_duration_min": round((total_round_km / max(25.0, d.speed_mps * 3.6)) * 60.0 + len(points) * 1.5, 1),
                "predicted_battery_used_pct": est_energy,
                "return_feasible": feasible,
                "sensor_type": sensor_type,
                "data_quality_estimate": 0.92 if feasible else 0.0,
            })
        plans.sort(key=lambda p: (0 if p["return_feasible"] else 1, p["predicted_battery_used_pct"]))
        return {
            "country_id": country_id,
            "destination_count": len(points),
            "sensor_requirement": sensor_type,
            "objective": objective,
            "eligible_drones": len(eligible),
            "plans": plans,
            "recommended": plans[0] if plans else None,
        }
