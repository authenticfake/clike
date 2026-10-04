"""runId is generated when missing, never the string "None" (WP7.10)."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services import harper  # noqa: E402

POLICY = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}


class RunIdTests(unittest.TestCase):
    def _run(self, run_id):
        async def fake_post_json(path, payload):
            return {"ok": True, "phase": payload["phase"], "text": "", "files": [], "diffs": [], "warnings": [],
                    "errors": [], "runId": payload.get("runId")}

        async def no_selection(**_kw):
            return {}

        payload = {"project_id": "p", "model": "openai:gpt-5.4-mini", "docRoot": "docs/harper",
                   "messages": [{"role": "user", "content": "/spec"}], "executionPreference": "cloud_only"}
        if run_id is not ...:
            payload["runId"] = run_id
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=POLICY):
            return asyncio.run(harper.run_phase("spec", payload))["runId"]

    def test_missing_or_null_run_id_is_generated(self):
        for value in (..., None, "", "None"):
            rid = self._run(value)
            self.assertRegex(rid, r"^spec-[0-9a-f]{12}$", repr(value))

    def test_null_flags_are_normalized(self):
        seen = {}

        async def capture(path, payload):
            seen.update(payload)
            return {"ok": True, "phase": "spec", "files": [], "runId": payload.get("runId")}

        async def no_selection(**_kw):
            return {}

        with patch.object(harper, "_post_json", side_effect=capture), patch.object(
            harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=POLICY):
            asyncio.run(harper.run_phase("spec", {"runId": "r", "flags": None, "messages": []}))
        self.assertEqual(seen["flags"], {})

    def test_given_run_id_is_kept(self):
        self.assertEqual(self._run("run-42"), "run-42")


if __name__ == "__main__":
    unittest.main()
