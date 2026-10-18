"""Orchestrator MCP (H2): Harper read tools can target a CLike project, confined like eval/gate."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class McpProjectRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-mcp-")).resolve()
        self.proj = self.tmp / "projects" / "pingboard"
        (self.proj / "docs" / "harper").mkdir(parents=True)
        (self.proj / "docs" / "harper" / "plan.json").write_text(json.dumps({"reqs": [{"id": "REQ-001", "title": "t", "status": "open"}]}))
        self.env = patch.dict(os.environ, {"DEV_FOLDER": str(self.tmp / "projects")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_req_list_reads_the_given_project(self):
        import mcp_server

        result = mcp_server.harper_req_list(project_root=str(self.proj))
        self.assertIn("REQ-001", json.dumps(result))

    def test_project_outside_the_projects_dir_is_refused(self):
        import mcp_server

        with self.assertRaises(ValueError):
            mcp_server.harper_req_list(project_root="/etc")


if __name__ == "__main__":
    unittest.main()


class McpHardeningTests(unittest.TestCase):
    """MCP audit 2026-10-18: confined run ids, project-scoped reports, OAuth discovery, tools/list."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-mcp-h-")).resolve()
        self.proj = self.tmp / "projects" / "pingboard"
        (self.proj / "runs" / "eval" / "REQ-001").mkdir(parents=True)
        (self.proj / "runs" / "eval" / "REQ-001" / "report_REQ-001_1.json").write_text(json.dumps({"status": "FAIL"}))
        (self.proj / "runs" / "eval" / "REQ-001" / "report_REQ-001_2.json").write_text(json.dumps({"status": "PASS"}))
        self.runs = self.tmp / "runs"
        (self.runs / "state" / "audit").mkdir(parents=True)
        (self.runs / "r1").mkdir()
        self.env = patch.dict(os.environ, {"DEV_FOLDER": str(self.tmp / "projects"), "RUNS_DIR": str(self.runs),
                                          "CLIKE_API_TOKEN": "t" * 48})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_ids_cannot_leave_the_runs_directory_or_read_clike_state(self):
        import mcp_server

        with patch.object(mcp_server, "_runs_root", return_value=self.runs):
            for bad in ("..", "../etc", "/etc", "state", "a/b"):
                with self.assertRaises(ValueError, msg=bad):
                    mcp_server.runs_read(bad)
                with self.assertRaises(ValueError, msg=bad):
                    mcp_server.eval_read_summary(run_id=bad)
            self.assertNotIn("state", [r["run_id"] for r in mcp_server.runs_list()["runs"]])

    def test_reports_are_read_from_the_given_project(self):
        import mcp_server

        result = mcp_server.eval_read_summary(project_root=str(self.proj), req_id="REQ-001")
        self.assertTrue(result["ok"])
        self.assertEqual(result["eval_summary"]["status"], "PASS")  # the latest report
        self.assertIsNone(mcp_server.gate_read_decision(project_root=str(self.proj), req_id="REQ-001")["path"])

    def test_oauth_discovery_is_404_without_auth_and_mcp_needs_the_token(self):
        from starlette.testclient import TestClient
        from app import app

        client = TestClient(app, base_url="http://localhost:8080")
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp",
                     "/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
            self.assertEqual(client.get(path).status_code, 404, path)
        self.assertEqual(client.post("/register", json={}).status_code, 404)
        self.assertEqual(client.post("/mcp/", json={}).status_code, 401)

    def test_tools_list_over_streamable_http(self):
        from starlette.testclient import TestClient
        from app import app

        headers = {"Authorization": f"Bearer {'t' * 48}", "Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        with TestClient(app, base_url="http://localhost:8080") as client:
            init = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
            self.assertEqual(init.status_code, 200, init.text)
            listed = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            self.assertEqual(listed.status_code, 200, listed.text)
            names = {t["name"] for t in listed.json()["result"]["tools"]}
            for expected in ("harper_plan_read", "harper_req_next", "harper_status_read", "eval_read_summary", "gate_read_decision", "rag_search"):
                self.assertIn(expected, names)
