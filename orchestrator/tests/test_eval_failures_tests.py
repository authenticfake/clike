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


if __name__ == "__main__":
    unittest.main()
