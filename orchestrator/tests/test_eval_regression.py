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
    def test_an_agent_eval_check_can_re_run_a_promoted_reqs_regression(self):
        # eval-check while repairing: some checks of the REQ and the regression of one promoted REQ
        own = [c["name"] for c in self._post("/v1/eval/run", "REQ-002").json()["cases"] if not c["name"].startswith(("env::", "structure::"))]
        body = self._post("/v1/eval/run", "REQ-002", regression=True, checks=own[:1], regression_reqs=["REQ-001"]).json()
        names = [c["name"] for c in body["cases"]]
        self.assertTrue(any(n.startswith("regression::REQ-001::") for n in names), names)
        self.assertTrue(body["partial"])
        self.assertFalse(body["promotable"])
        self.assertEqual(body["regression_scope"], ["REQ-001"])
        # a check subset alone still runs no regression
        only = self._post("/v1/eval/run", "REQ-002", regression=True, checks=own[:1]).json()
        self.assertFalse(any(c["name"].startswith("regression::") for c in only["cases"]))

    def test_the_full_eval_after_a_passing_targeted_one_reuses_what_ran_on_the_same_inputs(self):
        # B2B REQ-032: the confirmation eval re-ran ~7 of its ~28 minutes exactly as the targeted
        # re-eval had just run them (the REQ's checks, the regression of REQ-008 and REQ-014)
        plan_path = self.proj / "docs" / "harper" / "plan.json"
        plan = json.loads(plan_path.read_text())
        plan["reqs"][2]["status"] = "done"  # REQ-003 promoted too: one REQ reused, one run
        plan_path.write_text(json.dumps(plan))
        reused = "Reused: same inputs as the targeted re-eval"
        targeted = self._post("/v1/eval/run", "REQ-002", regression=True, regression_reqs=["REQ-001"]).json()
        self.assertTrue(targeted["partial"])
        self.assertIn(targeted["status"], ("PASS", "PASS_WITH_WARNINGS"))
        full = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertIn(full["status"], ("PASS", "PASS_WITH_WARNINGS"))
        self.assertNotIn("partial", full)
        self.assertIn("reused_targeted_at", full)
        by = {c["name"]: c for c in full["cases"]}
        own = [n for n in by if not n.startswith(("regression::", "env::", "structure::", "ltc::"))]
        self.assertTrue(own and all(reused in by[n]["stdout"] for n in own), own)
        req1 = [n for n in by if n.startswith("regression::REQ-001::") and "::env::" not in n]
        req3 = [n for n in by if n.startswith("regression::REQ-003::")]
        self.assertTrue(req1 and all(reused in by[n]["stdout"] for n in req1), req1)
        self.assertTrue(req3 and not any(reused in by[n]["stdout"] for n in req3), req3)
        # the inputs change: nothing is reused
        (self.proj / "runs" / "kit" / "REQ-002" / "src" / "checkout.py").write_text(
            "from pricing import price\n\ndef total(n):\n    return n * price()  # changed\n")
        again = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertNotIn("reused_targeted_at", again)
        self.assertFalse(any(reused in c["stdout"] for c in again["cases"]))

    def test_a_targeted_re_eval_regresses_only_the_named_reqs_and_is_never_a_verdict(self):
        # a repair loop re-evaluates the REQs that failed before the repair; the full eval decides
        full = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertTrue(any(n.startswith("regression::REQ-001::") for n in [c["name"] for c in full["cases"]]))
        self.assertNotIn("partial", full)
        other = self._post("/v1/eval/run", "REQ-002", regression=True, regression_reqs=["REQ-999"]).json()
        self.assertFalse(any(c["name"].startswith("regression::REQ-001::") for c in other["cases"]))
        self.assertTrue(other["partial"])
        self.assertFalse(other["promotable"])
        self.assertEqual(other["regression_scope"], ["REQ-999"])
        named = self._post("/v1/eval/run", "REQ-002", regression=True, regression_reqs=["req-001"]).json()
        self.assertTrue(any(c["name"].startswith("regression::REQ-001::") for c in named["cases"]))
        self.assertTrue(named["partial"])

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

    def test_a_promoted_check_already_failing_without_the_candidate_does_not_block(self):
        # REQ-001's check fails on the promoted tree alone (its environment needs a variable nobody
        # sets any more): REQ-002 did not cause it, so it is a warning naming REQ-001.
        ltc = {"req_id": "REQ-001", "run_from": "runs/kit/REQ-001",
               "checks": [{"id": "unit", "command": 'test -n "$REQ001_STALE_SETTING"', "blocking": True}]}
        (self.proj / "runs" / "kit" / "REQ-001" / "ci" / "LTC.json").write_text(json.dumps(ltc))

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "PASS_WITH_WARNINGS", body)
        case = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["passed"])
        self.assertFalse(case["blocking"])
        self.assertIn("Already failing without this candidate", case["stderr"])

    def test_a_test_reconciled_in_the_candidate_is_the_one_the_regression_runs(self):
        # REQ-002 changes price() on purpose and reconciles REQ-001's test in its own test root: the
        # regression runs that version (what promotion delivers) and names it as a warning.
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        (kit / "test" / "test_pricing.py").write_text("from pricing import price\nassert price() == 12\n")

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "PASS_WITH_WARNINGS", body)
        self.assertIn("regression::REQ-001::unit", [c["name"] for c in body["cases"] if c["passed"]])
        audit = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::reconciled-tests")
        self.assertFalse(audit["passed"])
        self.assertFalse(audit["blocking"])
        self.assertIn("test/test_pricing.py", audit["stdout"])
        # the candidate's own tests are not added to the regressed REQ's checks
        self.assertNotIn("test_checkout.py", audit["stdout"])

    def test_a_reconciled_test_gets_the_candidate_support_files_next_to_it(self):
        # The reconciled test imports a helper the candidate added beside it: the helper comes too,
        # a new test of the candidate in the same directory does not.
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        (kit / "test" / "expected.py").write_text("PRICE = 12\n")
        (kit / "test" / "test_extra.py").write_text("def test_never_in_regression():\n    assert False\n")
        (kit / "test" / "test_pricing.py").write_text(
            "import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\n"
            "from expected import PRICE\nfrom pricing import price\nassert price() == PRICE\n"
        )
        # the candidate's conftest for its own tests elsewhere, and a helper nobody imports
        (kit / "test" / "helpers").mkdir()
        (kit / "test" / "helpers" / "conftest.py").write_text("import missing_dependency\n")
        (kit / "test" / "helpers" / "fixtures.py").write_text("PRICE = 12\n")

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "PASS_WITH_WARNINGS", body)
        audit = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::reconciled-tests")
        self.assertIn("test/expected.py", audit["stdout"])
        self.assertNotIn("test_extra.py", audit["stdout"])
        # only what the reconciled test imports: a conftest elsewhere would load into REQ-001's run
        self.assertNotIn("test/helpers/", audit["stdout"])
        work = self.proj / "runs" / "eval" / "REQ-002" / "regression" / "REQ-001" / "work" / "REQ-001" / "test"
        self.assertFalse((work / "test_extra.py").exists())

    def test_a_reconciled_test_in_a_subdirectory_gets_the_helper_at_the_test_root(self):
        # REQ-001's test lives in test/v2; the candidate reconciles it and puts the helper it imports
        # at its test root (on the test path): the helper comes too, the candidate's own test does not.
        promoted = self.proj / "runs" / "kit" / "REQ-001"
        (promoted / "test" / "test_pricing.py").unlink()
        (promoted / "test" / "v2").mkdir()
        (promoted / "test" / "v2" / "test_pricing.py").write_text("from pricing import price\nassert price() == 10\n")
        ltc = {"req_id": "REQ-001", "run_from": "runs/kit/REQ-001",
               "checks": [{"id": "unit", "command": "PYTHONPATH=src:test python3 test/v2/test_pricing.py", "blocking": True}]}
        (promoted / "ci" / "LTC.json").write_text(json.dumps(ltc))
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        (kit / "test" / "req001_support.py").write_text("from req001_values import PRICE\n")
        # a package marker of the candidate named like a source package: importing from the source
        # package does not bring it (it would shadow src/pricing)
        (kit / "test" / "stubs" / "pricing").mkdir(parents=True)
        (kit / "test" / "stubs" / "pricing" / "__init__.py").write_text("")
        (kit / "test" / "v2" / "req001_values.py").parent.mkdir()
        (kit / "test" / "v2" / "req001_values.py").write_text("PRICE = 12\n")
        (kit / "test" / "v2" / "test_pricing.py").write_text(
            "from req001_support import PRICE\nfrom pricing import price\nassert price() == PRICE\n"
        )

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "PASS_WITH_WARNINGS", body)
        audit = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::reconciled-tests")
        self.assertIn("test/req001_support.py", audit["stdout"])
        self.assertNotIn("test/stubs/", audit["stdout"])
        # imported by the helper, not by the test: it comes too
        self.assertIn("test/v2/req001_values.py", audit["stdout"])
        self.assertNotIn("test_checkout.py", audit["stdout"])

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
        # done but never auto-merged and no history to tell which copy is newer: the KIT stays the
        # source of truth, so REQ-001's pricing.py (no discount) wins over the canonical one.
        body = self._post("/v1/eval/run", "REQ-002").json()
        self.assertEqual(body["status"], "FAIL")

    def _git(self, *args, date=None):
        import subprocess

        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", *args], cwd=self.proj, env=env, check=True, capture_output=True)

    def test_without_a_promotion_record_a_canonical_file_changed_later_wins(self):
        # done before promotion records existed: REQ-001's KIT pricing.py was committed first, a later
        # REQ changed the canonical one (discount). The stale KIT copy must not replace it.
        self._git("init", "-q")
        self._git("add", "runs/kit/REQ-001")
        self._git("commit", "-q", "-m", "REQ-001", date="2026-10-01T10:00:00")
        self._git("add", "src")
        self._git("commit", "-q", "-m", "later REQ", date="2026-10-05T10:00:00")
        body = self._post("/v1/eval/run", "REQ-002").json()
        self.assertEqual(body["status"], "PASS", [(c["name"], c.get("stderr", "")[-300:]) for c in body["cases"] if not c["passed"]])

    def test_without_a_promotion_record_a_kit_file_committed_later_still_wins(self):
        # a folder/suffix strategy left the KIT as the source of truth: its file is the newer one
        self._git("init", "-q")
        self._git("add", "src")
        self._git("commit", "-q", "-m", "canonical", date="2026-10-01T10:00:00")
        self._git("add", "runs/kit/REQ-001")
        self._git("commit", "-q", "-m", "REQ-001", date="2026-10-05T10:00:00")
        self.assertEqual(self._post("/v1/eval/run", "REQ-002").json()["status"], "FAIL")


    def test_the_regression_runs_the_promoted_version_of_a_reconciled_test(self):
        # A later REQ changed the price on purpose, reconciled REQ-001's test and promoted both. The
        # next candidate does not carry that test: REQ-001's regression runs the promoted version,
        # not the original in its KIT (which pins the old price).
        self._promoted("REQ-001", "REQ-004")
        self._git("init", "-q")
        self._git("add", "runs/kit")
        self._git("commit", "-q", "-m", "KITs", date="2026-10-01T10:00:00")
        (self.proj / "src" / "pricing.py").write_text("def price():\n    return 12\n\ndef discount():\n    return 1\n")
        (self.proj / "test").mkdir(exist_ok=True)
        (self.proj / "test" / "test_pricing.py").write_text("from pricing import price\nassert price() == 12\n")
        self._git("add", "src", "test")
        self._git("commit", "-q", "-m", "later REQ promoted", date="2026-10-05T10:00:00")
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 23\n")

        # the shared root conftest is merged at promotion: REQ-001 keeps its own
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "conftest.py").write_text("REQ001 = 1\n")
        self._git("add", "runs/kit/REQ-001/test/conftest.py")
        self._git("commit", "-q", "-m", "REQ-001 conftest", date="2026-10-02T10:00:00")
        (self.proj / "test" / "conftest.py").write_text("SHARED = 1\n")
        self._git("add", "test/conftest.py")
        self._git("commit", "-q", "-m", "shared conftest", date="2026-10-06T10:00:00")

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertIn("regression::REQ-001::unit", [c["name"] for c in body["cases"] if c["passed"]], body)
        work = self.proj / "runs" / "eval" / "REQ-002" / "regression" / "REQ-001" / "work" / "REQ-001" / "test"
        self.assertEqual((work / "conftest.py").read_text(), "REQ001 = 1\n")
        self.assertEqual((work / "test_pricing.py").read_text(), "from pricing import price\nassert price() == 12\n")

    def test_the_promoted_version_of_a_test_gets_the_helpers_it_imports(self):
        # the reconciled test promotion delivered imports a helper that sits at the canonical test root
        self._promoted("REQ-001", "REQ-004")
        self._git("init", "-q")
        self._git("add", "runs/kit")
        self._git("commit", "-q", "-m", "KITs", date="2026-10-01T10:00:00")
        (self.proj / "src" / "pricing.py").write_text("def price():\n    return 12\n\ndef discount():\n    return 1\n")
        (self.proj / "test").mkdir(exist_ok=True)
        (self.proj / "test" / "req001_support.py").write_text("PRICE = 12\n")
        (self.proj / "test" / "test_pricing.py").write_text(
            "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n"
            "from req001_support import PRICE\nfrom pricing import price\nassert price() == PRICE\n"
        )
        (self.proj / "test" / "conftest.py").write_text("import missing_module\n")
        self._git("add", "src", "test")
        self._git("commit", "-q", "-m", "later REQ promoted", date="2026-10-05T10:00:00")
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 23\n")

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertIn("regression::REQ-001::unit", [c["name"] for c in body["cases"] if c["passed"]], body)
        work = self.proj / "runs" / "eval" / "REQ-002" / "regression" / "REQ-001" / "work" / "REQ-001" / "test"
        self.assertTrue((work / "req001_support.py").is_file())
        self.assertFalse((work / "conftest.py").exists())  # the shared root conftest is not brought

    def test_a_promoted_req_service_runs_its_promoted_code(self):
        # REQ-002 starts REQ-001 as a service: REQ-001 is promoted and its KIT pricing.py is stale
        from eval_runner import EvalRunner

        self._promoted("REQ-001", "REQ-004")
        runner = EvalRunner(self.proj)
        _workdir, env, _cases = runner._service_runtime(
            {"name": "pricing-api", "req": "REQ-001"}, req_id="REQ-002", env={}, work_kit_root=None
        )
        self.assertIn("discount", (Path(env["SERVICE_SRC_DIR"]) / "pricing.py").read_text())

    def test_a_candidate_file_identical_to_the_promoted_one_reconciles_nothing(self):
        # The candidate carries the promoted test/conftest.py unchanged; REQ-001's own conftest differs.
        # Overlaying it would replace REQ-001's fixtures with a file promotion does not change.
        self._promoted("REQ-001", "REQ-004")
        (self.proj / "test").mkdir(exist_ok=True)
        (self.proj / "test" / "conftest.py").write_text("SHARED = 1\n")
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "conftest.py").write_text("REQ001_FIXTURE = 1\n")
        (self.proj / "runs" / "kit" / "REQ-002" / "test" / "conftest.py").write_text("SHARED = 1\n")

        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertNotIn("regression::REQ-001::reconciled-tests", [c["name"] for c in body["cases"]], body)


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

    def test_a_superseded_check_is_dropped_in_any_section_of_the_ltc(self):
        # B2B: LTCs declare their checks under "commands" too; only "checks" was filtered
        ltc = {"req_id": "REQ-001", "run_from": "runs/kit/REQ-001",
               "commands": [{"id": "unit", "cmd": UNIT.format(name="pricing"), "blocking": True}]}
        (self.proj / "runs" / "kit" / "REQ-001" / "ci" / "LTC.json").write_text(json.dumps(ltc))
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"], supersedes=[{"check": "REQ-001#unit", "reason": "v2"}])
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "PASS", evaluated)
        self.assertNotIn("regression::REQ-001::unit", [c["name"] for c in evaluated["cases"]])

    def _reporting_test(self, names):
        """REQ-001's check reports its failed tests the way a test runner does."""
        lines = "".join(f"    print('FAILED test/test_pricing.py::{n} - AssertionError: assert 12 == 10')\n" for n in names)
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "test_pricing.py").write_text(
            "import sys\nfrom pricing import price\nif price() != 10:\n" + lines + "    sys.exit(1)\n")

    def test_a_superseded_test_does_not_fail_the_regression_wherever_it_runs(self):
        # B2B REQ-037: REQ-016's superseded test ran (and failed) in REQ-014's check; test references
        # REQ-x#path::name were never applied
        self._reporting_test(["test_price"])
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"],
                      supersedes=[{"check": "REQ-001#test/test_pricing.py::test_price", "reason": "price list v2"}])
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "PASS", evaluated)
        case = next(c for c in evaluated["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["blocking"])
        self.assertIn("Superseded tests", case["stderr"])
        self.assertIn("superseded by REQ-002: price list v2", case["stderr"])

    def _amended_failure(self, extra, acceptance=None):
        """REQ-001's test fails the way a runner prints it; REQ-002 amends REQ-001, declares nothing."""
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "test_pricing.py").write_text(
            "import sys\nfrom pricing import price\n\ndef test_price():\n    pass\n\nif price() != 10:\n"
            "    print('FAILED test/test_pricing.py::test_price[eur] - AssertionError: assert {1, 2} == {1}')\n"
            f"    print('{extra}')\n    sys.exit(1)\n")
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"], supersedes=[], **({"acceptance": acceptance} if acceptance else {}))
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "FAIL")
        return next(c for c in evaluated["cases"] if c["name"] == "regression::REQ-001::unit")

    def test_a_pinned_list_the_req_extends_gets_the_declaration(self):
        # B2B REQ-037: a REQ-015 test pinned the exact session fields the release extends
        case = self._amended_failure("Extra items in the left set:")
        self.assertTrue(case["blocking"])
        self.assertIn('/eval REQ-002 --supersede REQ-001#test/test_pricing.py::test_price "', case["stderr"])

    def test_a_broken_guarantee_of_an_amended_req_is_a_regression_not_a_declaration(self):
        # B2B REQ-038: a fixture relabel no longer refused ("DID NOT RAISE") was offered as a supersede
        case = self._amended_failure("Failed: DID NOT RAISE ValidationError")
        self.assertIn("not an extension of what they pin: a regression REQ-002 must fix", case["stderr"])
        self.assertNotIn("--supersede", case["stderr"])

    def test_a_req_that_promises_the_tests_still_hold_gets_no_declaration(self):
        case = self._amended_failure("Extra items in the left set:", acceptance=["REQ-002-A01: existing refusal tests still hold"])
        self.assertNotIn("--supersede", case["stderr"])

    def test_a_check_whose_summary_counts_more_failures_still_fails(self):
        # only the superseded test is named, but the runner reports an error it does not name as a test
        test = self.proj / "runs" / "kit" / "REQ-001" / "test" / "test_pricing.py"
        test.write_text("import sys\nfrom pricing import price\nif price() != 10:\n"
                        "    print('FAILED test/test_pricing.py::test_price - AssertionError')\n"
                        "    print('ERROR collecting test/test_tax.py')\n"
                        "    print('==== 1 failed, 3 passed, 1 error in 0.2s ====')\n    sys.exit(1)\n")
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"],
                      supersedes=[{"check": "REQ-001#test/test_pricing.py::test_price", "reason": "v2"}])
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "FAIL")
        case = next(c for c in evaluated["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertTrue(case["blocking"])

    def test_a_check_with_other_failed_tests_still_fails_and_names_the_superseded_ones(self):
        self._reporting_test(["test_price", "test_rounding"])
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        self._declare(change="MODIFIED", amends=["REQ-001"],
                      supersedes=[{"check": "REQ-001#test/test_pricing.py::test_price", "reason": "v2"}])
        evaluated = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["status"], "FAIL")
        case = next(c for c in evaluated["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertTrue(case["blocking"])
        self.assertIn("leave them as they are", case["stderr"])

    def test_a_retired_req_leaves_the_regression_set(self):
        from eval_runner import EvalRunner

        self._declare(change="REMOVED", retires=["REQ-001"])
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-002"), [])
        # another candidate still regresses REQ-001 until REQ-002 is promoted
        self.assertEqual(EvalRunner(self.proj).regression_req_ids("REQ-003"), ["REQ-001"])


class RootFilesEvalTests(_RegressionProject):
    """KIT root/ deliverables (scripts/, deploy/…) are at the eval workspace root, as after promotion."""

    def _script(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def test_candidate_root_files_are_at_the_workspace_root(self):
        self._script(self.proj / "scripts" / "common.sh", "echo canonical\n")
        kit = self.proj / "runs" / "kit" / "REQ-002"
        self._script(kit / "root" / "scripts" / "deploy_check.sh", "test -f scripts/common.sh && echo ok\n")
        ltc = _ltc("REQ-002", "checkout", extra_checks=[
            {"id": "root-script", "command": "sh scripts/deploy_check.sh", "blocking": True}])
        (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
        body = self._post("/v1/eval/run", "REQ-002").json()
        self.assertEqual(body["status"], "PASS", body)
        self.assertIn("root-script", self._case_names_from(body))

    def test_regression_sees_the_candidate_root_files_and_names_them(self):
        # REQ-001 (promoted) delivered a root script and checks it; the candidate rewrites it.
        self._script(self.proj / "scripts" / "common.sh", "exit 0\n")
        self._script(self.proj / "runs" / "kit" / "REQ-001" / "root" / "scripts" / "common.sh", "exit 0\n")
        ltc1 = _ltc("REQ-001", "pricing", extra_checks=[
            {"id": "common", "command": "sh scripts/common.sh", "blocking": True}])
        (self.proj / "runs" / "kit" / "REQ-001" / "ci" / "LTC.json").write_text(json.dumps(ltc1))
        kit = self.proj / "runs" / "kit" / "REQ-002"
        self._script(kit / "root" / "scripts" / "common.sh", "exit 3\n")
        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(body["status"], "FAIL", body)
        self.assertIn("regression::REQ-001::common", body["blocking_failures"])
        failing = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::common")
        self.assertIn("- scripts/common.sh", failing["stderr"])  # the candidate's root file, named
        # without the candidate's change the promoted check passes on the canonical script
        (kit / "root" / "scripts" / "common.sh").unlink()
        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertNotIn("regression::REQ-001::common", body.get("blocking_failures") or [])

    def _case_names_from(self, body):
        return [c["name"] for c in body["cases"]]


class ReconciledJsImportsTests(unittest.TestCase):
    def test_a_reconciled_js_test_gets_the_candidate_modules_it_imports(self):
        # B2B REQ-024: the candidate's test/fixtures.ts (shared with REQ-002/005/008/012) imports
        # './v2/req-024.fixtures'; without it every promoted REQ importing fixtures.ts failed to load.
        import eval_runner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "fixtures.ts": "import type { X } from '@/lib/contracts';\nimport { routing } from './v2/req-024.fixtures';\n"
                               "export * from \"./shared/index.js\";\nconst late = await import('./lazy');\n"
                               "const legacy = require('../outside');\n",
                "v2/req-024.fixtures.ts": "export const routing = 1;\n",
                "shared/index.ts": "export const s = 1;\n",
                "lazy.tsx": "export default 1;\n",
                "v2/req-024.spec.ts": "test('x', () => {});\n",
            }
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            support = {rel: root / rel for rel in files if not rel.endswith(".spec.ts") and rel != "fixtures.ts"}
            found = eval_runner._imported_support("fixtures.ts", root / "fixtures.ts", support)
            self.assertEqual(sorted(found), ["lazy.tsx", "shared/index.ts", "v2/req-024.fixtures.ts"])
            # a nested file resolves from its own directory
            (root / "v2" / "helper.ts").write_text("import { routing } from './req-024.fixtures';\n")
            self.assertEqual(eval_runner._imported_support("v2/helper.ts", root / "v2" / "helper.ts", support),
                             ["v2/req-024.fixtures.ts"])
