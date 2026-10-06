"""Gate integrity regression suite (WP6): acceptance lock, tamper detection, audited override."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.testclient import TestClient  # noqa: E402

TOKEN = "i" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}
REQ = "REQ-001"
LTC = {
    "req_id": REQ,
    "checks": [
        {"id": "unit", "command": "python3 test/test_app.py", "blocking": True},
        {"id": "lint", "command": "true", "blocking": True},
    ],
}
TEST_PY = "import sys\nassert 1 + 1 == 2\nprint('ok')\n"


class GateIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-integrity-")).resolve()
        cls.projects = cls.tmp / "projects"
        cls.projects.mkdir()
        cls.state = cls.tmp / "state"
        cls._env = patch.dict(
            os.environ,
            {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(cls.projects), "CLIKE_STATE_DIR": str(cls.state)},
        )
        cls._env.start()
        from app import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8080")

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.proj = self.projects / f"p{self._testMethodName[-24:]}"
        kit = self.proj / "runs" / "kit" / REQ
        (kit / "ci").mkdir(parents=True)
        (kit / "test").mkdir()
        (kit / "src").mkdir()
        (kit / "ci" / "LTC.json").write_text(json.dumps(LTC))
        (kit / "test" / "test_app.py").write_text(TEST_PY)
        self.kit = kit

    # helpers
    def _eval(self):
        return self.client.post(
            "/v1/eval/run",
            params={"profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ},
            headers=AUTH,
        )

    def _gate(self, **params):
        return self.client.post(
            "/v1/gate/check",
            params={"profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ, **params},
            headers=AUTH,
        )

    def _anomaly_kinds(self, response):
        return {a["kind"] for a in (response.json().get("integrity") or {}).get("anomalies", [])}

    # tests
    def test_unchanged_surface_runs_and_reports_integrity(self):
        r = self._eval()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["integrity"]["ok"])
        g = self._gate()
        self.assertEqual(g.json()["gate"], "PASS", g.text)
        self.assertEqual(g.json()["reason_code"], "GATE_PASS")
        self.assertTrue(g.json()["integrity"]["ok"])

    def test_modified_test_blocks_the_gate_without_running(self):
        self._eval()
        (self.kit / "test" / "test_app.py").write_text(TEST_PY.replace("== 2", "== 2 or True"))
        g = self._gate()
        body = g.json()
        self.assertEqual(body["gate"], "FAIL")
        self.assertEqual(body["reason_code"], "GATE_BLOCKED_ACCEPTANCE_TAMPERED")
        self.assertEqual(body["raw_eval_status"], "NOT_RUN")
        self.assertEqual(self._anomaly_kinds(g), {"modified"})

    def test_removed_test_is_detected(self):
        self._eval()
        (self.kit / "test" / "test_app.py").unlink()
        self.assertEqual(self._anomaly_kinds(self._gate()), {"removed"})

    def test_ltc_check_removed_or_made_non_blocking_is_weakening(self):
        self._eval()
        weakened = {"req_id": REQ, "checks": [{"id": "unit", "command": "python3 test/test_app.py", "blocking": False}]}
        (self.kit / "ci" / "LTC.json").write_text(json.dumps(weakened))
        g = self._gate()
        anomalies = g.json()["integrity"]["anomalies"]
        self.assertEqual(anomalies[0]["kind"], "weakened")
        details = " ".join(anomalies[0]["details"])
        self.assertIn("check removed: lint", details)
        self.assertIn("check made non-blocking: unit", details)

    def test_skip_marker_added_is_detected(self):
        self._eval()
        (self.kit / "test" / "test_app.py").write_text("import pytest\n@pytest.mark.skip\n" + TEST_PY)
        self.assertEqual(self._anomaly_kinds(self._gate()), {"skip_added"})

    def test_added_files_do_not_block(self):
        self._eval()
        (self.kit / "test" / "test_extra.py").write_text("print('more tests')\n")
        g = self._gate()
        self.assertEqual(g.json()["gate"], "PASS", g.text)
        self.assertIn("test/test_extra.py", g.json()["integrity"]["added"])

    def test_source_changes_are_allowed(self):
        self._eval()
        (self.kit / "src" / "app.py").write_text("print('fixed')\n")
        self.assertEqual(self._gate().json()["gate"], "PASS")

    def test_new_kit_generation_rebaselines_the_lock(self):
        from services import harper

        self._eval()
        (self.kit / "test" / "test_app.py").write_text(TEST_PY + "# regenerated by /kit\n")
        payload = {"repository_context": {"workspace_folder": str(self.proj)}}
        harper._acceptance_hook(payload, "kit", REQ)
        self.assertEqual(self._gate().json()["gate"], "PASS")

    def test_eval_prepass_cannot_weaken_tests_after_the_lock(self):
        """/eval locks before the local-agent pre-pass; edits made by the pre-pass are caught."""
        from services import harper

        payload = {"repository_context": {"workspace_folder": str(self.proj)}}
        harper._acceptance_hook(payload, "eval", REQ)  # orchestrator builds the pre-pass package
        (self.kit / "test" / "test_app.py").write_text("print('always green')\n")  # agent weakens the test
        r = self._eval()  # canonical eval
        self.assertEqual(r.json()["reason_code"], "ACCEPTANCE_TAMPERED")
        self.assertFalse(r.json()["promotable"])

    def test_manual_verdict_is_not_accepted_on_gate_check(self):
        g = self._gate(mode="manual", verdict="pass")  # query
        self.assertEqual(g.status_code, 400)
        self.assertIn("/v1/gate/override", g.text)
        body = self.client.post(  # body, as the extension sends it
            "/v1/gate/check",
            params={"profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ},
            json={"mode": "manual", "verdict": "pass"},
            headers=AUTH,
        )
        self.assertEqual(body.status_code, 400)

    def test_override_requires_a_reason_and_is_audited(self):
        short = self.client.post(
            "/v1/gate/override", json={"project_root": str(self.proj), "req_id": REQ, "reason": "ok"}, headers=AUTH
        )
        self.assertEqual(short.status_code, 422)
        r = self.client.post(
            "/v1/gate/override",
            json={"project_root": str(self.proj), "req_id": REQ, "reason": "flaky infra check, verified by hand", "author": "dev"},
            headers=AUTH,
        )
        body = r.json()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((body["gate"], body["status"], body["reason_code"]), ("pass", "OVERRIDE", "GATE_MANUAL_OVERRIDE"))
        self.assertFalse(body["passed"])
        audit = (self.state / "audit" / "gate_overrides.jsonl").read_text().strip().splitlines()
        entry = json.loads(audit[-1])
        self.assertEqual(entry["audit_id"], body["override"]["audit_id"])
        self.assertEqual(entry["author"], "dev")
        self.assertEqual(entry["artifacts"]["files"], 2)
        self.assertEqual(len(entry["artifacts"]["sha256"]), 64)

    def test_override_is_confined(self):
        r = self.client.post(
            "/v1/gate/override",
            json={"project_root": str(self.tmp), "req_id": REQ, "reason": "outside the projects dir"},
            headers=AUTH,
        )
        self.assertEqual(r.status_code, 403)
        r = self.client.post(
            "/v1/gate/override",
            json={"project_root": str(self.proj), "req_id": "../REQ-1", "reason": "bad req id value"},
            headers=AUTH,
        )
        self.assertEqual(r.status_code, 400)

    def test_state_lives_outside_the_workspace(self):
        self._eval()
        self.assertFalse(any(p.name.endswith(".lock.json") for p in self.proj.rglob("*")))
        self.assertTrue(any(self.state.rglob(f"{REQ}.lock.json")))

    # --- auto-eval amendments ------------------------------------------------------
    def test_repair_can_fix_an_ltc_command_and_the_next_eval_is_clean(self):
        from services import gate_integrity

        self.assertEqual(self._eval().status_code, 200)  # takes the lock
        fixed = {**LTC, "checks": [{"id": "unit", "command": "python3 test/test_app.py -v", "blocking": True}, LTC["checks"][1]]}
        text = json.dumps(fixed)
        result = gate_integrity.amend_acceptance_surface(self.proj, REQ, {"ci/LTC.json": text}, reason="command path")
        self.assertEqual((result["accepted"], result["rejected"]), (["ci/LTC.json"], {}))
        (self.kit / "ci" / "LTC.json").write_text(text)
        self.assertNotIn("modified", self._anomaly_kinds(self._eval()))
        audit = (self.state / "audit" / "acceptance_amendments.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(audit[-1])["files"], ["ci/LTC.json"])

    def test_repair_cannot_weaken_the_ltc_or_touch_tests(self):
        from services import gate_integrity

        self._eval()
        weaker = {**LTC, "checks": [{"id": "unit", "command": "true", "blocking": False}]}
        result = gate_integrity.amend_acceptance_surface(
            self.proj, REQ, {"ci/LTC.json": json.dumps(weaker), "test/test_app.py": "pass\n"}, reason="x")
        self.assertEqual(result["accepted"], [])
        self.assertIn("check removed: lint", result["rejected"]["ci/LTC.json"])
        self.assertIn("check made non-blocking: unit", result["rejected"]["ci/LTC.json"])
        self.assertIn("test/test_app.py", result["rejected"])

    def test_repair_may_only_drop_imports_from_a_locked_test(self):
        from services import gate_integrity

        (self.kit / "test" / "test_app.py").write_text("import os\nimport sys\n" + TEST_PY)
        self._eval()
        cases = {
            "adds an import": ("import os\nimport sys\nimport json\n" + TEST_PY, False),
            "changes an assertion": ("import sys\n" + TEST_PY.replace("== 2", "== 2 or True"), False),
            "drops an unused import": ("import sys\n" + TEST_PY, True),  # last: it updates the lock
        }
        for label, (content, ok) in cases.items():
            with self.subTest(label):
                result = gate_integrity.amend_acceptance_surface(
                    self.proj, REQ, {"test/test_app.py": content}, reason="lint")
                self.assertEqual(result["accepted"] == ["test/test_app.py"], ok, result)

        # The accepted cleanup is part of the lock: the next eval is clean once it is written.
        (self.kit / "test" / "test_app.py").write_text("import sys\n" + TEST_PY)
        self.assertEqual(self._anomaly_kinds(self._eval()), set())

    def test_a_test_shown_wrong_by_the_eval_is_fixed_with_its_assertions_unchanged(self):
        from services import gate_integrity

        broken = (
            "import pytest\n\n"
            "def test_delete(client):\n"
            "    response = client.delete('/x', content='{}')\n"
            "    assert response.status_code == 405\n"
            "    with pytest.raises(ValueError):\n"
            "        int('x')\n"
        )
        (self.kit / "test" / "test_api.py").write_text(broken)
        self._eval()
        fixed = broken.replace("client.delete('/x', content='{}')", "client.request('DELETE', '/x', content='{}')")
        evidence = "FAILED test/test_api.py::test_delete\ntest/test_api.py:4: TypeError"
        amend = gate_integrity.amend_acceptance_surface

        cases = {
            "no evidence of a test error": (fixed, "test/test_api.py:4: AssertionError", "does not show an error"),
            "assertion weakened": (fixed.replace("== 405", "in (200, 405)"), evidence, "assertion identical"),
            "raises loosened": (fixed.replace("ValueError", "Exception"), evidence, "assertion identical"),
            "skip added": (fixed.replace("def test_delete", "@pytest.mark.skip\ndef test_delete"), evidence, "skip"),
        }
        for label, (content, proof, issue) in cases.items():
            with self.subTest(label):
                result = amend(self.proj, REQ, {"test/test_api.py": content}, reason="r", evidence=proof)
                self.assertEqual(result["accepted"], [])
                self.assertIn(issue, result["rejected"]["test/test_api.py"][0])

        result = amend(self.proj, REQ, {"test/test_api.py": fixed}, reason="r", evidence=evidence)
        self.assertEqual((result["accepted"], result["test_fixes"]), (["test/test_api.py"], ["test/test_api.py"]))

        (self.kit / "test" / "test_api.py").write_text(fixed)
        gate = self._gate().json()
        self.assertTrue(gate["review_required"])
        self.assertEqual(gate["acceptance_amendments"][-1]["kinds"], {"test/test_api.py": "test_fix"})

    def test_local_agent_repair_is_governed_through_the_amend_endpoint(self):
        # The agent already wrote its changes: the extension sends them with the previous content.
        self._eval()
        before_test = (self.kit / "test" / "test_app.py").read_text()
        before_ltc = (self.kit / "ci" / "LTC.json").read_text()
        fixed_ltc = json.dumps({**LTC, "checks": [{**LTC["checks"][0], "command": "python3 test/test_app.py -v"}, LTC["checks"][1]]})
        (self.kit / "test" / "test_app.py").write_text("pass\n")
        (self.kit / "ci" / "LTC.json").write_text(fixed_ltc)
        body = {
            "project_root": str(self.proj), "req_id": REQ,
            "changes": {"test/test_app.py": "pass\n", "ci/LTC.json": fixed_ltc},
            "previous": {"test/test_app.py": before_test, "ci/LTC.json": before_ltc},
            "evidence": "unit failed",
        }
        result = self.client.post("/v1/acceptance/amend", json=body, headers=AUTH).json()
        self.assertEqual(result["accepted"], ["ci/LTC.json"])
        self.assertIn("test/test_app.py", result["rejected"])

        # The extension restores the rejected test: the next eval is clean, with the amended LTC.
        (self.kit / "test" / "test_app.py").write_text(before_test)
        self.assertEqual(self._anomaly_kinds(self._eval()), set())

        # Re-submitting accepted content is a no-op; a forged "previous" is not trusted.
        again = self.client.post("/v1/acceptance/amend", json={**body, "changes": {"ci/LTC.json": fixed_ltc}}, headers=AUTH).json()
        self.assertEqual((again["accepted"], again["rejected"]), ([], {}))
        forged = {**body, "changes": {"test/test_app.py": "import os\n" + TEST_PY}, "previous": {"test/test_app.py": "import os\nimport sys\n" + TEST_PY}}
        self.assertIn("test/test_app.py", self.client.post("/v1/acceptance/amend", json=forged, headers=AUTH).json()["rejected"])

    def test_amend_endpoint_is_confined(self):
        body = {"project_root": "/etc", "req_id": REQ, "changes": {"ci/LTC.json": "{}"}}
        self.assertIn(self.client.post("/v1/acceptance/amend", json=body, headers=AUTH).status_code, (400, 403))

    def test_repair_can_upgrade_ci_requirements(self):
        from services import gate_integrity

        (self.kit / "ci" / "requirements.txt").write_text("fastapi==0.1\n")
        self._eval()
        result = gate_integrity.amend_acceptance_surface(self.proj, REQ, {"ci/requirements.txt": "fastapi==0.115.0\n"}, reason="CVE")
        self.assertEqual(result["accepted"], ["ci/requirements.txt"])
        (self.kit / "ci" / "requirements.txt").write_text("fastapi==0.115.0\n")
        self.assertNotIn("modified", self._anomaly_kinds(self._eval()))


if __name__ == "__main__":
    unittest.main()
