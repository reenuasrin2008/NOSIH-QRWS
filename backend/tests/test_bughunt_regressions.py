import asyncio
from collections import deque
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import httpx

from app.main import app, global_services
from app.providers.ai_providers import (
    AIProviderManager,
    GeminiAdapter,
    GrokAdapter,
    KeyRecord,
)


class TestBugHuntRegressions(unittest.TestCase):
    """Regression tests for AI Pipeline, Approvals, Providers & API Routes Bug Hunt."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    # ------------------------------------------------------------------
    # 1. Providers: Multi-Key Rotation, Malformed Payloads & Context Safety
    # ------------------------------------------------------------------
    def test_provider_rotates_within_same_provider_on_429(self) -> None:
        mgr = AIProviderManager()
        mgr.key_pool.keys["gemini"] = [
            KeyRecord(key_id="gemini_key_1", provider="gemini", secret="sec-1"),
            KeyRecord(key_id="gemini_key_2", provider="gemini", secret="sec-2"),
        ]
        mgr.key_pool.keys["grok"] = []
        calls = []

        async def _fake_generate(prompt, system_prompt, api_key, model, tools=None):
            calls.append(api_key)
            if api_key == "sec-1":
                req = httpx.Request("POST", "https://example.test")
                resp = httpx.Response(429, request=req)
                raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)
            return "Grounded response from key 2"

        mgr.adapters["gemini"].generate = _fake_generate  # type: ignore[method-assign]
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash", "GROK_MODEL": ""}):
            out = asyncio.run(
                mgr.synthesize_narrative("status", {"exposed": 100}, "fallback")
            )

        self.assertEqual(calls, ["sec-1", "sec-2"])
        self.assertEqual(out["provider_used"], "gemini")
        self.assertEqual(out["text"], "Grounded response from key 2")
        self.assertEqual(mgr.key_pool.keys["gemini"][0].rate_limit_events, 1)
        self.assertGreater(mgr.key_pool.keys["gemini"][0].cooldown_until_ts, time.time())

    def test_provider_enable_key_resets_error_count(self) -> None:
        mgr = AIProviderManager()
        rec = KeyRecord(key_id="gemini_key_1", provider="gemini", secret="sec-1")
        mgr.key_pool.keys["gemini"] = [rec]
        for _ in range(5):
            mgr.key_pool.record_error(rec, "boom")
        self.assertFalse(rec.healthy)
        self.assertTrue(mgr.key_pool.enable_key("gemini_key_1"))
        self.assertTrue(rec.healthy)
        self.assertEqual(rec.error_count, 0)
        # One subsequent error must not immediately flip healthy back to False
        mgr.key_pool.record_error(rec, "transient")
        self.assertTrue(rec.healthy)

    def test_provider_malformed_json_and_empty_candidates_fallback(self) -> None:
        mgr = AIProviderManager()
        mgr.key_pool.keys["gemini"] = [KeyRecord(key_id="gemini_key_1", provider="gemini", secret="sec-1")]
        mgr.key_pool.keys["grok"] = [KeyRecord(key_id="grok_key_1", provider="grok", secret="sec-g1")]

        bad_gemini_resp = MagicMock()
        bad_gemini_resp.raise_for_status.return_value = None
        bad_gemini_resp.json.return_value = {"candidates": []}

        bad_grok_resp = MagicMock()
        bad_grok_resp.raise_for_status.return_value = None
        bad_grok_resp.json.return_value = {"choices": [{"message": {"content": None}}]}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [bad_gemini_resp, bad_grok_resp]
        mgr.http_pool.get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-flash", "GROK_MODEL": "grok-2"}):
            out = asyncio.run(
                mgr.synthesize_narrative(
                    user_query=None,  # type: ignore[arg-type]
                    grounded_context={"kpis": [{"a": 1}], "list": [1, 2]},
                    fallback_text="Deterministic fallback summary",
                )
            )

        self.assertEqual(out["provider_used"], "local_deterministic_orchestrator")
        self.assertEqual(out["text"], "Deterministic fallback summary")

    def test_adapters_raise_clean_value_error_on_malformed_json(self) -> None:
        bad_resp = MagicMock()
        bad_resp.raise_for_status.return_value = None
        bad_resp.json.side_effect = ValueError("Invalid JSON")

        pool = MagicMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = bad_resp
        pool.get_client.return_value = mock_client

        gem = GeminiAdapter(http_pool=pool)
        grok = GrokAdapter(http_pool=pool)

        with self.assertRaises(ValueError):
            asyncio.run(gem.generate("hi", "sys", "k", "m"))
        with self.assertRaises(ValueError):
            asyncio.run(grok.generate("hi", "sys", "k", "m"))

    # ------------------------------------------------------------------
    # 2. Approvals: Double-Approval, Post-Execution Reject & v2 Cache
    # ------------------------------------------------------------------
    def test_double_approval_and_post_execution_guards_and_v2_cache_invalidation(self) -> None:
        # Warm /api/v2/snapshot cache
        snap_before = self.client.get("/api/v2/snapshot").json()
        ver_before = snap_before["world_version"]
        swarms_before = snap_before["data"]["counts"]["swarms"]

        # Create a pending swarm approval
        prep = self.client.post(
            "/api/swarms/prepare",
            json={"country_id": "COUNTRY-03", "drone_count": 2, "mode": "AREA_SCAN", "formation": "SEARCH_GRID"},
        )
        self.assertEqual(prep.status_code, 200)
        aid = prep.json()["approval_id"]

        # Approve & execute once
        first = self.client.post(f"/api/approvals/{aid}/approve", json={"auto_execute": True})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "EXECUTED")

        # Verify /api/v2/snapshot cache invalidated and reflects the new swarm
        snap_after = self.client.get("/api/v2/snapshot").json()
        self.assertGreater(snap_after["world_version"], ver_before)
        self.assertEqual(snap_after["data"]["counts"]["swarms"], swarms_before + 1)

        # Double-approve must fail cleanly with 400 and NOT create a second swarm
        second = self.client.post(f"/api/approvals/{aid}/approve", json={"auto_execute": True})
        self.assertEqual(second.status_code, 400)
        snap_after_dup = self.client.get("/api/v2/snapshot").json()
        self.assertEqual(snap_after_dup["data"]["counts"]["swarms"], swarms_before + 1)

        # Rejecting an already EXECUTED approval must fail cleanly with 400 and preserve EXECUTED status
        rej_after_exec = self.client.post(f"/api/approvals/{aid}/reject", json={"note": "too late"})
        self.assertEqual(rej_after_exec.status_code, 400)
        self.assertEqual(global_services.approval_engine.approvals[aid].status, "EXECUTED")

        # Modifying an already EXECUTED approval must fail cleanly with 400
        mod_after_exec = self.client.post(f"/api/approvals/{aid}/modify", json={"updates": {"drone_count": 5}})
        self.assertEqual(mod_after_exec.status_code, 400)

    def test_rejected_approval_cannot_be_reapproved_or_rerejected_and_unknown_is_404(self) -> None:
        prep = self.client.post(
            "/api/swarms/prepare",
            json={"country_id": "COUNTRY-03", "drone_count": 2, "mode": "AREA_SCAN", "formation": "SEARCH_GRID"},
        ).json()
        aid = prep["approval_id"]

        r1 = self.client.post(f"/api/approvals/{aid}/reject", json={"note": "cancel"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["status"], "REJECTED")

        # Re-rejecting or re-approving must return 400
        self.assertEqual(self.client.post(f"/api/approvals/{aid}/reject", json={"note": "again"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/approvals/{aid}/approve", json={"auto_execute": True}).status_code, 400)

        # Unknown approval_id returns 404
        self.assertEqual(self.client.post("/api/approvals/APR-DOESNOTEXIST/approve", json={}).status_code, 404)
        self.assertEqual(self.client.post("/api/approvals/APR-DOESNOTEXIST/reject", json={}).status_code, 404)
        self.assertEqual(self.client.post("/api/approvals/APR-DOESNOTEXIST/modify", json={"updates": {}}).status_code, 404)

    # ------------------------------------------------------------------
    # 3. JARVIS Agent: Empty/Long Messages, Polish Fallback & SSE Stream
    # ------------------------------------------------------------------
    def test_empty_and_long_chat_messages_handled_cleanly(self) -> None:
        empty_resp = self.client.post("/api/ai/chat", json={"message": "   \t\n  ", "session_id": "empty-sess"})
        self.assertEqual(empty_resp.status_code, 200)
        body = empty_resp.json()
        self.assertEqual(body["globe_state"], "IDLE")
        self.assertEqual(body["intents"], [])
        self.assertEqual(body["tools_called"], [])
        self.assertTrue(body["assistant_message"])

        long_msg = "status of COUNTRY-03 " + ("x" * 10000)
        long_resp = self.client.post("/api/ai/chat", json={"message": long_msg, "session_id": "long-sess"})
        self.assertEqual(long_resp.status_code, 200)
        self.assertLessEqual(len(long_resp.json()["user_message"]), 4000)

    def test_llm_polish_exception_falls_back_to_deterministic_answer(self) -> None:
        agent = global_services.jarvis
        with patch.object(
            agent.provider_manager,
            "synthesize_narrative",
            new=AsyncMock(side_effect=RuntimeError("provider explosion")),
        ):
            reply = asyncio.run(
                agent.process_command("show hospital status in COUNTRY-03", session_id="polish-err", use_llm_polish=True)
            )
        self.assertEqual(reply["provider"], "local_deterministic_orchestrator")
        self.assertIn("Medical grid", reply["assistant_message"])

    def test_llm_polish_omits_redundant_tool_schemas(self) -> None:
        agent = global_services.jarvis
        with patch.object(
            agent.provider_manager,
            "synthesize_narrative",
            new=AsyncMock(return_value={
                "text": "Grounded provider summary",
                "provider_used": "gemini",
                "model_used": "gemini-2.5-flash",
            }),
        ) as synthesize:
            reply = asyncio.run(
                agent.process_command("show hospital status in COUNTRY-03", session_id="polish-tools", use_llm_polish=True)
            )
        self.assertEqual(reply["provider"], "gemini")
        self.assertEqual(reply["assistant_message"], "Grounded provider summary")
        self.assertNotIn("tool_schemas", synthesize.call_args.kwargs)

    def test_chat_stream_emits_sse_error_event_on_exception(self) -> None:
        with patch.object(
            global_services.jarvis,
            "process_command",
            new=AsyncMock(side_effect=RuntimeError("simulated stream failure")),
        ):
            resp = self.client.post("/api/ai/chat/stream", json={"message": "hello", "session_id": "stream-err"})
        self.assertEqual(resp.status_code, 200)
        lines = [ln for ln in resp.text.splitlines() if ln.startswith("data: ")]
        self.assertTrue(lines)
        payload = json.loads(lines[-1].removeprefix("data: "))
        self.assertEqual(payload["type"], "error")
        self.assertIn("simulated stream failure", payload["error"])

    def test_session_eviction_cleans_orphaned_conversations(self) -> None:
        agent = global_services.jarvis
        agent.conversations["orphan-session-xyz"] = deque([{"reply_id": "MSG-1"}])
        agent._evict_stale_sessions(max_age_seconds=3600.0)
        self.assertNotIn("orphan-session-xyz", agent.conversations)

    # ------------------------------------------------------------------
    # 4. API Routes: Unknown Entities (404/400), Mode Cache & Deque Logs
    # ------------------------------------------------------------------
    def test_unknown_country_and_entity_routes_never_500(self) -> None:
        bad_cid = "COUNTRY-99"
        get_404_routes = [
            f"/api/countries/{bad_cid}/cities",
            f"/api/countries/{bad_cid}/population",
            f"/api/disasters/cascade/{bad_cid}",
            f"/api/ambulances/requirements/{bad_cid}",
            f"/api/resources/shortages/{bad_cid}",
            f"/api/mutual-aid/{bad_cid}",
            f"/api/equity/{bad_cid}",
        ]
        for url in get_404_routes:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 404, f"Expected 404 for GET {url}, got {r.status_code}")

        self.assertEqual(self.client.post(f"/api/counterfactual/{bad_cid}").status_code, 404)
        self.assertEqual(self.client.post(f"/api/playbooks/PB-01/adapt/{bad_cid}").status_code, 404)
        self.assertEqual(
            self.client.post("/api/disasters/prepare", json={"country_id": bad_cid}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/swarms/prepare", json={"country_id": bad_cid}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/swarms/prepare",
                json={"country_id": "COUNTRY-03", "mode": "NOT_A_MODE", "formation": "SEARCH_GRID"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/mutual-aid/prepare",
                json={"target_country_id": "COUNTRY-03", "donor_country_id": bad_cid},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/routes/explore",
                json={"drone_id": "D-99-99", "destination_lat": 10.0, "destination_lon": 20.0},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/routes/multistop",
                json={"country_id": "COUNTRY-03", "points": []},
            ).status_code,
            400,
        )

    def test_world_mode_change_invalidates_v2_snapshot_cache(self) -> None:
        s1 = self.client.get("/api/v2/snapshot").json()
        v1 = s1["world_version"]
        new_mode = "REPLAY" if s1["data"]["clock"]["mode"] != "REPLAY" else "LIVE"
        m_resp = self.client.post(f"/api/world/mode/{new_mode}")
        self.assertEqual(m_resp.status_code, 200)
        s2 = self.client.get("/api/v2/snapshot").json()
        self.assertGreater(s2["world_version"], v1)
        self.assertEqual(s2["data"]["clock"]["mode"], new_mode)

    def test_routes_logs_handles_deque_and_events_limit_bounds(self) -> None:
        orig_logs = global_services.route_explorer.route_logs
        try:
            global_services.route_explorer.route_logs = deque([{"route_id": "R-1"}, {"route_id": "R-2"}], maxlen=50)
            r = self.client.get("/api/routes/logs")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.json()["logs"]), 2)
        finally:
            global_services.route_explorer.route_logs = orig_logs

        self.assertEqual(self.client.get("/api/events?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/events?limit=-5").status_code, 422)


if __name__ == "__main__":
    unittest.main()
