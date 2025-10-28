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
import json  # needed for fallback: parse plain-text JSON {"files":[...]}

import httpx
import re
import time
from functools import lru_cache

log = logging.getLogger("gateway.anthropic")

# Anthropic REST header
ANTHROPIC_VERSION = "2023-06-01"  # As of 2025 this header value remains current.
# Some beta features require the "anthropic-beta" header (comma-separated values).


# ----------------------------- helpers (shared shape) -----------------------------
CANON_4_5 = "claude-sonnet-4-5"
CANON_4_5_VERSION = "20250929"  # default; verrà superato se troviamo una versione più recente via /v1/models

_ALIAS_MAP = {
    "claude-4-5-sonnet": CANON_4_5,
    "claude-4.5-sonnet": CANON_4_5,
    "claude sonnet 4.5": CANON_4_5,
    "claude-sonnet-4.5": CANON_4_5,
    "sonnet-4.5": CANON_4_5,
    "sonnet-4-5": CANON_4_5,
    # vecchi alias:
    "claude-sonnet-4-0": "claude-sonnet-4-20250514",
    "claude-opus-4-0": "claude-opus-4-20250514",
}

def _strip_version_suffix(model: str) -> str:
    return re.sub(r"([\-@])20\d{6}$", "", model or "")

def _ensure_version_suffix(model: str, default_date: str) -> str:
    if re.search(r"([\-@])20\d{6}$", model or ""):
        return model
    return f"{model}-{default_date}"

@lru_cache(maxsize=1)
def _cached_model_list(base_url: str, api_key: str, timeout: float = 20.0) -> list[str]:
    import httpx
    # Normalize base_url so that we can always call '/v1/models' safely
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]  # drop trailing '/v1'
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    with httpx.Client(base_url=base, headers=headers, timeout=timeout) as cli:
        r = cli.get("/v1/models")
        r.raise_for_status()
        data = r.json() or {}
        ids = [x.get("id") for x in (data.get("data") or []) if isinstance(x, dict)]
        return [i for i in ids if isinstance(i, str)]

def _pick_latest_with_prefix(ids: list[str], prefix: str) -> str | None:
    cand = []
    for mid in ids:
        if not mid.startswith(prefix):
            continue
        m = re.search(r"([\-@])(20\d{6})$", mid)
        date = m.group(2) if m else "00000000"
        cand.append((date, mid))
    if not cand:
        return None
    cand.sort(reverse=True)
    return cand[0][1]

def _normalize_model_id_for_anthropic(model: str, base_url: str, api_key: str) -> str:
    raw = (model or "").strip()
    low = raw.lower()
    canon = _ALIAS_MAP.get(low, raw)
    # se è la famiglia 4.5 senza data, aggiungi suffisso
    if _strip_version_suffix(canon) == CANON_4_5:
        canon = _ensure_version_suffix(CANON_4_5, CANON_4_5_VERSION)
    # prova ad aggiornare alla versione più recente disponibile
    try:
        ids = _cached_model_list(base_url, api_key)
        latest = _pick_latest_with_prefix(ids, CANON_4_5)
        if latest and _strip_version_suffix(canon) == CANON_4_5:
            canon = latest
    except Exception:
        pass
    return canon

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
    # Haiku 4.5: if tools are provided but tool_choice not set, allow auto tool use.
    try:
        if _strip_version_suffix(model) in ("claude-haiku-4-5",) and out.get("tools") and "tool_choice" not in out:
            out["tool_choice"] = "auto"
    except Exception:
        pass
    return _filter_payload(out)



# ----------------------------- normalizers ----------------------------------------
def _extract_files_from_json_text(text: str) -> List[Dict[str, Any]]:
    """
    If the assistant returned JSON in plain text with a {"files":[...]} shape,
    extract it and return a normalized list of files:
    {path:str, content:str, language?:str, executable?:bool}
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(text, str):
        return out
    s = text.strip()
    if not s:
        return out
    # quick gate: must look like JSON
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return out
    try:
        data = json.loads(s)
    except Exception:
        return out

    # Accept both top-level {"files":[...]} and array of such objects
    candidates = []
    if isinstance(data, dict) and isinstance(data.get("files"), list):
        candidates = data["files"]
    elif isinstance(data, list):
        # e.g., [{"files":[...]}]
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("files"), list):
                candidates.extend(item["files"])

    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if isinstance(path, str) and isinstance(content, str):
            cleaned = {"path": path, "content": content}
            if isinstance(item.get("language"), str):
                cleaned["language"] = item["language"]
            if isinstance(item.get("executable"), bool):
                cleaned["executable"] = item["executable"]
            out.append(cleaned)
    return out

def _normalize_messages_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Claude Messages API response to the unified envelope.

    Logs:
    - number of content blocks and their types
    - tool_use blocks and extracted files count
    - fallback: files parsed from plain text JSON
    """
    text_parts: List[str] = []
    tool_uses: List[Dict[str, Any]] = []
    files_out: List[Dict[str, Any]] = []

    blocks = resp_json.get("content") or []
    log.info("anthropic.normalize: content_blocks=%d", len(blocks))

    def _coerce_files(value: Any) -> List[Dict[str, Any]]:
        """
        Accepts various shapes and returns a clean list of files:
        {path:str, content:str, language?:str, executable?:bool}

        Handles:
        - list[dict]
        - JSON string representing list[dict]
        - single dict {"path":..., "content":...}
        """
        out: List[Dict[str, Any]] = []

        # Case 1: the model returned a JSON string for files (Haiku does this)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                log.info("anthropic.normalize: _coerce_files parsed JSON from string, type=%s", type(parsed).__name__)
                value = parsed
            except Exception as e:
                log.warning("anthropic.normalize: _coerce_files cannot parse string JSON: %s", e)
                return out

        # Case 2: single dict
        if isinstance(value, dict):
            maybe = value
            path = maybe.get("path")
            content = maybe.get("content")
            if isinstance(path, str) and isinstance(content, str):
                cleaned = {"path": path, "content": content}
                if isinstance(maybe.get("language"), str):
                    cleaned["language"] = maybe["language"]
                if isinstance(maybe.get("executable"), bool):
                    cleaned["executable"] = maybe["executable"]
                out.append(cleaned)
            return out

        # Case 3: list of dicts
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                content = item.get("content")
                if isinstance(path, str) and isinstance(content, str):
                    cleaned = {"path": path, "content": content}
                    if isinstance(item.get("language"), str):
                        cleaned["language"] = item["language"]
                    if isinstance(item.get("executable"), bool):
                        cleaned["executable"] = item["executable"]
                    out.append(cleaned)
            return out

        # Unknown shape → nothing
        log.info("anthropic.normalize: _coerce_files unsupported type: %s", type(value).__name__)
        return out


    # parse content blocks
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            log.info("anthropic.normalize: block[%d] skipped (not dict)", i)
            continue
        btype = block.get("type")
        log.info("anthropic.normalize: block[%d].type=%s", i, btype)

        if btype == "text" and isinstance(block.get("text"), str):
            text = block["text"]
            text_parts.append(text)
            # log lunghezza testo per debug, no contenuto
            log.info("anthropic.normalize: block[%d] text_len=%d", i, len(text))

        elif btype == "tool_use":
            tool_uses.append(block)
            name = (block.get("name") or "").strip().lower()
            inp = block.get("input") or {}
            log.info("anthropic.normalize: block[%d] tool_use name=%s", i, name)
            # estrai files se presenti (input.files o input.file)
            if isinstance(inp, dict) and isinstance(inp.get("files"), list):
                extracted = _coerce_files(inp["files"])
                files_out.extend(extracted)
                log.info("anthropic.normalize: block[%d] tool_use files_found=%d", i, len(extracted))
            elif name == "emit_files" and isinstance(inp, dict) and isinstance(inp.get("file"), dict):
                extracted = _coerce_files([inp["file"]])
                files_out.extend(extracted)
                log.info("anthropic.normalize: block[%d] tool_use single file_found=%d", i, len(extracted))

    text = "\n".join([t for t in text_parts if t]).strip()
    finish_reason = (resp_json.get("stop_reason") or "") or ""
    usage = resp_json.get("usage") or {}

    # Se tool_use presente ma nessun file estratto → WARN utile
    if tool_uses and not files_out:
        log.warning("anthropic.normalize: tool_use_present=true but files_out=0 (finish_reason=%s)", finish_reason)

    # Fallback: se non abbiamo trovato files via tool_use,
    # prova a parsare il testo come JSON con chiave "files".
    if not files_out and text:
        try:
            files_from_text = _extract_files_from_json_text(text)
            if files_from_text:
                files_out.extend(files_from_text)
                log.info("anthropic.normalize: files parsed from text JSON: %d", len(files_from_text))
                # opzionale: svuota text così l’orchestrator non lo tratta come output umano
                text = ""
            else:
                log.info("anthropic.normalize: no files in text JSON")
        except Exception as e:
            log.warning("anthropic.normalize: JSON parse fallback error: %s", e)

    raw = {
        "id": resp_json.get("id"),
        "model": resp_json.get("model"),
        "role": resp_json.get("role"),
        "stop_sequence": resp_json.get("stop_sequence"),
        "tool_uses": tool_uses,
    }

    log.info(
        "anthropic.normalize: result text_len=%d files=%d finish_reason=%s usage_in=%s usage_out=%s",
        len(text),
        len(files_out),
        finish_reason,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )

    return _mk_unified_result(
        ok=True,
        text=text,
        files=files_out,
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
    gen = dict(gen or {})
    # 1) NORMALIZZA MODEL ID QUI (difesa in profondità)
    log.info("anthropic_complete_unified model: %s", model)
    normalized_model = _normalize_model_id_for_anthropic(model, base_url, api_key)
    log.info("anthropic_complete_unified normalized_model: %s", normalized_model)
    payload = _build_messages_payload(normalized_model, messages, gen or {})
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
        log.exception("anthropic complete unified Error code and  %s", r.status_code)
        log.exception("anthropic complete unified Error  %s", r)
        try:
            response_body = r.text
            # Se la risposta è JSON, potresti volerla formattare meglio,
            # ma r.text è sufficiente per catturare il contenuto grezzo.
        except Exception:
            response_body = "Impossibile decodificare il corpo della risposta."
        # Logga tutte le informazioni rilevanti in un unico messaggio formattato
        log.error(
            "Anthropic API Error (Status: %d) - URL: %s\n"
            "Messaggio di Errore API:\n%s",
            r.status_code,
            r.url,
            response_body
        )
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
            j = r.json()
            # log compatti di servizio
            try:
                _content_types = [b.get("type") for b in (j.get("content") or []) if isinstance(b, dict)]
            except Exception:
                _content_types = []
            log.info(
                "anthropic_complete_unified 200: stop_reason=%s content_types=%s",
                j.get("stop_reason"),
                _content_types,
            )
            normalized = _normalize_messages_response(j)
            log.info(
                "anthropic_complete_unified normalized: ok=%s text_len=%d files=%d finish_reason=%s",
                normalized.get("ok"),
                len(normalized.get("text") or ""),
                len(normalized.get("files") or []),
                normalized.get("finish_reason"),
            )
            return normalized
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
    # try:
    #     j = r.json()
    # except Exception:
    #     j = {}

    # code = j.get("type") or j.get("error", {}).get("type") or str(r.status_code)
    # message = j.get("message") or j.get("error", {}).get("message") or r.text
    # param = j.get("param") or j.get("error", {}).get("param") or ""

    # return _mk_unified_result(
    #     ok=False,
    #     text="",
    #     files=[],
    #     usage=j.get("usage") or {},
    #     finish_reason=j.get("stop_reason") or "",
    #     raw={
    #         "status": r.status_code,
    #         "error": j,
    #     },
    #     errors=[f"anthropic:{code}:{param}:{message}"],
    # )


# Optional lightweight convenience (string-only) -----------------------------------


# async def chat(
#     base_url: str,
#     api_key: str,
#     model: str,
#     messages: List[Dict[str, Any]],
#     *,
#     timeout: Optional[float] = 340.0,
#     **gen: Any,
# ) -> str:
#     """
#     Convenience wrapper returning just text. Preserves backwards compatibility
#     with older call-sites that expected `anthropic.chat(...)->str`.
#     """
#     # Costruisci le opzioni di generazione (Anthropic accetta max_output_tokens ma l'adapter converte)
#     temperature = gen.get('temperature', 0.5) # Recupera 'temperature', usa 0.5 come default se non fornito
#     max_tokens = gen.get('max_tokens')
#     log.info(f"temperature: {temperature}, max_tokens: {max_tokens}")
#     gen = {
#         'temperature': temperature,
#         'max_tokens': max_tokens,
#     }

#     return await anthropic_complete_unified(base_url, api_key, model, messages, gen or {}, timeout=timeout)
    
async def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    *,
    timeout: Optional[float] = 340.0,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    reasoning: Optional[Dict[str, Any]] = None,  # mantenuto per simmetria con openai_compat (ignorato da Anthropic)
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
    top_p: Optional[float] = None,
    stop: Optional[List[str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Unified adapter entry for Anthropic (OpenAI-compat envelope).
    Mirrors openai_compat.chat signature and returns:
    { ok, text, files, usage, finish_reason, raw, errors }
    """
    gen = {
        "temperature": temperature,
        "max_tokens": max_tokens,            # verrà mappato a max_output_tokens dal builder
        "response_format": response_format,  # ignorato da Anthropic ma pass-through
        "tools": tools,
        "tool_choice": tool_choice,
        "top_p": top_p,
        # OpenAI-style 'stop' → Anthropic 'stop_sequences'
        "stop_sequences": stop if stop else None,
        # opzionali per parità di superficie
        "thinking": kwargs.get("thinking"),
        "attachments": kwargs.get("attachments"),
        "cache_control": kwargs.get("cache_control"),
        "betas": kwargs.get("betas"),
        
    }
    gen["api"] = "chat"
    # pulisci None
    gen = {k: v for k, v in gen.items() if v is not None}

    return await anthropic_complete_unified(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        gen=gen,
        timeout=timeout,
    )

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
