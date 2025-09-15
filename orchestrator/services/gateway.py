# Thin client to the Gateway (OpenAI-compatible). Comments in English.
import httpx
from typing import Dict, Any
from config import settings

class GatewayClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = base_url or settings.gateway_url
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.client.post("/v1/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()

    def embeddings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.client.post("/v1/embeddings", json=payload)
        r.raise_for_status()
        return r.json()

    def list_models(self) -> Dict[str, Any]:
        r = self.client.get("/v1/models")
        r.raise_for_status()
        return r.json()