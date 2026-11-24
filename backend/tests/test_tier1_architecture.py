from __future__ import annotations

from collections import deque
import importlib
from pathlib import Path
import unittest

from app.ai.entities import (
    _RE_BATTERY_PCT,
    _RE_DRONE_ID,
    build_country_lookup,
    extract_battery_threshold,
    extract_drone_id,
    extract_entities,
)
from app.ai.formatters import JarvisReply, ToolTraceEntry, summarize_result
from app.ai.intents import recognize_intents
from app.ai.jarvis_agent import (
    JarvisAgent,
    JarvisReply as ReexportedJarvisReply,
    SessionContext as ReexportedSessionContext,
    ToolTraceEntry as ReexportedToolTraceEntry,
)
from app.ai.registry import (
    _ID_FIELDS,
    _walk_objects,
    assert_registry_integrity,
    build_tool_registry,
    build_tool_schemas,
    wrap_validated_handler,
)
from app.ai.session import MAX_SESSIONS, SessionContext, evict_stale_sessions
from app.ai.tools import build_all_tool_handlers
from app.approvals.engine import ApprovalEngine
from app.events.bus import AuthoritativeEventBus
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.providers.ai_providers import AIProviderManager
from app.world.global_engine import GlobalWorldEngine


class TestTier1Architecture(unittest.TestCase):
    """Tier 1.1 modular architecture & Tier 1.3 regex disambiguation verification."""

    def setUp(self) -> None:
        self.bus = AuthoritativeEventBus()
        self.world = GlobalWorldEngine(self.bus)
        self.explorer = AdvancedRouteExplorer(self.world)
        self.approvals = ApprovalEngine(self.world)
        self.providers = AIProviderManager()
        self.agent = JarvisAgent(self.world, self.explorer, self.approvals, self.providers)

    def test_nine_domain_tool_modules_import_and_merge_to_50(self) -> None:
        expected_modules = [
            "app.ai.tools.navigation",
            "app.ai.tools.world",
            "app.ai.tools.disasters",
            "app.ai.tools.medical",
            "app.ai.tools.logistics",
            "app.ai.tools.drones",
            "app.ai.tools.routing",
            "app.ai.tools.governance",
            "app.ai.tools.actions",
        ]
        self.assertEqual(len(expected_modules), 9)

        for mod_name in expected_modules:
            mod = importlib.import_module(mod_name)
            self.assertTrue(
                callable(getattr(mod, "build_handlers", None)),
                f"{mod_name} must expose build_handlers",
            )

        merged = build_all_tool_handlers(self.world, self.explorer, self.approvals, deque(maxlen=100))
        self.assertEqual(len(merged), 50)
        self.assertEqual(self.agent.tool_count, 50)
        self.assertEqual(len(self.agent._tool_handlers), 50)
        self.assertEqual(len(self.agent.registry), 50)

    def test_jarvis_agent_line_count_reduced(self) -> None:
        jarvis_path = Path(__file__).resolve().parents[1] / "app" / "ai" / "jarvis_agent.py"
        line_count = len(jarvis_path.read_text(encoding="utf-8").splitlines())
        self.assertLess(line_count, 650, f"jarvis_agent.py should be < 650 lines, got {line_count}")

    def test_public_reexports_and_domain_modules(self) -> None:
        self.assertIs(ReexportedSessionContext, SessionContext)
        self.assertIs(ReexportedJarvisReply, JarvisReply)
        self.assertIs(ReexportedToolTraceEntry, ToolTraceEntry)
        self.assertEqual(MAX_SESSIONS, 500)
        self.assertTrue(callable(evict_stale_sessions))
        self.assertTrue(callable(summarize_result))
        self.assertTrue(callable(build_tool_schemas))
        self.assertTrue(callable(build_tool_registry))
        self.assertTrue(callable(assert_registry_integrity))
        self.assertTrue(callable(_walk_objects))
        self.assertTrue(callable(wrap_validated_handler))
        self.assertIn("country_id", _ID_FIELDS)

        intents = recognize_intents("show blocked roads and hospital status in Aurelia")
        self.assertIn("blocked_roads", intents)
        self.assertIn("hospital_status", intents)

    def test_tier13_drone_id_regex_disambiguation(self) -> None:
        # Must NOT false-positive on "3D-15" or bare "D-20"
        self.assertIsNone(_RE_DRONE_ID.search("3D-15"))
        self.assertIsNone(extract_drone_id("render 3D-15 map sector"))
        self.assertIsNone(_RE_DRONE_ID.search("D-20"))
        self.assertIsNone(extract_drone_id("highway D-20 is flooded"))
        self.assertIsNone(extract_drone_id("3D-03-01 model"))

        # Must extract properly with disambiguating keyword or unambiguous D-XX-XX
        self.assertEqual(extract_drone_id("focus on drone D-03-01"), "D-03-01")
        self.assertEqual(extract_drone_id("track uav D-02-04"), "D-02-04")
        self.assertEqual(extract_drone_id("drone D-20 status"), "D-20")
        self.assertEqual(extract_drone_id("unit D-07 ready"), "D-07")
        self.assertEqual(extract_drone_id("destroy D-03-01 immediately"), "D-03-01")

    def test_tier13_battery_pct_regex_disambiguation(self) -> None:
        # Must NOT false-positive on "arrive under 20 minutes" or other non-battery thresholds
        self.assertIsNone(_RE_BATTERY_PCT.search("arrive under 20 minutes"))
        self.assertIsNone(extract_battery_threshold("ambulances should arrive under 20 minutes"))
        self.assertIsNone(extract_battery_threshold("distance below 15 km"))

        # Must extract properly when battery/charge/power keyword or explicit "%" is present
        self.assertEqual(extract_battery_threshold("show drones with battery below 25%"), 25.0)
        self.assertEqual(extract_battery_threshold("battery under 30"), 30.0)
        self.assertEqual(extract_battery_threshold("charge < 40%"), 40.0)
        self.assertEqual(extract_battery_threshold("power threshold=20"), 20.0)
        self.assertEqual(extract_battery_threshold("drones below 35%"), 35.0)

    def test_tier13_end_to_end_extract_entities(self) -> None:
        ctx = SessionContext(default_country="COUNTRY-03")
        lookup = build_country_lookup(self.world)

        msg_fp = "Check 3D-15 corridor and arrive under 20 minutes"
        ent_fp = extract_entities(msg_fp, msg_fp.lower(), ctx, self.world, lookup)
        self.assertIsNone(ent_fp["drone_id"])
        self.assertNotIn("battery_threshold", ent_fp["counts"])

        msg_ok = "Track drone D-03-01 and list drones with battery below 25%"
        ent_ok = extract_entities(msg_ok, msg_ok.lower(), ctx, self.world, lookup)
        self.assertEqual(ent_ok["drone_id"], "D-03-01")
        self.assertEqual(ent_ok["counts"].get("battery_threshold"), 25.0)


if __name__ == "__main__":
    unittest.main()
