"""Auto-eval KIT repair (roadmap §3): prompt, lock kept, governed acceptance changes."""

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

REQ = "REQ-001"
LTC = {"req_id": REQ, "checks": [{"id": "unit", "command": "pytest test/wrong_path.py", "blocking": True}]}
POLICY = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}


class KitRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-repair-")).resolve()
        self.proj = self.tmp / "projects" / "demo"
        kit = self.proj / "runs" / "kit" / REQ
        (kit / "ci").mkdir(parents=True)
        (kit / "test").mkdir()
        (kit / "src").mkdir()
        (kit / "ci" / "LTC.json").write_text(json.dumps(LTC))
        (kit / "test" / "test_app.py").write_text("from app import f\n\ndef test_f():\n    assert f() == 1\n")
        (kit / "src" / "app.py").write_text("def f():\n    return 0\n")
        self.env = patch.dict(os.environ, {"DEV_FOLDER": str(self.tmp / "projects"), "CLIKE_STATE_DIR": str(self.tmp / "state")})
        self.env.start()
        gate_integrity.ensure_lock(self.proj, REQ)  # first eval took the lock

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, gateway_files):
        sent = []

        async def fake_post_json(path, payload):
            sent.append(payload)
            return {"ok": True, "phase": "kit", "text": "", "files": gateway_files, "diffs": [], "warnings": [], "errors": [], "runId": "r"}

        async def no_selection(**_kw):
            return {}

        payload = {
            "runId": "r", "project_id": "demo", "model": "openai:gpt-6.1-sol", "docRoot": "docs/harper",
            "messages": [{"role": "user", "content": f"/kit {REQ}"}], "executionPreference": "cloud_only",
            "core_blobs": {"plan.json": json.dumps({"reqs": [{"id": REQ, "title": "t", "acceptance": ["a"], "lane": "python"}]})},
            "repository_context": {"workspace_folder": str(self.proj)},
            "kit": {"targets": [REQ], "repair": {
                "cycle": 1, "max_cycles": 2, "hint": "f must return 1",
                "failures": [{"name": "unit", "code": 4, "command": "pytest test/wrong_path.py", "output": "ERROR: file not found"}],
                "files": [{"path": f"runs/kit/{REQ}/src/app.py", "content": "def f():\n    return 0\n"}],
            }},
        }
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=POLICY), patch.object(
            harper, "_write_stage_artifact", return_value=None
        ), patch.object(gate_integrity, "record_kit_generation") as new_generation:
            out = asyncio.run(harper.run_phase("kit", payload))
        return out, sent, new_generation

    def test_repair_prompt_lock_and_governed_changes(self):
        fixed_ltc = json.dumps({**LTC, "checks": [{"id": "unit", "command": "pytest test/test_app.py", "blocking": True}]})
        out, sent, new_generation = self._run([
            {"path": f"runs/kit/{REQ}/src/app.py", "content": "def f():\n    return 1\n"},
            {"path": f"runs/kit/{REQ}/ci/LTC.json", "content": fixed_ltc},
            {"path": f"runs/kit/{REQ}/test/test_app.py", "content": "def test_f():\n    pass\n"},
        ])
        new_generation.assert_not_called()  # the lock stays in force
        user = sent[0]["composed_messages"][1]["content"]
        self.assertIn("## AUTO-EVAL REPAIR — cycle 1 of 2", user)
        self.assertIn("ERROR: file not found", user)
        self.assertIn("f must return 1", user)
        self.assertIn(f"#### runs/kit/{REQ}/src/app.py", user)
        paths = [f["path"] for f in out["files"]]
        self.assertEqual(paths, [f"runs/kit/{REQ}/src/app.py", f"runs/kit/{REQ}/ci/LTC.json"])  # no guardrails, no test edit
        self.assertIn("repair_amendment_accepted:ci/LTC.json", out["warnings"])
        self.assertTrue(any(w.startswith(f"repair_change_rejected:test/test_app.py") for w in out["warnings"]))
        self.assertEqual(out["repair"]["amendments"]["accepted"], ["ci/LTC.json"])

    def test_a_cloud_repair_keeps_a_test_the_lock_does_not_hold(self):
        # parity with local agents: a test file added after the lock is not locked acceptance
        added = f"runs/kit/{REQ}/test/test_reconciled.py"
        out, _sent, _gen = self._run([
            {"path": f"runs/kit/{REQ}/src/app.py", "content": "def f():\n    return 1\n"},
            {"path": added, "content": "from app import f\n\ndef test_g():\n    assert f() == 1\n"},
        ])
        self.assertIn(added, [f["path"] for f in out["files"]])
        self.assertEqual(out["repair"]["amendments"]["unlocked"], ["test/test_reconciled.py"])
        self.assertFalse(any(w.startswith("repair_change_rejected:test/test_reconciled.py") for w in out["warnings"]))


if __name__ == "__main__":
    unittest.main()


def test_kit_options_accept_bmad_flag_and_auto_eval_request():
    from schemas.harper import HarperKitOptions

    assert HarperKitOptions().repair is None
    assert HarperKitOptions(repair=True).repair is True
    request = {"cycle": 1, "max_cycles": 2, "failures": [], "files": []}
    assert HarperKitOptions(repair=request).repair == request


def test_repair_prompt_shows_code_first_and_lists_clike_context_files():
    """A big KIT: the files named in the failures, tests and sources are shown before docs; CLike's
    context files and lockfiles (often > the whole budget) are listed, never shown."""
    from services.cloud_prompt.messages import _kit_repair_section

    kit = f"runs/kit/{REQ}"
    files = [
        {"path": f"{kit}/ci/package-lock.json", "content": "L" * 90000},
        {"path": f"{kit}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json", "content": "C" * 97000},
        {"path": f"{kit}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md", "content": "C" * 88000},
        {"path": f"{kit}/docs/NOTES.md", "content": "notes"},
        {"path": f"{kit}/src/web/features/runs/RunMonitor.tsx", "content": "export function RunMonitor() {}"},
        {"path": f"{kit}/src/web/lib/api.ts", "content": "export const api = 1;"},
        {"path": f"{kit}/test/runs.states.test.tsx", "content": "it('renders', () => {});"},
    ]
    repair = {"cycle": 1, "max_cycles": 3, "files": files, "failures": [{
        "name": "test:unit", "code": 1, "command": "node ci/check.mjs unit",
        "output": "FAIL test/runs.states.test.tsx\n ❯ src/web/features/runs/RunMonitor.tsx:40:3",
    }]}
    text = _kit_repair_section(repair, REQ)
    order = [text.index(f"#### {kit}/{rel}") for rel in (
        "test/runs.states.test.tsx", "src/web/features/runs/RunMonitor.tsx", "src/web/lib/api.ts", "docs/NOTES.md")]
    assert order[1] < order[2] < order[3] and order[0] < order[2]
    assert "CCCC" not in text and "LLLL" not in text
    assert f"- {kit}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json" in text
    assert "group them by root cause" in text


def test_agent_repair_prompt_keeps_the_errors_and_offers_the_sandbox_re_run():
    from services.local_agent.common import _kit_repair_context
    from services.local_agent.kit import _kit_stage

    excerpt = "FAIL test/a.test.ts > x\nAssertionError: expected 1 to be 2\n ❯ test/a.test.ts:7:3\n" + "y" * 3000
    payload = {"kit": {"repair": {"cycle": 2, "max_cycles": 3, "eval_check": True, "failures": [
        {"name": "test:unit", "code": 1, "command": "node ci/check.mjs unit", "output": excerpt},
        {"name": "regression::REQ-000::lint", "code": 1, "command": "x", "output": "E1"},
    ]}}}
    _stage, _title, rules = _kit_stage(REQ, payload, _kit_repair_context(REQ, payload))
    text = "\n".join(rules)
    assert "AssertionError: expected 1 to be 2\n ❯ test/a.test.ts:7:3" in text  # lines kept, start kept
    assert "y" * 3000 in text
    assert "`node .clike/bin/eval-check.mjs test:unit`" in text  # regression checks are not re-run by name
    without = {"kit": {"repair": {**payload["kit"]["repair"], "eval_check": False}}}
    assert "eval-check" not in "\n".join(_kit_stage(REQ, without, _kit_repair_context(REQ, without))[2])
