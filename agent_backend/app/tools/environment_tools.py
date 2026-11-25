"""Environment weather and lighting adjustment tools."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition


def build_environment_tools() -> List[ToolDefinition]:
    async def inject_environment_event(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        return await sim.post("/api/environment/events", json_body={
            "event_kind": args["event_kind"],
            "params": args.get("params", {}),
        })

    return [
        ToolDefinition(
            "inject_environment_event",
            "environment",
            "Inject a metropolitan environment event (increase_wind, heavy_rain, change_wind_direction, toggle_day_night, close_airspace).",
            {
                "type": "object",
                "properties": {
                    "event_kind": {
                        "type": "string",
                        "enum": ["increase_wind", "heavy_rain", "change_wind_direction", "toggle_day_night", "close_airspace", "expand_fire", "new_fire", "new_flood"],
                    },
                    "params": {"type": "object"},
                },
                "required": ["event_kind"],
                "additionalProperties": False,
            },
            inject_environment_event,
            PermissionLevel.OPERATIONAL,
            idempotent=False,
        )
    ]
