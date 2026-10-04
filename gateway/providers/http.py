"""Shared HTTP plumbing for provider calls (WP7).

* ``post_with_retries``: bounded retries with exponential backoff and jitter on
  rate limits / transient upstream errors (429, 500, 502, 503, 504, 529) and on
  connection failures. Read timeouts are NOT retried: a long generation that
  timed out would be paid again. ``Retry-After`` is honoured (capped).
* ``TRANSPORT``: tests set an ``httpx.MockTransport`` here to observe the exact
  requests a provider sends.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("gateway.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
RETRYABLE_EXCEPTIONS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout)
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 20.0
RETRY_AFTER_CAP_S = 30.0

TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


def _delay(attempt: int, response: Optional[httpx.Response]) -> float:
    if response is not None:
        raw = response.headers.get("retry-after")
        try:
            if raw is not None:
                return min(float(raw), RETRY_AFTER_CAP_S)
        except ValueError:
            pass
    if BACKOFF_BASE_S <= 0:
        return 0.0
    return min(BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, BACKOFF_BASE_S), BACKOFF_CAP_S)


async def post_with_retries(
    url: str,
    *,
    headers: Dict[str, str],
    json: Any,
    timeout: Optional[float],
    attempts: int = MAX_ATTEMPTS,
) -> httpx.Response:
    """POST with retries. Returns the last response; raises the last exception if none succeeded."""
    async with httpx.AsyncClient(timeout=timeout, transport=TRANSPORT) as client:
        for attempt in range(attempts):
            response: Optional[httpx.Response] = None
            try:
                response = await client.post(url, headers=headers, json=json)
            except RETRYABLE_EXCEPTIONS as exc:
                if attempt == attempts - 1:
                    raise
                log.warning("provider POST %s failed (%s); retry %d/%d", url, type(exc).__name__, attempt + 1, attempts - 1)
            else:
                if response.status_code not in RETRYABLE_STATUS or attempt == attempts - 1:
                    return response
                log.warning("provider POST %s -> %d; retry %d/%d", url, response.status_code, attempt + 1, attempts - 1)
            await asyncio.sleep(_delay(attempt, response))
    raise RuntimeError("unreachable")  # pragma: no cover
