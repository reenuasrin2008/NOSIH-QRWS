"""Comprehensive AI Rescue Agent tests: 6-key rotation, failover, real native tool calling, permissions, interruption, and JSON memory."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / "agent_backend"
BACKEND_DIR = PROJECT_ROOT / "backend"


import subprocess
import time


if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from app.agent.memory import ConversationMemoryStore
from app.agent.rescue_agent import RescueAgent
from app.config import AgentSettings
from app.models.messages import AgentMode, ProviderMode
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.key_rotator import ProviderError, ProviderErrorKind, RoundRobinKeyRotator
from app.providers.provider_manager import ProviderManager
from app.services.execution_logger import AgentEventHub, ExecutionLogger
from app.services.simulation_client import SimulationClient
from app.tools.registry import ToolRegistry


class TestKeyRotationAndProviders(unittest.TestCase):
    def test_grok_and_gemini_strict_round_robin_and_cooldown(self):
        grok_rot = RoundRobinKeyRotator("GROK", ["gsk-11111111", "gsk-22222222", "gsk-33333333"], cooldown_rate_limit_s=60)
        seq = [grok_rot.acquire_next().alias for _ in range(4)]
        self.assertEqual(seq, ["GROK_KEY_1", "GROK_KEY_2", "GROK_KEY_3", "GROK_KEY_1"])

        # Rate-limit key 2 -> skipped cleanly
        grok_rot.record_failure(grok_rot.slots[1], ProviderErrorKind.RATE_LIMIT, "429")
        next_two = [grok_rot.acquire_next().alias for _ in range(2)]
        self.assertEqual(next_two, ["GROK_KEY_3", "GROK_KEY_1"])

        # Permanent AUTH_INVALID on all 3 Gemini keys -> raises AUTH_INVALID without looping forever
        gem_rot = RoundRobinKeyRotator("GEMINI", ["AIza-11111111", "AIza-22222222", "AIza-33333333"])
        for slot in gem_rot.slots:
            gem_rot.record_failure(slot, ProviderErrorKind.AUTH_INVALID, "401")
        with self.assertRaises(ProviderError) as ctx:
            gem_rot.acquire_next()
        self.assertEqual(ctx.exception.kind, ProviderErrorKind.AUTH_INVALID)

    def test_auto_provider_failover_grok_to_gemini(self):
        async def _run():
            def grok_handler(req: httpx.Request) -> httpx.Response:
                return httpx.Response(429, text="rate limit exceeded")

            def gemini_handler(req: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={
                    "candidates": [{"content": {"parts": [{"text": "Gemini fallback succeeded"}]}, "finishReason": "STOP"}]
                })

            grok = GrokProvider(["gsk-11111111", "gsk-22222222", "gsk-33333333"], transport=httpx.MockTransport(grok_handler))
            gemini = GeminiProvider(["AIza-11111111", "AIza-22222222", "AIza-33333333"], transport=httpx.MockTransport(gemini_handler))
            mgr = ProviderManager(grok, gemini, default_mode=ProviderMode.AUTO)

            resp = await mgr.generate_with_tools(
                system_prompt="sys",
                messages=[{"role": "user", "content": "status?"}],
                tool_schemas=[],
            )
            self.assertEqual(resp.provider, "GEMINI")
            self.assertEqual(resp.key_alias, "GEMINI_KEY_1")
            self.assertEqual(resp.switched_from, "GROK")
            self.assertIn("Gemini fallback", resp.text)

        asyncio.run(_run())


class TestRealMultiStepFunctionCallingEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim_port = 18009
        cls.sim_url = f"http://127.0.0.1:{cls.sim_port}"
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.sim_port)],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 12.0
        while time.time() < deadline:
            try:
                r = httpx.get(f"{cls.sim_url}/api/health", timeout=1.0)
                if r.status_code == 200:
                    return
            except Exception:
                time.sleep(0.2)
        cls.proc.terminate()
        raise RuntimeError("Simulation backend failed to start for E2E test")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "proc", None):
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except Exception:
                cls.proc.kill()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _build_agent(self, grok_transport=None, gemini_transport=None, mode=AgentMode.AUTONOMOUS, prov_mode=ProviderMode.GROK):
        settings = AgentSettings(
            grok_api_keys=["gsk-11111111", "gsk-22222222", "gsk-33333333"],
            gemini_api_keys=["AIza-11111111", "AIza-22222222", "AIza-33333333"],
            default_agent_mode=mode.value,
            default_provider_mode=prov_mode.value,
            simulation_api_base_url=self.sim_url,
        )
        sim_client = SimulationClient(base_url=self.sim_url)
        registry = ToolRegistry()
        memory = ConversationMemoryStore(base_dir=self.root)
        logger = ExecutionLogger(base_dir=self.root)
        hub = AgentEventHub()
        grok = GrokProvider(settings.grok_api_keys, transport=grok_transport)
        gemini = GeminiProvider(settings.gemini_api_keys, transport=gemini_transport)
        pm = ProviderManager(grok, gemini, default_mode=prov_mode)
        agent = RescueAgent(settings, pm, sim_client, registry, memory, logger, hub)
        return agent, sim_client, memory, logger

    def test_multi_step_grok_tool_calls_against_live_simulation(self):
        """Proves genuine Grok tool_calls -> Python validation -> real Simulation API -> real result returned -> verified report."""
        step_counter = {"n": 0}
        seen_tool_results: List[Dict[str, Any]] = []

        def grok_mock(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content.decode("utf-8"))
            # Capture real tool results fed back to the model
            for m in body.get("messages", []):
                if m.get("role") == "tool":
                    seen_tool_results.append(json.loads(m["content"]))

            step_counter["n"] += 1
            n = step_counter["n"]
            if n == 1:
                return httpx.Response(200, json={
                    "id": "resp_1",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "create_flood",
                                    "arguments": json.dumps({"x": 1850, "z": 2100, "severity": 0.8, "affected_radius": 320}),
                                },
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                })
            if n == 2:
                return httpx.Response(200, json={
                    "id": "resp_2",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {"id": "call_2", "type": "function", "function": {"name": "get_all_disasters", "arguments": "{}"}},
                                {"id": "call_3", "type": "function", "function": {"name": "prioritize_survivors", "arguments": "{}"}},
                                {"id": "call_4", "type": "function", "function": {"name": "get_available_drones", "arguments": "{}"}},
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }],
                })
            if n == 3:
                return httpx.Response(200, json={
                    "id": "resp_3",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{
                                "id": "call_5",
                                "type": "function",
                                "function": {
                                    "name": "create_rescue_task",
                                    "arguments": json.dumps({"name": "Flood Rooftop Rescue", "x": 1850, "z": 2100, "priority": "critical", "auto_assign": True}),
                                },
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                })
            return httpx.Response(200, json={
                "id": "resp_4",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Flood created, survivors prioritized, and critical rescue task dispatched and verified.",
                    },
                    "finish_reason": "stop",
                }],
            })

        async def _run():
            agent, _sim, memory, logger = self._build_agent(grok_transport=httpx.MockTransport(grok_mock))
            trace = await agent.handle_user_command("Create a flood at (1850, 2100), inspect survivors, and dispatch rescue.")
            self.assertEqual(trace.status, "COMPLETED")
            self.assertEqual(len(trace.tool_records), 5)
            self.assertTrue(all(r.status == "SUCCESS" for r in trace.tool_records))
            # Verify state_version incremented on real simulation mutations
            self.assertGreater(trace.tool_records[0].state_version_after, trace.tool_records[0].state_version_before)
            # Verify real tool results were actually returned to the model
            self.assertGreaterEqual(len(seen_tool_results), 5)
            self.assertTrue(seen_tool_results[0]["success"])
            # Verify JSON execution trace persisted on disk
            saved_exec = logger.get_execution(trace.execution_id)
            self.assertIsNotNone(saved_exec)
            self.assertEqual(saved_exec["execution_id"], trace.execution_id)
            # Verify JSON conversation memory persisted & restored
            reloaded = memory.load_session(trace.session_id)
            self.assertEqual(len(reloaded.messages), 2)
            self.assertIsNotNone(reloaded.current_context.selected_disaster_id)

        asyncio.run(_run())

    def test_gemini_native_function_call_invalid_tool_and_assisted_approval(self):
        turn = {"n": 0}

        def gemini_mock(req: httpx.Request) -> httpx.Response:
            turn["n"] += 1
            if turn["n"] == 1:
                return httpx.Response(200, json={
                    "candidates": [{
                        "content": {
                            "parts": [
                                {"functionCall": {"name": "execute_shell_hack", "args": {"cmd": "ls"}}},
                                {"functionCall": {"name": "create_fire", "args": {"x": 2200, "z": 1600, "severity": 0.7}}},
                            ]
                        },
                        "finishReason": "STOP",
                    }]
                })
            return httpx.Response(200, json={
                "candidates": [{
                    "content": {"parts": [{"text": "Awaiting operator approval to create the fire event."}]},
                    "finishReason": "STOP",
                }]
            })

        async def _run():
            agent, _sim, _mem, _log = self._build_agent(
                gemini_transport=httpx.MockTransport(gemini_mock),
                mode=AgentMode.ASSISTED,
                prov_mode=ProviderMode.GEMINI,
            )
            trace = await agent.handle_user_command("Create a fire at (2200, 1600).")
            # First tool (not allowlisted) must be REJECTED
            self.assertEqual(trace.tool_records[0].status, "REJECTED")
            # Second tool in ASSISTED mode must be PENDING_APPROVAL
            self.assertEqual(trace.tool_records[1].status, "PENDING_APPROVAL")
            self.assertEqual(trace.status, "PENDING_APPROVAL")
            self.assertEqual(len(trace.pending_actions), 1)

            # Now operator approves -> actually executes against live simulation!
            approved = await agent.approve_pending_actions(trace.execution_id)
            self.assertEqual(approved.status, "COMPLETED")
            self.assertEqual(approved.pending_actions[0].status, "EXECUTED")

        asyncio.run(_run())

    def test_operator_interruption_stops_queued_tools(self):
        def grok_mock(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": "resp_int",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {"id": "c1", "type": "function", "function": {"name": "get_world_version", "arguments": "{}"}},
                            {"id": "c2", "type": "function", "function": {"name": "create_fire", "arguments": json.dumps({"x": 1500, "z": 1500})}},
                        ],
                    },
                    "finish_reason": "tool_calls",
                }],
            })

        async def _run():
            agent, _sim, _mem, _log = self._build_agent(grok_transport=httpx.MockTransport(grok_mock))
            # Intercept after first tool starts by setting cancel event
            orig_exec = agent.executor.execute_tool

            async def _exec_then_stop(*args, **kwargs):
                res = await orig_exec(*args, **kwargs)
                agent.stop_current_execution()
                return res

            agent.executor.execute_tool = _exec_then_stop  # type: ignore
            trace = await agent.handle_user_command("Check version then start fire.")
            self.assertEqual(trace.status, "INTERRUPTED")
            # Only 1st tool ran; 2nd queued tool did NOT execute
            self.assertEqual(len(trace.tool_records), 1)
            self.assertEqual(trace.tool_records[0].tool, "get_world_version")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
