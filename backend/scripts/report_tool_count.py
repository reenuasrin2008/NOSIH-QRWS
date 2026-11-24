#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.events.bus import AuthoritativeEventBus
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine


def main() -> None:
    event_bus = AuthoritativeEventBus()
    world = GlobalWorldEngine(event_bus)
    route_explorer = AdvancedRouteExplorer(world)
    approval_engine = ApprovalEngine(world)
    provider_manager = AIProviderManager()
    agent = JarvisAgent(
        world=world,
        route_explorer=route_explorer,
        approval_engine=approval_engine,
        provider_manager=provider_manager,
    )
    print(agent.tool_count)


if __name__ == "__main__":
    main()
