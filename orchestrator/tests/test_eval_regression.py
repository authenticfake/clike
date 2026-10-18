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


class _RegressionProject(unittest.TestCase):
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

class EvalRegressionTests(_RegressionProject):
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

    def test_application_factory_is_a_launcher_and_eval_reports_missing_ones(self):
        kit = self.proj / "runs" / "kit" / "REQ-003"
        requirements = {"required_outputs": [{"role": "module_launcher", "required": True}]}
        (kit / "ci" / "FILE_REQUIREMENTS.json").write_text(json.dumps(requirements))

        evaluated = self._post("/v1/eval/run", "REQ-003").json()
        self.assertEqual(evaluated["status"], "FAIL")
        self.assertIn("structure::module_launcher", evaluated["blocking_failures"])
        case = next(c for c in evaluated["cases"] if c["name"] == "structure::module_launcher")
        self.assertIn("Accepted:", case["stderr"])

        (kit / "src" / "application.py").write_text("from fastapi import FastAPI\n\ndef create_app():\n    return FastAPI()\n")
        self.assertEqual(self._post("/v1/eval/run", "REQ-003").json()["status"], "PASS")

    def test_only_test_checks_of_a_promoted_req_block_as_regression(self):
        from eval_runner import EvalCase, _is_regression_test_case

        def case(name, out, passed=False):
            return EvalCase(name=name, passed=passed, code=1, stdout=out, stderr="")

        self.assertTrue(_is_regression_test_case(case("unit-tests", "1 failed, 3 passed")))
        self.assertFalse(_is_regression_test_case(case("lint", "E501")))
        self.assertFalse(_is_regression_test_case(case("types", "error: x")))
        self.assertFalse(_is_regression_test_case(
            case("tests", "FAIL Required test coverage of 85% not reached. Total coverage: 63.16%\n73 passed in 3s")))
        self.assertTrue(_is_regression_test_case(
            case("tests", "FAILED test_a.py::t\nFAIL Required test coverage of 85% not reached.\n1 failed, 2 passed")))


if __name__ == "__main__":
    unittest.main()


class PromotedKitCompositionTests(_RegressionProject):
    """A promoted KIT is already in the canonical tree, merged with what later REQs changed: its
    stale KIT copy must not shadow the canonical files, neither as a dependency nor in its own
    regression run."""

    def setUp(self):
        super().setUp()
        plan = json.loads((self.proj / "docs" / "harper" / "plan.json").read_text())
        plan["reqs"].append({"id": "REQ-004", "status": "done", "dependsOn": ["REQ-001"]})
        (self.proj / "docs" / "harper" / "plan.json").write_text(json.dumps(plan))
        # REQ-004, promoted after REQ-001, added discount() to pricing.py in the canonical tree.
        self._kit("REQ-004", "pricing", "def price():\n    return 10\n\ndef discount():\n    return 1\n",
                  "from pricing import discount\nassert discount() == 1\n", ltc=_ltc("REQ-004", "pricing"))
        (self.proj / "src").mkdir(exist_ok=True)
        (self.proj / "src" / "pricing.py").write_text("def price():\n    return 10\n\ndef discount():\n    return 1\n")
        # REQ-002 (depends on REQ-001) uses the canonical discount().
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "checkout.py").write_text("from pricing import price, discount\n\ndef total(n):\n    return n * price() - discount()\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 19\n")

    def _promoted(self, *req_ids):
        for req_id in req_ids:
            report = self.proj / "runs" / "kit" / req_id / "promotion" / "2026-10-15T00-00-00-000Z" / "report.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"req_id": req_id, "promoted": True}))

    def test_a_promoted_dependency_kit_does_not_shadow_the_canonical_tree(self):
        self._promoted("REQ-001", "REQ-004")
        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "PASS", [(c["name"], c.get("stderr", "")[-300:]) for c in body["cases"] if not c["passed"]])
        self.assertIn("regression::REQ-001::unit", [c["name"] for c in body["cases"]])
        self.assertIn("regression::REQ-004::unit", [c["name"] for c in body["cases"]])

    def test_without_a_promotion_record_the_kit_is_still_composed(self):
        # done but never auto-merged (e.g. an older strategy): the KIT stays the source of truth,
        # so REQ-001's pricing.py (no discount) wins over the canonical one, as before.
        body = self._post("/v1/eval/run", "REQ-002").json()
        self.assertEqual(body["status"], "FAIL")


class DeclaredChangeRegressionTests(_RegressionProject):
    """/idea --extend: a MODIFIED REQ supersedes checks of the REQ it amends; a REMOVED REQ retires one."""

    def _declare(self, **fields):
        plan_path = self.proj / "docs" / "harper" / "plan.json"
        plan = json.loads(plan_path.read_text())
        plan["reqs"][1].update(fields)
        plan_path.write_text(json.dumps(plan))

    def test_a_declared_change_replaces_exactly_the_superseded_checks(self):
        # REQ-002 changes the price on purpose and declares it: REQ-001's unit check is superseded.
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"],
                      supersedes=[{"check": "REQ-001#unit", "reason": "price list v2"}])

        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "PASS", evaluated)
        names = [c["name"] for c in evaluated["cases"]]
        self.assertIn("regression::REQ-001::unit::superseded", names)
        self.assertNotIn("regression::REQ-001::unit", names)
        note = next(c for c in evaluated["cases"] if c["name"].endswith("::superseded"))
        self.assertIn("REQ-002: price list v2", note["stdout"])
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        self.assertEqual(gate["gate"], "PASS", gate)

    def test_an_undeclared_change_still_fails(self):
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"], supersedes=[{"check": "REQ-001#lint", "reason": "x"}])
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "FAIL")
        self.assertIn("regression::REQ-001::unit", evaluated["blocking_failures"])

    def test_a_retired_req_leaves_the_regression_set(self):
        from eval_runner import EvalRunner

        self._declare(change="REMOVED", retires=["REQ-001"])
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-002"), [])
        # another candidate still regresses REQ-001 until REQ-002 is promoted
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-003"), ["REQ-001"])
