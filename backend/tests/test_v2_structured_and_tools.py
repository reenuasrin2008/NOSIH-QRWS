from __future__ import annotations

import time
import unittest
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from app.api.structured_api import SUPPORTED_TABLE_RESOURCES, VersionedResponseCache, build_v2_router
from app.main import app, global_services


class TestV2StructuredAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not any(getattr(r, "path", None) == "/api/v2/snapshot" for r in app.routes):
            app.include_router(build_v2_router(global_services))
        cls.client = TestClient(app)

    def _assert_envelope(self, payload: Dict[str, Any], expected_count: Optional[int] = None) -> None:
        for key in ("ok", "schema_version", "world_version", "generated_at", "count", "data"):
            self.assertIn(key, payload, f"Missing envelope key: {key}")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "2.0")
        self.assertEqual(payload["world_version"], global_services.event_bus.world_version)
        self.assertIsInstance(payload["generated_at"], str)
        self.assertGreater(len(payload["generated_at"]), 10)
        self.assertIsInstance(payload["count"], int)
        if expected_count is not None:
            self.assertEqual(payload["count"], expected_count)

    def test_01_snapshot_endpoint_and_envelope(self) -> None:
        resp = self.client.get("/api/v2/snapshot")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body, expected_count=7)

        data = body["data"]
        for key in ("totals", "clock", "countries", "active_disasters", "counts"):
            self.assertIn(key, data)
        self.assertEqual(len(data["countries"]), 7)
        self.assertEqual(data["totals"]["countries"], 7)
        self.assertEqual(data["counts"]["countries"], 7)
        self.assertEqual(data["counts"]["drones"], 98)
        # Compact representation omits heavy boundary polygons
        self.assertNotIn("boundary", data["countries"][0])
        self.assertIn("lat", data["countries"][0])
        self.assertIn("lon", data["countries"][0])

    def test_02_country_bundle_complete_and_404(self) -> None:
        resp = self.client.get("/api/v2/country/COUNTRY-03/bundle")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body)
        self.assertGreater(body["count"], 0)

        data = body["data"]
        expected_keys = (
            "profile",
            "cities",
            "districts",
            "hospitals",
            "shelters",
            "warehouses",
            "ambulances",
            "fire_units",
            "drones",
            "roads",
            "animals",
            "disasters",
            "ambulance_requirements",
            "resource_requirements",
            "equity",
            "cascade_graph",
        )
        for key in expected_keys:
            self.assertIn(key, data, f"Missing bundle key: {key}")

        self.assertEqual(data["profile"]["country_id"], "COUNTRY-03")
        self.assertGreater(len(data["cities"]), 0)
        self.assertGreater(len(data["districts"]), 0)
        self.assertGreater(len(data["hospitals"]), 0)
        self.assertGreater(len(data["drones"]), 0)
        self.assertIn("available_beds", data["hospitals"][0])
        self.assertIn("remaining_capacity", data["shelters"][0])
        self.assertIn("nodes", data["cascade_graph"])
        self.assertIn("districts", data["equity"])

        missing = self.client.get("/api/v2/country/COUNTRY-999/bundle")
        self.assertEqual(missing.status_code, 404)

    def test_03_tables_all_resources_and_country_filter(self) -> None:
        for resource in SUPPORTED_TABLE_RESOURCES:
            resp = self.client.get(f"/api/v2/tables/{resource}")
            self.assertEqual(resp.status_code, 200, f"Failed for resource={resource}")
            body = resp.json()
            self._assert_envelope(body)
            table = body["data"]
            self.assertIn("columns", table)
            self.assertIn("rows", table)
            self.assertEqual(body["count"], len(table["rows"]))
            self.assertGreater(len(table["columns"]), 0)
            if table["rows"]:
                first_row = table["rows"][0]
                self.assertEqual(list(first_row.keys()), table["columns"])
                for col, val in first_row.items():
                    self.assertIsInstance(
                        val,
                        (str, int, float, bool, type(None)),
                        f"Non-tabular value in {resource}.{col}: {type(val)}",
                    )

        # Country filter
        filtered = self.client.get("/api/v2/tables/drones?country_id=COUNTRY-03")
        self.assertEqual(filtered.status_code, 200)
        f_body = filtered.json()
        self._assert_envelope(f_body)
        self.assertGreater(f_body["count"], 0)
        for row in f_body["data"]["rows"]:
            self.assertEqual(row["country_id"], "COUNTRY-03")

        # Invalid resource
        bad = self.client.get("/api/v2/tables/unknown_resource")
        self.assertEqual(bad.status_code, 400)

    def test_04_search_exact_substring_and_fuzzy(self) -> None:
        # Exact ID search
        r_exact = self.client.get("/api/v2/search?q=COUNTRY-03")
        self.assertEqual(r_exact.status_code, 200)
        b_exact = r_exact.json()
        self._assert_envelope(b_exact)
        self.assertGreater(b_exact["count"], 0)
        top = b_exact["data"][0]
        for field in ("entity_type", "id", "name", "country_id", "status"):
            self.assertIn(field, top)
        self.assertEqual(top["entity_type"], "country")
        self.assertEqual(top["id"], "COUNTRY-03")

        # Substring search across cities/hospitals
        r_sub = self.client.get("/api/v2/search?q=Delta")
        self.assertEqual(r_sub.status_code, 200)
        b_sub = r_sub.json()
        self._assert_envelope(b_sub)
        self.assertTrue(any(m["entity_type"] == "city" and "Delta" in m["name"] for m in b_sub["data"]))

        # Fuzzy typo search ("Auralia" -> "Aurelia Coast")
        r_fuzzy = self.client.get("/api/v2/search?q=Auralia")
        self.assertEqual(r_fuzzy.status_code, 200)
        b_fuzzy = r_fuzzy.json()
        self._assert_envelope(b_fuzzy)
        self.assertTrue(
            any(m["entity_type"] == "country" and m["id"] == "COUNTRY-01" for m in b_fuzzy["data"]),
            f"Expected fuzzy match for COUNTRY-01 in {b_fuzzy['data']}",
        )

        # Filtered search for drones in COUNTRY-01
        r_drn = self.client.get("/api/v2/search?q=D-01&entity_type=drone&country_id=COUNTRY-01")
        self.assertEqual(r_drn.status_code, 200)
        b_drn = r_drn.json()
        self._assert_envelope(b_drn)
        self.assertGreater(b_drn["count"], 0)
        for m in b_drn["data"]:
            self.assertEqual(m["entity_type"], "drone")
            self.assertEqual(m["country_id"], "COUNTRY-01")

        # Empty query
        r_empty = self.client.get("/api/v2/search?q=")
        self.assertEqual(r_empty.status_code, 200)
        self._assert_envelope(r_empty.json(), expected_count=0)
        self.assertEqual(r_empty.json()["data"], [])

    def test_05_entities_index_lookup(self) -> None:
        resp = self.client.get("/api/v2/entities/index")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self._assert_envelope(body)
        idx = body["data"]
        self.assertEqual(body["count"], len(idx))
        self.assertIn("COUNTRY-03", idx)
        entry = idx["COUNTRY-03"]
        for field in ("id", "entity_type", "name", "country_id", "status", "lat", "lon"):
            self.assertIn(field, entry)
        self.assertEqual(entry["entity_type"], "country")

        # Filtered index
        f_resp = self.client.get("/api/v2/entities/index?country_id=COUNTRY-03&entity_type=hospital")
        self.assertEqual(f_resp.status_code, 200)
        f_body = f_resp.json()
        self._assert_envelope(f_body)
        self.assertGreater(f_body["count"], 0)
        for item in f_body["data"].values():
            self.assertEqual(item["country_id"], "COUNTRY-03")
            self.assertEqual(item["entity_type"], "hospital")

    def test_06_version_cache_hits_and_invalidation(self) -> None:
        # 1. Direct cache unit check: <1 ms repeated reads & invalidation on version bump
        c = VersionedResponseCache()
        calls = {"n": 0}

        def _build() -> Dict[str, Any]:
            calls["n"] += 1
            return {"ok": True, "val": calls["n"]}

        v1_a = c.get_or_build(10, ("k",), _build)
        t0 = time.perf_counter()
        v1_b = c.get_or_build(10, ("k",), _build)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertIs(v1_a, v1_b)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(c.hits, 1)
        self.assertEqual(c.misses, 1)
        self.assertLess(elapsed_ms, 1.0)

        v2 = c.get_or_build(11, ("k",), _build)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(v2["val"], 2)

        # 2. End-to-end HTTP version-cache hit and automatic invalidation on world_version bump
        r1 = self.client.get("/api/v2/snapshot").json()
        r2 = self.client.get("/api/v2/snapshot").json()
        self.assertEqual(r1["world_version"], r2["world_version"])
        self.assertEqual(r1["generated_at"], r2["generated_at"])

        prev_version = r1["world_version"]
        global_services.event_bus.emit(
            "test.v2_cache_invalidation",
            payload={"source": "test_v2_structured_and_tools"},
            category="simulation",
        )
        r3 = self.client.get("/api/v2/snapshot").json()
        self.assertGreater(r3["world_version"], prev_version)
        self.assertNotEqual(r3["generated_at"], r1["generated_at"])


if __name__ == "__main__":
    unittest.main()
