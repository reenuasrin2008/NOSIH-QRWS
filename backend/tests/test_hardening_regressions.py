from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.events.bus import AuthoritativeEventBus
from app.main import app, global_services
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIKeyPool, AIProviderManager, KeyRecord
from app.world.global_engine import GlobalWorldEngine


class TestHardeningRegressions(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_reset_requires_confirmation_and_preserves_experiments(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "experiments").mkdir()
            experiment = base / "experiments" / "keep.json"
            experiment.write_text('{"run_id":"KEEP"}', encoding="utf-8")
            snapshot = base / "world_snapshot.json"
            snapshot.write_text('{"snapshot":true}', encoding="utf-8")
            with patch.dict(os.environ, {"LOCAL_DATA_DIR": td}):
                self.assertEqual(self.client.post("/api/world/reset-local-snapshots").status_code, 422)
                self.assertEqual(
                    self.client.post("/api/world/reset-local-snapshots", json={"confirm": "NO"}).status_code,
                    400,
                )
                response = self.client.post(
                    "/api/world/reset-local-snapshots",
                    json={"confirm": "RESET_SNAPSHOTS"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(experiment.exists())
                self.assertFalse(snapshot.exists())

    def test_reset_rebinds_jarvis_tools_to_new_world(self) -> None:
        response = self.client.post(
            "/api/world/reset-local-snapshots",
            json={"confirm": "RESET_SNAPSHOTS"},
        )
        self.assertEqual(response.status_code, 200)
        country_id = "COUNTRY-03"
        global_services.world.countries[country_id].name = "Reset Probe Country"
        result = global_services.jarvis.execute_tool_direct("get_country_status", {"country_id": country_id})
        self.assertEqual(result["status"], "OK")
        self.assertIn("Reset Probe Country", json.dumps(result["result"]))

    def test_provider_errors_redact_secret_values(self) -> None:
        pool = AIKeyPool()
        key = KeyRecord(key_id="gemini_key_1", provider="gemini", secret="super-secret-key")
        pool.keys["gemini"] = [key]
        pool.record_error(key, "request failed for https://example.test?key=super-secret-key")
        self.assertNotIn("super-secret-key", key.last_error)
        self.assertIn("[REDACTED]", key.last_error)

    def test_blank_model_settings_use_provider_defaults(self) -> None:
        with patch.dict(os.environ, {"GEMINI_MODEL": "", "GROK_MODEL": ""}):
            status = AIProviderManager().get_status()["providers"]
        self.assertEqual(status["gemini"]["model"], "gemini-2.5-flash")
        self.assertEqual(status["grok"]["model"], "grok-3")

    def test_invalid_drone_id_never_retargets_failure_proposal(self) -> None:
        bus = AuthoritativeEventBus()
        world = GlobalWorldEngine(bus)
        approvals = ApprovalEngine(world)
        agent = JarvisAgent(
            world=world,
            route_explorer=AdvancedRouteExplorer(world),
            approval_engine=approvals,
            provider_manager=AIProviderManager(),
        )
        result = agent.execute_tool_direct("prepare_drone_failure", {"country_id": "COUNTRY-03", "drone_id": "D-99-99"})
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(len(approvals.approvals), 0)

    def test_multistop_request_is_bounded(self) -> None:
        points = [{"lat": 19.8, "lon": 84.5, "elevation_m": 80.0} for _ in range(51)]
        response = self.client.post(
            "/api/routes/multistop",
            json={"country_id": "COUNTRY-03", "points": points},
        )
        self.assertEqual(response.status_code, 422)

    def test_expired_and_invalid_modified_approvals_cannot_execute(self) -> None:
        bus = AuthoritativeEventBus()
        world = GlobalWorldEngine(bus)
        engine = ApprovalEngine(world)
        approval = engine.create_approval_request(
            "deploy_swarm", "Swarm", "Swarm", "COUNTRY-03", {"drone_count": 2, "mode": "AREA_SCAN", "formation": "SEARCH_GRID"}
        )
        approval.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            engine.approve_and_execute(approval.approval_id)

        fresh = engine.create_approval_request(
            "deploy_swarm", "Swarm", "Swarm", "COUNTRY-03", {"drone_count": 2, "mode": "AREA_SCAN", "formation": "SEARCH_GRID"}
        )
        with self.assertRaises(ValueError):
            engine.modify_pending(fresh.approval_id, {"drone_count": 999})
        self.assertEqual(fresh.parameters["drone_count"], 2)

    def test_concurrent_approval_executes_only_once(self) -> None:
        bus = AuthoritativeEventBus()
        world = GlobalWorldEngine(bus)
        engine = ApprovalEngine(world)
        approval = engine.create_approval_request("dispatch_ambulances", "Ambulances", "Ambulances", "COUNTRY-03", {"count": 1})
        barrier = threading.Barrier(2)

        def approve() -> str:
            barrier.wait()
            try:
                return engine.approve_and_execute(approval.approval_id).status
            except ValueError:
                return "REJECTED_RACE"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: approve(), range(2)))
        self.assertEqual(results.count("EXECUTED"), 1)
        dispatched = sum(1 for ambulance in world.ambulances.values() if ambulance.country_id == "COUNTRY-03" and ambulance.status == "DISPATCHED")
        self.assertEqual(dispatched, 1)

    def test_queued_frontend_commands_are_replayed(self) -> None:
        bus = AuthoritativeEventBus()
        command = bus.dispatch_frontend_command("camera.focus_country", target_id="COUNTRY-03", frontend="quantum-world")
        self.assertEqual(command.status, "queued_frontend_disconnected")
        queued = bus.get_queued_commands("quantum-world")
        self.assertEqual([item["command_id"] for item in queued], [command.command_id])
        bus.mark_command_dispatched(command.command_id)
        self.assertEqual(bus.get_queued_commands("quantum-world"), [])


if __name__ == "__main__":
    unittest.main()
