# services/llm_client.py

import httpx
import logging
from config import settings
import  json, logging


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
    response_format=None, tools=None, tool_choice=None, profile=None
) -> str:
    import httpx
    base = (base_url or str(getattr(settings, "GATEWAY_URL", "http://localhost:8000"))).rstrip("/")
    to = float(timeout or float(getattr(settings, "REQUEST_TIMEOUT_S", 60)))
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_format is not None:
        body["response_format"] = response_format
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if profile is not None:
        body["profile"] = profile  # facoltativo, utile per osservabilità/routing coerente
   
    log.info("generate request: %s", json.dumps({
        "model": body.get("model"),
        "messages_len": len(messages),
        "has_response_format": bool(response_format),
        "has_tools": bool(tools)
    }))
    async with httpx.AsyncClient(timeout=to) as client:
        r = await client.post(f"{base}/v1/chat/completions", json=body)
        r.raise_for_status()
        data = r.json() or {}
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for seg in content:
                if isinstance(seg, dict):
                    if isinstance(seg.get("text"), str):
                        parts.append(seg["text"])
                    elif isinstance(seg.get("content"), str):
                        parts.append(seg["content"])
                elif isinstance(seg, str):
                    parts.append(seg)
            return "".join(parts).strip()
        if isinstance(content, str) and content.strip():
            return content.strip()

        # 2) Fallback legacy: lasciali
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        if "text" in data:
            return data["text"]

        return ""
    


async def llm_transform_code(model: str, lang: str, code: str, instruction: str) -> str:
    """
    Trasformazione “code-in / code-out”: il modello deve restituire **solo** codice.
    """
    sys = "You are Clike, an expert software engineering assistant. Output only the transformed code, no prose."
    usr = f"Language: {lang}\nInstruction: {instruction}\nCode:\n```{lang}\n{code}\n```"
    return await call_gateway_chat(model, [{"role":"system","content":sys},{"role":"user","content":usr}], temperature=0.1)
