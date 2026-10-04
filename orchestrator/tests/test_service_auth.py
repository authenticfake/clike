"""Security regression suite for the service perimeter (WP3)."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.routing import Route, WebSocketRoute  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from utils import service_auth  # noqa: E402
from utils.service_auth import ServiceAuthMiddleware, internal_auth_headers  # noqa: E402

TOKEN = "t" * 48
BASE = "http://127.0.0.1:8080"


async def _ok(request):
    return PlainTextResponse("ok")


async def _ws(websocket):
    await websocket.accept()
    await websocket.close()


def _client(token=TOKEN, **mw):
    app = Starlette(
        routes=[
            Route("/health", _ok),
            Route("/v1/data", _ok, methods=["GET", "POST"]),
            Route("/v1/metrics/x", _ok, methods=["GET", "POST"]),
            WebSocketRoute("/ws", _ws),
        ]
    )
    app.add_middleware(ServiceAuthMiddleware, **mw)
    env = {"CLIKE_API_TOKEN": token} if token is not None else {}
    with patch.dict(os.environ, env, clear=False):
        if token is None:
            os.environ.pop("CLIKE_API_TOKEN", None)
        return TestClient(app, base_url=BASE)


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


class ServiceAuthMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN})
        self._env.start()
        os.environ.pop("CLIKE_ALLOWED_HOSTS", None)

    def tearDown(self):
        self._env.stop()

    def test_missing_token_is_rejected(self):
        r = _client().get("/v1/data")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("www-authenticate"), 'Bearer realm="clike"')

    def test_wrong_token_is_rejected(self):
        self.assertEqual(_client().get("/v1/data", headers=_auth("x" * 48)).status_code, 401)

    def test_non_bearer_scheme_is_rejected(self):
        self.assertEqual(_client().get("/v1/data", headers={"Authorization": f"Basic {TOKEN}"}).status_code, 401)

    def test_valid_token_is_accepted(self):
        r = _client().post("/v1/data", headers=_auth())
        self.assertEqual((r.status_code, r.text), (200, "ok"))

    def test_bearer_scheme_is_case_insensitive(self):
        self.assertEqual(_client().get("/v1/data", headers={"Authorization": f"bearer {TOKEN}"}).status_code, 200)

    def test_health_is_open(self):
        self.assertEqual(_client().get("/health").status_code, 200)

    def test_fails_closed_without_configured_token(self):
        os.environ.pop("CLIKE_API_TOKEN", None)
        client = _client(token=None)
        self.assertEqual(client.get("/v1/data", headers=_auth()).status_code, 503)
        self.assertEqual(client.get("/health").status_code, 200)

    def test_unexpected_host_is_rejected_even_with_token(self):
        r = _client().get("/v1/data", headers={**_auth(), "Host": "evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_service_hosts_are_allowed(self):
        for host in ["localhost:8080", "127.0.0.1", "[::1]:8080", "gateway:8000", "orchestrator:8080"]:
            with self.subTest(host):
                self.assertEqual(_client().get("/v1/data", headers={**_auth(), "Host": host}).status_code, 200)

    def test_allowed_hosts_are_configurable(self):
        with patch.dict(os.environ, {"CLIKE_ALLOWED_HOSTS": "clike.internal"}):
            client = _client()
            self.assertEqual(client.get("/v1/data", headers={**_auth(), "Host": "clike.internal"}).status_code, 200)
            self.assertEqual(client.get("/v1/data", headers={**_auth(), "Host": "localhost"}).status_code, 403)

    def test_cookie_only_for_get_under_cookie_prefix(self):
        client = _client(cookie_prefixes=("/v1/metrics/",))
        cookie = {"Cookie": f"{service_auth.COOKIE_NAME}={TOKEN}"}
        self.assertEqual(client.get("/v1/metrics/x", headers=cookie).status_code, 200)
        self.assertEqual(client.post("/v1/metrics/x", headers=cookie).status_code, 401)
        self.assertEqual(client.get("/v1/data", headers=cookie).status_code, 401)

    def test_websocket_without_token_is_closed(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with _client().websocket_connect("/ws") as ws:
                ws.receive_text()

    def test_internal_headers(self):
        self.assertEqual(internal_auth_headers(), _auth())
        with patch.dict(os.environ, {"CLIKE_API_TOKEN": ""}):
            self.assertEqual(internal_auth_headers(), {})


class ServiceAuthModuleParityTests(unittest.TestCase):
    def test_gateway_copy_is_identical(self):
        orch = (ORCHESTRATOR_ROOT / "utils/service_auth.py").read_bytes()
        gw = (REPO_ROOT / "gateway/utils/service_auth.py").read_bytes()
        self.assertEqual(orch, gw, "gateway/utils/service_auth.py must stay identical to the orchestrator copy")


class OrchestratorAppPerimeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN, "CLIKE_MCP_SERVER_ENABLED": "true"})
        cls._env.start()
        os.environ.pop("CLIKE_ALLOWED_HOSTS", None)
        from app import app

        cls.app = app
        cls.client = TestClient(app, base_url=BASE, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def test_debug_is_off(self):
        self.assertFalse(self.app.debug)

    def test_health_open(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_protected_endpoints_require_token(self):
        for method, path in [
            ("GET", "/v1/harper/profiles"),
            ("POST", "/v1/eval/run"),
            ("POST", "/v1/apply"),
            ("POST", "/v1/harper/kit"),
            ("POST", "/mcp/"),
        ]:
            with self.subTest(path):
                self.assertEqual(self.client.request(method, path, json={}).status_code, 401)

    def test_git_helper_routes_are_gone(self):
        # WP7.13: the extension is the only Git actor; the orchestrator must not run git.
        for path in ("/git/branch", "/git/commit", "/git/pr"):
            with self.subTest(path):
                self.assertEqual(self.client.post(path, json={}, headers=_auth()).status_code, 404)

    def test_token_grants_access(self):
        self.assertEqual(self.client.get("/v1/harper/profiles", headers=_auth()).status_code, 200)

    def test_no_cors_for_foreign_origins(self):
        r = self.client.options(
            "/v1/eval/run",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in r.headers})
        r = self.client.get("/v1/harper/profiles", headers={**_auth(), "Origin": "https://evil.example"})
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in r.headers})

    def test_unhandled_errors_do_not_leak_details(self):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/__boom")
        async def boom():
            raise RuntimeError("secret internal detail /etc/passwd")

        self.app.include_router(router)
        r = self.client.get("/__boom", headers=_auth())
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret internal detail", r.text)
        self.assertEqual(r.json()["code"], "internal_error")
        self.assertTrue(r.json()["correlation_id"])


if __name__ == "__main__":
    unittest.main()
