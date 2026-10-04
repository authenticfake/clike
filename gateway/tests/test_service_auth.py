"""Gateway perimeter regression suite (WP3): token auth, no CORS, telemetry UI cookie login."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "g" * 48
BASE = "http://127.0.0.1:8000"


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


class GatewayPerimeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="clike-gw-auth-")
        (Path(cls._tmp) / "demo.json").write_text(json.dumps({"phase": "spec", "timestamp": 1}) + "\n")
        cls._env = patch.dict(
            os.environ,
            {
                "CLIKE_API_TOKEN": TOKEN,
                "MODELS_CONFIG": str(REPO_ROOT / "configs/models.yaml"),
                "HARPER_TELEMETRY_DIR": cls._tmp,
            },
        )
        cls._env.start()
        os.environ.pop("CLIKE_ALLOWED_HOSTS", None)
        from app import app

        cls.app = app
        cls.client = TestClient(app, base_url=BASE, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def test_health_open(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_protected_endpoints_require_token(self):
        for method, path in [
            ("GET", "/v1/models"),
            ("POST", "/v1/chat/completions"),
            ("POST", "/v1/harper/run"),
            ("POST", "/v1/embeddings"),
            ("GET", "/v1/metrics/harper/projects"),
        ]:
            with self.subTest(path):
                self.assertEqual(self.client.request(method, path, json={}).status_code, 401)

    def test_token_grants_access(self):
        self.assertEqual(self.client.get("/v1/models", headers=_auth()).status_code, 200)

    def test_no_cors_for_foreign_origins(self):
        r = self.client.options(
            "/v1/harper/run",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in r.headers})

    def test_foreign_host_rejected(self):
        self.assertEqual(self.client.get("/v1/models", headers={**_auth(), "Host": "evil.example"}).status_code, 403)

    def test_telemetry_ui_shell_is_open_and_escapes_output(self):
        r = self.client.get("/v1/metrics/harper/ui")
        self.assertEqual(r.status_code, 200)
        self.assertIn("function esc(", r.text)
        self.assertIn("/v1/metrics/login", r.text)

    def test_telemetry_login_sets_strict_httponly_cookie(self):
        client = TestClient(self.app, base_url=BASE)
        self.assertEqual(client.post("/v1/metrics/login", json={"token": "wrong" * 10}).status_code, 401)
        r = client.post("/v1/metrics/login", json={"token": TOKEN})
        self.assertEqual(r.status_code, 204)
        cookie = r.headers.get("set-cookie", "").lower()
        for attr in ("httponly", "samesite=strict", "path=/v1/metrics"):
            self.assertIn(attr, cookie)
        # cookie authorizes telemetry reads only
        self.assertEqual(client.get("/v1/metrics/harper/projects").status_code, 200)
        self.assertEqual(client.get("/v1/models").status_code, 401)
        # logout clears it
        client.post("/v1/metrics/logout")
        client.cookies.clear()
        self.assertEqual(client.get("/v1/metrics/harper/projects").status_code, 401)

    def test_unhandled_errors_do_not_leak_details(self):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/__boom")
        async def boom():
            raise RuntimeError("secret internal detail")

        self.app.include_router(router)
        r = self.client.get("/__boom", headers=_auth())
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret internal detail", r.text)
        self.assertTrue(r.json()["correlation_id"])


if __name__ == "__main__":
    unittest.main()
