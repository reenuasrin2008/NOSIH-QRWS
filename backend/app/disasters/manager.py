"""Unified disaster lifecycle manager with multi-hazard cascades and hazard-zone sync."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from app.core.models import (
    CityEnvironment,
    DisasterEvent,
    DisasterStatus,
    DisasterType,
    Epicentre,
    HazardZone,
    SimulatedSurvivor,
)
from app.disasters.building_collapse import step_building_collapse
from app.disasters.cyclone import step_cyclone
from app.disasters.disaster_presets import get_disaster_preset, load_disaster_presets
from app.disasters.earthquake import apply_seismic_shock, step_earthquake
from app.disasters.fire import step_fire
from app.disasters.flood import step_flood
from app.disasters.landslide import step_landslide
from app.disasters.survivor_generator import generate_survivors_for_disaster


_HAZARD_KIND_MAP = {
    DisasterType.FLOOD: ("flood", 22.0),
    DisasterType.EARTHQUAKE: ("blocked_area", 45.0),
    DisasterType.FIRE: ("fire", 95.0),
    DisasterType.CYCLONE: ("no_fly", 140.0),
    DisasterType.BUILDING_COLLAPSE: ("blocked_area", 65.0),
    DisasterType.LANDSLIDE: ("blocked_area", 55.0),
}


class DisasterLifecycleManager:
    """Owns all DisasterEvents, their lifecycle transitions, and cascades."""

    def __init__(self, seed: int = 20261124):
        self.seed = seed
        self.events: Dict[str, DisasterEvent] = {}
        self.timeline: List[Dict[str, Any]] = []
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"DIS-{self._counter:04d}"

    def _validate_epicentre(self, city: CityEnvironment, x: float, z: float) -> None:
        if x < 0.0 or x > city.world_size or z < 0.0 or z > city.world_size:
            raise ValueError(
                f"Epicentre ({x}, {z}) is outside world bounds [0, {city.world_size}]."
            )

    def _record_timeline(self, sim_time_s: float, event_id: str, action: str, detail: str) -> None:
        self.timeline.append({
            "sim_time_s": round(sim_time_s, 1),
            "event_id": event_id,
            "action": action,
            "detail": detail,
        })
        if len(self.timeline) > 500:
            self.timeline = self.timeline[-500:]

    def _sync_hazard(self, city: CityEnvironment, ev: DisasterEvent) -> None:
        kind, ceiling = _HAZARD_KIND_MAP.get(ev.type, ("blocked_area", 80.0))
        is_active = ev.status in (
            DisasterStatus.ACTIVE,
            DisasterStatus.INTENSIFYING,
            DisasterStatus.PROPAGATING,
            DisasterStatus.STABILIZING,
            DisasterStatus.CONTAINED,
        )
        # Cyclone affects weather broadly without hard-blocking the entire city airspace
        hz_radius = ev.affected_radius if ev.type != DisasterType.CYCLONE else min(220.0, ev.affected_radius * 0.28)
        existing = next((h for h in city.hazards if h.id == ev.hazard_id), None) if ev.hazard_id else None
        if existing:
            existing.x = ev.epicentre.x
            existing.z = ev.epicentre.z
            existing.radius = round(hz_radius, 1)
            existing.severity = ev.severity
            existing.active = is_active
        elif is_active:
            hz_id = f"HZ-{ev.event_id}"
            ev.hazard_id = hz_id
            city.hazards.append(
                HazardZone(
                    id=hz_id,
                    kind=kind,
                    x=ev.epicentre.x,
                    z=ev.epicentre.z,
                    radius=round(hz_radius, 1),
                    severity=ev.severity,
                    altitude_ceiling=ceiling,
                    active=True,
                    disaster_event_id=ev.event_id,
                )
            )

    def create_disaster(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        *,
        disaster_type: DisasterType,
        x: float,
        z: float,
        y: float = 0.0,
        severity: float = 0.75,
        affected_radius: float = 260.0,
        duration: float = 900.0,
        propagation_speed: float = 1.0,
        start_delay: float = 0.0,
        sim_time_s: float = 0.0,
        auto_start: bool = True,
        seed: Optional[int] = None,
        magnitude: float = 0.0,
        parent_event_id: Optional[str] = None,
        state_version: int = 1,
    ) -> Tuple[DisasterEvent, List[SimulatedSurvivor]]:
        self._validate_epicentre(city, x, z)
        eid = self._next_id()
        ev_seed = seed if seed is not None else (self.seed + self._counter * 31)
        max_r = min(city.world_size * 0.48, max(affected_radius * 1.9, affected_radius + 180.0))
        status = DisasterStatus.CREATED
        if start_delay > 0.0:
            status = DisasterStatus.SCHEDULED
        elif auto_start:
            status = DisasterStatus.ACTIVE

        ev = DisasterEvent(
            event_id=eid,
            type=disaster_type,
            status=status,
            seed=ev_seed,
            epicentre=Epicentre(x=round(x, 1), y=round(y, 1), z=round(z, 1)),
            severity=round(max(0.05, min(1.0, severity)), 2),
            affected_radius=round(max(30.0, min(2000.0, affected_radius)), 1),
            initial_radius=round(max(30.0, min(2000.0, affected_radius)), 1),
            max_radius=round(max_r, 1),
            propagation_speed=round(max(0.1, min(5.0, propagation_speed)), 2),
            start_time=round(sim_time_s + max(0.0, start_delay), 1),
            duration=round(max(30.0, min(7200.0, duration)), 1),
            magnitude=magnitude,
            parent_event_id=parent_event_id,
            state_version=state_version,
        )
        self.events[eid] = ev
        self._record_timeline(sim_time_s, eid, "CREATED", f"{disaster_type.value} created at ({x:.0f}, {z:.0f}) severity={ev.severity}")

        new_survivors: List[SimulatedSurvivor] = []
        if status == DisasterStatus.ACTIVE:
            new_survivors = self._activate_event(city, survivors, ev, sim_time_s)
        return ev, new_survivors

    def _activate_event(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        ev: DisasterEvent,
        sim_time_s: float,
    ) -> List[SimulatedSurvivor]:
        ev.status = DisasterStatus.ACTIVE
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, ev.event_id, "ACTIVATED", f"{ev.type.value} active (radius={ev.affected_radius}m)")
        new_survivors: List[SimulatedSurvivor] = []
        if not ev.related_survivors:
            new_survivors = generate_survivors_for_disaster(city, ev, len(survivors), sim_time_s)
            for s in new_survivors:
                survivors[s.survivor_id] = s
                ev.related_survivors.append(s.survivor_id)
        # Apply immediate first tick impact so buildings/roads reflect the event immediately
        self._dispatch_step(city, survivors, ev, dt=1.0, sim_time_s=sim_time_s)
        self._sync_hazard(city, ev)
        return new_survivors

    def start_disaster(self, city: CityEnvironment, survivors: Dict[str, SimulatedSurvivor], event_id: str, sim_time_s: float) -> Tuple[DisasterEvent, List[SimulatedSurvivor]]:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        new_s = self._activate_event(city, survivors, ev, sim_time_s)
        return ev, new_s

    def pause_disaster(self, event_id: str, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.status = DisasterStatus.PAUSED
        self._record_timeline(sim_time_s, event_id, "PAUSED", "Disaster progression paused")
        return ev

    def resume_disaster(self, city: CityEnvironment, event_id: str, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.status = DisasterStatus.ACTIVE
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "RESUMED", "Disaster progression resumed")
        return ev

    def stop_disaster(self, city: CityEnvironment, event_id: str, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.status = DisasterStatus.RESOLVED
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "RESOLVED", "Disaster stopped and marked resolved")
        return ev

    def remove_disaster(self, city: CityEnvironment, event_id: str, sim_time_s: float) -> bool:
        ev = self.events.pop(event_id, None)
        if not ev:
            return False
        if ev.hazard_id:
            city.hazards = [h for h in city.hazards if h.id != ev.hazard_id]
        self._record_timeline(sim_time_s, event_id, "REMOVED", "Disaster removed from simulation")
        return True

    def reset_disaster(self, city: CityEnvironment, event_id: str, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.elapsed_time = 0.0
        ev.affected_radius = ev.initial_radius
        ev.water_level_m = 0.0
        ev.aftershock_count = 0
        ev.metadata.pop("initial_shock_applied", None)
        ev.metadata.pop("collapse_applied", None)
        ev.status = DisasterStatus.ACTIVE
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "RESET", "Disaster reset to initial parameters")
        return ev

    def adjust_severity(self, city: CityEnvironment, event_id: str, delta: float, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.severity = round(max(0.05, min(1.0, ev.severity + delta)), 2)
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "SEVERITY_CHANGED", f"Severity updated to {ev.severity}")
        return ev

    def expand_radius(self, city: CityEnvironment, event_id: str, delta_radius: float, sim_time_s: float) -> DisasterEvent:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.affected_radius = round(max(30.0, min(2000.0, ev.affected_radius + delta_radius)), 1)
        ev.max_radius = max(ev.max_radius, ev.affected_radius)
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "RADIUS_EXPANDED", f"Radius updated to {ev.affected_radius}m")
        return ev

    def move_epicentre(self, city: CityEnvironment, event_id: str, x: float, z: float, sim_time_s: float) -> DisasterEvent:
        self._validate_epicentre(city, x, z)
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        ev.epicentre.x = round(x, 1)
        ev.epicentre.z = round(z, 1)
        self._sync_hazard(city, ev)
        self._record_timeline(sim_time_s, event_id, "EPICENTRE_MOVED", f"Epicentre moved to ({x:.0f}, {z:.0f})")
        return ev

    def trigger_aftershock(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        event_id: str,
        sim_time_s: float,
        scale: float = 0.65,
    ) -> Dict[str, Any]:
        ev = self.events.get(event_id)
        if not ev:
            raise KeyError(f"Disaster {event_id} not found")
        if ev.type != DisasterType.EARTHQUAKE:
            raise ValueError(f"Aftershocks can only be triggered on earthquake events (got {ev.type.value})")
        ev.aftershock_count += 1
        shock = apply_seismic_shock(city, ev, shock_scale=scale)
        cascades = self._spawn_collapse_cascades(city, survivors, ev, shock.get("newly_collapsed", []), sim_time_s)
        self._record_timeline(sim_time_s, event_id, "AFTERSHOCK", f"Aftershock #{ev.aftershock_count} triggered; {len(cascades)} new collapse(s)")
        return {"event": ev, "shock": shock, "cascades": cascades}

    def _spawn_collapse_cascades(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        parent: DisasterEvent,
        newly_collapsed: List[Dict[str, Any]],
        sim_time_s: float,
    ) -> List[DisasterEvent]:
        spawned: List[DisasterEvent] = []
        for col in newly_collapsed[:2]:  # Cap cascade burst per shock
            col_ev, _ = self.create_disaster(
                city,
                survivors,
                disaster_type=DisasterType.BUILDING_COLLAPSE,
                x=col["x"],
                z=col["z"],
                severity=min(1.0, parent.severity),
                affected_radius=max(75.0, col.get("debris_radius", 80.0)),
                duration=parent.duration,
                sim_time_s=sim_time_s,
                auto_start=True,
                parent_event_id=parent.event_id,
                state_version=parent.state_version,
            )
            spawned.append(col_ev)
        return spawned

    def _dispatch_step(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        ev: DisasterEvent,
        dt: float,
        sim_time_s: float,
    ) -> Dict[str, Any]:
        if ev.type == DisasterType.FLOOD:
            return step_flood(city, ev, dt)
        if ev.type == DisasterType.EARTHQUAKE:
            res = step_earthquake(city, ev, dt)
            if res.get("newly_collapsed"):
                self._spawn_collapse_cascades(city, survivors, ev, res["newly_collapsed"], sim_time_s)
            return res
        if ev.type == DisasterType.FIRE:
            return step_fire(city, ev, dt)
        if ev.type == DisasterType.CYCLONE:
            return step_cyclone(city, ev, dt)
        if ev.type == DisasterType.BUILDING_COLLAPSE:
            return step_building_collapse(city, ev, dt)
        if ev.type == DisasterType.LANDSLIDE:
            return step_landslide(city, ev, dt)
        return {"geometry_changed": False}

    def step(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        dt: float,
        sim_time_s: float,
    ) -> Dict[str, Any]:
        """Advance all active/scheduled disasters by dt seconds."""
        changed_regions: List[Tuple[float, float, float]] = []
        newly_activated: List[str] = []
        for ev in list(self.events.values()):
            if ev.status == DisasterStatus.SCHEDULED and sim_time_s >= ev.start_time:
                self._activate_event(city, survivors, ev, sim_time_s)
                newly_activated.append(ev.event_id)
                changed_regions.append((ev.epicentre.x, ev.epicentre.z, ev.affected_radius))
                continue

            if ev.status not in (
                DisasterStatus.ACTIVE,
                DisasterStatus.INTENSIFYING,
                DisasterStatus.PROPAGATING,
                DisasterStatus.STABILIZING,
                DisasterStatus.CONTAINED,
            ):
                continue

            ev.elapsed_time = round(ev.elapsed_time + dt, 2)
            if ev.elapsed_time >= ev.duration:
                ev.status = DisasterStatus.RESOLVED
                self._sync_hazard(city, ev)
                self._record_timeline(sim_time_s, ev.event_id, "RESOLVED", "Disaster duration completed")
                changed_regions.append((ev.epicentre.x, ev.epicentre.z, ev.affected_radius))
                continue

            res = self._dispatch_step(city, survivors, ev, dt, sim_time_s)
            self._sync_hazard(city, ev)
            if res.get("geometry_changed"):
                changed_regions.append((ev.epicentre.x, ev.epicentre.z, ev.affected_radius))

        return {"changed_regions": changed_regions, "newly_activated": newly_activated}

    def load_preset(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        preset_id: str,
        sim_time_s: float,
        state_version: int = 1,
    ) -> Tuple[List[DisasterEvent], List[SimulatedSurvivor]]:
        preset = get_disaster_preset(preset_id)
        if not preset:
            raise KeyError(f"Disaster preset '{preset_id}' not found")
        created_events: List[DisasterEvent] = []
        created_survivors: List[SimulatedSurvivor] = []
        for spec in preset.get("events", []):
            ep = spec.get("epicentre", {"x": city.world_size * 0.5, "y": 0.0, "z": city.world_size * 0.5})
            ev, surs = self.create_disaster(
                city,
                survivors,
                disaster_type=DisasterType(spec["type"]),
                x=float(ep.get("x", 2000.0)),
                z=float(ep.get("z", 2000.0)),
                y=float(ep.get("y", 0.0)),
                severity=float(spec.get("severity", 0.78)),
                affected_radius=float(spec.get("affected_radius", 280.0)),
                duration=float(spec.get("duration", 900.0)),
                propagation_speed=float(spec.get("propagation_speed", 1.0)),
                start_delay=float(spec.get("start_delay", 0.0)),
                magnitude=float(spec.get("magnitude", 0.0)),
                sim_time_s=sim_time_s,
                auto_start=True,
                state_version=state_version,
            )
            created_events.append(ev)
            created_survivors.extend(surs)
        return created_events, created_survivors

    def create_random_scenario(
        self,
        city: CityEnvironment,
        survivors: Dict[str, SimulatedSurvivor],
        sim_time_s: float,
        seed: Optional[int] = None,
        state_version: int = 1,
    ) -> Tuple[List[DisasterEvent], List[SimulatedSurvivor]]:
        rng = random.Random(seed if seed is not None else (self.seed + len(self.events) * 17))
        presets = load_disaster_presets()
        if presets:
            chosen = rng.choice(presets)
            return self.load_preset(city, survivors, chosen["preset_id"], sim_time_s, state_version=state_version)
        dtype = rng.choice(list(DisasterType))
        x = rng.uniform(city.world_size * 0.2, city.world_size * 0.8)
        z = rng.uniform(city.world_size * 0.2, city.world_size * 0.8)
        ev, surs = self.create_disaster(
            city, survivors, disaster_type=dtype, x=x, z=z,
            severity=round(rng.uniform(0.6, 0.92), 2),
            affected_radius=round(rng.uniform(200.0, 380.0), 1),
            sim_time_s=sim_time_s, auto_start=True, state_version=state_version,
        )
        return [ev], surs
