"""Service authentication for CLike HTTP services (WP3).

Kept byte-identical in orchestrator/utils/ and gateway/utils/ (checked by
tests) until both services share a package.

* ``ServiceAuthMiddleware``: pure ASGI middleware. Every HTTP/WebSocket
  request needs ``Authorization: Bearer <CLIKE_API_TOKEN>`` except the
  configured open paths. Fails closed: when the token is not configured all
  protected requests get 503. Also rejects unexpected ``Host`` headers
  (DNS rebinding protection).
* Optional cookie auth for browser pages (telemetry UI): an ``HttpOnly``,
  ``SameSite=Strict`` cookie is accepted on GET requests under
  ``cookie_prefixes`` only.
* ``internal_auth_headers()``: headers for service-to-service calls.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Iterable, Optional

TOKEN_ENV = "CLIKE_API_TOKEN"
ALLOWED_HOSTS_ENV = "CLIKE_ALLOWED_HOSTS"
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1", "gateway", "orchestrator")
COOKIE_NAME = "clike_token"
MIN_TOKEN_LENGTH = 32

log = logging.getLogger("clike.auth")


def configured_token() -> str:
    return (os.getenv(TOKEN_ENV) or "").strip()


def internal_auth_headers() -> dict:
    token = configured_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def allowed_hosts() -> set[str]:
    raw = os.getenv(ALLOWED_HOSTS_ENV)
    hosts = [h.strip().lower() for h in raw.split(",")] if raw else list(DEFAULT_ALLOWED_HOSTS)
    return {h for h in hosts if h}


def _host_without_port(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # [::1]:8080
        return host[1 : host.find("]")] if "]" in host else host
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def tokens_match(presented: Optional[str], expected: str) -> bool:
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def _bearer(headers: dict) -> Optional[str]:
    value = headers.get(b"authorization", b"").decode("latin-1").strip()
    if value[:7].lower() == "bearer ":
        return value[7:].strip()
    return None


def _cookie(headers: dict, name: str) -> Optional[str]:
    raw = headers.get(b"cookie", b"").decode("latin-1")
    for part in raw.split(";"):
        key, _, val = part.strip().partition("=")
        if key == name:
            return val
    return None


class ServiceAuthMiddleware:
    def __init__(
        self,
        app,
        *,
        open_paths: Iterable[str] = ("/health",),
        open_prefixes: Iterable[str] = (),
        cookie_prefixes: Iterable[str] = (),
    ):
        self.app = app
        self.open_paths = set(open_paths)
        self.open_prefixes = tuple(open_prefixes)
        self.cookie_prefixes = tuple(cookie_prefixes)
        token = configured_token()
        if not token:
            log.error("%s is not set: all protected endpoints will answer 503", TOKEN_ENV)
        elif len(token) < MIN_TOKEN_LENGTH:
            log.warning("%s is shorter than %d characters", TOKEN_ENV, MIN_TOKEN_LENGTH)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        host = _host_without_port(headers.get(b"host", b"").decode("latin-1"))
        if host not in allowed_hosts():
            return await _deny(scope, send, 403, "host_not_allowed", "Host header not allowed")

        path = scope.get("path") or ""
        if path in self.open_paths or any(path.startswith(p) for p in self.open_prefixes):
            return await self.app(scope, receive, send)

        expected = configured_token()
        if not expected:
            return await _deny(scope, send, 503, "auth_not_configured", f"{TOKEN_ENV} is not configured on the server")

        presented = _bearer(headers)
        if presented is None and scope.get("method") == "GET" and any(path.startswith(p) for p in self.cookie_prefixes):
            presented = _cookie(headers, COOKIE_NAME)
        if not tokens_match(presented, expected):
            return await _deny(scope, send, 401, "unauthorized", "Missing or invalid service token")
        return await self.app(scope, receive, send)


async def _deny(scope, send, status: int, code: str, message: str):
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"code": code, "detail": message}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if status == 401:
        headers.append((b"www-authenticate", b'Bearer realm="clike"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
