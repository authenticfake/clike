"""Gateway → orchestrator → extension error contract (WP7).

401/503 with a top-level ``code`` of ``unauthorized``/``auth_not_configured`` are reserved for the
service token. Gateway failures reach the client with a status and code it can act on, for every
Harper phase, instead of a generic 500.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.testclient import TestClient  # noqa: E402

TOKEN = "e" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BODY = {"project_id": "p", "model": "openai:gpt-5.4-mini", "docRoot": "docs/harper",
        "messages": [{"role": "user", "content": "x"}], "executionPreference": "cloud_only", "runId": "r"}


class GatewayErrorContractTests(unittest.TestCase):
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

    def _phase(self, phase, exc):
        async def failing_post_json(path, payload):
            raise exc

        async def no_selection(**_kw):
            return {}

        policy = {"requested": "cloud_only", "selected": "cloud", "reason": "test", "phase_supported": True}
        with patch.object(self.harper, "_post_json", side_effect=failing_post_json), patch.object(
            self.harper, "resolve_llm_selection", side_effect=no_selection
        ), patch.object(self.harper, "resolve_execution_policy", return_value=policy):
            return self.client.post(f"/v1/harper/{phase}", json={**BODY, "phase": phase, "cmd": phase}, headers=AUTH)

    def test_provider_not_configured_reaches_the_client_for_every_phase(self):
        err = self.harper.GatewayUpstreamError(503, "provider 'anthropic' is not configured", "provider_not_configured")
        for phase in ("idea", "spec", "plan", "finalize"):
            with self.subTest(phase):
                r = self._phase(phase, err)
                self.assertEqual(r.status_code, 503, r.text)
                self.assertEqual(r.json()["code"], "provider_not_configured")
                self.assertIn("not configured", r.json()["detail"])

    def test_gateway_auth_failure_is_502_not_401(self):
        r = self._phase("spec", self.harper.GatewayUpstreamError(401, "Missing or invalid service token", "unauthorized"))
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["upstream_status"], 401)

    def test_rate_limit_stays_429_and_server_errors_are_502(self):
        self.assertEqual(self._phase("plan", self.harper.GatewayUpstreamError(429, "rate")).status_code, 429)
        r = self._phase("idea", self.harper.GatewayUpstreamError(500, "boom"))
        self.assertEqual((r.status_code, r.json()["code"]), (502, "gateway_error"))

    def test_unknown_model_is_400(self):
        from routes import v1
        from services.llm_contracts import ModelSelectionError

        async def unknown(**_kw):
            raise ModelSelectionError("model 'nope' not found in catalog")

        with patch.object(v1, "resolve_llm_selection", side_effect=unknown):
            r = self.client.post("/v1/chat", json={"model": "nope", "messages": [{"role": "user", "content": "hi"}]}, headers=AUTH)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(r.json(), {"code": "model_selection_error", "detail": "model 'nope' not found in catalog"})

    def test_chat_keeps_the_provider_cause(self):
        import httpx
        from routes import v1

        req = httpx.Request("POST", "http://gateway:8000/v1/chat/completions")
        cases = [
            (502, {"detail": {"message": "provider call failed", "errors": ["anthropic:400:invalid_request_error:Your credit balance is too low"]}}, 502),
            (503, {"detail": {"code": "provider_not_configured", "message": "provider 'anthropic' is not configured"}}, 503),
            (429, {"detail": "rate limited"}, 429),
            (401, {"code": "unauthorized", "detail": "Missing or invalid service token"}, 502),
        ]
        for upstream, body, expected in cases:
            with self.subTest(upstream):
                exc = httpx.HTTPStatusError("x", request=req, response=httpx.Response(upstream, json=body, request=req))
                http_exc = v1._gateway_chat_failure(exc)
                self.assertEqual(http_exc.status_code, expected)
                self.assertIn(f"({upstream})", http_exc.detail)
        self.assertIn("credit balance is too low", v1._gateway_chat_failure(
            httpx.HTTPStatusError("x", request=req, response=httpx.Response(502, json=cases[0][1], request=req))).detail)


if __name__ == "__main__":
    unittest.main()
