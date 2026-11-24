from __future__ import annotations

import asyncio
import copy
import time
import unittest
from collections import deque

from fastapi.testclient import TestClient

from app.ai.jarvis_agent import JarvisAgent, _ID_FIELDS
from app.ai.tool_args import TOOL_ARGS_MODELS, TOOL_DESCRIPTIONS
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
        agent._assert_registry_integrity()
        self.assertEqual(agent.tool_count, 50)
        schemas = agent.get_tool_schemas()
        self.assertEqual(len(schemas), 50)
        for schema in schemas:
            self.assertIs(schema["parameters"].get("additionalProperties"), False)
            self.assertIn("annotations", schema)
            self.assertIn("x-category", schema)
            self.assertIn("x-requiresApproval", schema)
            if schema["name"].startswith("prepare_"):
                self.assertIs(schema["x-requiresApproval"], True)
                self.assertIs(schema["annotations"].get("readOnlyHint"), False)
                self.assertIs(schema["annotations"].get("destructiveHint"), True)
            else:
                self.assertIs(schema["x-requiresApproval"], False)
                self.assertIs(schema["annotations"].get("readOnlyHint"), True)
                self.assertIs(schema["annotations"].get("destructiveHint"), False)

    def test_02_prepare_tools_return_approval_id_without_world_mutation(self) -> None:
        world, _, agent = _make_isolated_agent()
        disasters_before = copy.deepcopy({k: to_dict(v) for k, v in world.disasters.items()})
        drones_before = copy.deepcopy({k: to_dict(v) for k, v in world.drones.items()})
        ambulances_before = copy.deepcopy({k: to_dict(v) for k, v in world.ambulances.items()})

        prepare_tools = [s["name"] for s in agent.get_tool_schemas() if s["name"].startswith("prepare_")]
        self.assertGreaterEqual(len(prepare_tools), 6)

        for tool_name in prepare_tools:
            out = agent.execute_tool_direct(tool_name, {"country_id": "COUNTRY-03"})
            self.assertEqual(out["status"], "OK", f"{tool_name} failed: {out}")
            res = out["result"]
            approval_id = res.get("approval_id") or (res.get("approval") or {}).get("approval_id")
            self.assertIsNotNone(approval_id, f"{tool_name} did not return an approval_id")
            self.assertTrue(str(approval_id).startswith("APR-"), f"Unexpected approval_id format: {approval_id}")

        self.assertEqual({k: to_dict(v) for k, v in world.disasters.items()}, disasters_before)
        self.assertEqual({k: to_dict(v) for k, v in world.drones.items()}, drones_before)
        self.assertEqual({k: to_dict(v) for k, v in world.ambulances.items()}, ambulances_before)

    def test_execute_tool_direct_invalid_args_returns_error_dict(self) -> None:
        world, approval_engine, agent = _make_isolated_agent()
        approvals_before = len(approval_engine.approvals)
        disasters_before = len(world.disasters)

        # Unknown tool never raises
        unknown_out = agent.execute_tool_direct("nonexistent_tool", {})
        self.assertEqual(unknown_out["status"], "ERROR")
        self.assertEqual(unknown_out["duration_ms"], 0.0)
        self.assertIn("Unknown tool", unknown_out["error"])

        # Invalid severity, invalid country_id, unexpected extra key never raise
        for tool_name, bad_args in [
            ("prepare_disaster_event", {"country_id": "COUNTRY-03", "severity": 1.5}),
            ("get_country_status", {"country_id": "COUNTRY-99"}),
            ("view_country", {"country_id": "COUNTRY-03", "unexpected_flag": True}),
        ]:
            out = agent.execute_tool_direct(tool_name, bad_args)
            self.assertEqual(out["status"], "ERROR")
            self.assertEqual(out["tool"], tool_name)
            self.assertIn("error", out)
            self.assertIn("trace_entry", out)
            self.assertEqual(out["trace_entry"]["status"], "ERROR")

        self.assertEqual(len(approval_engine.approvals), approvals_before)
        self.assertEqual(len(world.disasters), disasters_before)

        # HTTP route returns 422 with JSON body containing status == "ERROR" and error
        resp = self.client.post(
            "/api/ai/tools/prepare_disaster_event",
            json={"country_id": "COUNTRY-03", "severity": 1.5},
        )
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["status"], "ERROR")
        self.assertIn("error", body)

        resp_unknown = self.client.post("/api/ai/tools/does_not_exist", json={})
        self.assertEqual(resp_unknown.status_code, 422)
        self.assertEqual(resp_unknown.json()["status"], "ERROR")

    def test_04_category_filtering_medical_excludes_prepare_swarm(self) -> None:
        _, _, agent = _make_isolated_agent()
        medical_schemas = agent.get_tool_schemas(categories={"medical"})
        self.assertGreater(len(medical_schemas), 0)
        names = {s["name"] for s in medical_schemas}
        self.assertNotIn("prepare_swarm_operation", names)
        for s in medical_schemas:
            self.assertEqual(s["x-category"], "medical")

    def test_05_bounded_memory_eviction_and_per_session_camera(self) -> None:
        world, approval_engine, agent = _make_isolated_agent()
        self.assertIsInstance(agent.tool_logs, deque)
        self.assertEqual(agent.tool_logs.maxlen, 2000)
        self.assertIsInstance(approval_engine.audit_log, deque)
        self.assertEqual(approval_engine.audit_log.maxlen, 5000)

        initial_selected = world.selected_country_id
        target_country = "COUNTRY-01" if initial_selected != "COUNTRY-01" else "COUNTRY-02"
        out = agent.execute_tool_direct("view_country", {"country_id": target_country})
        self.assertEqual(out["status"], "OK")
        self.assertEqual(world.selected_country_id, initial_selected)

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

        orig = agent._tool_handlers["get_country_status"]
        try:
            def _boom(_args):
                raise RuntimeError("simulated telemetry fault")

            agent._tool_handlers["get_country_status"] = _boom
            reply = asyncio.run(agent.process_command("Status report for Veridia Basin", session_id="err-test"))
            self.assertEqual(reply["globe_state"], "ERROR")
            self.assertEqual(reply["intents_succeeded"], 0)
            self.assertEqual(reply["intents_failed"], 1)
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

    def test_globe_state_not_awaiting_approval_on_prepare_error(self) -> None:
        _, _, agent = _make_isolated_agent()
        orig = agent._tool_handlers["prepare_swarm_operation"]
        try:
            def _boom(_args):
                raise RuntimeError("swarm staging fault")

            agent._tool_handlers["prepare_swarm_operation"] = _boom
            reply = asyncio.run(
                agent.process_command("Prepare an 8-drone medical delivery swarm for Country 3", session_id="prep-err")
            )
            self.assertNotEqual(reply["globe_state"], "AWAITING_APPROVAL")
            self.assertEqual(reply["globe_state"], "ERROR")
            self.assertEqual(reply["intents_succeeded"], 0)
            self.assertEqual(reply["intents_failed"], 1)
            self.assertIsNone(reply["pending_approval"])
        finally:
            agent._tool_handlers["prepare_swarm_operation"] = orig

        # Also verify compound command where view_country succeeds but prepare_swarm fails
        # does not lie with AWAITING_APPROVAL
        orig_swarm = agent._tool_handlers["prepare_swarm_operation"]
        try:
            agent._tool_handlers["prepare_swarm_operation"] = lambda _a: (_ for _ in ()).throw(RuntimeError("boom"))
            reply2 = asyncio.run(
                agent.process_command("View Country 3 and deploy an 8-drone swarm", session_id="prep-err-2")
            )
            self.assertNotEqual(reply2["globe_state"], "AWAITING_APPROVAL")
            self.assertEqual(reply2["intents_succeeded"], 1)
            self.assertEqual(reply2["intents_failed"], 1)
        finally:
            agent._tool_handlers["prepare_swarm_operation"] = orig_swarm

    def test_prepare_drone_failure_no_drones(self) -> None:
        world, _, agent = _make_isolated_agent()
        world.drones.clear()

        out = agent.execute_tool_direct("prepare_drone_failure", {"country_id": "COUNTRY-03"})
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("No drones available", out["error"])

        reply = asyncio.run(agent.process_command("Destroy a drone in Country 3", session_id="no-drones"))
        self.assertEqual(reply["globe_state"], "ERROR")
        self.assertEqual(reply["intents_succeeded"], 0)
        self.assertEqual(reply["intents_failed"], 1)

    def test_registry_integrity_covers_all_id_fields(self) -> None:
        _, _, agent = _make_isolated_agent()
        # Verify all _ID_FIELDS are checked by mutating a copy of schema map
        expected_ids = {
            "country_id",
            "donor_country_id",
            "hospital_id",
            "drone_id",
            "district_id",
            "event_id",
            "road_id",
            "approval_id",
        }
        self.assertEqual(_ID_FIELDS, expected_ids)

        # Strip pattern from a nested/top-level ID field and ensure _assert_registry_integrity raises
        saved_schema = copy.deepcopy(agent._tool_schema_map["focus_hospital"])
        try:
            agent._tool_schema_map["focus_hospital"]["parameters"]["properties"]["hospital_id"].pop("pattern", None)
            with self.assertRaises(AssertionError):
                agent._assert_registry_integrity()
        finally:
            agent._tool_schema_map["focus_hospital"] = saved_schema

        # Strip additionalProperties on nested what_if object and ensure _assert_registry_integrity raises
        saved_cf = copy.deepcopy(agent._tool_schema_map["run_counterfactual_comparison"])
        try:
            agent._tool_schema_map["run_counterfactual_comparison"]["parameters"]["properties"]["what_if"].pop(
                "additionalProperties", None
            )
            with self.assertRaises(AssertionError):
                agent._assert_registry_integrity()
        finally:
            agent._tool_schema_map["run_counterfactual_comparison"] = saved_cf

    def test_every_handler_has_args_model(self) -> None:
        _, _, agent = _make_isolated_agent()
        handlers = set(agent._tool_handlers.keys())
        models = set(TOOL_ARGS_MODELS.keys())
        descriptions = set(TOOL_DESCRIPTIONS.keys())
        self.assertEqual(len(handlers), 50)
        self.assertEqual(handlers, models)
        self.assertEqual(handlers, descriptions)
        for name, model_cls in TOOL_ARGS_MODELS.items():
            d = model_cls().to_handler_dict()
            self.assertIsInstance(d, dict, f"{name} to_handler_dict() did not return dict")

    def test_optional_nested_whatif_schema(self) -> None:
        _, _, agent = _make_isolated_agent()
        schema = agent._tool_schema_map["run_counterfactual_comparison"]["parameters"]
        what_if = schema["properties"]["what_if"]
        self.assertEqual(what_if.get("type"), "object")
        self.assertIs(what_if.get("additionalProperties"), False)
        self.assertNotIn("$ref", what_if)
        self.assertNotIn("allOf", what_if)
        for field_name in ("ambulance_loss_ratio", "drone_availability_ratio", "road_closure_ratio"):
            self.assertIn(field_name, what_if["properties"])

        # Valid call with what_if dict succeeds; unknown nested key returns ERROR
        ok = agent.execute_tool_direct(
            "run_counterfactual_comparison",
            {"country_id": "COUNTRY-03", "what_if": {"road_closure_ratio": 0.4}},
        )
        self.assertEqual(ok["status"], "OK")

        bad = agent.execute_tool_direct(
            "run_counterfactual_comparison",
            {"country_id": "COUNTRY-03", "what_if": {"bogus_ratio": 0.4}},
        )
        self.assertEqual(bad["status"], "ERROR")

    def test_every_schema_self_validates(self) -> None:
        _, _, agent = _make_isolated_agent()
        try:
            import jsonschema
        except ImportError:
            jsonschema = None

        for schema in agent.get_tool_schemas():
            name = schema["name"]
            params = schema["parameters"]
            self.assertEqual(params.get("type"), "object")
            self.assertIs(params.get("additionalProperties"), False)
            if jsonschema is not None:
                jsonschema.Draft7Validator.check_schema(params)
                # Validate default non-null args against the emitted JSON schema
                defaults = {
                    k: v
                    for k, v in TOOL_ARGS_MODELS[name]().to_handler_dict().items()
                    if v is not None
                }
                jsonschema.validate(instance=defaults, schema=params)

    def test_full_tool_sweep_no_exceptions(self) -> None:
        _, _, agent = _make_isolated_agent()
        self.assertEqual(len(agent._tool_handlers), 50)
        for tool_name in sorted(agent._tool_handlers.keys()):
            out = agent.execute_tool_direct(tool_name, {})
            self.assertEqual(out["status"], "OK", f"Tool '{tool_name}' failed default sweep: {out}")
            self.assertIn("result", out)
            self.assertIn("trace_entry", out)


if __name__ == "__main__":
    unittest.main()
