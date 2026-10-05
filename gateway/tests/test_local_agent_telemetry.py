"""Local-agent runs reach the telemetry portal (no provider call goes through the gateway)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

TOKEN = "t" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class LocalAgentTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN})
        self._env.start()
        os.environ.pop("CLIKE_ALLOWED_HOSTS", None)
        from app import app
        from routes import harper as harper_routes
        from routes import telemetry_api

        self._dirs = [patch.object(harper_routes, "TELEMETRY_DIR", Path(self.tmp.name)),
                      patch.object(telemetry_api, "TELEMETRY_DIR", Path(self.tmp.name))]
        for p in self._dirs:
            p.start()
        self.client = TestClient(app, base_url="http://127.0.0.1:8000")

    def tearDown(self):
        for p in self._dirs:
            p.stop()
        self._env.stop()
        self.tmp.cleanup()

    def test_agent_run_is_recorded_in_the_portal_format(self):
        body = {
            "project_id": "pingboard", "run_id": "r1", "phase": "kit", "provider": "claude_code",
            "model": "claude-opus-5-5", "usage": {"input_tokens": 3, "output_tokens": 40, "note": "x"},
            "pricing": {"total_cost": 0.05, "unit": "usd_api_equivalent"}, "files_len": 7, "duration_ms": 1200,
            "executor": "claude_code",
        }
        self.assertEqual(self.client.post("/v1/harper/telemetry", json=body, headers=AUTH).json(), {"ok": True})
        rows = [json.loads(line) for line in (Path(self.tmp.name) / "pingboard.json").read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["provider"], row["model"], row["execution"], row["phase"]), ("claude_code", "claude-opus-5-5", "local_agent", "kit"))
        self.assertEqual(row["usage"], {"input_tokens": 3, "output_tokens": 40})  # non-numeric dropped
        self.assertIsInstance(row["timestamp"], float)

        from routes.telemetry_api import _cost_from_row

        self.assertEqual(_cost_from_row(row), 0.05)

    def test_requires_the_service_token(self):
        body = {"project_id": "p", "phase": "kit", "provider": "claude_code"}
        self.assertEqual(self.client.post("/v1/harper/telemetry", json=body).status_code, 401)


if __name__ == "__main__":
    unittest.main()
