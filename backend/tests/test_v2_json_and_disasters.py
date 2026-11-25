"""Comprehensive Quantum Rescue V2 tests: JSON-only storage, disasters, survivors, and replay."""
from __future__ import annotations

import concurrent.futures
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.core.models import BuildingDamageState, DisasterType, FailureType, SimulationStatus, SurvivorStatus
from app.logging.export_manager import build_experiment_zip
from app.simulation.world import SimulationWorld
from app.storage.event_journal import EventJournal
from app.storage.experiment_repository import JsonExperimentRepository
from app.storage.json_store import (
    append_jsonl,
    export_json_bundle,
    import_json_bundle,
    read_json_safe,
    read_jsonl,
    recover_jsonl,
    write_json_atomic,
)


class TestJsonStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_write_missing_corrupt_and_backup_recovery(self):
        target = self.root / "state.json"
        self.assertEqual(read_json_safe(target, default={"missing": True}), {"missing": True})

        write_json_atomic(target, {"v": 1, "name": "alpha"}, create_backup=True, add_schema_version=True)
        loaded = read_json_safe(target)
        self.assertEqual(loaded["v"], 1)
        self.assertEqual(loaded["schema_version"], "2.0.0")

        # Update with backup so .bak holds v=1
        write_json_atomic(target, {"v": 2, "name": "beta"}, create_backup=True)
        # Corrupt target file
        target.write_text("{broken json...", encoding="utf-8")
        recovered = read_json_safe(target, default=None, recover_from_backup=True)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["v"], 1)
        # Ensure corrupt file was quarantined
        corrupt_files = list(self.root.glob("state.json.corrupt.*"))
        self.assertGreaterEqual(len(corrupt_files), 1)

    def test_concurrent_atomic_updates(self):
        target = self.root / "concurrent.json"

        def _worker(i: int):
            write_json_atomic(target, {"worker": i, "items": list(range(20))})
            return read_json_safe(target)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(_worker, range(24)))
        for r in results:
            self.assertIsInstance(r, dict)
            self.assertIn("worker", r)

    def test_jsonl_recovery_and_bundle_export_import(self):
        jpath = self.root / "events.jsonl"
        append_jsonl(jpath, {"id": 1, "msg": "ok"})
        with jpath.open("a", encoding="utf-8") as fh:
            fh.write("{partial corrupt line\n")
        append_jsonl(jpath, {"id": 2, "msg": "ok2"})

        recs = read_jsonl(jpath)
        self.assertEqual(len(recs), 2)
        stats = recover_jsonl(jpath)
        self.assertEqual(stats, {"valid": 2, "dropped": 1})

        # Bundle export/import
        src = self.root / "src_dir"
        dst = self.root / "dst_dir"
        write_json_atomic(src / "a.json", {"a": 1})
        write_json_atomic(src / "b.json", {"b": 2})
        bundle = export_json_bundle(src, self.root / "bundle.json")
        imported = import_json_bundle(bundle, dst)
        self.assertEqual(set(imported), {"a.json", "b.json"})
        self.assertEqual(read_json_safe(dst / "a.json")["a"], 1)

    def test_json_experiment_repository_no_sqlite(self):
        repo = JsonExperimentRepository(base_dir=self.root)
        repo.save_experiment(
            "RUN-TEST1", "SCEN-1", 42, "hybrid", "COMPLETED", 120.0, 91.5,
            {"metrics": {"score": 91.5}}, {"frames": [{"t": 5}]},
            events=[{"id": "EV-1"}], drones=[{"id": "D-01"}], tasks=[{"id": "T-001"}], optimizer=[{"opt": 1}],
        )
        listed = repo.list_experiments()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["run_id"], "RUN-TEST1")

        fetched = repo.get_experiment("RUN-TEST1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["replay"]["frames"][0]["t"], 5)
        self.assertEqual(len(fetched["drones"]), 1)

        # Verify ZERO database files exist
        db_files = list(self.root.rglob("*.db")) + list(self.root.rglob("*.sqlite*"))
        self.assertEqual(db_files, [])


class TestDisasterAndSimulationEngine(unittest.TestCase):
    def test_all_disaster_types_and_multi_hazard_cascades(self):
        world = SimulationWorld(seed=20261124)

        # 1. Flood creation, spread, and survivor generation
        flood_res = world.create_disaster(DisasterType.FLOOD, 1850, 2100, severity=0.82, affected_radius=320)
        flood_id = flood_res["disaster"]["event_id"]
        self.assertGreater(len(flood_res["new_survivors"]), 0)
        initial_r = flood_res["disaster"]["affected_radius"]

        # 2. Earthquake structural damage & aftershock
        eq_res = world.create_disaster(DisasterType.EARTHQUAKE, 2000, 1950, severity=0.92, affected_radius=420)
        eq_id = eq_res["disaster"]["event_id"]
        dmg_summary = world.get_building_damage_summary()
        self.assertGreater(dmg_summary["total_damaged"], 0)
        aftershock = world.trigger_aftershock(eq_id, scale=0.7)
        self.assertEqual(aftershock["disaster"]["aftershock_count"], 1)

        # 3. Fire, Cyclone, Landslide, Building Collapse
        world.create_disaster(DisasterType.FIRE, 2400, 1500, severity=0.85, affected_radius=200)
        world.create_disaster(DisasterType.CYCLONE, 2000, 2000, severity=0.85, affected_radius=700)
        world.create_disaster(DisasterType.LANDSLIDE, 2900, 1700, severity=0.75, affected_radius=200)
        world.create_disaster(DisasterType.BUILDING_COLLAPSE, 1500, 1500, severity=0.9, affected_radius=120)

        # Step simulation and verify dynamic propagation
        world.status = SimulationStatus.RUNNING
        for _ in range(15):
            world.step(dt=1.0)

        self.assertGreater(world.disasters.events[flood_id].affected_radius, initial_r)
        self.assertGreater(world.disasters.events[flood_id].water_level_m, 0.0)
        self.assertGreater(world.city.weather.wind_speed_mps, 10.0)

        # Survivor search, verify, prioritize
        found = world.search_area_for_survivors(1850, 2100, 500)
        self.assertGreater(len(found), 0)
        first_sid = found[0]["survivor_id"]
        verified = world.verify_survivor_location(first_sid)
        self.assertEqual(verified["status"], SurvivorStatus.LOCATED.value)
        ranked = world.prioritize_survivors()
        self.assertGreater(len(ranked), 0)

        # Bounds validation rejects out-of-world coordinates
        with self.assertRaises(ValueError):
            world.create_disaster(DisasterType.FLOOD, 9999, 9999)

    def test_snapshot_restore_and_drone_failure_recovery(self):
        world = SimulationWorld(seed=12345)
        world.create_disaster(DisasterType.FLOOD, 1900, 2000, severity=0.75, affected_radius=280)
        world.run_optimizer("initial_plan")
        for _ in range(8):
            world.step(dt=1.0)

        # Drone failure & recovery
        active_drone = next((d for d in world.drones.values() if d.active_task_id), next(iter(world.drones.values())))
        fail_res = world.inject_failure(active_drone.id, FailureType.MOTOR_FAILURE)
        self.assertTrue(fail_res["ok"])

        # Snapshot serialization & full deserialization
        snap = world.serialize_world()
        restored = SimulationWorld.deserialize_world(snap)
        self.assertEqual(restored.run_id, world.run_id)
        self.assertEqual(restored.state_version, world.state_version)
        self.assertEqual(len(restored.disasters.events), len(world.disasters.events))
        self.assertEqual(len(restored.survivors), len(world.survivors))

        # ZIP export works cleanly
        zbytes = build_experiment_zip(world)
        self.assertGreater(len(zbytes), 1000)

    def test_fastapi_e2e_disaster_and_experiment_endpoints(self):
        from app.main import app

        client = TestClient(app)
        self.assertEqual(client.get("/api/health").json()["storage"], "json_only")
        r = client.post("/api/disasters/preset", json={"preset_id": "CHENNAI_MONSOON_FLOOD"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()["disasters"]), 1)

        surs = client.get("/api/survivors/prioritized").json()
        self.assertGreater(len(surs), 0)

        # Save and retrieve JSON experiment
        saved = client.post("/api/experiments/save").json()
        self.assertTrue(saved["saved"])
        rid = saved["run_id"]
        exp = client.get(f"/api/experiments/{rid}").json()
        self.assertEqual(exp["run_id"], rid)


if __name__ == "__main__":
    unittest.main()
