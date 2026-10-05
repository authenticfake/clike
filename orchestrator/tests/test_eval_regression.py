"""Auto-eval L2: regression of dependency and promoted REQs, and the gate warnings policy."""

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

TOKEN = "r" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}
UNIT = "PYTHONPATH=src python3 test/test_{name}.py"


def _ltc(req_id, name, *, extra_checks=()):
    checks = [{"id": "unit", "command": UNIT.format(name=name), "blocking": True}, *extra_checks]
    return {"req_id": req_id, "run_from": f"runs/kit/{req_id}", "checks": checks}


class EvalRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-regression-")).resolve()
        cls.projects = cls.tmp / "projects"
        cls.projects.mkdir()
        cls._env = patch.dict(
            os.environ,
            {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(cls.projects), "CLIKE_STATE_DIR": str(cls.tmp / "state")},
        )
        cls._env.start()
        os.environ.pop("CLIKE_EVAL_SANDBOX_URL", None)
        os.environ.pop("CLIKE_GATE_STRICT_WARNINGS", None)
        from app import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8080")

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # REQ-001 (promoted) provides pricing.price(); REQ-002 depends on it; REQ-003 is unrelated and open.
        self.proj = self.projects / f"p{self._testMethodName[-24:]}"
        plan = {
            "reqs": [
                {"id": "REQ-001", "status": "done", "dependsOn": []},
                {"id": "REQ-002", "status": "open", "dependsOn": ["REQ-001"]},
                {"id": "REQ-003", "status": "open", "dependsOn": []},
            ]
        }
        (self.proj / "docs" / "harper").mkdir(parents=True)
        (self.proj / "docs" / "harper" / "plan.json").write_text(json.dumps(plan))
        self._kit("REQ-001", "pricing", "def price():\n    return 10\n",
                  "from pricing import price\nassert price() == 10\n")
        self._kit("REQ-002", "checkout", "from pricing import price\n\ndef total(n):\n    return n * price()\n",
                  "from checkout import total\nassert total(2) == 20\n")
        self._kit("REQ-003", "other", "VALUE = 1\n", "from other import VALUE\nassert VALUE == 1\n")

    def _kit(self, req_id, name, src, test, ltc=None):
        kit = self.proj / "runs" / "kit" / req_id
        for sub in ("ci", "src", "test"):
            (kit / sub).mkdir(parents=True, exist_ok=True)
        (kit / "src" / f"{name}.py").write_text(src)
        (kit / "test" / f"test_{name}.py").write_text(test)
        (kit / "ci" / "LTC.json").write_text(json.dumps(ltc or _ltc(req_id, name)))
        return kit

    def _post(self, route, req_id, **body):
        return self.client.post(
            route,
            json={"profile": f"runs/kit/{req_id}/ci/LTC.json", "project_root": str(self.proj), "req_id": req_id, **body},
            headers=AUTH,
        )

    def _case_names(self, response):
        return [c["name"] for c in response.json()["cases"]]

    def test_regression_set_is_the_promoted_reqs(self):
        from eval_runner import EvalRunner

        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-002"), ["REQ-001"])
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-003"), ["REQ-001"])
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-001"), [])

        # A dependency that is not promoted is not a regression target.
        plan_path = self.proj / "docs" / "harper" / "plan.json"
        plan = json.loads(plan_path.read_text())
        plan["reqs"][0]["status"] = "open"
        plan_path.write_text(json.dumps(plan))
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-002"), [])

    def test_regression_is_opt_in(self):
        response = self._post("/v1/eval/run", "REQ-002")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(any(n.startswith("regression::") for n in self._case_names(response)))

    def test_compatible_candidate_passes_with_the_promoted_checks(self):
        response = self._post("/v1/eval/run", "REQ-002", regression=True)
        body = response.json()
        self.assertEqual(body["status"], "PASS", body)
        self.assertIn("regression::REQ-001::unit", self._case_names(response))
        self.assertTrue(body["regression"])

    def test_candidate_breaking_a_promoted_req_fails_the_eval_and_the_gate(self):
        # REQ-002 rewrites pricing.price(): its own test passes, REQ-001's acceptance test does not.
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")

        own = self._post("/v1/eval/run", "REQ-002")
        self.assertEqual(own.json()["status"], "PASS", own.json())

        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "FAIL")
        self.assertIn("regression::REQ-001::unit", evaluated["blocking_failures"])

        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        self.assertEqual(gate["gate"], "FAIL")
        self.assertEqual(gate["reason_code"], "GATE_BLOCKED_REGRESSION")
        self.assertEqual(gate["regression_failures"], ["regression::REQ-001::unit"])

    def test_regression_does_not_overwrite_the_promoted_req_eval(self):
        self._post("/v1/eval/run", "REQ-002", regression=True)
        base = self.proj / "runs" / "eval"
        self.assertTrue((base / "REQ-002" / "regression" / "REQ-001").is_dir())
        self.assertFalse((base / "REQ-001").exists())

    def test_warnings_do_not_block_the_gate_unless_strict(self):
        ltc = _ltc("REQ-003", "other", extra_checks=[{"id": "style", "command": "false", "blocking": False}])
        self._kit("REQ-003", "other", "VALUE = 1\n", "from other import VALUE\nassert VALUE == 1\n", ltc=ltc)

        relaxed = self._post("/v1/gate/check", "REQ-003").json()
        self.assertEqual((relaxed["gate"], relaxed["reason_code"]), ("PASS", "GATE_PASS_WITH_WARNINGS"))
        self.assertEqual(relaxed["warning_count"], 1)

        strict = self._post("/v1/gate/check", "REQ-003", strict=True).json()
        self.assertEqual((strict["gate"], strict["reason_code"]), ("FAIL", "GATE_BLOCKED_WARNINGS_PRESENT"))

        with patch.dict(os.environ, {"CLIKE_GATE_STRICT_WARNINGS": "1"}):
            self.assertEqual(self._post("/v1/gate/check", "REQ-003").json()["gate"], "FAIL")

    def test_python_package_launcher_satisfies_the_module_launcher_requirement(self):
        from routes.routes_eval import _required_output_blockers

        kit = self.proj / "runs" / "kit" / "REQ-003"
        requirements = {"required_outputs": [{"role": "module_launcher", "required": True}]}
        (kit / "ci" / "FILE_REQUIREMENTS.json").write_text(json.dumps(requirements))
        self.assertEqual([b["role"] for b in _required_output_blockers(self.proj, "REQ-003")], ["module_launcher"])

        (kit / "src" / "other_cli").mkdir()
        (kit / "src" / "other_cli" / "__main__.py").write_text("print('run')\n")
        self.assertEqual(_required_output_blockers(self.proj, "REQ-003"), [])


if __name__ == "__main__":
    unittest.main()
