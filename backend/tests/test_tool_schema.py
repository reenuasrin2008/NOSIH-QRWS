from __future__ import annotations

import asyncio
import copy
import time
import unittest
from collections import deque

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.core.compat import to_dict
from app.events.bus import AuthoritativeEventBus
from app.main import app
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


class TestToolSchemaAndHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_01_registry_integrity_at_startup(self) -> None:
        _, _, agent = _make_isolated_agent()
        # _assert_registry_integrity() is invoked in __init__ and should also pass explicitly
        agent._assert_registry_integrity()
        self.assertEqual(agent.tool_count, 50)
        schemas = agent.get_tool_schemas()
        self.assertEqual(len(schemas), 50)
        for schema in schemas:
            self.assertIs(schema["parameters"].get("additionalProperties"), False)
            self.assertIn("annotations", schema)
            if schema["name"].startswith("prepare_"):
                self.assertIs(schema["annotations"].get("requiresApproval"), True)
                self.assertIs(schema["annotations"].get("readOnlyHint"), False)
            else:
                self.assertIs(schema["annotations"].get("requiresApproval"), False)
                self.assertIs(schema["annotations"].get("readOnlyHint"), True)

    def test_02_prepare_tools_return_approval_id_without_world_mutation(self) -> None:
        world, _, agent = _make_isolated_agent()
        disasters_before = copy.deepcopy({k: to_dict(v) for k, v in world.disasters.items()})
        drones_before = copy.deepcopy({k: to_dict(v) for k, v in world.drones.items()})
        ambulances_before = copy.deepcopy({k: to_dict(v) for k, v in world.ambulances.items()})

        prepare_tools = [s["name"] for s in agent.get_tool_schemas() if s["name"].startswith("prepare_")]
        self.assertGreaterEqual(len(prepare_tools), 6)

        for tool_name in prepare_tools:
            out = agent.execute_tool_direct(tool_name, {"country_id": "COUNTRY-03"})
            res = out["result"]
            approval_id = res.get("approval_id") or (res.get("approval") or {}).get("approval_id")
            self.assertIsNotNone(approval_id, f"{tool_name} did not return an approval_id")
            self.assertTrue(str(approval_id).startswith("APR-"), f"Unexpected approval_id format: {approval_id}")

        self.assertEqual({k: to_dict(v) for k, v in world.disasters.items()}, disasters_before)
        self.assertEqual({k: to_dict(v) for k, v in world.drones.items()}, drones_before)
        self.assertEqual({k: to_dict(v) for k, v in world.ambulances.items()}, ambulances_before)

    def test_03_invalid_args_raise_validation_error_before_world_mutation(self) -> None:
        world, approval_engine, agent = _make_isolated_agent()
        approvals_before = len(approval_engine.approvals)
        disasters_before = len(world.disasters)

        with self.assertRaises(ValidationError):
            agent.execute_tool_direct("prepare_disaster_event", {"country_id": "COUNTRY-03", "severity": 1.5})

        with self.assertRaises(ValidationError):
            agent.execute_tool_direct("get_country_status", {"country_id": "COUNTRY-99"})

        with self.assertRaises(ValidationError):
            agent.execute_tool_direct("view_country", {"country_id": "COUNTRY-03", "unexpected_flag": True})

        self.assertEqual(len(approval_engine.approvals), approvals_before)
        self.assertEqual(len(world.disasters), disasters_before)

    def test_04_category_filtering_medical_excludes_prepare_swarm(self) -> None:
        _, _, agent = _make_isolated_agent()
        medical_schemas = agent.get_tool_schemas(categories={"medical"})
        self.assertGreater(len(medical_schemas), 0)
        names = {s["name"] for s in medical_schemas}
        self.assertNotIn("prepare_swarm_operation", names)
        for s in medical_schemas:
            self.assertEqual(s["annotations"]["category"], "medical")

    def test_05_bounded_memory_eviction_and_per_session_camera(self) -> None:
        world, approval_engine, agent = _make_isolated_agent()
        self.assertIsInstance(agent.tool_logs, deque)
        self.assertEqual(agent.tool_logs.maxlen, 2000)
        self.assertIsInstance(approval_engine.audit_log, deque)
        self.assertEqual(approval_engine.audit_log.maxlen, 5000)

        initial_selected = world.selected_country_id
        target_country = "COUNTRY-01" if initial_selected != "COUNTRY-01" else "COUNTRY-02"
        agent.execute_tool_direct("view_country", {"country_id": target_country})
        self.assertEqual(world.selected_country_id, initial_selected)

        # Stale session eviction
        stale_ctx = agent._get_session("stale-session")
        stale_ctx.last_seen = time.time() - 7200.0
        agent._evict_stale_sessions(max_age_seconds=3600.0)
        self.assertNotIn("stale-session", agent.sessions)

    def test_06_structured_tool_error_and_globe_error_state(self) -> None:
        _, _, agent = _make_isolated_agent()
        trace = []
        err = agent._run_tool(trace, "get_country_status", {"country_id": "COUNTRY-99"})
        self.assertEqual(err["status"], "ERROR")
        self.assertEqual(err["tool"], "get_country_status")
        self.assertEqual(err["category"], "world")
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["status"], "ERROR")

        # Force handler error during process_command to verify globe_state == "ERROR"
        orig = agent._tool_handlers["get_country_status"]
        try:
            def _boom(_args):
                raise RuntimeError("simulated telemetry fault")

            agent._tool_handlers["get_country_status"] = _boom
            reply = asyncio.run(agent.process_command("Status report for Veridia Basin", session_id="err-test"))
            self.assertEqual(reply["globe_state"], "ERROR")
            self.assertIn("Sir", reply["assistant_message"])
        finally:
            agent._tool_handlers["get_country_status"] = orig

    def test_07_reset_local_snapshots_endpoint_and_deque_routes(self) -> None:
        resp = self.client.post("/api/world/reset-local-snapshots")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["reset"])
        self.assertIn("seed", body)

        audit_resp = self.client.get("/api/audit-logs")
        self.assertEqual(audit_resp.status_code, 200)
        self.assertIsInstance(audit_resp.json()["audit_log"], list)
        self.assertIsInstance(audit_resp.json()["tool_logs"], list)

        conv_resp = self.client.get("/api/ai/conversations/default")
        self.assertEqual(conv_resp.status_code, 200)
        self.assertIsInstance(conv_resp.json()["messages"], list)


if __name__ == "__main__":
    unittest.main()
