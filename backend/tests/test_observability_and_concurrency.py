from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi.testclient import TestClient

from app.events.bus import AuthoritativeEventBus
from app.main import app, global_services
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import DisasterType


class TestObservabilityAndConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_01_health_endpoint(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["world_version"], global_services.event_bus.world_version)
        self.assertIsInstance(data["uptime_seconds"], (int, float))
        self.assertGreaterEqual(data["uptime_seconds"], 0.0)
        self.assertEqual(data["tool_count"], global_services.jarvis.tool_count)
        self.assertGreater(data["tool_count"], 0)
        self.assertEqual(data["seed"], global_services.world.seed)

    def test_02_prometheus_metrics_endpoint(self) -> None:
        resp = self.client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp.headers.get("content-type", ""))
        body = resp.text
        for metric_name in (
            "jarvis_tool_calls_total",
            "jarvis_sessions_active",
            "jarvis_tool_errors_total",
            "world_disasters_active",
            "world_approvals_pending",
            "world_version",
        ):
            self.assertIn(metric_name, body)

    def test_03_ai_latency_before_and_after_chat(self) -> None:
        saved_convs = dict(global_services.jarvis.conversations)
        try:
            global_services.jarvis.conversations.clear()
            r_empty = self.client.get("/api/ai/latency")
            self.assertEqual(r_empty.status_code, 200)
            empty_data = r_empty.json()
            self.assertEqual(empty_data["count"], 0)
            self.assertEqual(empty_data["p50_ms"], 0.0)
            self.assertEqual(empty_data["p95_ms"], 0.0)
            self.assertEqual(empty_data["p99_ms"], 0.0)
            self.assertEqual(empty_data["max_ms"], 0.0)

            r_chat = self.client.post(
                "/api/ai/chat",
                json={"message": "Show hospital status in Veridia Basin", "session_id": "latency-test-sess"},
            )
            self.assertEqual(r_chat.status_code, 200)

            r_after = self.client.get("/api/ai/latency")
            self.assertEqual(r_after.status_code, 200)
            after_data = r_after.json()
            self.assertGreaterEqual(after_data["count"], 1)
            self.assertGreaterEqual(after_data["p50_ms"], 0.0)
            self.assertLessEqual(after_data["p50_ms"], after_data["p95_ms"])
            self.assertLessEqual(after_data["p95_ms"], after_data["p99_ms"])
            self.assertLessEqual(after_data["p99_ms"], after_data["max_ms"])
        finally:
            global_services.jarvis.conversations.clear()
            global_services.jarvis.conversations.update(saved_convs)

    def test_04_world_replay_endpoint(self) -> None:
        start_ver = global_services.event_bus.world_version
        r_dis = self.client.post(
            "/api/disasters",
            json={"country_id": "COUNTRY-02", "disaster_type": "FLOOD", "severity": 0.65},
        )
        self.assertEqual(r_dis.status_code, 200)
        approval = r_dis.json()
        self.client.post(f"/api/approvals/{approval['approval_id']}/approve", json={"auto_execute": True})
        end_ver = global_services.event_bus.world_version
        self.assertGreater(end_ver, start_ver)

        resp = self.client.get(
            f"/api/world/replay?from_version={start_ver + 1}&to_version={end_ver}&limit=50"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["seed"], global_services.world.seed)
        self.assertEqual(data["world_version"], end_ver)
        self.assertGreaterEqual(len(data["events"]), 1)
        for ev in data["events"]:
            self.assertGreaterEqual(ev["world_version"], start_ver + 1)
            self.assertLessEqual(ev["world_version"], end_ver)

    def test_05_deterministic_reseed_endpoint(self) -> None:
        def _canonical_world_snapshot():
            ov = self.client.get("/api/world/overview").json()
            # Strip wall-clock / version fields that naturally increment on reseed
            ov.pop("frontends", None)
            ov["clock"].pop("world_version", None)
            for dis in ov.get("active_disasters", []):
                dis.pop("created_at", None)
            drones = self.client.get("/api/global/drones").json()["drones"]
            hospitals = self.client.get("/api/hospitals").json()["hospitals"]
            return {"overview": ov, "drones": drones, "hospitals": hospitals}

        v_before = global_services.event_bus.world_version
        r1 = self.client.post("/api/world/reseed?seed=42")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertTrue(d1["reseeded"])
        self.assertEqual(d1["seed"], 42)
        self.assertGreater(d1["world_version"], v_before)
        snap1 = _canonical_world_snapshot()

        # Mutate the world heavily between the two reseeds
        self.client.post("/api/world/tick?dt_seconds=180")
        disaster_approval = self.client.post(
            "/api/disasters",
            json={"country_id": "COUNTRY-06", "disaster_type": "FIRE", "severity": 0.85},
        ).json()
        self.client.post(f"/api/approvals/{disaster_approval['approval_id']}/approve", json={"auto_execute": True})
        self.client.post("/api/world/tick?dt_seconds=180")

        r2 = self.client.post("/api/world/reseed?seed=42")
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertTrue(d2["reseeded"])
        self.assertEqual(d2["seed"], 42)
        self.assertGreater(d2["world_version"], d1["world_version"])
        snap2 = _canonical_world_snapshot()

        self.assertEqual(snap1, snap2)

    def test_06_multithreaded_step_and_inject_disaster_stress(self) -> None:
        bus = AuthoritativeEventBus()
        world = GlobalWorldEngine(bus, seed=42)
        self.assertIsInstance(world._mutation_lock, type(threading.RLock()))

        errors: list[Exception] = []
        initial_disaster_count = len(world.disasters)
        country_ids = list(world.countries.keys())
        disaster_types = [DisasterType.FLOOD, DisasterType.FIRE, DisasterType.CYCLONE, DisasterType.LANDSLIDE]

        def _stepper(worker_id: int) -> int:
            for _ in range(15):
                world.step(dt_seconds=30.0)
            return worker_id

        def _injector(worker_id: int) -> int:
            for i in range(10):
                cid = country_ids[(worker_id + i) % len(country_ids)]
                dtype = disaster_types[(worker_id + i) % len(disaster_types)]
                world.inject_disaster(country_id=cid, disaster_type=dtype, severity=0.6, radius_km=8.0)
            return worker_id

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = []
            for w in range(4):
                futures.append(pool.submit(_stepper, w))
                futures.append(pool.submit(_injector, w))
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:  # pragma: no cover
                    errors.append(exc)

        self.assertEqual(errors, [])
        # 40 injected disasters (+ any secondary flood cascades) from a clean seed.
        self.assertGreaterEqual(len(world.disasters), initial_disaster_count + 40)
        self.assertEqual(len(world.countries), 7)
        self.assertEqual(len(world.drones), 98)


if __name__ == "__main__":
    unittest.main()
