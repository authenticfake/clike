"""Eval sandbox service and orchestrator routing (WP6.4)."""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import httpx  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

TOKEN = "s" * 48
REQ = "REQ-001"
_SECRET_RE = re.compile(r"(API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY|ACCESS_KEY)", re.I)


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not _SECRET_RE.search(k)}
    env.update(extra)
    return env


def _load_sandbox_app():
    import eval_sandbox_app

    return importlib.reload(eval_sandbox_app)


class EvalSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-sandbox-")).resolve()
        cls.projects = cls.tmp / "projects"
        cls.proj = cls.projects / "demo"
        kit = cls.proj / "runs" / "kit" / REQ
        (kit / "ci").mkdir(parents=True)
        (kit / "test").mkdir()
        (kit / "ci" / "LTC.json").write_text(
            json.dumps({"req_id": REQ, "checks": [{"id": "hello", "command": "echo from-sandbox", "blocking": True}]})
        )
        (cls.tmp / "outside").mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_refuses_to_start_with_credentials_in_env(self):
        env = _clean_env(OPENAI_API_KEY="sk-test", PYTHONPATH=str(ORCHESTRATOR_ROOT))
        proc = subprocess.run(
            [sys.executable, "-c", "import eval_sandbox_app"],
            cwd=ORCHESTRATOR_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refuses to start with credentials", proc.stderr)

    def test_runs_the_workspace_profile_and_is_confined(self):
        with patch.dict(os.environ, _clean_env(DEV_FOLDER=str(self.projects)), clear=True):
            sandbox = TestClient(_load_sandbox_app().app)
            ok = sandbox.post("/run", json={"project_root": str(self.proj), "profile": f"runs/kit/{REQ}/ci/LTC.json", "req_id": REQ})
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertEqual(ok.json()["cases"][-1]["stdout"].strip(), "from-sandbox")
            outside = sandbox.post("/run", json={"project_root": str(self.tmp / "outside"), "profile": "LTC.json"})
            self.assertEqual(outside.status_code, 403)
            traversal = sandbox.post("/run", json={"project_root": str(self.proj), "profile": "../../outside/x.json"})
            self.assertEqual(traversal.status_code, 400)
            missing = sandbox.post("/run", json={"project_root": str(self.proj), "profile": "nope.json"})
            self.assertEqual(missing.status_code, 404)

    def test_report_roundtrip(self):
        from eval_runner import EvalCase, EvalReport, report_from_dict, report_to_dict

        rep = EvalReport(profile="p", req_id=REQ, mode="auto", passed=1, failed=0,
                         cases=[EvalCase(name="c", passed=True, code=0, stdout="o", stderr="")], status="PASS")
        self.assertEqual(report_from_dict(json.loads(json.dumps(report_to_dict(rep)))), rep)

    def test_orchestrator_routes_eval_and_gate_to_the_sandbox(self):
        with patch.dict(os.environ, _clean_env(DEV_FOLDER=str(self.projects)), clear=True):
            sandbox = TestClient(_load_sandbox_app().app)

        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append(url)
            with patch.dict(os.environ, {"DEV_FOLDER": str(self.projects)}):
                r = sandbox.post("/run", json=json)
            return httpx.Response(r.status_code, content=r.content, headers={"content-type": "application/json"})

        env = {
            "CLIKE_API_TOKEN": TOKEN,
            "DEV_FOLDER": str(self.projects),
            "CLIKE_STATE_DIR": str(self.tmp / "state"),
            "CLIKE_EVAL_SANDBOX_URL": "http://eval-sandbox:8090",
        }
        with patch.dict(os.environ, env):
            from app import app
            from routes import routes_eval

            client = TestClient(app, base_url="http://127.0.0.1:8080")
            params = {"profile": f"runs/kit/{REQ}/ci/LTC.json", "project_root": str(self.proj), "req_id": REQ}
            auth = {"Authorization": f"Bearer {TOKEN}"}
            with patch.object(routes_eval.httpx, "post", side_effect=fake_post):
                ev = client.post("/v1/eval/run", params=params, headers=auth)
                gate = client.post("/v1/gate/check", params=params, headers=auth)
            self.assertEqual((ev.status_code, ev.json()["executor"]), (200, "sandbox"), ev.text)
            self.assertEqual((gate.json()["gate"], gate.json()["executor"]), ("PASS", "sandbox"), gate.text)
            self.assertEqual(calls, ["http://eval-sandbox:8090/run"] * 2)

            def unreachable(*_a, **_k):
                raise httpx.ConnectError("down")

            with patch.object(routes_eval.httpx, "post", side_effect=unreachable):
                down = client.post("/v1/eval/run", params=params, headers=auth)
            self.assertEqual(down.status_code, 503)


if __name__ == "__main__":
    unittest.main()
