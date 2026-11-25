"""Central allowlisted canonical tool registry."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.tools.disaster_tools import build_disaster_tools
from app.tools.drone_tools import build_drone_tools
from app.tools.environment_tools import build_environment_tools
from app.tools.navigation_tools import build_navigation_tools
from app.tools.optimization_tools import build_optimization_tools
from app.tools.rescue_tools import build_rescue_tools
from app.tools.schemas import ToolDefinition
from app.tools.visual_tools import build_visual_tools
from app.tools.world_tools import build_world_tools


class ToolRegistry:
    """Explicit allowlist registry of all validated, implemented simulation tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        for group in (
            build_world_tools(),
            build_disaster_tools(),
            build_drone_tools(),
            build_rescue_tools(),
            build_navigation_tools(),
            build_optimization_tools(),
            build_environment_tools(),
            build_visual_tools(),
        ):
            for td in group:
                self.register(td)

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        return sorted(self._tools.keys())

    def canonical_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_canonical_schema() for t in self._tools.values()]

    def catalog(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "category": t.category,
                "description": t.description,
                "permission_level": t.permission_level.value,
                "idempotent": t.idempotent,
                "timeout_seconds": t.timeout_seconds,
            }
            for t in self._tools.values()
        ]
