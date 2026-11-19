"""Test strength (a test must fail without the KIT's code) and locked quality configurations
(a repair may not relax a linter, a type checker, test options or coverage). No LLM."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.testclient import TestClient  # noqa: E402

from services import quality_configs, test_strength  # noqa: E402

TOKEN = "s" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}
REQ = "REQ-001"
LTC = {"req_id": REQ, "checks": [{"id": "unit", "command": "python3 test/test_app.py", "blocking": True},
                                 {"id": "lint", "command": "true", "blocking": True}]}
STRONG_TEST = (
    "import pathlib, sys\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))\n"
    "from app import VALUE\nassert VALUE == 2\nprint('ok')\n"
)
WEAK_TEST = "FIXTURE = {'value': 2}\nassert FIXTURE['value'] == 2\nprint('ok')\n"
PYPROJECT = """[project]
name = "app"
dependencies = ["fastapi"]

[tool.ruff.lint]
select = ["E", "F", "B"]
ignore = ["E501"]

[tool.mypy]
strict = true

[tool.pytest.ini_options]
addopts = "-q"
filterwarnings = ["error"]

[tool.coverage.report]
fail_under = 85
"""


def weak(rel, before, after):
    return quality_configs.weakening(rel, before, after)


class QualityConfigWeakeningTests(unittest.TestCase):
    def test_python_tools_relaxed_are_weakenings(self):
        cases = {
            "ruff rule ignored": PYPROJECT.replace('ignore = ["E501"]', 'ignore = ["E501", "F401"]'),
            "ruff rule dropped": PYPROJECT.replace('["E", "F", "B"]', '["E", "F"]'),
            "per-file ignore": PYPROJECT + '\n[tool.ruff.lint.per-file-ignores]\n"src/*" = ["B"]\n',
            "mypy strict off": PYPROJECT.replace("strict = true", "strict = false"),
            "mypy override": PYPROJECT + '\n[[tool.mypy.overrides]]\nmodule = "app.db"\nignore_errors = true\n',
            "deselect": PYPROJECT.replace('addopts = "-q"', 'addopts = "-q --deselect test/test_a.py::test_x"'),
            "warnings": PYPROJECT.replace('filterwarnings = ["error"]', "filterwarnings = []"),
            "coverage": PYPROJECT.replace("fail_under = 85", "fail_under = 60"),
            "broken": PYPROJECT + "\n[tool.ruff\n",
        }
        for label, after in cases.items():
            with self.subTest(label):
                self.assertTrue(weak("src/pyproject.toml", PYPROJECT, after), label)

    def test_python_changes_that_relax_nothing_are_free(self):
        stricter = PYPROJECT.replace('["E", "F", "B"]', '["E", "F", "B", "UP"]').replace("fail_under = 85", "fail_under = 90")
        deps = PYPROJECT.replace('["fastapi"]', '["fastapi", "httpx>=0.27"]')
        for after in (PYPROJECT, stricter, deps, PYPROJECT.replace('ignore = ["E501"]', "ignore = []")):
            self.assertEqual(weak("pyproject.toml", PYPROJECT, after), [])
        # a configuration that did not parse before is not judged
        self.assertEqual(weak("pyproject.toml", "[tool.ruff\n", PYPROJECT), [])

    def test_ini_files(self):
        cfg = "[flake8]\nselect = E,F\nignore = E501\nmax-complexity = 10\n\n[mypy]\ndisallow_untyped_defs = True\n"
        self.assertTrue(weak("setup.cfg", cfg, cfg.replace("ignore = E501", "ignore = E501,F401")))
        self.assertTrue(weak("setup.cfg", cfg, cfg.replace("max-complexity = 10", "max-complexity = 30")))
        self.assertTrue(weak("setup.cfg", cfg, cfg.replace("disallow_untyped_defs = True", "disallow_untyped_defs = False")))
        self.assertEqual(weak("setup.cfg", cfg, cfg.replace("max-complexity = 10", "max-complexity = 8")), [])
        ruff = '[lint]\nselect = ["E"]\n'
        self.assertTrue(weak("ruff.toml", ruff, ruff + 'extend-ignore = ["E711"]\n'))

    def test_tsconfig_with_comments(self):
        ts = '{\n  // strict build\n  "compilerOptions": {"strict": true, "noUnusedLocals": true,},\n  "include": ["src"],\n}\n'
        self.assertTrue(weak("tsconfig.json", ts, ts.replace('"strict": true', '"strict": false')))
        self.assertTrue(weak("tsconfig.app.json", ts, ts.replace('"strict": true,', '"strict": true, "noImplicitAny": false,')))
        self.assertTrue(weak("tsconfig.json", ts, ts.replace('"include": ["src"],', '"include": ["src"], "exclude": ["src/legacy.ts"],')))
        self.assertEqual(weak("tsconfig.json", ts, ts.replace('"include": ["src"],', '"include": ["src"], "exclude": ["dist", "node_modules"],')), [])
        self.assertEqual(weak("tsconfig.json", ts, ts.replace('"strict": true,', '"strict": true, "noUncheckedIndexedAccess": true,')), [])

    def test_eslint_and_pre_commit(self):
        rc = json.dumps({"extends": ["eslint:recommended"], "rules": {"no-console": "error", "eqeqeq": ["error", "always"]}})
        self.assertTrue(weak(".eslintrc.json", rc, rc.replace('"no-console": "error"', '"no-console": "warn"')))
        self.assertTrue(weak(".eslintrc.json", rc, rc.replace('"no-console": "error"', '"no-console": "error", "no-undef": "off"')))
        self.assertEqual(weak(".eslintrc.json", rc, rc.replace('"no-console": "error"', '"no-console": "error", "curly": "error"')), [])
        flat = "export default [{ rules: { 'no-console': 'error' } }];\n"
        self.assertTrue(weak("eslint.config.mjs", flat, flat.replace("'no-console': 'error'", "'no-console': 'off'")))
        self.assertTrue(weak("eslint.config.mjs", flat, "export default [{ ignores: ['src/legacy/**'] }, " + flat[15:]))
        hooks = "repos:\n- repo: local\n  hooks:\n  - id: ruff\n  - id: mypy\n"
        self.assertTrue(weak(".pre-commit-config.yaml", hooks, hooks.replace("  - id: mypy\n", "")))

    def test_names(self):
        for rel in ("src/pyproject.toml", "root/web/tsconfig.app.json", "eslint.config.mjs", ".pre-commit-config.yaml", "setup.cfg"):
            self.assertTrue(quality_configs.is_quality_config(rel), rel)
        for rel in ("src/app.py", "package.json", "ci/LTC.json", "README.md"):
            self.assertFalse(quality_configs.is_quality_config(rel), rel)


class TestStrengthUnitTests(unittest.TestCase):
    def test_counts_of_the_common_runners(self):
        self.assertEqual(test_strength.counts("==== 2 failed, 5 passed in 0.3s ===="), {"passed": 5, "failed": 2})
        self.assertEqual(test_strength.counts("==== 7 passed in 0.3s ===="), {"passed": 7, "failed": 0})
        self.assertEqual(test_strength.counts("Tests:       1 failed, 4 passed, 5 total"), {"passed": 4, "failed": 1})
        self.assertEqual(test_strength.counts(" Tests  3 failed | 9 passed (12)"), {"passed": 9, "failed": 3})
        self.assertIsNone(test_strength.counts("ImportError: cannot import name"))

    def test_only_test_checks_are_measured(self):
        ltc = {"checks": [
            {"id": "unit", "command": "pytest -q test"}, {"id": "lint", "command": "ruff check ."},
            {"id": "typecheck", "command": "mypy src"}, {"id": "behaviour", "command": "bash ci/run.sh"},
            {"id": "coverage", "command": "pytest --cov --cov-fail-under=80"},
        ]}
        case = lambda name, **kw: SimpleNamespace(name=name, passed=kw.get("passed", True), blocking=kw.get("blocking", True), blocked=False)
        cases = [case("unit"), case("lint"), case("typecheck"), case("behaviour"), case("coverage"), case("regression::REQ-000::unit")]
        self.assertEqual(test_strength.candidates(cases, ltc), ["unit", "behaviour", "coverage"])

    def test_summary_and_the_warning(self):
        base = [SimpleNamespace(name="unit", passed=True, blocked=False, stdout="", stderr=""),
                SimpleNamespace(name="api", passed=False, blocked=False, stdout="== 2 failed, 3 passed in 1s ==", stderr="")]
        result = test_strength.summarize(["unit", "api"], base)
        self.assertEqual((result["weak"], result["failing"], result["partial"]), (["unit"], ["api"], {"api": {"passed": 3, "failed": 2}}))
        case = test_strength.case_fields(result, REQ)
        self.assertEqual((case["name"], case["passed"], case["blocking"]), ("acceptance::test-strength", False, False))
        self.assertIn("unit of REQ-001 pass on the code before this KIT", case["stdout"])
        self.assertIn("api: 3 of 5 tests already pass", case["stdout"])
        self.assertIsNone(test_strength.case_fields({"checks": [], "weak": []}, REQ))
        self.assertIsNone(test_strength.case_fields({"checks": ["unit"], "error": "x"}, REQ))


class StrengthAndQualityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-strength-")).resolve()
        cls.projects = cls.tmp / "projects"
        cls.projects.mkdir()
        cls.state = cls.tmp / "state"
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(cls.projects), "CLIKE_STATE_DIR": str(cls.state)})
        cls._env.start()
        from app import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8080")

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.proj = self.projects / f"p{self._testMethodName[-28:]}"
        kit = self.proj / "runs" / "kit" / REQ
        for sub in ("ci", "test", "src"):
            (kit / sub).mkdir(parents=True)
        (kit / "ci" / "LTC.json").write_text(json.dumps(LTC))
        (kit / "test" / "test_app.py").write_text(STRONG_TEST)
        (kit / "src" / "app.py").write_text("VALUE = 1 + 1\n")
        (kit / "src" / "pyproject.toml").write_text(PYPROJECT)
        self.kit = kit

    def _eval(self):
        return self.client.post("/v1/eval/run", headers=AUTH, params={
            "profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ}).json()

    def _gate(self):
        return self.client.post("/v1/gate/check", headers=AUTH, params={
            "profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ}).json()

    def _amend(self, changes, previous=None, deleted=None):
        return self.client.post("/v1/acceptance/amend", headers=AUTH, json={
            "project_root": str(self.proj), "req_id": REQ, "changes": changes, "previous": previous or {},
            "evidence": "lint failed", "deleted": deleted or []}).json()

    def _case(self, body, name="acceptance::test-strength"):
        return next((c for c in body["cases"] if c["name"] == name), None)

    # test strength
    def test_a_test_that_passes_without_the_code_is_a_warning_measured_once(self):
        (self.kit / "test" / "test_app.py").write_text(WEAK_TEST)
        body = self._eval()
        case = self._case(body)
        self.assertEqual(body["status"], "PASS_WITH_WARNINGS", body)
        self.assertTrue(body["passed"])  # a warning: the auto-eval loop stops on it, nothing to repair
        self.assertEqual((case["passed"], case["blocking"]), (False, False))
        self.assertIn("unit of REQ-001 pass on the code before this KIT", case["stdout"])
        gate = self._gate()
        self.assertEqual((gate["gate"], gate["reason_code"]), ("PASS", "GATE_PASS_WITH_WARNINGS"))
        with patch("routes.routes_eval._execute_profile", wraps=__import__("routes.routes_eval", fromlist=["x"])._execute_profile) as run:
            again = self._eval()
        self.assertFalse([c for c in run.call_args_list if c.kwargs.get("baseline")])  # recorded: not run again
        self.assertEqual(self._case(again)["passed"], False)

    def test_a_test_that_needs_the_code_is_strong(self):
        body = self._eval()
        case = self._case(body)
        self.assertEqual(body["status"], "PASS", body)
        self.assertTrue(case["passed"])
        self.assertIn("fails on the code before this KIT", case["stdout"])

    def test_a_new_test_measures_again(self):
        (self.kit / "test" / "test_app.py").write_text(WEAK_TEST)
        self.assertEqual(self._eval()["status"], "PASS_WITH_WARNINGS")
        (self.kit / "test" / "test_value.py").write_text(STRONG_TEST)  # a test added after the lock
        ltc = {**LTC, "checks": [*LTC["checks"], {"id": "unit-value", "command": "python3 test/test_value.py", "blocking": True}]}
        (self.kit / "ci" / "LTC.json").write_text(json.dumps(ltc))
        self._amend({"ci/LTC.json": json.dumps(ltc)}, {"ci/LTC.json": json.dumps(LTC)})
        case = self._case(self._eval())
        self.assertIn("unit of REQ-001", case["stdout"])  # still weak, now measured with the new check
        self.assertNotIn("unit-value", case["stdout"].split("pass on the code")[0])

    def test_switched_off(self):
        (self.kit / "test" / "test_app.py").write_text(WEAK_TEST)
        with patch.dict(os.environ, {"CLIKE_EVAL_TEST_STRENGTH": "0"}):
            body = self._eval()
        self.assertEqual(body["status"], "PASS")
        self.assertIsNone(self._case(body))

    def test_a_failing_eval_is_not_measured(self):
        (self.kit / "src" / "app.py").write_text("VALUE = 3\n")
        body = self._eval()
        self.assertEqual(body["status"], "FAIL")
        self.assertIsNone(self._case(body))

    # quality configurations
    def test_quality_configs_are_locked_and_relaxing_them_is_rejected(self):
        self._eval()
        relaxed = PYPROJECT.replace('ignore = ["E501"]', 'ignore = ["E501", "B008"]')
        result = self._amend({"src/pyproject.toml": relaxed}, {"src/pyproject.toml": PYPROJECT})
        self.assertEqual(result["accepted"], [])
        self.assertIn("now ignored: ruff:B008", " ".join(result["rejected"]["src/pyproject.toml"]))
        deps = PYPROJECT.replace('["fastapi"]', '["fastapi", "httpx"]')
        result = self._amend({"src/pyproject.toml": deps}, {"src/pyproject.toml": PYPROJECT})
        self.assertEqual(result["accepted"], ["src/pyproject.toml"])
        # a configuration added after the lock is not locked: kept as written
        result = self._amend({"src/web/tsconfig.json": '{"compilerOptions": {"strict": false}}'})
        self.assertEqual(result["unlocked"], ["src/web/tsconfig.json"])
        # removing a locked configuration is rejected (the extension restores it)
        result = self._amend({}, {"src/pyproject.toml": deps}, deleted=["src/pyproject.toml"])
        self.assertIn("src/pyproject.toml", result["rejected"])

    def test_the_gate_blocks_a_relaxed_quality_config_and_not_other_changes(self):
        self._eval()
        (self.kit / "src" / "pyproject.toml").write_text(PYPROJECT.replace('["fastapi"]', '["fastapi", "httpx"]'))
        self.assertEqual(self._gate()["gate"], "PASS")
        (self.kit / "src" / "pyproject.toml").write_text(PYPROJECT.replace("strict = true", "strict = false"))
        gate = self._gate()
        self.assertEqual((gate["gate"], gate["reason_code"]), ("FAIL", "GATE_BLOCKED_ACCEPTANCE_TAMPERED"))
        anomaly = gate["integrity"]["anomalies"][0]
        self.assertEqual((anomaly["path"], anomaly["kind"]), ("src/pyproject.toml", "weakened"))
        self.assertIn("strict flag turned off: mypy:strict", " ".join(anomaly["details"]))

    def test_cloud_repair_drops_a_relaxed_quality_config(self):
        from services import harper

        self._eval()
        prefix = f"runs/kit/{REQ}/"
        out = {"files": [
            {"path": prefix + "src/pyproject.toml", "content": PYPROJECT.replace("fail_under = 85", "fail_under = 10")},
            {"path": prefix + "src/app.py", "content": "VALUE = 2\n"},
        ]}
        payload = {"repository_context": {"workspace_folder": str(self.proj)}, "auto_eval": {"cycle": 1, "failures": []}}
        with patch.object(harper, "_kit_repair", return_value={"cycle": 1, "failures": []}):
            harper._apply_repair_governance(payload, out, REQ)
        self.assertEqual([f["path"] for f in out["files"]], [prefix + "src/app.py"])
        self.assertTrue(any(w.startswith("repair_change_rejected:src/pyproject.toml") for w in out["warnings"]))


if __name__ == "__main__":
    unittest.main()
