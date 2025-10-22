# app/providers/ollama.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger("gateway.provider.ollama")

# ---------------- Unified envelope (parity with openai_compat) ----------------
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

# ---------------- Helpers -----------------------------------------------------
def _flatten_messages(messages: List[Dict[str, Any]]) -> str:
    """Flatten OpenAI-like messages into a simple chatml-ish prompt (fallback path)."""
    out: List[str] = []
    for m in messages or []:
        role = (m.get("role") or "").strip()
        content = m.get("content") or ""
        if role == "system":
            out.append(f"<|system|>\n{content}\n")
        elif role == "user":
            out.append(f"<|user|>\n{content}\n")
        elif role == "assistant":
            out.append(f"<|assistant|>\n{content}\n")
        else:
            out.append(str(content))
    out.append("<|assistant|>\n")
    return "\n".join(out)

async def _post_json(url: str, json: Dict[str, Any], timeout: float) -> Tuple[int, Dict[str, Any], str]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=json)
        txt = r.text
        try:
            j = r.json()
        except Exception:
            j = {}
        return r.status_code, j, txt

def _usage_from_ollama(j: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Ollama's counters to a stable usage shape.
    generate: prompt_eval_count, eval_count
    chat:     (some impls also return *_count)
    """
    pt = int(j.get("prompt_eval_count") or 0)
    ct = int(j.get("eval_count") or 0)
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct if (pt or ct) else None,
        "timings": {
            "total_ms": int((j.get("total_duration") or 0) / 1_000_000) if j.get("total_duration") else None,
            "eval_ms": int((j.get("eval_duration") or 0) / 1_000_000) if j.get("eval_duration") else None,
            "prompt_ms": int((j.get("prompt_eval_duration") or 0) / 1_000_000) if j.get("prompt_eval_duration") else None,
        },
    }

def _build_options(gen: Dict[str, Any]) -> Dict[str, Any]:
    """Translate generic generation knobs to Ollama's 'options'."""
    opts: Dict[str, Any] = {}
    if "temperature" in gen and gen["temperature"] is not None:
        opts["temperature"] = gen["temperature"]
    if "top_p" in gen and gen["top_p"] is not None:
        opts["top_p"] = gen["top_p"]
    # num_predict ~ max_tokens
    if "max_tokens" in gen and gen["max_tokens"] is not None:
        opts["num_predict"] = int(gen["max_tokens"])
    # stop sequences
    if "stop" in gen and gen["stop"]:
        opts["stop"] = gen["stop"]
    return opts

# ---------------- Normalizers -------------------------------------------------
def _normalize_chat_resp(j: Dict[str, Any], route: str, payload_echo: Dict[str, Any]) -> Dict[str, Any]:
    """
    /api/chat returns:
    { "message": {"role":"assistant","content":"..."}, "done":true, "done_reason":"..." , ...}
    Some servers return {"response":"..."} instead.
    """
    msg = ((j.get("message") or {}) or {}).get("content") or j.get("response") or ""
    usage = _usage_from_ollama(j)
    finish = j.get("done_reason") or ("stop" if j.get("done") else "")
    raw = {
        "route": route,
        "id": j.get("id"),
        "model": j.get("model"),
        "created_at": j.get("created_at"),
        "payload_echo": {k: v for k, v in payload_echo.items() if k != "messages"},
    }
    return _mk_unified_result(True, str(msg or "").strip(), [], usage, finish, raw, [])

def _normalize_generate_resp(j: Dict[str, Any], route: str, payload_echo: Dict[str, Any]) -> Dict[str, Any]:
    """
    /api/generate returns:
    { "response":"...", "done":true, "done_reason":"...", "eval_count":..., "prompt_eval_count":... }
    """
    msg = j.get("response") or ""
    usage = _usage_from_ollama(j)
    finish = j.get("done_reason") or ("stop" if j.get("done") else "")
    raw = {
        "route": route,
        "model": j.get("model"),
        "created_at": j.get("created_at"),
        "payload_echo": {k: v for k, v in payload_echo.items() if k != "prompt"},
    }
    return _mk_unified_result(True, str(msg or "").strip(), [], usage, finish, raw, [])

# ---------------- Public API --------------------------------------------------
async def ollama_complete_unified(
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
    timeout: float = 240.0,
) -> Dict[str, Any]:
    log.info("ollama_complete_unified: %s", messages)
    log.info("ollama_complete_unified: %s", gen)
    """
    Try /api/chat first (non-stream), then fallback to /api/generate with flattened prompt.
    Always return the unified envelope.
    """
    gen = gen or {}
    base = base_url.rstrip("/")
    chat_url = f"{base}/api/chat"
    gen_url = f"{base}/api/generate"

    # 1) /api/chat
    chat_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": _build_options(gen),
    }
    status, j, txt = await _post_json(chat_url, chat_payload, timeout)
    if status == 200 and (("message" in j) or ("response" in j)):
        return _normalize_chat_resp(j, "chat", chat_payload)
    # Non-200 or unexpected shape → fallback

    # 2) /api/generate
    prompt = _flatten_messages(messages)
    gen_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": _build_options(gen),
    }
    log.info("generate payload: %s", gen_payload)
    status, j, txt = await _post_json(gen_url, gen_payload, timeout)
    log.info("generate response: %s", j)

    if status == 200 and ("response" in j):
        return _normalize_generate_resp(j, "generate", gen_payload)

    # Error path (no raise; envelope with ok=False)
    err = j if isinstance(j, dict) and j else {"status": status, "text": txt[:800]}
    return _mk_unified_result(
        ok=False,
        text="",
        files=[],
        usage={},
        finish_reason="",
        raw={"error": err, "route": "chat->generate"},
        errors=[f"ollama:{status}:unexpected_response"],
    )

# OpenAI-like convenience: same signature surface as openai_compat.chat()
async def chat(
    base: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 240.0,
    
) -> Dict[str, Any]:
    gen = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return await ollama_complete_unified(base, model, messages, gen, timeout)

# Optional: retro-compat (string only)
async def chat_text(base_url: str, model: str, messages: List[Dict[str, Any]], **gen: Any) -> str:
    out = await ollama_complete_unified(base_url, model, messages, gen, timeout=float(gen.get("timeout", 240.0)))
    if out.get("ok"):
        return out.get("text", "")
    raise RuntimeError(out.get("errors") or "ollama: error")

# Embeddings (supported by Ollama as /api/embeddings for some models)
async def embeddings(base_url: str, model: str, input_text: str, timeout: float = 120.0) -> List[float]:
    url = f"{base_url.rstrip('/')}/api/embeddings"
    log.info("Embeddings: %s", url + f"?model={model}&prompt={input_text}")
    payload = {"model": model, "prompt": input_text}
    log.info("Embeddings payload: %s", payload)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        j = r.json()
        # common shapes: {'embedding': [...]} or OpenAI-like {'data':[{'embedding':[...]}]}
        if isinstance(j.get("embedding"), list):
            return j["embedding"]
        data = (j.get("data") or [])
        if data and isinstance(data[0], dict) and isinstance(data[0].get("embedding"), list):
            return data[0]["embedding"]
        return []
