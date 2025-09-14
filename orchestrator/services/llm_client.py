# services/llm_client.py
import os
import httpx
import logging
from config import settings


log = logging.getLogger("llm")

# Timeout più alto per cold-start: 120s di read/write/pool
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=120.0)

async def call_gateway_chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
    base_url: str | None = None,
    timeout: float | None = None,
) -> str:
    import httpx
    base = (base_url or str(getattr(settings, "GATEWAY_URL", "http://localhost:8000"))).rstrip("/")
    to = float(timeout or float(getattr(settings, "REQUEST_TIMEOUT_S", 60)))
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=to) as client:
        r = await client.post(f"{base}/v1/chat/completions", json=body)
        r.raise_for_status()
        data = r.json() or {}
        # Supporto OpenAI-style
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        # Supporto gateway che risponde "text"
        if "text" in data:
            return data["text"]
        # Fallback
        return str(data)


async def llm_transform_code(model: str, lang: str, code: str, instruction: str) -> str:
    """
    Trasformazione “code-in / code-out”: il modello deve restituire **solo** codice.
    """
    sys = "You are Clike, an expert software engineering assistant. Output only the transformed code, no prose."
    usr = f"Language: {lang}\nInstruction: {instruction}\nCode:\n```{lang}\n{code}\n```"
    return await call_gateway_chat(model, [{"role":"system","content":sys},{"role":"user","content":usr}], temperature=0.1)
