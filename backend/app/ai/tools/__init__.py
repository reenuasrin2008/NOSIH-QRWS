from __future__ import annotations

from collections import deque
from typing import Any, Callable, Dict

from app.ai.tools import (
    actions,
    disasters,
    drones,
    governance,
    logistics,
    medical,
    navigation,
    routing,
    world as world_tools,
)
from app.approvals.engine import ApprovalEngine
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.world.global_engine import GlobalWorldEngine

DOMAIN_MODULES = (
    navigation,
    world_tools,
    disasters,
    medical,
    logistics,
    drones,
    routing,
    governance,
    actions,
)


def build_all_tool_handlers(
    world: GlobalWorldEngine,
    route_explorer: AdvancedRouteExplorer,
    approval_engine: ApprovalEngine,
    tool_logs: deque,
) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    """Merge all 9 domain handler builders into the complete 50-tool raw handler map."""
    groups = (
        navigation.build_handlers(world),
        world_tools.build_handlers(world),
        disasters.build_handlers(world),
        medical.build_handlers(world),
        logistics.build_handlers(world),
        drones.build_handlers(world),
        routing.build_handlers(world, route_explorer),
        governance.build_handlers(world, approval_engine, tool_logs),
        actions.build_handlers(world, approval_engine),
    )
    merged: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
    for group in groups:
        overlap = set(merged.keys()) & set(group.keys())
        if overlap:
            raise AssertionError(f"Duplicate tool handler definitions detected: {sorted(overlap)}")
        merged.update(group)
    return merged


__all__ = [
    "DOMAIN_MODULES",
    "actions",
    "build_all_tool_handlers",
    "disasters",
    "drones",
    "governance",
    "logistics",
    "medical",
    "navigation",
    "routing",
    "world_tools",
]