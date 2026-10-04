"""KIT staged chain end to end (N4: the hardener stage used to raise NameError)."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services import harper  # noqa: E402

REQ = "REQ-001"


def _response(phase, files):
    return {"ok": True, "phase": phase, "text": "", "files": files, "diffs": [], "warnings": [], "errors": [], "runId": "r"}


class KitChainTests(unittest.TestCase):
    def test_full_chain_reaches_hardener_and_promotion_eval(self):
        calls = []

        async def fake_post_json(path, payload):
            phase = payload.get("phase")
            calls.append(phase)
            if phase == "kit":
                return _response(phase, [
                    {"path": f"runs/kit/{REQ}/src/app_logic.py", "content": "def f():\n    return 1\n"},
                    {"path": f"runs/kit/{REQ}/test/test_app_logic.py", "content": "def test_f():\n    assert True\n"},
                ])
            if phase == "integrity_eval":
                return _response(phase, [{"path": f"runs/kit/{REQ}/reports/integrity.json", "content": json.dumps({"verdict": "needs_hardening"})}])
            return _response(phase, [])

        async def no_selection(**_kw):
            return {}

        payload = {
            "runId": "r",
            "project_id": "p",
            "phase": "kit",
            "model": "openai:gpt-5.4-mini",
            "docRoot": "docs/harper",
            "messages": [{"role": "user", "content": "/kit"}],
            "core_blobs": {"plan.json": json.dumps({"reqs": [{"id": REQ, "title": "t", "acceptance": ["a"], "lane": "python"}]})},
            "kit": {"targets": [REQ], "phases": ["kit", "integrity_eval", "promotion_hardener", "promotion_eval"]},
            "executionPreference": "cloud_only",
        }
        policy = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=policy), patch.object(
            harper, "_write_stage_artifact", return_value=None
        ):
            out = asyncio.run(harper.run_phase("kit", payload))

        self.assertEqual(calls[0], "kit")
        self.assertIn("promotion_hardener", calls, f"chain stopped early: {calls} / {out.get('promotion_eval_status')}")
        self.assertNotIn("NameError", json.dumps(out, default=str))


if __name__ == "__main__":
    unittest.main()
