# services/llm_client.py

import httpx
import logging
from config import settings
import  json, logging


log = logging.getLogger("orcehstrator:service:llm_client")
# orchestrator/services/llm_client.py

import os, json, httpx, asyncio
from typing import Any, Dict, List, Optional

# ... i tuoi import/utility già presenti ...

async def call_gateway_chat_json(
    model: str,
    messages: List[Dict[str, Any]],
    base_url: str = "http://localhost:8000",
    timeout: float = 60.0,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
    profile: Optional[str] = None
) -> Dict[str, Any]:
    """
    Variante che ritorna direttamente il JSON del gateway.
    Non tocca la call esistente (che torna stringa).
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        # allineo sia max_tokens che max_completion_tokens per GPT-5
        payload["max_tokens"] = int(max_tokens)
        if str(model).startswith("gpt-5"):
            payload["max_completion_tokens"] = int(max_tokens)

    if response_format is not None:
        payload["response_format"] = response_format
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if profile is not None:
        payload["profile"] = profile

    url = base_url.rstrip("/") + "/v1/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        # Se il provider risponde 400/500, riporto il body per diagnosi chiare
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"gateway HTTP {r.status_code}: {r.text}") from e
        return r.json()

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
    response_format=None, tools=None, tool_choice=None, profile=None, provider: str | None = None
) -> str:
    log.info("call_gateway_chat request: %s", json.dumps({
        "model": model,
        "base_url": base_url,
        "messages_len": len(messages),
        "has_response_format": bool(response_format),
        "has_tools": bool(tools),
        "provider": provider,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "profile": profile
    }))
    # Guardia difensiva
    if not isinstance(messages, list):
        raise ValueError("call_gateway_chat: 'messages' must be a list of {role, content}")

    base = (base_url or str(getattr(settings, "GATEWAY_URL", "http://localhost:8000"))).rstrip("/")
    to = float(timeout or float(getattr(settings, "REQUEST_TIMEOUT_S", 240)))
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_format is not None:
        body["response_format"] = response_format
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if profile is not None:
        body["profile"] = profile  # facoltativo, utile per osservabilità/routing coerente
    if provider is not None:
        body["provider"] = provider
   
    log.info("generate request: %s", json.dumps({
        "model": body.get("model"),
        "messages_len": len(messages),
        "has_response_format": bool(response_format),
        "has_tools": bool(tools),
        "provider": body.get("provider")
    }))
    headers = {"Content-Type": "application/json"}
    if provider is not None:
        headers["X-CLike-Provider"] = provider
        
    async with httpx.AsyncClient(timeout=to) as client:
        r = await client.post(f"{base}/v1/chat/completions", json=body, headers=headers)
        r.raise_for_status()
        txt = r.text
         # Parse robusto
        try:
            data = r.json()
            if isinstance(data, str):
                # double-encoded
                try:
                    data = json.loads(data)
                except Exception:
                    pass
        except Exception:
            # plain text → prova a caricare come JSON, altrimenti ritorna text raw
            try:
                data = json.loads(txt)
            except Exception:
                return {"version": "1.0", "text": txt, "usage": {}, "sources": []}

        # Estrai testo assistant
        text_out = ""


        # msg = ((data.get("choices") or [{}])[0].get("message") or {})
        # content = msg.get("content", "")
        # if isinstance(content, list):
        #     parts = []
        #     for seg in content:
        #         if isinstance(seg, dict):
        #             if isinstance(seg.get("text"), str):
        #                 parts.append(seg["text"])
        #             elif isinstance(seg.get("content"), str):
        #                 parts.append(seg["content"])
        #         elif isinstance(seg, str):
        #             parts.append(seg)
        #     return "".join(parts).strip()
        # if isinstance(content, str) and content.strip():
        #     return content.strip()

        # # 2) Fallback legacy: lasciali
        # if "choices" in data:
        #     return data["choices"][0]["message"]["content"]
        # if "text" in data:
        #     return data["text"]
        # 1) OpenAI-like
        if isinstance(data, dict):
            try:
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
            except Exception:
                pass

            # 2) Fallback legacy: altre chiavi note
            if "choices" in data:
                try:
                    return data["choices"][0]["message"]["content"]
                except Exception:
                    pass
            if "text" in data and isinstance(data["text"], str):
                return data["text"]
            if "response" in data and isinstance(data["response"], str):
                return data["response"]

        # 3) Se data è una stringa JSON double-encoded
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return str(parsed).strip()
            except Exception:
                return data.strip()

        # 4) Ultimo fallback: tutto come stringa
        return str(data or "").strip()

     
    


async def llm_transform_code(model: str, lang: str, code: str, instruction: str) -> str:
    """
    Trasformazione “code-in / code-out”: il modello deve restituire **solo** codice.
    """
    sys = "You are Clike, an expert software engineering assistant. Output only the transformed code, no prose."
    usr = f"Language: {lang}\nInstruction: {instruction}\nCode:\n```{lang}\n{code}\n```"
    return await call_gateway_chat(model, [{"role":"system","content":sys},{"role":"user","content":usr}], temperature=0.1)
