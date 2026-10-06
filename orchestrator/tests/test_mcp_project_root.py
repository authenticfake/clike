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
