"""Eval pre-check of the variables an LTC needs from the environment (e.g. a test database). No LLM."""
from pathlib import Path

from eval_runner import (
    ENVIRONMENT_MISSING_REASON,
    EvalRunner,
    missing_environment_case,
    required_environment_variables,
)


def _names(ltc):
    return [v["name"] for v in required_environment_variables(ltc)]


def test_contract_form_and_free_form_of_earlier_kits():
    contract = {"environment": {"required_variables": [
        {"name": "APP_TEST_DATABASE_URL", "purpose": "real PostgreSQL", "example": "postgresql+psycopg://me@host.containers.internal:5432/t"},
        {"name": "APP_OPTIONAL_URL", "optional": True},
    ]}}
    assert _names(contract) == ["APP_TEST_DATABASE_URL"]
    legacy = {"environment": {
        "python": "3.12",
        "LEADINTEL_TEST_DATABASE_URL": "Required isolated real PostgreSQL 16 or compatible database",
        "CLIKE_EVAL_WORKSPACE": "Required: provided by CLike",
        "APP_LOG_LEVEL": "info",
        "APP_TRACE": "optional, required only for tracing",
    }}
    assert _names(legacy) == ["LEADINTEL_TEST_DATABASE_URL"]


def test_variables_the_ltc_sets_itself_are_not_required():
    ltc = {
        "environment": {"required_variables": [{"name": "APP_DB_URL"}]},
        "checks": [{"id": "it", "command": "true", "env": {"APP_DB_URL": "sqlite://"}}],
    }
    assert _names(ltc) == []


def test_missing_case_names_the_variable_and_the_fix():
    ltc = {"environment": {"required_variables": [{"name": "APP_DB_URL", "purpose": "real PostgreSQL"}]}}
    case = missing_environment_case(ltc, environ={})
    assert case.blocked and case.blocking and not case.passed
    assert "  - APP_DB_URL: real PostgreSQL" in case.stderr
    assert "docker/eval.env" in case.stderr and "host.containers.internal" in case.stderr
    assert missing_environment_case(ltc, environ={"APP_DB_URL": "postgresql://x"}) is None
    assert missing_environment_case(ltc, environ={"APP_DB_URL": "  "}) is not None


def test_run_profile_is_blocked_before_any_command(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("APP_DB_URL", raising=False)
    marker = tmp_path / "ran"
    ltc = {
        "req_id": "REQ-001",
        "environment": {"required_variables": [{"name": "APP_DB_URL"}]},
        "checks": [{"id": "unit", "command": f"touch {marker}", "blocking": True}],
    }
    report = EvalRunner(tmp_path).run_profile(profile="runs/kit/REQ-001/ci/LTC.json", ltc=ltc, req_id="REQ-001")
    assert report.status == "BLOCKED"
    assert report.reason_code == ENVIRONMENT_MISSING_REASON
    assert [c.name for c in report.cases] == ["env::required-variables"]
    assert not marker.exists()


def test_eval_work_dirs_go_to_the_base_dir_of_the_sandbox_volume(tmp_path: Path, monkeypatch):
    project = tmp_path / "My Project"
    project.mkdir()
    (project / "runs").write_text("not a dir")  # project not writable for runs/eval
    monkeypatch.delenv("CLIKE_EVAL_ROOT", raising=False)
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "vol"))
    (tmp_path / "vol").mkdir()
    assert EvalRunner(project)._eval_base_dir() == (tmp_path / "vol" / "My_Project").resolve()
