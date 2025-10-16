# app/providers/vllm.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from .openai_compat import coerce_text_and_usage  # reuse same text/usage extraction

log = logging.getLogger("gateway.vllm")

# --------------- Unified envelope (parity with openai_compat) -----------------
def _mk_unified_result(
    ok: bool,
    text: str,
    files: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "text": text or "",
        "files": files or [],
        "usage": usage or {},
        "finish_reason": finish_reason or "",
        "raw": raw or {},
        "errors": errors or [],
    }

def _build_payload(
    model: str,
    messages: List[Dict[str, Any]],
    gen: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build an OpenAI Chat Completions payload for vLLM servers.
    vLLM generally follows 'max_tokens' (not 'max_completion_tokens').
    """
    out: Dict[str, Any] = {"model": model, "messages": messages}
    # sampling
    if gen.get("temperature") is not None:
        out["temperature"] = gen["temperature"]
    if gen.get("top_p") is not None:
        out["top_p"] = gen["top_p"]
    if gen.get("stop"):
        out["stop"] = gen["stop"]
    # budget
    if gen.get("max_tokens") is not None:
        out["max_tokens"] = gen["max_tokens"]
    # response format
    if gen.get("response_format"):
        out["response_format"] = gen["response_format"]
    # tools
    if gen.get("tools"):
        out["tools"] = gen["tools"]
    if gen.get("tool_choice") is not None:
        out["tool_choice"] = gen["tool_choice"]
    return out

# ----------------------------- Normalizer ------------------------------------
def _normalize_vllm_response(j: Dict[str, Any]) -> Dict[str, Any]:
    """
    vLLM uses OpenAI-compatible shapes: {choices:[{message:{content:str}, finish_reason:...}], usage:{...}}
    """
    text, usage = coerce_text_and_usage(j)
    finish = ""
    try:
        if isinstance(j.get("choices"), list) and j["choices"]:
            finish = j["choices"][0].get("finish_reason") or ""
    except Exception:
        finish = ""
    raw = {
        "id": j.get("id"),
        "model": j.get("model"),
        "choices": j.get("choices"),
    }
    return _mk_unified_result(True, text, [], usage, finish, raw, [])

# ----------------------------- Public API ------------------------------------
async def vllm_complete_unified(
    base: str,
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
    timeout: float = 240.0,
) -> Dict[str, Any]:
    """
    Single-shot call to a vLLM OpenAI-compatible endpoint. No Authorization header is sent.
    """
    gen = gen or {}
    url = f"{base.rstrip('/')}/chat/completions"
    payload = _build_payload(model, messages, gen)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
    except Exception as e:
        return _mk_unified_result(
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=[f"httpx:{e}"],
        )

    if r.status_code == 200:
        try:
            return _normalize_vllm_response(r.json())
        except Exception as e:
            return _mk_unified_result(
                ok=False, text="", files=[], usage={}, finish_reason="",
                raw={"body_preview": (r.text or "")[:800]},
                errors=[f"normalize:{e}"],
            )

    # Non-200
    try:
        j = r.json()
    except Exception:
        j = {}
    return _mk_unified_result(
        ok=False, text="", files=[], usage={}, finish_reason="",
        raw={"status": r.status_code, "error": j or r.text},
        errors=[f"vllm:{r.status_code}:http_error"],
    )

# OpenAI-like convenience: match openai_compat.chat surface (api_key ignored)
async def chat(
    base: str,
    api_key: Optional[str],  # ignored for vLLM
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    reasoning: Optional[Dict[str, Any]] = None,  # ignored
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    timeout: float = 240.0,
    top_p: Optional[float] = None,
    stop: Optional[List[str]] = None,
) -> Dict[str, Any]:
    gen = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": response_format,
        "tools": tools,
        "tool_choice": tool_choice,
        "top_p": top_p,
        "stop": stop,
    }
    return await vllm_complete_unified(base, model, messages, gen, timeout)

# Optional: embeddings for vLLM OpenAI server
async def embeddings(base_url: str, model: str, input_text: str, timeout: float = 120.0) -> List[float]:
    url = f"{base_url.rstrip('/')}/embeddings"
    payload = {"model": model, "input": input_text}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        j = r.json()
        data = (j.get("data") or [])
        if data and isinstance(data[0], dict) and isinstance(data[0].get("embedding"), list):
            return data[0]["embedding"]
        return []
