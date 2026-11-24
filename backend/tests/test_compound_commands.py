from __future__ import annotations

import asyncio
import unittest

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
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


class TestCompoundCommands(unittest.TestCase):
    def test_compound_cyclone_swarm_and_mutual_aid(self) -> None:
        _, approval_engine, agent = _make_isolated_agent()
        approvals_before = len(approval_engine.approvals)

        reply = asyncio.run(
            agent.process_command(
                "Simulate a cyclone in Country 3, deploy an 8-drone swarm, and request mutual aid ambulances",
                session_id="compound-action-1",
            )
        )
        self.assertIn("prepare_disaster", reply["intents"])
        self.assertIn("prepare_swarm", reply["intents"])
        self.assertIn("mutual_aid", reply["intents"])
        self.assertEqual(reply["intents_succeeded"], len(reply["intents"]))
        self.assertEqual(reply["intents_failed"], 0)
        self.assertEqual(reply["globe_state"], "AWAITING_APPROVAL")
        self.assertIsNotNone(reply["pending_approval"])
        self.assertGreaterEqual(len(approval_engine.approvals), approvals_before + 3)

    def test_compound_one_failure_does_not_crash(self) -> None:
        _, _, agent = _make_isolated_agent()
        orig = agent._tool_handlers["get_blocked_roads"]
        try:
            def _boom(_args):
                raise RuntimeError("simulated road sensor outage")

            agent._tool_handlers["get_blocked_roads"] = _boom
            reply = asyncio.run(
                agent.process_command(
                    "View Country 3, check blocked roads, and check hospital status",
                    session_id="compound-partial-err",
                )
            )
            self.assertIn("view_country", reply["intents"])
            self.assertIn("blocked_roads", reply["intents"])
            self.assertIn("hospital_status", reply["intents"])
            self.assertEqual(reply["intents_succeeded"], 2)
            self.assertEqual(reply["intents_failed"], 1)
            self.assertNotEqual(reply["globe_state"], "ERROR")
            err_entries = [e for e in reply["execution_trace"] if e["status"] == "ERROR"]
            self.assertEqual(len(err_entries), 1)
            self.assertEqual(err_entries[0]["tool"], "get_blocked_roads")
        finally:
            agent._tool_handlers["get_blocked_roads"] = orig

    def test_compound_all_failures_sets_error_state(self) -> None:
        _, _, agent = _make_isolated_agent()
        orig_roads = agent._tool_handlers["get_blocked_roads"]
        orig_hosp = agent._tool_handlers["get_hospital_status"]
        try:
            agent._tool_handlers["get_blocked_roads"] = lambda _a: (_ for _ in ()).throw(RuntimeError("road fail"))
            agent._tool_handlers["get_hospital_status"] = lambda _a: (_ for _ in ()).throw(RuntimeError("hosp fail"))
            reply = asyncio.run(
                agent.process_command(
                    "Check blocked roads and hospital status in Country 3",
                    session_id="compound-all-err",
                )
            )
            self.assertEqual(reply["intents_succeeded"], 0)
            self.assertEqual(reply["intents_failed"], len(reply["intents"]))
            self.assertEqual(reply["globe_state"], "ERROR")
        finally:
            agent._tool_handlers["get_blocked_roads"] = orig_roads
            agent._tool_handlers["get_hospital_status"] = orig_hosp


if __name__ == "__main__":
    unittest.main()
