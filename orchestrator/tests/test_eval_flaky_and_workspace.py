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
