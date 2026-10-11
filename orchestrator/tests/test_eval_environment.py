"""Eval environment provisioning (generated values, test databases, services of other REQs). No LLM.

The PostgreSQL test runs only when CLIKE_TEST_POSTGRES_URL points to a server where the user may
create databases (e.g. postgresql://me@localhost:5432/postgres)."""
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

import eval_environment as ee
from eval_runner import ENVIRONMENT_MISSING_REASON, EvalRunner

SERVER = textwrap.dedent('''
    import http.server, os, sys
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = os.environ.get("APP_GREETING", "?").encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            elif self.path == "/session":
                ok = self.headers.get("Authorization") == "Bearer " + os.environ["APP_SESSIONS"]
                self.send_response(200 if ok else 401); self.end_headers()
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *a): pass
    http.server.HTTPServer(("127.0.0.1", int(os.environ["APP_PORT"])), H).serve_forever()
''')

CHECK = textwrap.dedent('''
    import os, sys, urllib.request
    url, session = os.environ["APP_TEST_API_URL"], os.environ["APP_TEST_SESSION"]
    assert os.environ["APP_LOCAL_SESSION"] == session
    assert len(os.environ["APP_CLIENT_ID"]) == 36
    assert urllib.request.urlopen(url + "/health").read() == b"hello"
    req = urllib.request.Request(url + "/session", headers={"Authorization": "Bearer " + session})
    assert urllib.request.urlopen(req).status == 200
    assert open(os.environ["SETUP_MARKER"]).read() == "migrated"
    print("integration ok")
''')


def _project(tmp_path: Path, consumer_ltc: dict) -> Path:
    project = tmp_path / "proj"
    provider = project / "runs/kit/REQ-001"
    (provider / "src").mkdir(parents=True)
    (provider / "ci").mkdir()
    (provider / "src/server.py").write_text(SERVER)
    (provider / "ci/LTC.json").write_text(json.dumps({"req_id": "REQ-001", "checks": [{"id": "t", "command": "true"}]}))
    consumer = project / "runs/kit/REQ-002"
    (consumer / "ci").mkdir(parents=True)
    (consumer / "test").mkdir()
    (consumer / "test/check_integration.py").write_text(CHECK)
    (consumer / "ci/LTC.json").write_text(json.dumps(consumer_ltc))
    return project


def _ltc(tmp_path: Path, **extra) -> dict:
    marker = tmp_path / "setup-marker"
    return {
        "req_id": "REQ-002",
        "environment": {"required_variables": [
            {"name": "APP_TEST_SESSION", "provision": "token"},
            {"name": "APP_CLIENT_ID", "provision": "uuid"},
            {"name": "APP_LOCAL_SESSION", "provision": "template", "value": "${APP_TEST_SESSION}"},
            {"name": "APP_TEST_API_URL", "provision": "service"},
        ]},
        "services": [{
            "name": "provider-api", "req": "REQ-001", "cwd": "src",
            "setup": [f"{sys.executable} -c \"open('{marker}', 'w').write('migrated')\""],
            "start": f"{sys.executable} server.py",
            "env": {"APP_GREETING": "hello", "APP_SESSIONS": "${APP_TEST_SESSION}"},
            "port_env": "APP_PORT",
            "ready": {"http_path": "/health"},
            "exports": {"APP_TEST_API_URL": "http://127.0.0.1:${PORT}"},
        }],
        "env": {"SETUP_MARKER": str(marker)},
        "checks": [{"id": "integration", "command": f"{sys.executable} test/check_integration.py", "cwd": "runs/kit/REQ-002"}],
        **extra,
    }


def test_generated_values_and_a_service_of_another_req_reach_the_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "eval"))
    project = _project(tmp_path, _ltc(tmp_path))
    ltc = json.loads((project / "runs/kit/REQ-002/ci/LTC.json").read_text())
    report = EvalRunner(project).run_profile(profile="runs/kit/REQ-002/ci/LTC.json", ltc=ltc, req_id="REQ-002")
    cases = {c.name: c for c in report.cases}
    assert report.status == "PASS", [(c.name, c.stderr[-800:]) for c in report.cases if not c.passed]
    assert "integration ok" in cases["integration"].stdout
    assert "exports APP_TEST_API_URL" in cases["env::service::provider-api"].stdout
    assert cases["env::provision::APP_TEST_SESSION"].passed


def test_the_service_is_stopped_after_the_eval(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "eval"))
    project = _project(tmp_path, _ltc(tmp_path))
    ltc = json.loads((project / "runs/kit/REQ-002/ci/LTC.json").read_text())
    runner = EvalRunner(project)
    started = []
    original = ee.start_service

    def spy(*args, **kwargs):
        result = original(*args, **kwargs)
        started.append(result[0])
        return result

    monkeypatch.setattr(ee, "start_service", spy)
    runner.run_profile(profile="runs/kit/REQ-002/ci/LTC.json", ltc=ltc, req_id="REQ-002")
    assert started and started[0].proc.poll() is not None


def test_a_service_that_does_not_start_fails_with_its_log(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "eval"))
    ltc = _ltc(tmp_path)
    ltc["services"][0]["start"] = f"{sys.executable} -c \"import sys; print('boom: bad config'); sys.exit(3)\""
    project = _project(tmp_path, ltc)
    report = EvalRunner(project).run_profile(profile="runs/kit/REQ-002/ci/LTC.json", ltc=ltc, req_id="REQ-002")
    case = {c.name: c for c in report.cases}["env::service::provider-api"]
    assert report.status == "FAIL" and not case.passed and case.blocking
    assert "exited with code 3" in case.stderr and "boom: bad config" in case.stderr


def test_missing_external_value_blocks_and_is_not_repairable():
    ltc = {"environment": {"required_variables": [{"name": "PROVIDER_API_URL", "provision": "external"}]}}
    missing = ee.missing_variables(ltc, {})
    assert [s.name for s, _ in missing] == ["PROVIDER_API_URL"] and not ee.repairable(missing)


def test_undeclared_variable_is_repairable_and_service_without_exporter_too():
    ltc = {"environment": {"required_variables": [{"name": "APP_URL"}, {"name": "APP_API", "provision": "service"}]}}
    missing = ee.missing_variables(ltc, {})
    assert {s.name for s, _ in missing} == {"APP_URL", "APP_API"} and ee.repairable(missing)


def test_database_url_needs_the_server_once_then_is_provisioned(tmp_path, monkeypatch):
    legacy = {"environment": {"APP_TEST_DATABASE_URL": "Required isolated real PostgreSQL 16 database"}}
    missing = ee.missing_variables(legacy, {})
    assert missing and "CLIKE_EVAL_POSTGRES_URL" in missing[0][1] and not ee.repairable(missing)
    assert ee.missing_variables(legacy, {"CLIKE_EVAL_POSTGRES_URL": "postgresql://u@h:5432/postgres"}) == []

    created = []
    spec = ee.VariableSpec(name="APP_TEST_DATABASE_URL", provision="postgres_database", options={"scheme": "postgresql+psycopg"})
    url = ee.provision_postgres(spec, "postgresql://me@host.containers.internal:5432/postgres", "My Proj", "REQ-002",
                                create=lambda admin, db: created.append((admin, db)))
    assert url.startswith("postgresql+psycopg://me@host.containers.internal:5432/clike_my_proj_req_002_")
    assert created[0][1] == url.rsplit("/", 1)[1]


def test_explicit_environment_value_wins_over_provisioning(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "eval"))
    monkeypatch.setenv("APP_TEST_SESSION", "from-eval-env")
    project = tmp_path / "p"
    (project / "runs/kit/REQ-009/ci").mkdir(parents=True)
    ltc = {
        "req_id": "REQ-009",
        "environment": {"required_variables": [{"name": "APP_TEST_SESSION", "provision": "token"}]},
        "checks": [{"id": "c", "command": f"{sys.executable} -c \"import os; assert os.environ['APP_TEST_SESSION'] == 'from-eval-env'\""}],
    }
    report = EvalRunner(project).run_profile(profile="runs/kit/REQ-009/ci/LTC.json", ltc=ltc, req_id="REQ-009")
    assert report.status == "PASS", [(c.name, c.stderr) for c in report.cases]


def test_blocked_report_says_whether_a_repair_can_fix_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_BASE_DIR", str(tmp_path / "eval"))
    project = tmp_path / "p"
    (project / "runs/kit/REQ-003/ci").mkdir(parents=True)
    ltc = {"req_id": "REQ-003", "environment": {"required_variables": [{"name": "APP_URL", "purpose": "required"}]},
           "checks": [{"id": "c", "command": "true"}]}
    report = EvalRunner(project).run_profile(profile="runs/kit/REQ-003/ci/LTC.json", ltc=ltc, req_id="REQ-003")
    assert report.reason_code == ENVIRONMENT_MISSING_REASON and report.environment_repairable is True


@pytest.mark.skipif(not os.getenv("CLIKE_TEST_POSTGRES_URL"), reason="needs CLIKE_TEST_POSTGRES_URL")
def test_real_postgres_database_is_created_fresh_every_run():
    import psycopg

    admin = os.environ["CLIKE_TEST_POSTGRES_URL"]
    spec = ee.VariableSpec(name="APP_TEST_DATABASE_URL", provision="postgres_database")
    url = ee.provision_postgres(spec, admin, "clike_selftest", "REQ-001")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE TABLE t (x int)")
    url_again = ee.provision_postgres(spec, admin, "clike_selftest", "REQ-001")
    assert url_again == url
    with psycopg.connect(url, autocommit=True) as conn:  # recreated: the table is gone
        assert conn.execute("SELECT to_regclass('public.t')").fetchone()[0] is None
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.rsplit("/", 1)[1]}" WITH (FORCE)')


# --- JS/TS locked-test fixes (gate_integrity) --------------------------------------------------

TS_TEST = """import { describe, expect, it } from 'vitest';
const env: NodeJS.ProcessEnv = {
  APP_ENV: 'local',
};
describe('forward', () => {
  it('denies foreign origins', () => {
    expect(forward(env)).toBe(403);
  });
});
"""


def _ts_issue(tmp_path, new, evidence):
    import hashlib
    from services.gate_integrity import _test_change_issue

    path = tmp_path / "server-api.test.ts"
    return _test_change_issue(path, hashlib.sha256(TS_TEST.encode()).hexdigest(), new, evidence, TS_TEST)


def test_ts_test_fixture_fix_is_accepted_with_compiler_evidence(tmp_path):
    fixed = TS_TEST.replace("  APP_ENV: 'local',", "  NODE_ENV: 'test', APP_ENV: 'local',")
    evidence = "test/server-api.test.ts(2,7): error TS2741: Property 'NODE_ENV' is missing"
    assert _ts_issue(tmp_path, fixed, evidence) is None
    assert _ts_issue(tmp_path, fixed, "") is not None  # no evidence that the test is wrong
    assert _ts_issue(tmp_path, fixed.replace("toBe(403)", "toBe(200)"), evidence) is not None
    assert _ts_issue(tmp_path, fixed.replace("it('denies", "it.skip('denies"), evidence) is not None
    assert _ts_issue(tmp_path, fixed.replace("denies foreign origins", "other"), evidence) is not None


def test_js_runtime_error_in_the_test_file_is_evidence(tmp_path):
    fixed = TS_TEST.replace("APP_ENV: 'local',", "APP_ENV: 'local', EXTRA: '1',")
    evidence = "TypeError: forward is not a function\n ❯ test/server-api.test.ts:7:12"
    assert _ts_issue(tmp_path, fixed, evidence) is None
