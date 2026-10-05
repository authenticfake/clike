"""Acceptance-first KIT: tests and eval profile are written and locked before the code (roadmap §3)."""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services import gate_integrity, harper  # noqa: E402
from services.cloud_prompt.active_output_contract import build_active_output_contract  # noqa: E402

REQ = "REQ-001"
POLICY = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}
PLAN = json.dumps({"reqs": [{"id": REQ, "title": "Pricing", "acceptance": ["price() returns 10"], "lane": "python"}]})
TEST_PY = "from pricing import price\n\ndef test_price():\n    assert price() == 10\n"
LTC = json.dumps({"req_id": REQ, "checks": [{"id": "unit", "command": "python -m pytest test", "blocking": True}]})


class AcceptanceFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-acceptance-")).resolve()
        self.proj = self.tmp / "projects" / "demo"
        (self.proj / "runs" / "kit" / REQ).mkdir(parents=True)
        self.env = patch.dict(os.environ, {"DEV_FOLDER": str(self.tmp / "projects"), "CLIKE_STATE_DIR": str(self.tmp / "state")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, kit, gateway_files):
        sent = []

        async def fake_post_json(path, payload):
            sent.append(payload)
            return {"ok": True, "phase": payload.get("phase"), "text": "", "files": gateway_files, "diffs": [],
                    "warnings": [], "errors": [], "runId": "r"}

        async def no_selection(**_kw):
            return {}

        payload = {
            "runId": "r", "project_id": "demo", "model": "openai:gpt-6.1-sol", "docRoot": "docs/harper",
            "messages": [{"role": "user", "content": f"/kit {REQ}"}], "executionPreference": "cloud_only",
            "core_blobs": {"plan.json": PLAN},
            "repository_context": {"workspace_folder": str(self.proj)},
            "kit": {"targets": [REQ], **kit},
        }
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=POLICY), patch.object(
            harper, "_write_stage_artifact", return_value=None
        ):
            out = asyncio.run(harper.run_phase("kit", payload))
        return out, sent

    def _write(self, rel, content):
        path = self.proj / "runs" / "kit" / REQ / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_acceptance_runs_alone(self):
        self.assertEqual(harper._normalize_requested_kit_phases({"phases": ["acceptance"]}), ["acceptance"])
        with self.assertRaises(ValueError):
            harper._normalize_requested_kit_phases({"phases": ["acceptance", "kit"]})

    def test_stage_one_writes_only_the_acceptance_surface(self):
        out, sent = self._run({"phases": ["acceptance"]}, [
            {"path": f"runs/kit/{REQ}/test/test_pricing.py", "content": TEST_PY},
            {"path": f"runs/kit/{REQ}/ci/LTC.json", "content": LTC},
            {"path": f"runs/kit/{REQ}/docs/ACCEPTANCE_{REQ}.md", "content": "| criterion | test |"},
            {"path": f"runs/kit/{REQ}/src/pricing.py", "content": "def price():\n    return 10\n"},
        ])
        self.assertEqual(sent[0]["phase"], "acceptance")
        user = sent[0]["composed_messages"][1]["content"]
        self.assertIn("## ACCEPTANCE STAGE — tests first", user)
        self.assertIn("Do NOT write src/", user)
        paths = [f["path"] for f in out["files"]]
        self.assertIn(f"runs/kit/{REQ}/test/test_pricing.py", paths)
        self.assertNotIn(f"runs/kit/{REQ}/src/pricing.py", paths)
        self.assertIn(f"acceptance_stage_output_dropped:src/pricing.py", out["warnings"])
        self.assertTrue(out["acceptance_stage"])

    def test_stage_two_codes_against_locked_tests(self):
        self._write("test/test_pricing.py", TEST_PY)
        self._write("ci/LTC.json", LTC)
        gate_integrity.record_kit_generation(self.proj, REQ)
        gate_integrity.ensure_lock(self.proj, REQ)  # /v1/acceptance/lock
        with patch.object(gate_integrity, "record_kit_generation") as new_generation:
            out, sent = self._run({"acceptance_first": True}, [
                {"path": f"runs/kit/{REQ}/src/pricing.py", "content": "def price():\n    return 10\n"},
                {"path": f"runs/kit/{REQ}/test/test_pricing.py", "content": "def test_price():\n    pass\n"},
            ])
        new_generation.assert_not_called()  # the lock taken after stage 1 stays in force
        user = sent[0]["composed_messages"][1]["content"]
        self.assertIn("## ACCEPTANCE-FIRST — implement against the locked tests", user)
        self.assertIn(f"- runs/kit/{REQ}/test/test_pricing.py", user)
        self.assertIn(f"candidate::runs/kit/{REQ}/test/test_pricing.py", sent[0]["core_blobs"])
        paths = [f["path"] for f in out["files"]]
        self.assertIn(f"runs/kit/{REQ}/src/pricing.py", paths)
        self.assertNotIn(f"runs/kit/{REQ}/test/test_pricing.py", paths)  # weakened test rejected
        self.assertTrue(any(w.startswith("repair_change_rejected:test/test_pricing.py") for w in out["warnings"]))

    def test_output_contract_of_the_acceptance_stage(self):
        requirements = {"required_outputs": [
            {"role": "primary_implementation", "path_hint": f"runs/kit/{REQ}/src/pricing.py"},
            {"role": "acceptance_tests", "path_hint": f"runs/kit/{REQ}/test/test_pricing.py"},
        ]}
        contract = build_active_output_contract(phase="acceptance", runner="cloud", req_id=REQ, file_requirements=requirements)
        self.assertIn(f"runs/kit/{REQ}/test/test_pricing.py", contract["required_outputs"])
        self.assertIn(f"runs/kit/{REQ}/docs/ACCEPTANCE_{REQ}.md", contract["required_outputs"])
        self.assertNotIn(f"runs/kit/{REQ}/src/pricing.py", contract["required_outputs"])
        self.assertEqual(contract["allowed_optional_output_globs"], [f"runs/kit/{REQ}/test/**", f"runs/kit/{REQ}/ci/**"])

    def test_local_agent_packages(self):
        from services.local_agent.kit import _kit_stage

        stage, _title, rules = _kit_stage(REQ, {"kit": {"phases": ["acceptance"]}}, {})
        self.assertEqual(stage, "acceptance")
        self.assertTrue(any("Do NOT write src/" in r for r in rules))
        stage, _title, rules = _kit_stage(REQ, {"kit": {"acceptance_first": True}}, {})
        self.assertEqual(stage, "code_after_locked_acceptance")
        self.assertEqual(_kit_stage(REQ, {"kit": {}}, {})[0], "kit")


if __name__ == "__main__":
    unittest.main()
