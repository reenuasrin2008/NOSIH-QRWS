from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app, global_services


class TestFrontendContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_tool_schemas_wire_format(self) -> None:
        resp = self.client.get("/api/ai/tools/schemas")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 50)
        schemas = body["schemas"]
        self.assertEqual(len(schemas), 50)

        for schema in schemas:
            name = schema["name"]
            is_action = name.startswith("prepare_")
            ann = schema["annotations"]
            self.assertIs(ann["readOnlyHint"], not is_action)
            self.assertIs(ann["destructiveHint"], is_action)
            self.assertIs(ann["idempotentHint"], not is_action)
            self.assertIs(ann["openWorldHint"], False)
            self.assertIn("x-category", schema)
            self.assertIsInstance(schema["x-category"], str)
            self.assertIs(schema["x-requiresApproval"], is_action)
            self.assertIs(schema["parameters"]["additionalProperties"], False)

    def test_tool_registry_preserves_frontend_fields(self) -> None:
        resp = self.client.get("/api/ai/tools")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 50)
        tools = body["tools"]
        for name, meta in tools.items():
            self.assertIn("category", meta)
            self.assertIn("requires_approval", meta)
            self.assertIn("read_only", meta)
            self.assertIs(meta["callable"], True)
            self.assertIs(meta["requires_approval"], name.startswith("prepare_"))

    def test_get_tool_schemas_category_filter_medical(self) -> None:
        medical = global_services.jarvis.get_tool_schemas(categories={"medical"})
        self.assertGreater(len(medical), 0)
        names = {s["name"] for s in medical}
        self.assertIn("get_hospital_status", names)
        self.assertIn("get_available_beds", names)
        self.assertNotIn("prepare_swarm_operation", names)
        for s in medical:
            self.assertEqual(s["x-category"], "medical")

    def test_jarvis_reply_contract_fields(self) -> None:
        resp = self.client.post("/api/ai/chat", json={"message": "Get hospital status for Country 3", "session_id": "contract-1"})
        self.assertEqual(resp.status_code, 200)
        reply = resp.json()
        required_keys = {
            "reply_id",
            "timestamp",
            "session_id",
            "user_message",
            "assistant_message",
            "spoken_summary",
            "provider",
            "model",
            "latency_ms",
            "globe_state",
            "intent",
            "intents",
            "intents_succeeded",
            "intents_failed",
            "entities",
            "kpis",
            "tables",
            "tools_called",
            "context",
            "execution_trace",
            "structured_cards",
            "frontend_commands",
            "pending_approval",
        }
        self.assertTrue(required_keys.issubset(set(reply.keys())))
        self.assertEqual(reply["intents_succeeded"], 1)
        self.assertEqual(reply["intents_failed"], 0)


if __name__ == "__main__":
    unittest.main()
