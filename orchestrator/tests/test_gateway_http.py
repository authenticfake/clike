"""Shared orchestrator→gateway client (WP7.12): token, timeout, connect-only retries."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import httpx  # noqa: E402

from services import gateway_http  # noqa: E402

TOKEN = "t" * 48


class GatewayHttpTests(unittest.TestCase):
    def _post(self, handler, **kw):
        async def go():
            try:
                return await gateway_http.post("http://gateway:8000/v1/harper/run", json={"a": 1}, timeout=5.0, **kw)
            finally:
                await gateway_http.aclose()

        with patch.object(gateway_http, "TRANSPORT", httpx.MockTransport(handler)), patch.object(
            gateway_http, "BACKOFF_BASE_S", 0
        ), patch.dict("os.environ", {"CLIKE_API_TOKEN": TOKEN}):
            return asyncio.run(go())

    def test_sends_the_service_token_which_cannot_be_overridden(self):
        seen = {}

        def handler(request):
            seen.update(request.headers)
            return httpx.Response(200, json={"ok": True})

        r = self._post(handler, headers={"Authorization": "Bearer other", "X-CLike-Provider": "openai"})
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(seen["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(seen["x-clike-provider"], "openai")

    def test_retries_connect_errors_then_succeeds(self):
        attempts = []

        def handler(request):
            attempts.append(1)
            if len(attempts) < 3:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={})

        self.assertEqual(self._post(handler).status_code, 200)
        self.assertEqual(len(attempts), 3)

    def test_gives_up_after_bounded_connect_retries(self):
        attempts = []

        def handler(request):
            attempts.append(1)
            raise httpx.ConnectError("refused", request=request)

        with self.assertRaises(httpx.ConnectError):
            self._post(handler)
        self.assertEqual(len(attempts), gateway_http.CONNECT_RETRIES + 1)

    def test_read_timeouts_and_http_errors_are_not_retried(self):
        for outcome in ("timeout", "500"):
            attempts = []

            def handler(request, outcome=outcome):
                attempts.append(1)
                if outcome == "timeout":
                    raise httpx.ReadTimeout("slow", request=request)
                return httpx.Response(500, json={})

            with self.subTest(outcome):
                if outcome == "timeout":
                    with self.assertRaises(httpx.ReadTimeout):
                        self._post(handler)
                else:
                    self.assertEqual(self._post(handler).status_code, 500)
                self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
