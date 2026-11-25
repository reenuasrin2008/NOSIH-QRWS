"""Compact live world context builder for the AI Rescue Agent."""
from __future__ import annotations

from typing import Any, Dict

from app.models.messages import SessionContext
from app.services.simulation_client import SimulationClient


class StateObserver:
    """Fetches concise, authoritative world context (preserving exact IDs and coordinates)."""

    def __init__(self, sim_client: SimulationClient):
        self.sim = sim_client

    async def build_compact_context(self, session_ctx: SessionContext) -> Dict[str, Any]:
        try:
            ver = await self.sim.get("/api/world/version")
            disasters = await self.sim.get("/api/disasters")
            survivors = await self.sim.get("/api/survivors")
            drones = await self.sim.get("/api/drones")
            weather = await self.sim.get("/api/world/weather")
            metrics_wrap = await self.sim.get("/api/world/metrics")
        except Exception as exc:
            return {"simulation_reachable": False, "error": str(exc)}

        avail = [d["id"] for d in drones if d.get("status") == "AVAILABLE"]
        failed = [d["id"] for d in drones if d.get("status") in ("DESTROYED", "DAMAGED", "COMMUNICATION_LOST")]
        active_disasters = [
            {
                "event_id": d["event_id"],
                "type": d["type"],
                "status": d["status"],
                "epicentre": d["epicentre"],
                "severity": d["severity"],
                "affected_radius": d["affected_radius"],
                "survivors": len(d.get("related_survivors", [])),
            }
            for d in disasters
        ]
        session_ctx.last_world_version = int(ver.get("state_version", 0))
        return {
            "simulation_reachable": True,
            "run_id": ver.get("run_id"),
            "state_version": ver.get("state_version"),
            "sim_time_s": ver.get("sim_time_s"),
            "status": ver.get("status"),
            "strategy": ver.get("strategy"),
            "world_bounds_m": {"x": [0, 4000], "z": [0, 4000]},
            "active_disasters": active_disasters,
            "total_survivors": len(survivors),
            "unrescued_survivors": sum(1 for s in survivors if s.get("status") not in ("EVACUATED", "MEDICAL_ASSISTANCE")),
            "total_drones": len(drones),
            "available_drones_count": len(avail),
            "available_drone_ids_sample": avail[:10],
            "failed_drone_ids": failed,
            "weather": weather,
            "metrics": metrics_wrap.get("metrics", {}),
            "session_context": session_ctx.model_dump(),
        }
