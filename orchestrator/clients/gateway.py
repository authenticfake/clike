# -*- coding: utf-8 -*-
from typing import Any, Dict, List
import asyncio, httpx, time
from orchestrator.config import settings

class GatewayClient:
    def __init__(self):
        self.base = settings.GATEWAY_URL.rstrip("/")

    async def _retry(self, fn, attempts: int | None = None):
        attempts = attempts or settings.RETRY_MAX_ATTEMPTS
        backoff = settings.RETRY_BACKOFF_S
        for i in range(attempts):
            try:
                return await fn()
            except httpx.HTTPError as e:
                if i == attempts - 1:
                    raise
                await asyncio.sleep(backoff)

    async def list_models(self) -> List[Dict[str, Any]]:
        async def _call():
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
                # Try /models then /v1/models
                for path in ("/models", "/v1/models"):
                    r = await client.get(self.base + path)
                    if r.status_code == 200:
                        data = r.json()
                        return data.get("models", data)  # be tolerant
                raise httpx.HTTPError("models endpoint not available")
        return await self._retry(_call)

    async def chat(self, model: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        async def _call():
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
                body = {"model": model, "messages": messages, "temperature": 0.2}
                r = await client.post(self.base + "/v1/chat/completions", json=body)
                r.raise_for_status()
                data = r.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                return {"text": text, "usage": usage}
        return await self._retry(_call)

gateway = GatewayClient()
