"""A promoted REQ's test that fails once is nondeterministic, not a regression; KIT scratch is never
copied into the eval workspace; a workspace CLike cannot compose is environment-blocked."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import eval_runner  # noqa: E402
from eval_runner import EvalRunner  # noqa: E402

from tests.test_eval_regression import _RegressionProject  # noqa: E402


class FlakyRegressionTests(_RegressionProject):
    def _flaky_req001(self, fail_times):
        counter = self.proj.parent / f"{self.proj.name}.count"
        counter.write_text("0")
        script = (
            "import sys, pathlib\n"
            f"p = pathlib.Path({str(counter)!r}); n = int(p.read_text()) + 1; p.write_text(str(n))\n"
            f"sys.exit(1 if n <= {fail_times} else 0)\n"
        )
        kit = self.proj / "runs" / "kit" / "REQ-001"
        (kit / "test" / "flaky.py").write_text(script)
        ltc = {"req_id": "REQ-001", "run_from": "runs/kit/REQ-001",
               "checks": [{"id": "unit", "command": "python3 test/flaky.py", "blocking": True}]}
        (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))

    def test_a_promoted_test_that_passes_on_retry_is_a_warning(self):
        self._flaky_req001(fail_times=1)
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        case = next(c for c in gate["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["passed"])
        self.assertFalse(case["blocking"])
        self.assertIn("Nondeterministic", case["stderr"])
        self.assertEqual(gate["gate"], "PASS", gate["reason_code"])

    def test_a_test_that_fails_twice_is_a_regression(self):
        # fails with the candidate and on the retry, passes on the promoted tree alone: a regression
        self._flaky_req001(fail_times=2)
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        self.assertEqual(gate["reason_code"], "GATE_BLOCKED_REGRESSION")

    def test_a_test_failing_without_the_candidate_too_is_a_warning(self):
        self._flaky_req001(fail_times=5)
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        case = next(c for c in gate["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["blocking"])
        self.assertIn("Already failing without this candidate", case["stderr"])
        self.assertEqual(gate["gate"], "PASS", gate["reason_code"])


class BaselineCacheTests(_RegressionProject):
    _flaky_req001 = FlakyRegressionTests._flaky_req001

    """The baseline (a promoted REQ's checks on the promoted tree alone) is computed once per promoted
    state, in the eval base dir outside the project, and reused by the next evals of any candidate."""

    def setUp(self):
        super().setUp()
        self.base = self.proj.parent / f"{self.proj.name}.evalbase"
        self.base.mkdir()
        self._root = patch.dict("os.environ", {"CLIKE_EVAL_ROOT": str(self.base)})
        self._root.start()
        self.addCleanup(self._root.stop)

    def _runs(self):
        return int((self.proj.parent / f"{self.proj.name}.count").read_text())

    def _eval(self):
        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        case = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["blocking"])
        self.assertIn("Already failing without this candidate", case["stderr"])

    def test_a_failure_already_known_on_the_promoted_tree_is_not_run_again(self):
        self._flaky_req001(fail_times=99)
        self._eval()
        self.assertEqual(self._runs(), 3)  # with the candidate, its retry, without the candidate
        self.assertTrue((self.base / ".regression-baseline" / "REQ-001.json").is_file())
        # a repair of the candidate: the promoted tree is the same, only the candidate's run is left
        (self.proj / "runs" / "kit" / "REQ-002" / "src" / "checkout.py").write_text(
            "from pricing import price\n\ndef total(n):\n    return price() * n\n")
        self._eval()
        self.assertEqual(self._runs(), 4)

    def test_a_changed_promoted_tree_computes_the_baseline_again(self):
        self._flaky_req001(fail_times=99)
        self._eval()
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "note.txt").write_text("changed\n")
        self._eval()
        self.assertEqual(self._runs(), 6)

    def test_a_check_that_failed_without_any_candidate_before_is_unstable(self):
        # B2B REQ-014: failed on the promoted tree alone at an earlier promoted state, then a new
        # promoted state where it passes alone once but fails with the candidate and its retry
        self._flaky_req001(fail_times=99)
        self._eval()
        (self.proj / "runs" / "kit" / "REQ-001" / "test" / "note.txt").write_text("changed\n")
        (self.proj.parent / f"{self.proj.name}.count").write_text("97")  # runs 98, 99 fail; 100 passes
        body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        case = next(c for c in body["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertFalse(case["blocking"])
        self.assertIn("an unstable check", case["stderr"])

    def test_no_baseline_is_kept_inside_the_project(self):
        self._root.stop()
        self._flaky_req001(fail_times=99)
        self._eval()
        self._eval()
        self.assertEqual(self._runs(), 6)
        self.assertEqual(list(self.proj.rglob(".regression-baseline")), [])
        self._root.start()


class ParallelRegressionTests(_RegressionProject):
    """Promoted REQs are regressed CLIKE_EVAL_REGRESSION_WORKERS at a time, reported in plan order."""

    def _timed_kits(self):
        plan = {"reqs": [
            {"id": "REQ-001", "status": "done", "dependsOn": []},
            {"id": "REQ-002", "status": "open", "dependsOn": ["REQ-001"]},
            {"id": "REQ-003", "status": "done", "dependsOn": []},
        ]}
        (self.proj / "docs" / "harper" / "plan.json").write_text(json.dumps(plan))
        stamps = self.proj.parent / f"{self.proj.name}.stamps"
        stamps.mkdir()
        for req in ("REQ-001", "REQ-003"):
            kit = self.proj / "runs" / "kit" / req
            (kit / "test" / "slow.py").write_text(
                "import pathlib, sys, time\n"
                f"d = pathlib.Path({str(stamps)!r}); (d / '{req}.start').write_text(str(time.time()))\n"
                "time.sleep(1.5)\n"
                f"(d / '{req}.end').write_text(str(time.time()))\n")
            ltc = {"req_id": req, "run_from": f"runs/kit/{req}",
                   "checks": [{"id": "unit", "command": "python3 test/slow.py", "blocking": True}]}
            (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
        return stamps

    def _overlap(self, stamps):
        t = {p.name: float(p.read_text()) for p in stamps.iterdir()}
        return t["REQ-001.start"] < t["REQ-003.end"] and t["REQ-003.start"] < t["REQ-001.end"]

    def _regression_names(self, body):
        return [c["name"] for c in body["cases"] if c["name"].startswith("regression::") and c["name"].endswith("::unit")]

    def test_two_workers_run_promoted_reqs_side_by_side_in_plan_order(self):
        stamps = self._timed_kits()
        with patch.dict("os.environ", {"CLIKE_EVAL_REGRESSION_WORKERS": "2"}):
            body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(self._regression_names(body), ["regression::REQ-001::unit", "regression::REQ-003::unit"])
        self.assertTrue(self._overlap(stamps))

    def test_one_worker_runs_them_one_after_the_other(self):
        stamps = self._timed_kits()
        with patch.dict("os.environ", {"CLIKE_EVAL_REGRESSION_WORKERS": "1"}):
            body = self._post("/v1/eval/run", "REQ-002", regression=True).json()
        self.assertEqual(self._regression_names(body), ["regression::REQ-001::unit", "regression::REQ-003::unit"])
        self.assertFalse(self._overlap(stamps))

    def test_the_workers_setting_is_bounded(self):
        for raw, expected in (("", 2), ("0", 1), ("x", 2), ("3", 3), ("99", 8)):
            with patch.dict("os.environ", {"CLIKE_EVAL_REGRESSION_WORKERS": raw}):
                self.assertEqual(eval_runner.regression_workers(), expected, raw)

    def test_service_ports_are_never_handed_out_twice(self):
        import eval_environment

        ports = [eval_environment.free_port() for _ in range(200)]
        self.assertEqual(len(set(ports)), len(ports))


class SharedFileDiagnosisTests(_RegressionProject):
    def test_a_regression_names_the_shared_files_the_candidate_replaced(self):
        # REQ-002 rewrites REQ-001's pricing.py: REQ-001's failing check names the file and the diff.
        (self.proj / "src").mkdir(exist_ok=True)
        (self.proj / "src" / "pricing.py").write_text("def price():\n    return 10\n")  # promoted
        kit = self.proj / "runs" / "kit" / "REQ-002"
        (kit / "src" / "pricing.py").write_text("def price():\n    return 12\n")
        (kit / "test" / "test_checkout.py").write_text("from checkout import total\nassert total(2) == 24\n")
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        case = next(c for c in gate["cases"] if c["name"] == "regression::REQ-001::unit")
        self.assertIn("Shared files changed", case["stderr"])
        self.assertIn("- src/pricing.py", case["stderr"])
        self.assertIn("+    return 12", case["stderr"])
        self.assertTrue(case["excerpt"].startswith(eval_runner._SHARED_FILES_NOTE))

    def test_no_note_when_the_candidate_touches_no_file_of_the_promoted_req(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs" / "kit" / "REQ-001" / "src").mkdir(parents=True)
            (root / "runs" / "kit" / "REQ-001" / "src" / "a.py").write_text("A = 1\n")
            (root / "cand" / "src").mkdir(parents=True)
            (root / "cand" / "src" / "b.py").write_text("B = 1\n")
            (root / "cand" / "src" / "node_modules").mkdir()
            self.assertEqual(eval_runner._shared_file_changes(root, root / "cand", root / "runs" / "kit" / "REQ-001"), [])
            (root / "cand" / "src" / "a.py").write_text("A = 1\n")  # same content: not a change
            self.assertEqual(eval_runner._shared_file_changes(root, root / "cand", root / "runs" / "kit" / "REQ-001"), [])


    def test_a_file_the_candidate_adds_in_a_promoted_test_directory_is_named(self):
        # B2B REQ-025: __init__.py added next to REQ-003's tests made them a package, their bare imports broke
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "runs" / "kit" / "REQ-003"
            (other / "test" / "execution").mkdir(parents=True)
            (other / "test" / "execution" / "test_race.py").write_text("from test_behavior import x\n")
            (root / "cand" / "test" / "execution").mkdir(parents=True)
            (root / "cand" / "test" / "__init__.py").write_text("")
            (root / "cand" / "test" / "execution" / "__init__.py").write_text("")
            (root / "cand" / "test" / "execution" / "test_new_req.py").write_text("")  # its own test: fine
            (root / "cand" / "test" / "mine").mkdir()
            (root / "cand" / "test" / "mine" / "helper.py").write_text("")  # its own directory: fine
            changes = eval_runner._shared_file_changes(root, root / "cand", other)
            self.assertEqual(
                [c.split(" ")[1] for c in changes], ["test/__init__.py", "test/execution/__init__.py"]
            )
            self.assertIn("package marker such as __init__.py", eval_runner._shared_files_note("REQ-003", changes))


class BaselineErrorsTests(unittest.TestCase):
    def test_a_check_failing_on_the_promoted_tree_with_other_errors_is_still_a_regression(self):
        # B2B REQ-003: below the coverage threshold on the promoted tree, an import error with the candidate
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "REQ-003.json"
            baseline = eval_runner._BaselineCache(path, "d1")
            coverage = "FAIL Required test coverage of 80% not reached. Total coverage: 27.40%"
            baseline.store({"test:integration": True}, {"test:integration": eval_runner.eval_failures.error_keys(coverage)})
            again = eval_runner._BaselineCache(path, "d1")
            self.assertEqual(again.new_errors("test:integration", coverage.replace("27.40", "31.02")), [])
            new = again.new_errors(
                "test:integration", coverage + "\nE   ModuleNotFoundError: No module named 'test_req_behavior'"
            )
            self.assertEqual(len(new), 1)
            self.assertIn("modulenotfounderror", new[0])
            self.assertEqual(again.new_errors("unknown", "Error: x"), [])  # no baseline errors kept: as before

    def test_test_file_names(self):
        for name in ("test_a.py", "a_test.go", "a.test.ts", "a.spec.js", "OrderTest.java", "OrderTests.cs", "a_spec.rb"):
            self.assertTrue(eval_runner._is_test_file_name(name), name)
        for name in ("__init__.py", "conftest.py", "jest.config.js", "vitest.config.ts", "pytest.ini", "helpers.py"):
            self.assertFalse(eval_runner._is_test_file_name(name), name)

class WorkspaceCopyTests(unittest.TestCase):
    def test_scratch_of_the_kit_is_not_copied_and_vanished_files_are_skipped(self):
        names = ["src", ".tmp", ".cache", "node_modules", ".npm-cache", "local-eval-workspaces", "app.py"]
        self.assertEqual(eval_runner._KIT_COPY_IGNORE("/x", names),
                         {".tmp", ".cache", "node_modules", ".npm-cache", "local-eval-workspaces"})
        with tempfile.TemporaryDirectory() as tmp:
            eval_runner._copy_if_present(str(Path(tmp) / "gone"), str(Path(tmp) / "dst"))
            self.assertFalse((Path(tmp) / "dst").exists())

    def test_a_workspace_clike_cannot_compose_is_environment_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            ltc = {"req_id": "REQ-001", "checks": [{"id": "unit", "command": "true"}]}
            (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
            runner = EvalRunner(root)
            real = runner._prepare_eval_workspace
            calls = []

            def once(**kw):
                calls.append(1)
                if len(calls) == 1:
                    raise OSError("file vanished during copy")
                return real(**kw)

            with patch.object(runner, "_prepare_eval_workspace", side_effect=once):
                report = runner.run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
            self.assertEqual(report.status, "PASS")  # retried once
            with patch.object(runner, "_prepare_eval_workspace", side_effect=OSError("still busy")):
                report = runner.run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
            case = report.cases[0]
            self.assertEqual(case.name, "env::prepare-workspace")
            self.assertTrue(case.blocked)
            self.assertIn("nothing to repair", case.stderr)


if __name__ == "__main__":
    unittest.main()


class ServiceBrokenByCandidateTests(unittest.TestCase):
    def test_a_service_that_starts_without_the_candidate_names_the_mandatory_configuration(self):
        from unittest.mock import patch

        from eval_runner import EvalCase, EvalReport, EvalRunner

        def case(name, passed):
            return EvalCase(name=name, passed=passed, code=0 if passed else 1, stdout="", stderr="boom")

        with tempfile.TemporaryDirectory() as tmp:
            runner = EvalRunner(Path(tmp))
            report = EvalReport(profile="LTC.json", req_id="REQ-002", mode="auto", passed=0, failed=1,
                                cases=[case("env::service::req001-api", False)])
            baseline = EvalReport(profile="LTC.json", req_id="REQ-002", mode="auto", passed=1, failed=0,
                                  cases=[case("env::service::req001-api", True)])
            with patch.object(EvalRunner, "run_profile", return_value=baseline):
                runner._mark_preexisting_regression_failures("REQ-020", Path(tmp) / "LTC.json", {"checks": []}, "REQ-002", report)
        service = report.cases[0]
        self.assertTrue(service.blocking)  # the candidate broke it: still a regression
        self.assertTrue(service.excerpt.startswith(eval_runner._SERVICE_BROKEN_NOTE))
        self.assertIn("keep it optional with a safe default", service.excerpt)
