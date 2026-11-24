from __future__ import annotations

import copy
import unittest

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.core.compat import to_dict
from app.events.bus import AuthoritativeEventBus
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine


def _make_isolated_agent() -> tuple[GlobalWorldEngine, ApprovalEngine, JarvisAgent]:
    bus = AuthoritativeEventBus()
    world = GlobalWorldEngine(bus)
    route_explorer = AdvancedRouteExplorer(world)
    approval_engine = ApprovalEngine(world)
    provider_manager = AIProviderManager()
    agent = JarvisAgent(
        world=world,
        route_explorer=route_explorer,
        approval_engine=approval_engine,
        provider_manager=provider_manager,
    )
    return world, approval_engine, agent


class TestApprovalsSafety(unittest.TestCase):
    def test_every_prepare_tool_never_mutates_world_state(self) -> None:
        world, approval_engine, agent = _make_isolated_agent()

        disasters_before = copy.deepcopy({k: to_dict(v) for k, v in world.disasters.items()})
        drones_before = copy.deepcopy({k: to_dict(v) for k, v in world.drones.items()})
        ambulances_before = copy.deepcopy({k: to_dict(v) for k, v in world.ambulances.items()})
        swarms_before = copy.deepcopy({k: to_dict(v) for k, v in world.swarms.items()})
        approvals_before = len(approval_engine.approvals)

        prepare_tools = [s["name"] for s in agent.get_tool_schemas() if s["name"].startswith("prepare_")]
        self.assertEqual(len(prepare_tools), 6)

        for tool_name in prepare_tools:
            out = agent.execute_tool_direct(tool_name, {"country_id": "COUNTRY-03"})
            self.assertEqual(out["status"], "OK", f"{tool_name} returned error: {out}")
            res = out["result"]
            approval_id = res.get("approval_id") or (res.get("approval") or {}).get("approval_id")
            self.assertTrue(
                isinstance(approval_id, str) and approval_id.startswith("APR-"),
                f"{tool_name} did not return a valid APR-* approval_id: {res}",
            )

        self.assertEqual(len(approval_engine.approvals), approvals_before + len(prepare_tools))
        self.assertEqual({k: to_dict(v) for k, v in world.disasters.items()}, disasters_before)
        self.assertEqual({k: to_dict(v) for k, v in world.drones.items()}, drones_before)
        self.assertEqual({k: to_dict(v) for k, v in world.ambulances.items()}, ambulances_before)
        self.assertEqual({k: to_dict(v) for k, v in world.swarms.items()}, swarms_before)


if __name__ == "__main__":
    unittest.main()
