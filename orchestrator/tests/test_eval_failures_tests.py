"""Failed tests and timeouts in the output of the test runners of any language (eval_failures)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import eval_failures  # noqa: E402
from eval_runner import EvalCase, EvalRunner  # noqa: E402


class FailedTestsTests(unittest.TestCase):
    def test_runner_formats(self):
        for line, expected in (
            # pytest (B2B REQ-017)
            ("FAILED test/v2/test_req_017_contracts.py::test_migration_chain_and_existing_manifest_entries - AssertionError: x",
             ("test/v2/test_req_017_contracts.py", "test_migration_chain_and_existing_manifest_entries")),
            # vitest (B2B REQ-014 running REQ-016's test)
            (" FAIL  ../../../../Users/a/B2B/test/v2/req-016.states.test.tsx > REQ-016 session states > clears revoked workspace rows",
             ("../../../../Users/a/B2B/test/v2/req-016.states.test.tsx", "REQ-016 session states > clears revoked workspace rows")),
            ("  ✘  3 [chromium] › tests/login.spec.ts:12:5 › signs in and out (2.1s)", ("tests/login.spec.ts", "signs in and out")),
            ("--- FAIL: TestCheckout (0.00s)", ("", "TestCheckout")),
            ("test pricing::tests::rounds ... FAILED", ("", "pricing::tests::rounds")),
            ("  Failed Shop.Tests.PriceTests.Rounds [12 ms]", ("", "Shop.Tests.PriceTests.Rounds")),
            ("testRounds(com.shop.PriceTest)  Time elapsed: 0.01 s  <<< FAILURE!", ("com.shop.PriceTest", "testRounds")),
            ("rspec ./spec/price_spec.rb:12 # Price rounds half up", ("./spec/price_spec.rb", "Price rounds half up")),
        ):
            self.assertEqual(eval_failures.failed_tests(line), [expected], line)
        self.assertEqual(eval_failures.failed_tests("test/x.py::test_a PASSED [ 50%]\n1 passed"), [])

    def test_a_failed_test_matches_its_reference(self):
        ref = "test/v2/req-016.states.test.tsx::clears revoked workspace rows/selections, and requires an explicit permitted choice"
        failed = eval_failures.failed_tests(
            " FAIL  ../../../../Users/a/B2B/test/v2/req-016.states.test.tsx > REQ-016 session states > "
            "clears revoked workspace rows/selections, and requires an explicit permitted choice")[0]
        self.assertTrue(eval_failures.test_matches(failed, ref))
        self.assertFalse(eval_failures.test_matches(failed, "test/v2/req-016.states.test.tsx::restores only the last workspace"))
        self.assertFalse(eval_failures.test_matches(failed, "test/v2/other.test.tsx::" + ref.split("::")[1]))
        self.assertTrue(eval_failures.test_matches(("test/x.py", "Setup::test_cli[a-1]"), "test/x.py::Setup::test_cli"))
        self.assertTrue(eval_failures.test_matches(("", "TestCheckout"), "pkg/checkout_test.go::TestCheckout"))

    def test_timeouts(self):
        for text in (
            "E   TimeoutError: Runtime test exceeded 30 seconds",                                  # B2B REQ-013
            "E   sqlalchemy.exc.OperationalError: (psycopg.errors.ConnectionTimeout) connection timeout expired",
            "subprocess.TimeoutExpired: Command '[...]' timed out after 300 seconds",              # B2B REQ-017
            "Error: Timed out waiting 60000ms from config.webServer.",                             # B2B REQ-024
            "Error: Timeout of 2000ms exceeded.",
            "context deadline exceeded",
        ):
            self.assertTrue(eval_failures.timed_out(text), text)
        self.assertFalse(eval_failures.timed_out(
            "test_failure_never_becomes_empty_fact[timeout-UNAVAILABLE] PASSED [ 68%]\n"
            "DeprecationWarning: You should not use the 'timeout' argument with the TestClient\nAssertionError: 1 != 2"))


class ReportedFailuresTests(unittest.TestCase):
    def test_summary_counts(self):
        self.assertEqual(eval_failures.reported_failures("=========== 1 failed, 28 passed, 1 warning in 0.58s ==========="), 1)
        self.assertEqual(eval_failures.reported_failures("====== 11 passed, 1 warning, 5 errors in 38.76s ======"), 5)
        self.assertEqual(eval_failures.reported_failures("      Tests  1 failed | 138 passed (139)"), 1)
        self.assertEqual(eval_failures.reported_failures("Tests run: 4, Failures: 1, Errors: 1, Skipped: 0"), 2)
        self.assertEqual(eval_failures.reported_failures("test/x.py::test_failed_login PASSED [ 50%]\n2 passed"), 0)


class TimeoutAloneTests(unittest.TestCase):
    def _case(self, name, text, passed=False):
        return EvalCase(name=name, passed=passed, code=0 if passed else 1, stdout="", stderr=text, excerpt=text, blocking=True)

    def test_a_timeout_under_parallel_load_is_run_again_alone(self):
        runner = EvalRunner(Path("/nonexistent"))
        slow = self._case("regression::REQ-013::test:integration", "E   TimeoutError: Runtime test exceeded 30 seconds")
        real = self._case("regression::REQ-017::tests", "subprocess.TimeoutExpired: timed out after 300 seconds")
        wrong = self._case("regression::REQ-020::unit", "AssertionError: assert 1 == 2")
        outcomes = {"REQ-013": True, "REQ-017": False}

        def fake_runner(req_id, other, candidate_src):
            def run_profile(profile, ltc, req_id, checks):
                return SimpleNamespace(cases=[SimpleNamespace(name=c, passed=outcomes[other]) for c in checks])
            return SimpleNamespace(run_profile=run_profile)

        ran = []
        with patch.object(runner, "_regression_runner", side_effect=lambda *a: ran.append(a[1]) or fake_runner(*a)), \
                patch("eval_runner.json.loads", return_value={}), patch.object(Path, "read_text", return_value="{}"):
            runner._rerun_timeouts_alone("REQ-037", Path("/c/src"), [slow, real, wrong], {})
        self.assertEqual(ran, ["REQ-013", "REQ-017"])  # only the timeouts, one REQ at a time
        self.assertFalse(slow.blocking)
        self.assertIn("passes when run alone", slow.stderr)
        self.assertTrue(real.blocking)
        self.assertIn("again when run alone", real.stderr)
        self.assertTrue(wrong.blocking)


class NodeManifestTests(unittest.TestCase):
    def test_a_declared_package_json_installs_whatever_the_main_runtime(self):
        # B2B REQ-038: a Python LTC with a web frontend named src/web/package.json; no install ran
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            (kit / "src" / "web").mkdir(parents=True)
            (kit / "src" / "web" / "package.json").write_text('{"name": "web"}')
            ltc = {"req_id": "REQ-001", "package_json": "runs/kit/REQ-001/src/web/package.json",
                   "environment": {"python": "3.12", "node": ">=22"},
                   "checks": [{"id": "unit", "command": f"{sys.executable} -c 'print(1)'"}]}
            (kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
            seen = []

            def fake(self, *, req_id, package_json, env, cwd):
                seen.append(Path(package_json).name)
                return env, [EvalCase(name="env::npm-install", passed=True, code=0, stdout="", stderr="")]

            with patch.object(EvalRunner, "_ensure_node_dependencies", fake):
                report = EvalRunner(root).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
            self.assertEqual(seen, ["package.json"])
            self.assertIn("env::npm-install", [c.name for c in report.cases])


class AcceptanceCoverageTests(unittest.TestCase):
    """B2B REQ-038: every LTC check could pass while the live probes and the browser journey were not
    implemented; the KIT's SELF_REVIEW said it was not promotable and CLike did not read it."""

    def _project(self, tmp, acceptance=None, review=None):
        import json
        root = Path(tmp)
        (root / "docs" / "harper").mkdir(parents=True)
        (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-038", "status": "in_progress",
            "acceptance": ["REQ-038-A01: preflight refuses fixtures", "REQ-038-A06: one probe per adapter",
                           "REQ-038-A07: real research observed by the developer"]}]}))
        docs = root / "runs" / "kit" / "REQ-038" / "docs"
        docs.mkdir(parents=True)
        if acceptance is not None:
            (docs / "ACCEPTANCE.json").write_text(json.dumps({"criteria": acceptance}))
        if review is not None:
            (docs / "SELF_REVIEW.md").write_text(review)
        return root

    LTC = {"checks": [{"id": "unit", "command": "true"}, {"id": "lint", "command": "true", "blocking": False}]}

    def _case(self, root):
        cases = EvalRunner(root)._acceptance_coverage_cases("REQ-038", self.LTC)
        return cases[0] if cases else None

    def test_a_partial_or_missing_criterion_blocks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(self._project(tmp, acceptance=[
                {"id": "REQ-038-A01", "status": "done", "checks": ["unit"]},
                {"id": "REQ-038-A06", "status": "missing", "note": "probes not implemented"},
                {"id": "REQ-038-A07", "status": "developer_evidence", "note": "real IT+GB research on the developer machine"}]))
            self.assertFalse(case.passed)
            self.assertTrue(case.blocking)
            self.assertIn("REQ-038-A06: missing — probes not implemented", case.stderr)
            self.assertIn("real IT+GB research", case.stdout)

    def test_done_needs_a_blocking_check_and_every_criterion_is_listed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(self._project(tmp, acceptance=[
                {"id": "REQ-038-A01", "status": "done", "checks": ["lint"]},
                {"id": "REQ-038-A06", "status": "done", "checks": ["unit"]}]))
            self.assertFalse(case.passed)
            self.assertIn("REQ-038-A01: done, but names no blocking check", case.stderr)
            self.assertIn("REQ-038-A07: not in ACCEPTANCE.json", case.stderr)

    def test_all_done_passes_and_developer_evidence_is_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(self._project(tmp, acceptance=[
                {"id": "REQ-038-A01", "status": "done", "checks": ["unit"]},
                {"id": "REQ-038-A06", "status": "done", "checks": ["unit"]},
                {"id": "REQ-038-A07", "status": "developer_evidence", "note": "observed on the developer machine"}]))
            self.assertTrue(case.passed)
            self.assertIn("observed on the developer machine", case.stdout)

    def test_a_self_review_that_says_incomplete_blocks_without_the_file_and_contradicts_it(self):
        import tempfile
        review = "The candidate must not be treated as complete or independently promotable until the gaps are resolved.\n"
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(self._project(tmp, review=review))
            self.assertFalse(case.passed)
            self.assertIn("declares REQ-038 incomplete", case.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            done = [{"id": f"REQ-038-A0{n}", "status": "done", "checks": ["unit"]} for n in (1, 6, 7)]
            case = self._case(self._project(tmp, acceptance=done, review=review))
            self.assertFalse(case.passed)
            self.assertIn("SELF_REVIEW.md says otherwise", case.stderr)

    def test_the_field_names_agents_use_are_understood(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(self._project(tmp, acceptance=[
                {"id": "REQ-038-A01", "status": "done", "blocking_checks": ["unit"], "evidence": "x"},
                {"id": "REQ-038-A06", "status": "done", "verified_by": ["unit"]},
                {"id": "REQ-038-A07", "status": "developer-evidence", "evidence": "real research on the developer machine"}]))
            self.assertTrue(case.passed, case.stderr)

    def test_nothing_declared_keeps_the_previous_behaviour(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._case(self._project(tmp, review="All criteria implemented and verified.\n")))


if __name__ == "__main__":
    unittest.main()
