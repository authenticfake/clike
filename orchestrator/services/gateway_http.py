"""Shared HTTP client from the orchestrator to the gateway (WP7.12).

One pooled ``httpx.AsyncClient`` per event loop (closed by the app lifespan), the service token
on every request, a timeout chosen by the caller, and a bounded retry **only** when the
connection cannot be established: nothing reached the gateway, so a retry cannot run (and bill)
an LLM call twice. Read timeouts and HTTP errors are never retried here; provider-level retries
live in the gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from utils.service_auth import internal_auth_headers

log = logging.getLogger("orchestrator.gateway_http")

CONNECT_RETRIES = int(os.getenv("CLIKE_GATEWAY_CONNECT_RETRIES", "2"))
BACKOFF_BASE_S = 0.5
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests inject an httpx.MockTransport

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _get_client() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        # A pooled client is bound to the loop that created it (asyncio.run in scripts/tests).
        _client = httpx.AsyncClient(transport=TRANSPORT)
        _client_loop = loop
    return _client


async def aclose() -> None:
    global _client, _client_loop
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client, _client_loop = None, None


async def post(
    url: str,
    *,
    json: Any,
    timeout: float | httpx.Timeout,
    headers: dict | None = None,
) -> httpx.Response:
    request_headers = {**(headers or {}), **internal_auth_headers()}  # the service token always wins
    attempt = 0
    while True:
        try:
            return await _get_client().post(url, json=json, timeout=timeout, headers=request_headers)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if attempt >= CONNECT_RETRIES:
                raise
            attempt += 1
            delay = BACKOFF_BASE_S * (2 ** (attempt - 1))
            log.warning("gateway connect failed (%s); retry %d/%d in %.1fs", type(exc).__name__, attempt, CONNECT_RETRIES, delay)
            await asyncio.sleep(delay)
