# FILE: anthropic.py
"""
anthropic.py — Unified adapter for Anthropic Claude APIs.

Goal:
- Mirror the normalized output shape used by openai_compat.py so that upstream
  callers (e.g., harper.py/services) can swap providers without code changes.
- Cover Anthropic Messages API features available today (Claude 3.x/3.7/4 family),
  including tool use, images, reasoning/“thinking” budget, beta headers, and
  optional cache controls.
- Evaluate (optional) Agent SDK integration behind a safe runtime check.

All runtime logs and errors are flattened into a unified dict:

{
  "ok": bool,
  "text": str,               # concatenated assistant textual output
  "files": List[Dict],       # reserved for future parity (e.g., artifacts)
  "usage": Dict,             # input_tokens, output_tokens, etc.
  "finish_reason": str,      # mapped from Anthropic's stop_reason
  "raw": Dict,               # original response keys or partial error context
  "errors": List[str],       # human-readable errors
}

Chat in Italian, code and comments in English.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import httpx

log = logging.getLogger("gateway.anthropic")

# Anthropic REST header
ANTHROPIC_VERSION = "2023-06-01"  # As of 2025 this header value remains current.
# Some beta features require the "anthropic-beta" header (comma-separated values).


# ----------------------------- helpers (shared shape) -----------------------------


def _mk_unified_result(
    ok: bool,
    text: str,
    files: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return the unified envelope expected by upstream code (aligns to openai_compat)."""
    return {
        "ok": ok,
        "text": text or "",
        "files": files or [],
        "usage": usage or {},
        "finish_reason": finish_reason or "",
        "raw": raw or {},
        "errors": errors or [],
    }


# ----------------------------- payload builders -----------------------------------


_MESSAGES_ALLOWED = {
    # top-level
    "model",
    "messages",
    "system",
    "metadata",
    "stop_sequences",
    "max_tokens",          # accepted; converted to max_output_tokens
    "max_output_tokens",   # native
    "temperature",
    "top_p",
    "top_k",
    "stream",
    "tools",
    "tool_choice",
    "attachments",
    # Anthropic extras
    "thinking",            # {"budget_tokens": int} for hybrid reasoning models
    "betas",               # list[str] -> "anthropic-beta" header
    "cache_control",       # {"type": "ephemeral"} or content-level controls
}


def _filter_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reject unknown keys early to surface misconfigurations."""
    unknown = [k for k in payload.keys() if k not in _MESSAGES_ALLOWED]
    if unknown:
        raise ValueError(f"[payload-validation] Unknown parameter(s) for Anthropic Messages: {unknown}")
    return payload

def _split_system_messages(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """
    Extract top-level system text for Anthropic and remove system turns from messages.
    Returns (system_text, filtered_messages).
    """
    systems: List[str] = []
    rest: List[Dict[str, Any]] = []
    for m in messages or []:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                systems.append(content)
            elif isinstance(content, list):
                # Se arrivano blocchi, estrai solo il testo dove presente
                for b in content:
                    if isinstance(b, dict) and isinstance(b.get("text"), str):
                        systems.append(b["text"])
        else:
            rest.append(m)
    return ("\n\n".join(systems).strip() if systems else ""), rest


def _convert_tools_for_anthropic(tools: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Accept OpenAI-style tools or Anthropic-style tools and return Anthropic tools.
    - OpenAI style: {"type":"function","function":{"name":..., "parameters": {...}, "description": "..."}}
    - Anthropic style: {"name":..., "description": "...", "input_schema": {...}}
    """
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        # Already Anthropic shape
        if "input_schema" in t and "name" in t and "description" in t:
            out.append(t)
            continue
        # OpenAI function tool
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            fn = t["function"]
            out.append({
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
            continue
        # Fallback: pass through as-is (best effort)
        out.append(t)
    return out


def _convert_tool_choice_for_anthropic(tool_choice: Any) -> Any:
    """
    Convert OpenAI-style tool_choice to Anthropic-style.
    - OpenAI: "auto" | "none" | {"type":"function","function":{"name":"..."}} | {"type": "tool", "name": "..."}
    - Anthropic: {"type":"auto"} | {"type":"none"} | {"type":"tool","name":"..."}
    """
    if tool_choice in ("auto", "none"):
        return {"type": str(tool_choice)}
    if isinstance(tool_choice, dict):
        # Already Anthropic shape
        if tool_choice.get("type") in ("auto", "none", "tool") and ("name" in tool_choice or tool_choice["type"] in ("auto","none")):
            return tool_choice
        # OpenAI function → Anthropic tool
        if tool_choice.get("type") == "function" and isinstance(tool_choice.get("function"), dict):
            name = tool_choice["function"].get("name")
            if name:
                return {"type": "tool", "name": name}
    return tool_choice


def _build_messages_payload(
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a clean /v1/messages payload from (model, messages, gen).

    - Moves any 'system' role turns to top-level 'system'
    - Accepts OpenAI-like 'max_tokens' → maps to 'max_output_tokens'
    - Converts tools/tool_choice where needed
    """
    gen = dict(gen or {})

    # 1) Estrarre ed alzare 'system'
    sys_text, msg_wo_system = _split_system_messages(messages or [])
    if sys_text and not gen.get("system"):
        gen["system"] = sys_text

    out: Dict[str, Any] = {
        "model": model,
        "messages": msg_wo_system,  # niente turni 'system' qui dentro
    }

    # 2) Token budget
    if "max_output_tokens" in gen:
        out["max_output_tokens"] = int(gen["max_output_tokens"])
    
    if "max_tokens" in gen:
        out["max_tokens"] = int(gen["max_tokens"])
    else:
        out["max_tokens"] = int(gen.get("default_max_tokens", 1024))
    

    # 3) Sampling
    if "temperature" in gen: out["temperature"] = gen["temperature"]
    if "top_p" in gen: out["top_p"] = gen["top_p"]
    if "top_k" in gen: out["top_k"] = gen["top_k"]
    if gen.get("stop_sequences"): out["stop_sequences"] = gen["stop_sequences"]

    # 4) System (top-level)
    if gen.get("system"): out["system"] = gen["system"]

    # 5) Tools & choice
    if gen.get("tools"): out["tools"] = _convert_tools_for_anthropic(gen["tools"])
    if gen.get("tool_choice"): out["tool_choice"] = _convert_tool_choice_for_anthropic(gen["tool_choice"])

    # 6) Reasoning budget / allegati / cache
    if isinstance(gen.get("thinking"), dict): out["thinking"] = gen["thinking"]
    if gen.get("attachments"): out["attachments"] = gen["attachments"]
    if gen.get("cache_control"): out["cache_control"] = gen["cache_control"]

    return _filter_payload(out)



# ----------------------------- normalizers ----------------------------------------


def _normalize_messages_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Claude Messages API response to the unified envelope.

    Anthropic response (abridged):
    {
      "id": "...",
      "type": "message",
      "role": "assistant",
      "content": [
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "foo", "input": {...}}
      ],
      "model": "claude-3-7-sonnet-20250224",
      "stop_reason": "end_turn" | "max_tokens" | "stop_sequence" | "tool_use" | None,
      "stop_sequence": null,
      "usage": {"input_tokens": 123, "output_tokens": 456}
    }
    """
    text_parts: List[str] = []
    tool_uses: List[Dict[str, Any]] = []

    for block in resp_json.get("content") or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
        elif btype == "tool_use":
            # Preserve tool_use structure for upstream tools in raw
            tool_uses.append(block)

    text = "\n".join([t for t in text_parts if t]).strip()
    finish_reason = (resp_json.get("stop_reason") or "") or ""
    usage = resp_json.get("usage") or {}

    raw = {
        "id": resp_json.get("id"),
        "model": resp_json.get("model"),
        "role": resp_json.get("role"),
        "stop_sequence": resp_json.get("stop_sequence"),
        "tool_uses": tool_uses,
    }

    return _mk_unified_result(
        ok=True,
        text=text,
        files=[],
        usage=usage,
        finish_reason=finish_reason,
        raw=raw,
        errors=[],
    )


# ----------------------------- public API -----------------------------------------


async def anthropic_complete_unified(
    base_url: str,
    api_key: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = 240.0,
) -> Dict[str, Any]:
    """
    Single entry point mirroring openai_compat.openai_complete_unified.
    Returns the normalized envelope (dict).

    Parameters
    - base_url: e.g., "https://api.anthropic.com/v1"
    - api_key: Anthropic API key (sent as 'x-api-key')
    - model: Claude model id
    - messages: Anthropic-compatible messages list (string content allowed)
    - gen: generation options; see _build_messages_payload()
    - timeout: http timeout in seconds
    """
    payload = _build_messages_payload(model, messages, gen or {})
    betas = (gen or {}).get("betas") or []
    log.info("anthropic_complete_unified betas: %s", betas)
    log.info("anthropic_complete_unified payload: %s", payload)
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    if api_key:
        headers["x-api-key"] = api_key
    if betas:
        headers["anthropic-beta"] = ",".join(betas)
    

    url = f"{base_url.rstrip('/')}/messages"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
    except Exception as e:
        log.exception("anthropic_complete_unified httpx error")
        return _mk_unified_result(
            ok=False,
            text="",
            files=[],
            usage={},
            finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=[f"httpx:{e}"],
        )
    
        
    if r.status_code >= 400:
        log.exception("anthropic complete unified Error code and text: %s", r.status_code, r.text)
        return _mk_unified_result(
            ok=False,
            text="",
            files=[],
            usage={},
            finish_reason="",
            raw={"body_preview": r.text[:800]},
            errors=[f"httpx:{r.status_code}"],
        )
    # 200 → normalize
    if r.status_code == 200:
        try:
            return _normalize_messages_response(r.json())
        except Exception as e:
            log.error("anthropic_complete_unified normalizer error: %s", e)
            body_preview = (r.text or "")[:800]
            return _mk_unified_result(
                ok=False,
                text="",
                files=[],
                usage={},
                finish_reason="",
                raw={"body_preview": body_preview},
                errors=[f"normalize:{e}"],
            )

    # Non-200 → return normalized error without raising
    try:
        j = r.json()
    except Exception:
        j = {}

    code = j.get("type") or j.get("error", {}).get("type") or str(r.status_code)
    message = j.get("message") or j.get("error", {}).get("message") or r.text
    param = j.get("param") or j.get("error", {}).get("param") or ""

    return _mk_unified_result(
        ok=False,
        text="",
        files=[],
        usage=j.get("usage") or {},
        finish_reason=j.get("stop_reason") or "",
        raw={
            "status": r.status_code,
            "error": j,
        },
        errors=[f"anthropic:{code}:{param}:{message}"],
    )


# Optional lightweight convenience (string-only) -----------------------------------


async def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    *,
    timeout: Optional[float] = 340.0,
    **gen: Any,
) -> str:
    """
    Convenience wrapper returning just text. Preserves backwards compatibility
    with older call-sites that expected `anthropic.chat(...)->str`.
    """
    # Costruisci le opzioni di generazione (Anthropic accetta max_output_tokens ma l'adapter converte)
    temperature = gen.get('temperature', 0.5) # Recupera 'temperature', usa 0.5 come default se non fornito
    max_tokens = gen.get('max_tokens')
    log.info(f"temperature: {temperature}, max_tokens: {max_tokens}")
    gen = {
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    return await anthropic_complete_unified(base_url, api_key, model, messages, gen or {}, timeout=timeout)
    


# Embeddings placeholder (Anthropic does not currently expose a public embeddings API)


async def embeddings(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Keep the same callable surface as openai_compat.embeddings but return a
    normalized “not supported” response to avoid breaking upstream code paths.
    """
    return _mk_unified_result(
        ok=False,
        text="",
        files=[],
        usage={},
        finish_reason="",
        raw={"note": "Anthropic embeddings are not available via Messages API."},
        errors=["unsupported:embeddings"],
    )


# Optional Agent SDK adapter (best-effort, safe to ignore if sdk not installed) ------


async def agent_task_unified(
    *,
    task: str,
    goal: Optional[str] = None,
    code_workspace: Optional[str] = None,
    sdk_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a simple agentic task using Claude Agent SDK (Python) if available.
    Returns unified envelope; on ImportError returns an informative error without raising.

    The Agent SDK is evolving; this adapter intentionally keeps a very small surface
    and should be considered experimental. Prefer `anthropic_complete_unified`
    for general chat and tool use flows.
    """
    try:
        # Lazy import to avoid hard dependency
        from claude_agent_sdk import ClaudeSDKClient  # type: ignore
    except Exception as e:
        return _mk_unified_result(
            ok=False,
            text="",
            files=[],
            usage={},
            finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=["agent-sdk:not-installed"],
        )

    try:
        client = ClaudeSDKClient(**(sdk_config or {}))
        # The actual SDK API may differ; this reflects current docs semantics:
        # - run a single task (query) with optional goal or workspace
        result = await client.query(task=task, goal=goal, code_workspace=code_workspace)  # type: ignore
        # Attempt to read common fields defensively
        text = (getattr(result, "text", None) or result.get("text") if isinstance(result, dict) else "") or ""
        usage = getattr(result, "usage", None) or (result.get("usage") if isinstance(result, dict) else {}) or {}
        raw = result if isinstance(result, dict) else {"result": str(result)}
        return _mk_unified_result(ok=True, text=text, files=[], usage=usage, finish_reason="", raw=raw, errors=[])
    except Exception as e:
        log.exception("agent_task_unified error")
        return _mk_unified_result(
            ok=False,
            text="",
            files=[],
            usage={},
            finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=["agent-sdk:runtime-error"],
        )
