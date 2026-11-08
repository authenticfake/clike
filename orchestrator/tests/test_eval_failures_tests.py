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


class ScenarioCoverageTests(unittest.TestCase):
    """Journey scenarios the plan gives a REQ (reqs[].scenarios) are criteria of their own: the
    login REQ is not done until wrong credentials, lockout, reset and expiry are proved."""

    LTC = {"checks": [{"id": "unit", "command": "true"}, {"id": "e2e", "command": "true"},
                      {"id": "lint", "command": "true", "blocking": False}]}

    def _case(self, tmp, acceptance=None, scenarios=("IAM-03", "IAM-05"), tests="def test_iam_03(): ...\n# IAM-05 reset link expires\n"):
        import json
        root = Path(tmp)
        (root / "docs" / "harper").mkdir(parents=True)
        (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-002", "status": "open",
            "acceptance": ["A01: a verified user signs in"], "scenarios": list(scenarios)}]}))
        docs = root / "runs" / "kit" / "REQ-002" / "docs"
        docs.mkdir(parents=True)
        if acceptance is not None:
            (docs / "ACCEPTANCE.json").write_text(json.dumps({"criteria": acceptance}))
        if tests:
            (root / "runs" / "kit" / "REQ-002" / "test").mkdir(parents=True)
            (root / "runs" / "kit" / "REQ-002" / "test" / "test_login.py").write_text(tests)
        cases = EvalRunner(root)._acceptance_coverage_cases("REQ-002", self.LTC)
        return cases[0] if cases else None

    def test_an_unproven_scenario_blocks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, acceptance=[
                {"id": "A01", "status": "done", "checks": ["unit"]},
                {"id": "IAM-03", "status": "done", "checks": ["lint"]}])
            self.assertFalse(case.passed)
            self.assertTrue(case.blocking)
            self.assertIn("IAM-03: done, but names no blocking check", case.stderr)
            self.assertIn("IAM-05: not in ACCEPTANCE.json", case.stderr)

    def test_scenarios_proved_by_own_entries_or_listed_under_a_criterion_pass(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, acceptance=[
                {"id": "A01", "status": "done", "checks": ["unit"], "scenarios": ["IAM-05"]},
                {"id": "IAM-03", "status": "done", "checks": ["e2e"]}])
            self.assertTrue(case.passed, case.stderr)
            self.assertIn("3 acceptance criteria", case.stdout)

    def test_a_scenario_no_test_names_blocks(self):
        import tempfile
        done = [{"id": "A01", "status": "done", "checks": ["unit"], "scenarios": ["IAM-05"]},
                {"id": "IAM-03", "status": "done", "checks": ["e2e"]}]
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, acceptance=done, tests="def test_login(): ...\n")
            self.assertFalse(case.passed)
            self.assertIn("IAM-03: no test of the KIT names it", case.stderr)
            self.assertIn("IAM-05: no test of the KIT names it", case.stderr)
        with tempfile.TemporaryDirectory() as tmp:  # name, underscore or compact forms all count
            case = self._case(tmp, acceptance=done, tests="it('IAM03 shows the generic message')\ndef test_iam_05(): ...\n")
            self.assertTrue(case.passed, case.stderr)

    def test_a_line_listing_many_ids_proves_none(self):
        import tempfile
        ids = ("IAM-03", "IAM-05", "IAM-06")
        done = [{"id": "A01", "status": "done", "checks": ["unit"], "scenarios": list(ids)}]
        with tempfile.TemporaryDirectory() as tmp:  # one comment naming every scenario is not a proof
            case = self._case(tmp, acceptance=done, scenarios=ids, tests="# covers IAM-03, IAM-05, IAM-06\ndef test_login(): ...\n")
            self.assertFalse(case.passed)
            self.assertIn("IAM-06: no test of the KIT names it (it appears only in a line that lists many ids)", case.stderr)
        with tempfile.TemporaryDirectory() as tmp:  # one test may prove two sides of the same behaviour
            case = self._case(tmp, acceptance=done, scenarios=ids,
                              tests="def test_iam_03_iam_05_generic_message(): ...\nit('IAM-06: expired session', () => {})\n")
            self.assertTrue(case.passed, case.stderr)

    def test_ids_match_on_boundaries_and_tests_are_found_by_file_name(self):
        import json
        import tempfile
        done = [{"id": "A01", "status": "done", "checks": ["unit"], "scenarios": ["IAM-03", "IAM-05"]}]
        with tempfile.TemporaryDirectory() as tmp:  # an identifier that only contains the letters is not a tag
            case = self._case(tmp, acceptance=done, tests="def test_diam_03(): ...\ndef claim05(): ...\n")
            self.assertFalse(case.passed)
            self.assertIn("IAM-03: no test of the KIT names it", case.stderr)
        with tempfile.TemporaryDirectory() as tmp:  # Go white-box tests next to the code, Rust #[test] modules
            case = self._case(tmp, acceptance=done, tests=None)
            kit = Path(tmp) / "runs" / "kit" / "REQ-002"
            (kit / "src" / "auth").mkdir(parents=True)
            (kit / "src" / "auth" / "login_test.go").write_text('func TestIAM03WrongPassword(t *testing.T) {}\n')
            (kit / "src" / "reset.rs").write_text("#[cfg(test)]\nmod t {\n#[test]\nfn iam_05_link_expires() {}\n}\n")
            (kit / "src" / "errors.py").write_text("CODES = ['IAM-03', 'IAM-05']  # not a test\n")
            case = EvalRunner(Path(tmp))._acceptance_coverage_cases("REQ-002", self.LTC)[0]
            self.assertTrue(case.passed, case.stderr)
        _ = json

    def test_scenarios_without_acceptance_file_block(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp)
            self.assertFalse(case.passed)
            self.assertIn("owns journey scenarios (IAM-03, IAM-05)", case.stderr)

    def test_a_bullet_stating_a_scenario_is_that_scenario_not_a_new_criterion(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "harper").mkdir(parents=True)
            (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-002", "status": "open",
                "acceptance": ["A01: a verified user signs in", "IAM-03: If the password is wrong, then …"], "scenarios": ["IAM-03"]}]}))
            kit = root / "runs" / "kit" / "REQ-002"
            (kit / "docs").mkdir(parents=True)
            (kit / "test").mkdir(parents=True)
            (kit / "test" / "test_login.py").write_text("def test_iam_03(): ...\n")
            (kit / "docs" / "ACCEPTANCE.json").write_text(json.dumps({"criteria": [
                {"id": "A01", "status": "done", "checks": ["unit"]}, {"id": "IAM-03", "status": "done", "checks": ["e2e"]}]}))
            case = EvalRunner(root)._acceptance_coverage_cases("REQ-002", self.LTC)[0]
            self.assertTrue(case.passed, case.stderr)
            self.assertIn("2 acceptance criteria", case.stdout)  # not A02 and IAM-03 twice

    def test_a_req_without_scenarios_keeps_the_previous_behaviour(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._case(tmp, scenarios=()))


class WorkspaceLockTests(unittest.TestCase):
    def test_two_runs_of_the_same_workspace_never_overlap(self):
        # B2B: /finalize --verify sent twice composed the same SOLUTION workspace at once
        import threading
        import time
        import tempfile
        active, overlaps = [0], []

        def slow(self, *args, **kwargs):
            active[0] += 1
            overlaps.append(active[0])
            time.sleep(0.2)
            active[0] -= 1
            from eval_runner import EvalReport
            return EvalReport(profile="p", req_id="SOLUTION", mode="auto", passed=0, failed=0, cases=[])

        with tempfile.TemporaryDirectory() as tmp, patch.object(EvalRunner, "_run_profile", slow), \
                patch("eval_runner.sandbox_resources.preflight", return_value=None):
            runners = [EvalRunner(Path(tmp), eval_key="SOLUTION") for _ in range(2)]
            threads = [threading.Thread(target=r.run_profile, kwargs={"profile": "p", "ltc": {}, "req_id": "SOLUTION"}) for r in runners]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
        self.assertEqual(max(overlaps), 1)


if __name__ == "__main__":
    unittest.main()


class EpicFeaturesTests(unittest.TestCase):
    """C3: an epic is done when every feature of FEATURES.json is done with its blocking checks."""

    LTC = {"checks": [{"id": "unit", "command": "true"}, {"id": "lint", "command": "true", "blocking": False}]}

    def _case(self, tmp, features=None, profile="C3"):
        import json
        root = Path(tmp)
        (root / "docs" / "harper").mkdir(parents=True)
        (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-004", "status": "open", "profile": profile,
            "features": [{"id": "F01", "title": "sign in"}, {"id": "F02", "title": "reset"}]}]}))
        docs = root / "runs" / "kit" / "REQ-004" / "docs"
        docs.mkdir(parents=True)
        if features is not None:
            (docs / "FEATURES.json").write_text(json.dumps({"epic": "REQ-004", "features": features}))
        cases = EvalRunner(root)._epic_features_cases("REQ-004", self.LTC)
        if not cases:
            return None
        if len(cases) == 1:
            return cases[0]
        from eval_runner import EvalCase
        return EvalCase(name="all", passed=all(c.passed for c in cases), code=1, blocking=True, stdout="",
                        stderr="\n".join(f"{c.name} {c.stderr}" for c in cases))

    def test_every_feature_done_with_a_blocking_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, [{"id": "F01", "status": "done", "checks": ["unit"]}, {"id": "F02", "status": "done", "checks": ["unit"]}])
            self.assertTrue(case.passed, case.stderr)

    def test_missing_todo_or_unproven_features_block(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, [{"id": "F01", "status": "done", "checks": ["lint"]}, {"id": "F03", "status": "todo", "title": "extra"}])
            self.assertFalse(case.passed)
            self.assertIn("F02: planned, not in FEATURES.json", case.stderr)
            self.assertIn("F01: done, but names no blocking check", case.stderr)
            self.assertIn("F03: todo", case.stderr)
            self.assertIn("acceptance::features::F02", case.stderr)  # one case per feature left
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("has no docs/FEATURES.json", self._case(tmp).stderr)

    def test_not_an_epic_is_not_checked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._case(tmp, profile="C2"))


class AcceptanceBookkeepingTests(unittest.TestCase):
    """Cloud pilot: the model wrote status 'implemented' and named a check 'tests' the LTC calls
    otherwise; the loop stopped as 'no progress' though the problems had changed."""

    LTC = {"checks": [{"id": "unit-tests", "command": "true"}, {"id": "lint", "command": "true"}]}

    def _case(self, tmp, criteria):
        import json
        root = Path(tmp)
        (root / "docs" / "harper").mkdir(parents=True)
        (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-009", "status": "open",
            "acceptance": ["A01: x", "A02: y"]}]}))
        docs = root / "runs" / "kit" / "REQ-009" / "docs"
        docs.mkdir(parents=True)
        (docs / "ACCEPTANCE.json").write_text(json.dumps({"criteria": criteria}))
        return EvalRunner(root)._acceptance_coverage_cases("REQ-009", self.LTC)[0]

    def test_done_synonyms_count_but_still_need_a_blocking_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, [{"id": "A01", "status": "implemented", "checks": ["unit-tests"]},
                                    {"id": "A02", "status": "Completed", "checks": ["lint"]}])
            self.assertTrue(case.passed, case.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            case = self._case(tmp, [{"id": "A01", "status": "implemented", "checks": ["tests"]},
                                    {"id": "A02", "status": "passed", "checks": ["lint"]}])
            self.assertFalse(case.passed)
            self.assertIn("A01: done, but names no blocking check", case.stderr)
            self.assertIn("Blocking checks of ci/LTC.json a criterion can name: lint, unit-tests", case.stderr)

    def test_acceptance_failures_get_a_fingerprint_that_follows_their_problems(self):
        import tempfile
        from eval_runner import EvalCase
        with tempfile.TemporaryDirectory() as tmp:
            runner = EvalRunner(Path(tmp))
            a = EvalCase(name="acceptance::coverage", passed=False, code=1, stdout="", stderr="A01: unknown status implemented")
            b = EvalCase(name="acceptance::coverage", passed=False, code=1, stdout="", stderr="A01: done, but names no blocking check")
            runner._report_from_cases(profile_path=Path(tmp) / "p", req_id="REQ-009", mode="auto", cases=[a])
            runner._report_from_cases(profile_path=Path(tmp) / "p", req_id="REQ-009", mode="auto", cases=[b])
            self.assertTrue(a.fingerprint and b.fingerprint and a.fingerprint != b.fingerprint)


class PromotedFileKeptTests(unittest.TestCase):
    """Cloud pilot: one generation rewrote the promoted app.py (196 -> 34 lines) and pyproject.toml
    (no dependencies); every promoted REQ's regression failed."""

    def _cases(self, tmp, files, amends=None):
        import json
        root = Path(tmp)
        (root / "docs" / "harper").mkdir(parents=True)
        req = {"id": "REQ-009", "status": "open", **({"amends": amends} if amends else {})}
        (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [req]}))
        app = "\n".join(f"app.include_router(router_{i})" for i in range(40)) + "\n"
        (root / "src" / "pkg").mkdir(parents=True)
        (root / "src" / "pkg" / "app.py").write_text(app)
        (root / "src" / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["fastapi==1", "SQLAlchemy==2"]\n')
        kit = root / "runs" / "kit" / "REQ-009" / "src"
        for rel, text in files.items():
            (kit / rel).parent.mkdir(parents=True, exist_ok=True)
            (kit / rel).write_text(text(app) if callable(text) else text)
        return {c.name: c for c in EvalRunner(root)._promoted_source_cases("REQ-009")}

    def test_a_shorter_rewrite_or_lost_dependencies_block(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cases = self._cases(tmp, {"pkg/app.py": "app = make()\napp.include_router(review)\n",
                                      "pyproject.toml": '[project]\nname="x"\ndependencies=["fastapi==1"]\n'})
            app = cases["structure::promoted-file-kept::src/pkg/app.py"]
            self.assertTrue(app.blocking and not app.passed)
            self.assertIn("keeps 0 of its 40 lines", app.stderr)
            self.assertIn("Current src/pkg/app.py (promoted)", app.stderr)
            deps = cases["structure::promoted-file-kept::src/pyproject.toml"]
            self.assertIn("drops promoted dependencies: sqlalchemy", deps.stderr)

    def test_extending_a_promoted_file_passes_and_an_amending_req_is_not_checked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cases = self._cases(tmp, {"pkg/app.py": lambda app: app + "app.include_router(review)\n",
                                      "pyproject.toml": '[project]\nname="x"\ndependencies=["fastapi==1", "SQLAlchemy==2", "openpyxl==3"]\n'})
            self.assertEqual(cases, {})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._cases(tmp, {"pkg/app.py": "app = make()\n"}, amends=["REQ-003"]), {})


class RegressionCandidateDependenciesTests(unittest.TestCase):
    """Epic pilot: the candidate added openpyxl to the shared app; a promoted REQ's regression
    environment, built from its own requirements only, failed on the import."""

    def test_a_regression_environment_gets_the_candidates_requirements_too(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cand = root / "runs" / "kit" / "REQ-009"
            (cand / "src").mkdir(parents=True)
            (cand / "ci").mkdir(parents=True)
            (cand / "ci" / "requirements.txt").write_text("openpyxl==3.1.5\n")
            other = root / "runs" / "kit" / "REQ-001" / "ci"
            other.mkdir(parents=True)
            (other / "requirements.txt").write_text("fastapi==0.115.12\n")
            ltc = {"req_id": "REQ-001", "runtime": {"name": "python"}, "checks": [{"id": "t", "command": "true"}]}
            (other / "LTC.json").write_text(json.dumps(ltc))
            runner = EvalRunner(root)._regression_runner("REQ-009", "REQ-001", cand / "src")
            self.assertEqual(runner._candidate_requirements(), [cand / "ci" / "requirements.txt"])
            seen = []

            def fake(self, *, req_id, requirements_file, env, cwd):
                seen.append(Path(requirements_file).read_text().strip())
                return env, []

            with patch.object(EvalRunner, "_ensure_eval_venv", fake):
                runner.run_profile(profile=str(other / "LTC.json"), ltc=ltc, req_id="REQ-001")
            self.assertEqual(seen, ["fastapi==0.115.12", "openpyxl==3.1.5"])
            self.assertEqual(EvalRunner(root)._candidate_requirements(), [])  # the candidate's own eval: nothing extra


class SharedSupportReadsKitTests(unittest.TestCase):
    def test_a_regression_failing_on_a_file_the_shared_conftest_reads_from_the_kit_is_explained(self):
        import json
        import tempfile
        from eval_runner import EvalCase
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "harper").mkdir(parents=True)
            (root / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-009", "status": "open"}]}))
            (root / "test").mkdir()
            (root / "test" / "conftest.py").write_text("import pytest\n")
            kit = root / "runs" / "kit" / "REQ-009" / "test"
            (kit / "leadintel" / "review").mkdir(parents=True)
            (kit / "conftest.py").write_text('CFG = (KIT_ROOT / "ci/fixtures/scoring.json")\n')
            (kit / "leadintel" / "review" / "conftest.py").write_text('X = (KIT_ROOT / "ci/fixtures/review.json")\n')
            runner = EvalRunner(root)
            reads = runner._shared_support_kit_reads("REQ-009")
            self.assertEqual(reads, {"test/conftest.py": ["ci/fixtures/scoring.json"]})  # own dir not shared
            failing = EvalCase(name="regression::REQ-007::test:unit", passed=False, code=1, stdout="",
                               stderr="FileNotFoundError: [Errno 2] No such file or directory: '/w/REQ-007/ci/fixtures/scoring.json'")
            other = EvalCase(name="regression::REQ-003::test:unit", passed=False, code=1, stdout="", stderr="AssertionError")
            runner._explain_kit_reads(reads, [failing, other])
            self.assertIn("in this regression the KIT is REQ-007's KIT, which has no ci/fixtures/scoring.json", failing.stderr)
            self.assertEqual(other.stderr, "AssertionError")
