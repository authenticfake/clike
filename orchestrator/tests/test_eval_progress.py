"""Live progress of an eval in flight (the chat's progress bar): the runner's registry, the
sandbox's GET /progress and the orchestrator's GET /v1/eval/progress."""
import importlib
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

from eval_runner import EvalRunner, eval_progress

TOKEN = "s" * 48


def _project(tmp_path: Path, checks):
    kit = tmp_path / "runs" / "kit" / "REQ-001"
    (kit / "ci").mkdir(parents=True)
    (kit / "src").mkdir()
    ltc = {"req_id": "REQ-001", "checks": [{"id": n, "command": c, "blocking": True} for n, c in checks]}
    return kit / "ci" / "LTC.json", ltc


def test_the_top_level_run_records_its_checks(tmp_path: Path):
    profile, ltc = _project(tmp_path, [("one", "true"), ("two", "true"), ("three", "false")])
    EvalRunner(tmp_path).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001")
    p = eval_progress(tmp_path, "req-001")
    assert p["state"] == "done" and p["phase"] == "done" and not p["partial"]
    assert (p["checks_total"], p["checks_done"]) == (3, 3)
    assert p["failed"] >= 1 and p["passed"] >= 2
    assert p["ended_at"] and p["elapsed_s"] >= 0


def test_the_progress_is_readable_while_a_check_runs(tmp_path: Path):
    profile, ltc = _project(tmp_path, [("quick", "true"), ("slow", "sleep 1.5"), ("last", "true")])
    t = threading.Thread(target=lambda: EvalRunner(tmp_path).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001"))
    t.start()
    seen = None
    deadline = time.time() + 10
    while time.time() < deadline:
        p = eval_progress(tmp_path, "REQ-001")
        if p and p.get("current") == "slow":
            seen = p
            break
        time.sleep(0.05)
    t.join()
    assert seen is not None, "the running check was never visible"
    assert seen["state"] == "running" and seen["phase"] == "checks"
    assert (seen["checks_done"], seen["checks_total"]) == (1, 3)
    assert eval_progress(tmp_path, "REQ-001")["state"] == "done"


def test_nested_runners_and_partial_runs(tmp_path: Path):
    profile, ltc = _project(tmp_path, [("one", "true")])
    EvalRunner(tmp_path, eval_key="REQ-002/regression/REQ-001", regression=True).run_profile(
        profile=str(profile), ltc=ltc, req_id="REQ-001")
    assert eval_progress(tmp_path, "REQ-001") is None, "a regression runner never writes the progress"
    EvalRunner(tmp_path).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001", checks=["one"])
    assert eval_progress(tmp_path, "REQ-001")["partial"] is True


def test_a_cancelled_run_and_the_regression_reqs(tmp_path: Path):
    profile, ltc = _project(tmp_path, [("one", "true")])
    cancel = threading.Event()
    cancel.set()
    EvalRunner(tmp_path, cancel_event=cancel).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001")
    assert eval_progress(tmp_path, "REQ-001")["state"] == "cancelled"

    runner = EvalRunner(tmp_path)
    runner._progress_start("REQ-009", partial=False)
    runner._progress(phase="regression", regression_total=2, regression_done=0, regression_current=[])
    runner._progress_regression("REQ-001", started=True)
    runner._progress_regression("REQ-002", started=True)
    assert eval_progress(tmp_path, "REQ-009")["regression_current"] == ["REQ-001", "REQ-002"]
    runner._progress_regression("REQ-001", started=False)
    p = eval_progress(tmp_path, "REQ-009")
    assert (p["regression_done"], p["regression_current"]) == (1, ["REQ-002"])


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if "KEY" not in k.upper() and "TOKEN" not in k.upper() and "SECRET" not in k.upper()}
    env.update(extra)
    return env


def test_sandbox_and_orchestrator_endpoints(tmp_path: Path):
    projects = tmp_path / "projects"
    proj = projects / "demo"
    profile, ltc = _project(proj, [("one", "true")])
    (tmp_path / "outside").mkdir()
    with patch.dict(os.environ, _clean_env(DEV_FOLDER=str(projects)), clear=True):
        import eval_sandbox_app
        sandbox = TestClient(importlib.reload(eval_sandbox_app).app)
        assert sandbox.get("/progress", params={"project_root": str(proj), "req_id": "REQ-404"}).json() == {"state": "unknown"}
        assert sandbox.get("/progress", params={"project_root": str(tmp_path / "outside"), "req_id": "REQ-001"}).status_code == 403
        EvalRunner(proj).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001")
        assert sandbox.get("/progress", params={"project_root": str(proj), "req_id": "REQ-001"}).json()["state"] == "done"

    calls = []

    async def fake_get(_client, url, params=None, **_kw):
        calls.append((url, params))
        with patch.dict(os.environ, {"DEV_FOLDER": str(projects)}):
            r = sandbox.get("/progress", params=params)
        return httpx.Response(r.status_code, content=r.content, headers={"content-type": "application/json"})

    env = {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(projects), "CLIKE_STATE_DIR": str(tmp_path / "state")}
    auth = {"Authorization": f"Bearer {TOKEN}"}
    params = {"project_root": str(proj), "req_id": "REQ-001"}
    with patch.dict(os.environ, {**env, "CLIKE_EVAL_SANDBOX_URL": "http://eval-sandbox:8090"}):
        from app import app
        from routes import routes_eval
        client = TestClient(app, base_url="http://127.0.0.1:8080")
        with patch.object(routes_eval.httpx.AsyncClient, "get", new=fake_get):
            via_sandbox = client.get("/v1/eval/progress", params=params, headers=auth)
        assert via_sandbox.status_code == 200 and via_sandbox.json()["state"] == "done", via_sandbox.text
        assert calls and calls[0][0] == "http://eval-sandbox:8090/progress"

        async def unreachable(*_a, **_k):
            raise httpx.ConnectError("down")
        with patch.object(routes_eval.httpx.AsyncClient, "get", new=unreachable):
            assert client.get("/v1/eval/progress", params=params, headers=auth).json() == {"state": "unknown"}
        assert client.get("/v1/eval/progress", params=params).status_code in (401, 403), "the service token is required"
    with patch.dict(os.environ, env):
        os.environ.pop("CLIKE_EVAL_SANDBOX_URL", None)
        local = client.get("/v1/eval/progress", params=params, headers=auth)
        assert local.json()["state"] == "done", local.text
