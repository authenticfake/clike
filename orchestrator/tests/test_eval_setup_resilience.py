"""Eval setup that fails for the sandbox's reasons, not the candidate's (lead-generation v3 REQ-026):
a database not created under parallel load, a regression whose environment did not come up, a single
check run without the setup it needs. No LLM."""
import sys
import types
import unittest
import unittest.mock

import eval_environment as ee
import eval_runner as er
from eval_runner import EvalCase, EvalReport, EvalRunner


def _report(*cases):
    return EvalReport(profile="p", req_id="REQ-006", mode="auto", passed=0, failed=0, cases=list(cases))


def _case(name, passed=True, blocked=False, blocking=True, stderr=""):
    return EvalCase(name=name, passed=passed, code=0 if passed else 1, stdout="", stderr=stderr,
                    blocking=blocking, blocked=blocked)


class _Runner:
    def __init__(self, *reports):
        self.reports = list(reports)
        self.calls = 0

    def run_profile(self, **_):
        self.calls += 1
        return self.reports.pop(0)


def _eval():
    runner = EvalRunner.__new__(EvalRunner)
    runner.cancel_event = None
    return runner


class RegressionSetupRetryTests(unittest.TestCase):
    def test_an_environment_that_comes_up_the_second_time_is_not_a_regression(self):
        first = _report(_case("python-dependencies", passed=False, blocking=False),
                        _case("unit", passed=False, blocked=True), _case("lint"))
        second = _report(_case("python-dependencies"), _case("unit"), _case("lint"))
        runner = _Runner(second)
        out = _eval()._retry_environment_setup(runner, "p", {}, "REQ-006", first)
        self.assertEqual(runner.calls, 1)
        self.assertIs(out, second)
        self.assertEqual(out.cases[0].name, "env::setup-retried")
        self.assertTrue(out.cases[0].passed and not out.cases[0].blocking)
        self.assertIn("REQ-006", out.cases[0].stdout)

    def test_a_database_that_fails_again_keeps_the_first_verdict(self):
        first = _report(_case("env::provision::APP_DATABASE_URL", passed=False))
        runner = _Runner(_report(_case("env::provision::APP_DATABASE_URL", passed=False)))
        self.assertIs(_eval()._retry_environment_setup(runner, "p", {}, "REQ-007", first), first)
        self.assertEqual(runner.calls, 1)

    def test_test_failures_and_lasting_blocks_are_not_re_run(self):
        failing_test = _report(_case("unit", passed=False))
        missing_tool = _report(_case("e2e", passed=False, blocked=True, stderr=f"{er._MISSING_TOOLS_NOTE}: pwsh"))
        for report in (failing_test, missing_tool, _report(_case("unit"))):
            runner = _Runner()
            self.assertIs(_eval()._retry_environment_setup(runner, "p", {}, "REQ-006", report), report)
            self.assertEqual(runner.calls, 0)


class SetupChecksTests(unittest.TestCase):
    def test_a_check_run_alone_gets_the_setup_before_it(self):
        names = ["python-dependencies", "npm-install", "lint", "unit", "rdi_25", "e2e-setup"]
        self.assertEqual(er._with_setup_checks(names, {"rdi_25"}), {"python-dependencies", "npm-install", "rdi_25"})
        self.assertEqual(er._with_setup_checks(names, {"python-dependencies"}), {"python-dependencies"})
        self.assertEqual(er._with_setup_checks(names, {"unknown"}), {"unknown"})
        self.assertFalse(er._is_setup_check("unit") or er._is_setup_check("rdi_25"))


class PostgresRetryTests(unittest.TestCase):
    def _fake_psycopg(self, failures):
        calls = {"n": 0}

        class OperationalError(Exception):
            pass

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql):
                calls.setdefault("sql", []).append(sql)

        def connect(dsn, autocommit, connect_timeout):
            calls["n"] += 1
            if calls["n"] <= failures:
                raise OperationalError("connection timeout expired")
            return _Conn()

        module = types.SimpleNamespace(connect=connect, OperationalError=OperationalError)
        return module, calls

    def test_a_server_slow_under_load_is_retried(self):
        module, calls = self._fake_psycopg(failures=2)
        slept = []
        with unittest.mock.patch.dict(sys.modules, {"psycopg": module}):
            ee.create_postgres_database("postgresql://u@db:5432/postgres", "lg_req007", sleep=slept.append)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(slept, [2.0, 5.0])
        self.assertEqual(len(calls["sql"]), 2)

    def test_a_server_that_stays_down_fails(self):
        module, calls = self._fake_psycopg(failures=99)
        with unittest.mock.patch.dict(sys.modules, {"psycopg": module}):
            with self.assertRaises(module.OperationalError):
                ee.create_postgres_database("postgresql://u@db:5432/postgres", "x", sleep=lambda s: None)
        self.assertEqual(calls["n"], ee._PG_ATTEMPTS)



if __name__ == "__main__":
    unittest.main()
