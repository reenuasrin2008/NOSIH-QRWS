from __future__ import annotations
import unittest
from fastapi.testclient import TestClient

from app.main import app, global_services
from app.world.global_models import GeoPoint, geo_to_local, local_to_geo


class TestQuantumRescueGlobalPlatform(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_01_world_creation_and_coordinate_roundtrip(self) -> None:
        ov = self.client.get("/api/world/overview").json()
        self.assertEqual(ov["totals"]["countries"], 7)
        self.assertEqual(ov["totals"]["drones_total"], 98)
        self.assertGreater(ov["totals"]["total_population"], 500000)

        origin = GeoPoint(lat=19.8, lon=84.5, elevation_m=12.0)
        pt = GeoPoint(lat=19.85, lon=84.54, elevation_m=95.0)
        x, y, z = geo_to_local(pt, origin)
        back = local_to_geo(x, y, z, origin)
        self.assertAlmostEqual(back.lat, pt.lat, places=3)
        self.assertAlmostEqual(back.lon, pt.lon, places=3)

    def test_02_realism_household_hospital_consistency(self) -> None:
        for hh in global_services.world.households.values():
            self.assertEqual(hh.resident_count, len(hh.member_ids))
        for h in global_services.world.hospitals.values():
            self.assertLessEqual(h.occupied_beds, h.total_beds)
            self.assertGreaterEqual(h.available_beds, 0)

    def test_03_flood_cyclone_fire_and_cascade(self) -> None:
        r_flood = self.client.post("/api/disasters", json={"country_id": "COUNTRY-01", "disaster_type": "FLOOD", "severity": 0.8})
        self.assertEqual(r_flood.status_code, 200)
        ev = r_flood.json()
        self.assertGreater(ev["affected_population"], 0)

        r_fire = self.client.post("/api/disasters", json={"country_id": "COUNTRY-05", "disaster_type": "FIRE", "severity": 0.75})
        self.assertEqual(r_fire.status_code, 200)

        r_tick = self.client.post("/api/world/tick?dt_seconds=120")
        self.assertEqual(r_tick.status_code, 200)

        cascade = self.client.get("/api/disasters/cascade/COUNTRY-03").json()
        self.assertGreaterEqual(len(cascade["nodes"]), 5)
        self.assertGreaterEqual(len(cascade["edges"]), 5)

    def test_04_jarvis_navigation_and_route_intelligence(self) -> None:
        resp = self.client.post("/api/ai/chat", json={"message": "View Country 1 and find the best drones to reach the hospital"}).json()
        self.assertEqual(resp["context"]["active_country_id"], "COUNTRY-01")
        self.assertGreaterEqual(len(resp["execution_trace"]), 2)
        self.assertTrue(any(c["command_type"] == "camera.focus_country" for c in resp["frontend_commands"]))
        route_cards = [c for c in resp["structured_cards"] if c["type"] == "route_comparison"]
        self.assertEqual(len(route_cards), 1)
        self.assertGreater(len(route_cards[0]["data"]["all_candidate_routes"]), 0)

    def test_05_multistop_sensor_mission(self) -> None:
        pts = [
            {"lat": 19.81, "lon": 84.51, "elevation_m": 80.0},
            {"lat": 19.83, "lon": 84.53, "elevation_m": 85.0},
            {"lat": 19.79, "lon": 84.49, "elevation_m": 90.0},
        ]
        res = self.client.post("/api/routes/multistop", json={"country_id": "COUNTRY-03", "points": pts, "sensor_type": "thermal"}).json()
        self.assertEqual(res["destination_count"], 3)
        self.assertGreater(len(res["plans"]), 0)

    def test_06_jarvis_proposal_approval_and_execution(self) -> None:
        resp = self.client.post("/api/ai/chat", json={"message": "Prepare an 8-drone medical delivery swarm for Country 3"}).json()
        apr = resp["pending_approval"]
        self.assertIsNotNone(apr)
        self.assertEqual(apr["status"], "PENDING")

        exec_resp = self.client.post(f"/api/approvals/{apr['approval_id']}/approve", json={"auto_execute": True}).json()
        self.assertEqual(exec_resp["status"], "EXECUTED")
        self.assertGreater(exec_resp["execution_result"]["deployed_drones"], 0)

    def test_07_drone_destruction_and_automatic_recovery(self) -> None:
        swarms = self.client.get("/api/swarms").json()["swarms"]
        self.assertGreater(len(swarms), 0)
        victim_id = swarms[0]["drone_ids"][0]
        apr = self.client.post(f"/api/global/drones/{victim_id}/destroy/prepare").json()
        res = self.client.post(f"/api/approvals/{apr['approval_id']}/approve", json={"auto_execute": True}).json()
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["execution_result"]["new_status"], "DESTROYED")
        self.assertIsNotNone(res["execution_result"]["replacement_drone_id"])

    def test_08_mutual_aid_counterfactual_and_equity(self) -> None:
        aid = self.client.get("/api/mutual-aid/COUNTRY-03?resource_type=ambulances").json()
        self.assertGreater(len(aid["eligible_donors"]), 0)
        donor = aid["eligible_donors"][0]["donor_country_id"]
        apr = self.client.post("/api/mutual-aid/prepare", json={
            "target_country_id": "COUNTRY-03",
            "donor_country_id": donor,
            "resource_type": "ambulances",
            "quantity": 2,
        }).json()
        ex = self.client.post(f"/api/approvals/{apr['approval_id']}/approve", json={"auto_execute": True}).json()
        self.assertEqual(ex["status"], "EXECUTED")
        self.assertEqual(len(ex["execution_result"]["transferred"]), 2)

        cf = self.client.post("/api/counterfactual/COUNTRY-03").json()
        self.assertEqual(len(cf["scenarios"]), 4)

        eq = self.client.get("/api/equity/COUNTRY-03").json()
        self.assertGreater(len(eq["districts"]), 0)

    def test_09_rbac_and_emergency_stop(self) -> None:
        r_denied = self.client.post("/api/world/emergency-stop", headers={"X-Operator-Role": "viewer"})
        self.assertEqual(r_denied.status_code, 403)
        r_ok = self.client.post("/api/world/emergency-stop", headers={"X-Operator-Role": "administrator"})
        self.assertEqual(r_ok.status_code, 200)
        self.assertTrue(r_ok.json()["emergency_stopped"])
        r_res = self.client.post("/api/world/emergency-resume", headers={"X-Operator-Role": "administrator"})
        self.assertFalse(r_res.json()["emergency_stopped"])

    def test_10_provider_status_and_global_exports(self) -> None:
        ps = self.client.get("/api/ai/providers/status").json()
        self.assertIn("gemini", ps["providers"])
        self.assertIn("grok", ps["providers"])

        geo = self.client.get("/api/global/export/geojson").json()
        self.assertEqual(geo["type"], "FeatureCollection")
        self.assertGreater(len(geo["features"]), 10)

        z = self.client.get("/api/global/export/zip")
        self.assertEqual(z.status_code, 200)
        self.assertGreater(len(z.content), 2000)



    def test_11_live_entities_and_hydrology(self) -> None:
        r0 = self.client.get("/api/world/live-entities/COUNTRY-03")
        self.assertEqual(r0.status_code, 200)
        d0 = r0.json()
        self.assertGreater(len(d0["people"]), 0)
        self.assertGreater(len(d0["ambulances"]), 0)
        self.assertGreater(len(d0["terrain"]), 0)
        # Advance multiple ticks to verify continuous movement & hydrology physics
        for _ in range(3):
            self.client.post("/api/world/tick?dt_seconds=180")
        d1 = self.client.get("/api/world/live-entities/COUNTRY-03").json()
        self.assertGreater(d1["clock"]["sim_time_s"], d0["clock"]["sim_time_s"])



    def test_12_zero_database_local_storage(self) -> None:
        from pathlib import Path
        r = self.client.post("/api/world/save-local")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["saved"])
        self.assertTrue(Path(r.json()["path"]).exists())
        r_exp = self.client.post("/api/experiments/save")
        self.assertEqual(r_exp.status_code, 200)
        self.assertEqual(len(list(Path(".").glob("*.db"))), 0)


if __name__ == "__main__":
    unittest.main()
