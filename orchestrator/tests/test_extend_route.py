"""/v1/harper/extend carries the extend options (plan mode and the /idea --extend cascade) to the prompt."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.testclient import TestClient  # noqa: E402

TOKEN = "x" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class ExtendRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN})
        cls._env.start()
        from app import app
        from services import harper

        cls.harper = harper
        cls.client = TestClient(app, base_url="http://127.0.0.1:8080", raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def _run(self, extend, model="openai:gpt-5.4-mini"):
        sent = {}

        async def capture(path, payload):
            sent.update(payload)
            return {"ok": True, "phase": "extend", "files": []}

        async def no_selection(**_kw):
            return {}

        policy = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}
        body = {"cmd": "extend", "phase": "extend", "project_id": "p", "model": model,
                "messages": [{"role": "user", "content": "/idea --extend"}], "executionPreference": "cloud_only",
                "runId": "r", "extend": extend}
        with patch.object(self.harper, "_post_json", side_effect=capture), patch.object(
            self.harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(self.harper, "resolve_execution_policy", return_value=policy):
            response = self.client.post("/v1/harper/extend", json=body, headers=AUTH)
        return response, json.dumps(sent.get("composed_messages") or sent, ensure_ascii=False)

    def test_cascade_options_reach_the_cloud_prompt(self):
        response, prompt = self._run({"mode": "cascade", "release": "v2", "baseline": "v1", "fromAttachment": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Release cascade (/idea --extend)", prompt)
        self.assertIn("target release: v2", prompt)

    def test_adopt_rules_and_documents_reach_the_cloud_prompt_on_every_provider(self):
        extend = {"mode": "adopt", "survey_report": "docs/harper/ADOPT_2026-10-28.md",
                  "areas": [{"name": "aigateway", "root": "aigateway", "baseline_req": "REQ-001"}],
                  "documents": [{"path": "aigateway/README.md", "text": "# AI Gateway\n\nRoutes model calls."}]}
        for model in ("openai:gpt-5.4-mini", "anthropic:claude-sonnet-5-5"):
            response, prompt = self._run(extend, model=model)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Adoption of an existing project (/adopt)", prompt)
            self.assertIn("aigateway (root aigateway, baseline REQ-001)", prompt)
            self.assertIn("Project document: aigateway/README.md", prompt)
            self.assertIn("Routes model calls.", prompt)
            self.assertNotIn("Release cascade", prompt)

    def test_plan_mode_request_reaches_the_cloud_prompt(self):
        response, prompt = self._run({"anchorReq": "REQ-006", "rawInput": "loyalty points"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("- anchor: REQ-006", prompt)
        self.assertNotIn("Release cascade", prompt)
