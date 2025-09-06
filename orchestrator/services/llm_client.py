# services/llm_client.py
import os
import httpx
import logging

log = logging.getLogger("llm")

# Timeout più alto per cold-start: 120s di read/write/pool
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=120.0)

async def call_gateway_chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 256,
    base_url: str,
    timeout: float = _DEFAULT_TIMEOUT
    ) -> str | None:
    """
    Chiama il gateway /v1/chat/completions.
    Se tolerate_timeout=True, su ReadTimeout ritorna None (consentendo il fallback).
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    log.info("[llm] POST %s model=%s payload_keys=%s", url, model, list(payload.keys()))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            # OpenAI-like format atteso dal gateway
            return data["choices"][0]["message"]["content"]
    except httpx.ReadTimeout as e:
        log.error("[llm] gateway call failed: ReadTimeout")
        raise
    except httpx.HTTPStatusError as e:
        # Log del body per capire "model not found" & co.
        body = e.response.text if e.response is not None else ""
        log.error("[llm] gateway %s -> %s body=%s", url, e.response.status_code if e.response else "NA", body)
        raise


async def llm_transform_code(model: str, lang: str, code: str, instruction: str) -> str:
    """
    Trasformazione “code-in / code-out”: il modello deve restituire **solo** codice.
    """
    sys = "You are Clike, an expert software engineering assistant. Output only the transformed code, no prose."
    usr = f"Language: {lang}\nInstruction: {instruction}\nCode:\n```{lang}\n{code}\n```"
    return await call_gateway_chat(model, [{"role":"system","content":sys},{"role":"user","content":usr}], temperature=0.1)
