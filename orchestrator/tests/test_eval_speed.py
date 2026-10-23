"""Eval speed without losing verdicts: static checks out of the regression, per-check durations,
node_modules store."""
import os
from pathlib import Path

from eval_runner import EvalRunner, _is_static_regression_check


def test_static_checks_are_recognised_tests_and_installs_are_not():
    for name in ("lint", "typecheck", "security:sast", "coverage", "ruff", "types", "eslint", "sbom", "license-check"):
        assert _is_static_regression_check(name), name
    for name in ("test:unit", "test:integration", "e2e", "requirements", "npm-install", "build", "smoke",
                 "test:coverage", "pytest", "migrate", "unit"):
        assert not _is_static_regression_check(name), name


def _ltc(*checks):
    return {"req_id": "REQ-001", "checks": [{"id": c, "command": "true", "blocking": True} for c in checks]}


def test_a_regression_run_skips_static_checks_and_times_the_rest(tmp_path: Path):
    kit = tmp_path / "runs" / "kit" / "REQ-001"
    (kit / "ci").mkdir(parents=True)
    (kit / "src").mkdir()
    ltc = _ltc("lint", "typecheck", "test:unit")
    nested = EvalRunner(tmp_path, eval_key="REQ-002/regression/REQ-001", regression=True)
    report = nested.run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
    names = [c.name for c in report.cases]
    assert "test:unit" in names and "lint" not in names and "typecheck" not in names
    note = next(c for c in report.cases if c.name == "static-checks::not-run")
    assert note.passed and not note.blocking and "lint, typecheck" in note.stdout
    unit = next(c for c in report.cases if c.name == "test:unit")
    assert unit.duration_s is not None and unit.duration_s >= 0

    # the REQ's own eval keeps every check
    own = EvalRunner(tmp_path).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
    assert {"lint", "typecheck", "test:unit"} <= {c.name for c in own.cases}


def test_a_regression_run_skips_the_promoted_reqs_own_regression_checks(tmp_path: Path):
    kit = tmp_path / "runs" / "kit" / "REQ-001"
    (kit / "ci").mkdir(parents=True)
    (kit / "src").mkdir()
    ltc = _ltc("test:unit", "regression", "test:backend-regression")
    nested = EvalRunner(tmp_path, eval_key="REQ-002/regression/REQ-001", regression=True)
    report = nested.run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
    names = [c.name for c in report.cases]
    assert "test:unit" in names and "regression" not in names and "test:backend-regression" not in names
    note = next(c for c in report.cases if c.name == "regression-checks::not-run")
    assert note.passed and not note.blocking and "regression, test:backend-regression" in note.stdout

    # a REQ whose only test check is called "regression" keeps it
    only = EvalRunner(tmp_path, eval_key="REQ-002/regression/REQ-001", regression=True).run_profile(
        profile=str(kit / "ci" / "LTC.json"), ltc=_ltc("build", "regression"), req_id="REQ-001")
    assert "regression" in {c.name for c in only.cases}
    # the REQ's own eval keeps every check
    own = EvalRunner(tmp_path).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001")
    assert {"test:unit", "regression", "test:backend-regression"} <= {c.name for c in own.cases}


def test_link_tree_shares_files_but_not_new_ones(tmp_path: Path):
    store = tmp_path / "store" / "node_modules"
    (store / "pkg").mkdir(parents=True)
    (store / "pkg" / "index.js").write_text("x")
    os.symlink("../pkg/index.js", store / "bin-link")
    work = tmp_path / "work" / "node_modules"
    assert EvalRunner._link_tree(store, work)
    assert (work / "pkg" / "index.js").read_text() == "x"
    assert os.path.samefile(work / "pkg" / "index.js", store / "pkg" / "index.js")
    assert os.readlink(work / "bin-link") == "../pkg/index.js"
    (work / "pkg" / "cache.json").write_text("{}")  # a file a test creates stays in its copy
    assert not (store / "pkg" / "cache.json").exists()


def test_a_recorded_verdict_is_reusable_only_while_its_inputs_stay_the_same(tmp_path: Path, monkeypatch):
    from services import eval_verdicts

    monkeypatch.setenv("CLIKE_STATE_DIR", str(tmp_path / "state"))
    proj = tmp_path / "proj"
    for rel, text in {"src/app.py": "x = 1\n", "runs/kit/REQ-002/src/new.py": "y = 2\n",
                      "runs/kit/REQ-002/ci/LTC.json": "{}", "docs/harper/plan.json": '{"reqs": []}',
                      "scripts/run.sh": "echo\n"}.items():
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text(text)
    eval_verdicts.record(proj, "REQ-002", True, {"status": "PASS", "cases": []})
    assert eval_verdicts.reusable(proj, "REQ-002", True)["report"]["status"] == "PASS"
    assert eval_verdicts.reusable(proj, "REQ-002", False) is None          # another regression mode
    (proj / "runs/kit/REQ-002/eval-noise").mkdir()                          # not an input
    (proj / "runs/kit/REQ-002/src/node_modules").mkdir()                   # installed: not an input
    (proj / "runs/kit/REQ-002/src/node_modules/x.js").write_text("1")
    assert eval_verdicts.reusable(proj, "REQ-002", True) is not None
    for rel in ("docs/harper/plan.json", "scripts/run.sh", "src/app.py", "runs/kit/REQ-002/src/new.py"):
        eval_verdicts.record(proj, "REQ-002", True, {"status": "PASS", "cases": []})
        (proj / rel).write_text((proj / rel).read_text() + " ")
        assert eval_verdicts.reusable(proj, "REQ-002", True) is None, rel
    eval_verdicts.record(proj, "REQ-002", True, {"status": "FAIL", "cases": []})
    assert eval_verdicts.reusable(proj, "REQ-002", True) is None            # only a passing verdict


def test_a_root_conftest_must_keep_the_shared_fixtures(tmp_path: Path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "conftest.py").write_text("import pytest\n\n@pytest.fixture\ndef workspace():\n    return 1\n\ndef helper():\n    pass\n")
    kit = tmp_path / "runs" / "kit" / "REQ-015"
    (kit / "test").mkdir(parents=True)
    (kit / "ci").mkdir()
    (kit / "test" / "conftest.py").write_text("import pytest\n\n@pytest.fixture\ndef provider():\n    return 2\n")
    ltc = _ltc("test:unit")
    report = EvalRunner(tmp_path).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-015")
    case = next(c for c in report.cases if c.name == "structure::shared-conftest::test")
    assert not case.passed and case.blocking and "helper, workspace" in case.stderr
    # keeping them (and adding its own) passes
    (kit / "test" / "conftest.py").write_text((tmp_path / "test" / "conftest.py").read_text() + "\ndef provider():\n    pass\n")
    report = EvalRunner(tmp_path).run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-015")
    assert next(c for c in report.cases if c.name == "structure::shared-conftest::test").passed


def test_a_support_file_the_eval_asked_to_drop_can_be_removed_tests_cannot(tmp_path: Path, monkeypatch):
    from services import gate_integrity as gi

    monkeypatch.setenv("CLIKE_STATE_DIR", str(tmp_path / "state"))
    kit = tmp_path / "runs" / "kit" / "REQ-015"
    (kit / "test" / "pkg").mkdir(parents=True)
    (kit / "ci").mkdir()
    (kit / "ci" / "LTC.json").write_text('{"checks": []}')
    conftest = "import pytest\n\n@pytest.fixture\ndef provider():\n    return 1\n"
    test_file = "def test_login():\n    assert True\n"
    (kit / "test" / "conftest.py").write_text(conftest)
    (kit / "test" / "pkg" / "test_login.py").write_text(test_file)
    gi.ensure_lock(tmp_path, "REQ-015")
    (kit / "test" / "conftest.py").unlink()
    (kit / "test" / "pkg" / "test_login.py").unlink()
    evidence = "structure::shared-conftest::test\nruns/kit/REQ-015/test/conftest.py replaces the shared test/conftest.py"
    result = gi.amend_acceptance_surface(
        tmp_path, "REQ-015", {}, reason="repair", evidence=evidence,
        previous={"test/conftest.py": conftest, "test/pkg/test_login.py": test_file},
        deleted=["test/conftest.py", "test/pkg/test_login.py"],
    )
    assert result["accepted"] == ["test/conftest.py"]
    assert "test/pkg/test_login.py" in result["rejected"]
    lock = gi.ensure_lock(tmp_path, "REQ-015")
    assert "test/conftest.py" not in lock["files"] and "test/pkg/test_login.py" in lock["files"]
    # not named by the eval: kept
    (kit / "test" / "conftest.py").write_text(conftest)
    gi.ensure_lock(tmp_path, "REQ-015")
    other = gi.amend_acceptance_surface(tmp_path, "REQ-015", {}, reason="r", evidence="unit failed",
                                        previous={"test/conftest.py": conftest}, deleted=["test/conftest.py"])
    assert other["accepted"] == [] or "test/conftest.py" in other["rejected"]


def _support_project(tmp_path: Path, files: dict, kit_files: dict) -> EvalRunner:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    kit = tmp_path / "runs" / "kit" / "REQ-024"
    for rel, text in kit_files.items():
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        (kit / rel).write_text(text)
    return EvalRunner(tmp_path)


def test_a_shared_test_support_file_must_keep_the_names_promoted_tests_use(tmp_path: Path):
    shared = "export const clientId = 'c1';\nexport function page() { return 1; }\nexport { base as fixtureBase };\n"
    files = {
        "test/fixtures.ts": shared,
        "test/workspace.spec.ts": "import { clientId, page } from './fixtures';\ntest('w', () => page(clientId));\n",
        "test/other.spec.ts": "test('o', () => { const page = 2; });\n",  # names a word, never the module
    }
    dropped = "export function page() { return 2; }\nexport { base as fixtureBase };\n"
    runner = _support_project(tmp_path, files, {"test/fixtures.ts": dropped})
    [case] = runner._shared_test_support_cases("REQ-024")
    assert case.name == "structure::shared-test-support::test/fixtures.ts" and case.blocking and not case.passed
    assert "clientId (used by test/workspace.spec.ts)" in case.stderr and "page" not in case.stderr.split("drops")[1].split(":")[0]
    # kept, and its own part added: nothing to say
    (tmp_path / "runs/kit/REQ-024/test/fixtures.ts").write_text(shared + "export const routing = 1;\n")
    assert runner._shared_test_support_cases("REQ-024") == []
    # dropped on purpose and the user reconciled by the candidate: the state after promotion is fine
    (tmp_path / "runs/kit/REQ-024/test/fixtures.ts").write_text(dropped)
    (tmp_path / "runs/kit/REQ-024/test/workspace.spec.ts").write_text("import { page } from './fixtures';\ntest('w', () => page());\n")
    assert runner._shared_test_support_cases("REQ-024") == []


def test_the_shared_support_check_reads_python_go_and_java(tmp_path: Path):
    files = {
        "test/req017_support.py": "PRICE = 12\n\ndef make_client():\n    return 1\n\ndef _private():\n    pass\n",
        "test/test_exports.py": "from req017_support import PRICE, make_client\n\ndef test_x():\n    assert make_client() and PRICE\n",
        "tests/helpers.go": "package api\n\nfunc NewServer() int { return 1 }\nfunc helper() {}\n",
        "tests/api_test.go": "package api\n\nfunc TestApi(t *testing.T) { NewServer() }\n",
        "test/ApiTestBase.java": "public abstract class ApiTestBase {\n  public Client client() { return null; }\n}\n",
        "test/OrdersTest.java": "class OrdersTest extends ApiTestBase {\n  @Test void x() { client(); }\n}\n",
        "test/conftest.py": "def workspace():\n    pass\n",  # the root conftest has its own check
    }
    kit = {
        "test/req017_support.py": "def make_client():\n    return 1\n",
        "tests/helpers.go": "package api\n\nfunc helper() {}\n",
        "test/ApiTestBase.java": "public abstract class ApiTestBase {\n}\n",
        "test/conftest.py": "def other():\n    pass\n",
    }
    runner = _support_project(tmp_path, files, kit)
    found = {c.name: c.stderr for c in runner._shared_test_support_cases("REQ-024")}
    assert set(found) == {
        "structure::shared-test-support::test/req017_support.py",
        "structure::shared-test-support::tests/helpers.go",
        "structure::shared-test-support::test/ApiTestBase.java",
    }
    assert "PRICE (used by test/test_exports.py)" in found["structure::shared-test-support::test/req017_support.py"]
    assert "NewServer (used by tests/api_test.go)" in found["structure::shared-test-support::tests/helpers.go"]
    assert "client (used by test/OrdersTest.java)" in found["structure::shared-test-support::test/ApiTestBase.java"]


def test_the_shared_support_case_is_in_the_eval_report(tmp_path: Path):
    files = {
        "test/fixtures.ts": "export const clientId = 'c1';\n",
        "test/workspace.spec.ts": "import { clientId } from './fixtures';\n",
    }
    runner = _support_project(tmp_path, files, {"test/fixtures.ts": "export const other = 1;\n", "ci/.keep": ""})
    kit = tmp_path / "runs" / "kit" / "REQ-024"
    report = runner.run_profile(profile=str(kit / "ci" / "LTC.json"), ltc=_ltc("test:unit"), req_id="REQ-024")
    case = next(c for c in report.cases if c.name == "structure::shared-test-support::test/fixtures.ts")
    assert case.blocking and not case.passed and report.status == "FAIL"


def test_a_kit_adding_a_test_layout_file_next_to_promoted_tests_is_blocked(tmp_path: Path):
    # B2B REQ-025: __init__.py under test/ broke REQ-003's imports by name; same rule in any language
    def write(rel, text=""):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    write("test/execution/test_race.py", "from test_behavior import x\n")
    write("test/web/orders.spec.ts", "test('a', () => {})\n")
    write("test/java/OrderTest.java", "class OrderTest {}\n")
    write("test/go/order_test.go", "package order\n")
    kit = "runs/kit/REQ-025/test/"
    write(kit + "__init__.py")                       # Python package marker at the shared root
    write(kit + "execution/__init__.py")
    write(kit + "execution/test_new.py")             # its own test: fine
    write(kit + "execution/req025_support.py")       # its own helper module: fine
    write(kit + "web/vitest.config.ts")              # JS/TS runner config
    write(kit + "java/pom.xml")                      # Maven
    write(kit + "go/go.mod")                         # Go module
    write(kit + "research/conftest.py")              # a directory of its own: fine
    write(kit + "research/__init__.py")
    runner = EvalRunner(tmp_path)
    [case] = runner._test_layout_cases("REQ-025")
    assert case.name == "structure::test-layout::test" and case.blocking and not case.passed
    for rel in ("test/__init__.py", "test/execution/__init__.py", "test/web/vitest.config.ts",
                "test/java/pom.xml", "test/go/go.mod"):
        assert f"runs/kit/REQ-025/{rel}" in case.stderr, rel
    for rel in ("test_new.py", "req025_support.py", "research/"):
        assert rel not in case.stderr, rel
    # a file the promoted tree already has is not an addition
    write("test/__init__.py")
    write("test/execution/__init__.py")
    write("test/web/vitest.config.ts")
    write("test/java/pom.xml")
    write("test/go/go.mod")
    assert runner._test_layout_cases("REQ-025") == []
