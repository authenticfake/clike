"""/local-agent/complete echoes the agent's telemetry and forwards it to the gateway portal."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.harper import _record_local_agent_telemetry  # noqa: E402

TELEMETRY = {"provider": "claude_code", "executor": "claude_code", "execution": "local_agent", "model": "claude-opus-5-5",
             "usage": {"input_tokens": 3, "output_tokens": 4}, "pricing": {"total_cost": 0.05}, "duration_ms": 900}


class LocalAgentTelemetryTests(unittest.TestCase):
    def _record(self, payload, normalized, post=None):
        post = post or AsyncMock(return_value={"ok": True})
        with patch("services.harper._post_json", post):
            asyncio.run(_record_local_agent_telemetry(payload, normalized))
        return post

    def test_forwarded_and_echoed(self):
        normalized = {"ok": True, "files": [{"path": "a"}, {"path": "b"}]}
        post = self._record({"phase": "kit", "runId": "r1", "project_id": "pingboard", "telemetry": TELEMETRY}, normalized)
        path, record = post.await_args.args
        self.assertEqual(path, "/v1/harper/telemetry")
        self.assertEqual((record["project_id"], record["phase"], record["provider"], record["files_len"]), ("pingboard", "kit", "claude_code", 2))
        self.assertEqual(normalized["telemetry"], TELEMETRY)
        self.assertEqual(normalized["usage"], TELEMETRY["usage"])

    def test_gateway_failure_never_fails_the_run(self):
        normalized = {"ok": True}
        self._record({"phase": "kit", "project_id": "p", "telemetry": TELEMETRY}, normalized,
                     post=AsyncMock(side_effect=RuntimeError("down")))
        self.assertTrue(normalized["ok"])

    def test_without_telemetry_or_project_nothing_is_sent(self):
        self.assertFalse(self._record({"phase": "kit", "project_id": "p"}, {}).await_count)
        self.assertFalse(self._record({"phase": "kit", "telemetry": TELEMETRY}, {}).await_count)


if __name__ == "__main__":
    unittest.main()
