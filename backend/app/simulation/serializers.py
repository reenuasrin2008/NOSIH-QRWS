"""Authoritative world, entity, and snapshot JSON serialization/deserialization."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.core.models import (
    CityEnvironment,
    DisasterEvent,
    DroneState,
    RescueTask,
    SimulatedSurvivor,
    SimulationEvent,
    SimulationStatus,
    StrategyMetrics,
    StrategyType,
)
from app.navigation.pathfinder import SpatialAirspaceGrid
from app.simulation.charging_manager import ChargingPadManager

if TYPE_CHECKING:
    from app.simulation.world import SimulationWorld


def serialize_city(world: "SimulationWorld") -> Dict[str, Any]:
    return world.city.model_dump()


def serialize_drone(drone: DroneState) -> Dict[str, Any]:
    return drone.model_dump()


def serialize_task(task: RescueTask) -> Dict[str, Any]:
    return task.model_dump()


def serialize_disaster(disaster: DisasterEvent) -> Dict[str, Any]:
    return disaster.model_dump()


def serialize_event(event: SimulationEvent) -> Dict[str, Any]:
    return event.model_dump()


def serialize_experiment(
    world: "SimulationWorld",
    leaderboard: Optional[List[StrategyMetrics]] = None,
) -> Dict[str, Any]:
    metrics = world.get_metrics()
    return {
        "schema_version": "2.0.0",
        "run_id": world.run_id,
        "scenario_id": world.city.scenario_id,
        "scenario_name": world.city.scenario_name,
        "seed": world.seed,
        "strategy": world.strategy.value,
        "status": world.status.value,
        "state_version": world.state_version,
        "sim_time_s": world.sim_time_s,
        "metrics": metrics.model_dump(),
        "leaderboard": [m.model_dump() for m in (leaderboard or [metrics])],
        "disasters": [d.model_dump() for d in world.disasters.events.values()],
        "survivors": [s.model_dump() for s in world.survivors.values()],
        "drones": [d.model_dump() for d in world.drones.values()],
        "tasks": [t.model_dump() for t in world.tasks.values()],
        "events": [e.model_dump() for e in world.events],
    }


def serialize_world(world: "SimulationWorld") -> Dict[str, Any]:
    """Produce a complete, restorable JSON snapshot of the authoritative SimulationWorld."""
    return {
        "schema_version": "2.0.0",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "run_id": world.run_id,
        "strategy": world.strategy.value,
        "seed": world.seed,
        "status": world.status.value,
        "state_version": world.state_version,
        "sim_time_s": world.sim_time_s,
        "speed_multiplier": world.speed_multiplier,
        "started_at_iso": world.started_at_iso,
        "planning_complete": world.planning_complete,
        "replanning_count": world.replanning_count,
        "tasks_recovered": world.tasks_recovered,
        "tasks_needing_recovery_total": world.tasks_needing_recovery_total,
        "airspace_conflicts_total": world.airspace_conflicts_total,
        "city": world.city.model_dump(),
        "drones": {did: d.model_dump() for did, d in world.drones.items()},
        "tasks": {tid: t.model_dump() for tid, t in world.tasks.items()},
        "disasters": {eid: d.model_dump() for eid, d in world.disasters.events.items()},
        "disaster_timeline": list(world.disasters.timeline),
        "survivors": {sid: s.model_dump() for sid, s in world.survivors.items()},
        "events": [e.model_dump() for e in world.events[-500:]],
        "analytics_series": list(world.analytics_series[-300:]),
        "replay_frames": list(world.replay_frames[-400:]),
    }


def deserialize_world(snapshot: Dict[str, Any], world_cls: type) -> "SimulationWorld":
    """Restore a SimulationWorld instance from a previously serialized JSON snapshot."""
    city = CityEnvironment.model_validate(snapshot["city"])
    world = world_cls(
        run_id=snapshot["run_id"],
        strategy=StrategyType(snapshot.get("strategy", "hybrid")),
        seed=int(snapshot.get("seed", city.seed)),
        scenario_id=city.scenario_id,
        scenario_name=city.scenario_name,
        city_density=city.city_density,
        building_density=city.building_density,
    )
    world.city = city
    world.grid = SpatialAirspaceGrid(city)
    world.charging = ChargingPadManager(city)
    world.status = SimulationStatus(snapshot.get("status", "PAUSED"))
    world.state_version = int(snapshot.get("state_version", 1))
    world.sim_time_s = float(snapshot.get("sim_time_s", 0.0))
    world.speed_multiplier = float(snapshot.get("speed_multiplier", 1.0))
    world.started_at_iso = snapshot.get("started_at_iso", world.started_at_iso)
    world.planning_complete = bool(snapshot.get("planning_complete", False))
    world.replanning_count = int(snapshot.get("replanning_count", 0))
    world.tasks_recovered = int(snapshot.get("tasks_recovered", 0))
    world.tasks_needing_recovery_total = int(snapshot.get("tasks_needing_recovery_total", 0))
    world.airspace_conflicts_total = int(snapshot.get("airspace_conflicts_total", 0))

    world.drones = {did: DroneState.model_validate(d) for did, d in snapshot.get("drones", {}).items()}
    world.tasks = {tid: RescueTask.model_validate(t) for tid, t in snapshot.get("tasks", {}).items()}
    world.disasters.events = {
        eid: DisasterEvent.model_validate(ev) for eid, ev in snapshot.get("disasters", {}).items()
    }
    world.disasters._counter = len(world.disasters.events)
    world.disasters.timeline = list(snapshot.get("disaster_timeline", []))
    world.survivors = {
        sid: SimulatedSurvivor.model_validate(s) for sid, s in snapshot.get("survivors", {}).items()
    }
    world.events = [SimulationEvent.model_validate(e) for e in snapshot.get("events", [])]
    world.analytics_series = list(snapshot.get("analytics_series", []))
    world.replay_frames = list(snapshot.get("replay_frames", []))
    return world
