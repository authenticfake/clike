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

# --- FILE BLOCK REGEX (priorità: BEGIN_FILE in fenced, poi BEGIN_FILE plain, poi file: fenced, poi file: plain)
_FILE_BLOCK_BEGIN_FENCED_RE = re.compile(
    r"(?:^|\n)```[^\n]*\n\s*BEGIN_FILE\s+([^\n]+)\n(.*?)(?:\nEND_FILE)?\n```",
    re.DOTALL | re.IGNORECASE,
)
_FILE_BLOCK_BEGIN_PLAIN_RE = re.compile(
    r"(?:^|\n)BEGIN_FILE\s+([^\n]+)\n(.*?)(?:\nEND_FILE|$)",
    re.DOTALL | re.IGNORECASE,
)
_FILE_BLOCK_FILE_FENCED_RE = re.compile(
    r"(?:^|\n)```[^\n]*\n\s*file:([^\n]+)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
_FILE_BLOCK_FILE_PLAIN_RE = re.compile(
    r"(?:^|\n)file:([^\n]+)\n(.*?)(?=(?:\n(?:BEGIN_FILE|file:)[^\n]*\n)|\Z)",
    re.DOTALL | re.IGNORECASE,
)

def _normalize_path(p: str) -> str:
    # difese: trim, rimuove CR/spazi invisibili, collassa doppi slash
    p = (p or "").strip().replace("\r", "")
    p = re.sub(r"[ \t]+$", "", p)        # trim trailing spaces
    p = re.sub(r"/{2,}", "/", p)         # // -> /
    return p

def _extract_file_blocks_any(text: str) -> List[Dict[str, Any]]:
    """
    Estrae i blocchi file in tutte le varianti senza duplicare.
    Ordine di estrazione:
      1) BEGIN_FILE dentro fenced
      2) BEGIN_FILE plain
      3) file: dentro fenced
      4) file: plain
    Usa 'seen_spans' per non ricatturare lo stesso intervallo due volte.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    collected: List[Dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    def _scan(rx: re.Pattern):
        for m in rx.finditer(text):
            span = m.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            path = _normalize_path(m.group(1) or "")
            body = (m.group(2) or "").strip()
            if not path:
                continue
            collected.append({"path": path, "content": body})

    # ordine deliberato per evitare doppi match sullo stesso blocco
    _scan(_FILE_BLOCK_BEGIN_FENCED_RE)
    _scan(_FILE_BLOCK_BEGIN_PLAIN_RE)
    _scan(_FILE_BLOCK_FILE_FENCED_RE)
    _scan(_FILE_BLOCK_FILE_PLAIN_RE)

    return _dedupe_files_by_path(collected)


def _dedupe_files_by_path(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for f in files or []:
        p = _normalize_path(f.get("path") or "")
        c = f.get("content") or ""
        if not p:
            continue
        prev = best.get(p)
        if prev is None or len(c) > len(prev.get("content") or ""):
            keep = {"path": p, "content": c}
            for k in ("language", "executable"):
                if k in f:
                    keep[k] = f[k]
            best[p] = keep
    return list(best.values())



def _strip_all_file_blocks(text: str) -> str:
    """
    Rimuove TUTTE le varianti di blocchi file dal testo:
      - ``` ... BEGIN_FILE <path> ... END_FILE ```
      - BEGIN_FILE <path> ... END_FILE   (plain)
      - ``` file:<path> ... ```
      - file:<path> ...                  (plain)
    Lascia solo il testo narrativo per evitare il doppio emit a valle.
    """
    if not isinstance(text, str) or not text:
        return text or ""

    s = text

    # Rimuovi in ordine di specificità usando le REGEX *definite* in alto:
    #   _FILE_BLOCK_BEGIN_FENCED_RE
    #   _FILE_BLOCK_BEGIN_PLAIN_RE
    #   _FILE_BLOCK_FILE_FENCED_RE
    #   _FILE_BLOCK_FILE_PLAIN_RE
    for rx in (
        _FILE_BLOCK_BEGIN_FENCED_RE,
        _FILE_BLOCK_BEGIN_PLAIN_RE,
        _FILE_BLOCK_FILE_FENCED_RE,
        _FILE_BLOCK_FILE_PLAIN_RE,
    ):
        s = rx.sub("", s)

    # Collassa triple backticks orfane e righe vuote eccessive
    s = re.sub(r"```+", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s



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

# --- file: providers/anthropic.py -------------------------------------------
def _build_messages_payload(
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Costruisce il payload per /v1/messages di Anthropic in modo compatibile
    con openai_compat:
      - sposta i turni 'system' a top-level
      - garantisce SEMPRE 'max_tokens' (obbligatorio per Anthropic)
      - opzionale: duplica su 'max_output_tokens' per future proof
    """
    gen = dict(gen or {})

    # 1) System al top-level
    sys_text, msg_wo_system = _split_system_messages(messages or [])
    if sys_text and not gen.get("system"):
        gen["system"] = sys_text

    out: Dict[str, Any] = {
        "model": model,
        "messages": msg_wo_system,  # niente 'system' dentro i turni
    }

    # 2) Token budget — Anthropic richiede 'max_tokens'
    tok = None
    if gen.get("max_tokens") is not None:
        tok = int(gen["max_tokens"])
    elif gen.get("max_output_tokens") is not None:
        tok = int(gen["max_output_tokens"])
    elif gen.get("default_max_tokens") is not None:
        tok = int(gen["default_max_tokens"])
    else:
        tok = 1024  # fallback sicuro

    out["max_tokens"] = tok
    # (facoltativo ma innocuo) per compat/telemetria futura

    # 3) Sampling
    if "temperature" in gen:
        out["temperature"] = gen["temperature"]
    if "top_p" in gen:
        out["top_p"] = gen["top_p"]
    if "top_k" in gen:
        out["top_k"] = gen["top_k"]
    if gen.get("stop_sequences"):
        out["stop_sequences"] = gen["stop_sequences"]

    # 4) System (top-level)
    if gen.get("system"):
        out["system"] = gen["system"]

    # 5) Tools & choice
    if gen.get("tools"):
        out["tools"] = _convert_tools_for_anthropic(gen["tools"])
    if gen.get("tool_choice"):
        out["tool_choice"] = _convert_tool_choice_for_anthropic(gen["tool_choice"])

    # 6) Extra (reasoning / attachments / cache)
    if isinstance(gen.get("thinking"), dict):
        out["thinking"] = gen["thinking"]
    if gen.get("attachments"):
        out["attachments"] = gen["attachments"]
    if gen.get("cache_control"):
        out["cache_control"] = gen["cache_control"]

    # Nota: alcuni modelli (p.es. haiku-4-5) gradiscono tool_choice="auto" se tools presenti
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
    Converte la risposta Anthropic /v1/messages nel *medesimo* envelope usato da openai_compat:
      { ok, text, files, usage, finish_reason, raw, errors }

    Regole fondamentali per parità:
    - Se sono presenti file estratti → 'text' deve essere vuoto (evita doppio parsing lato orchestrator).
    - Deduplica per 'path' mantenendo il contenuto più lungo.
    - Supporta tutte le varianti: tool_use -> input.files, BEGIN_FILE/END_FILE, file:<path>, fallback JSON {"files":[...]}.
    """
    text_parts: List[str] = []
    tool_uses: List[Dict[str, Any]] = []
    files_out: List[Dict[str, Any]] = []

    blocks = resp_json.get("content") or []
    log.info("anthropic.normalize: content_blocks=%d", len(blocks))

    # --- helper interno: coerce diversi formati "files" in lista normalizzata
    def _coerce_files(value: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        # stringa JSON -> dict/list
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception as e:
                log.warning("anthropic.normalize: files string not JSON: %s", e)
                return out
        # singolo oggetto
        if isinstance(value, dict):
            p, c = value.get("path"), value.get("content")
            if isinstance(p, str) and isinstance(c, str):
                item = {"path": _normalize_path(p), "content": c}
                if isinstance(value.get("language"), str):
                    item["language"] = value["language"]
                if isinstance(value.get("executable"), bool):
                    item["executable"] = value["executable"]
                out.append(item)
            return out
        # lista di oggetti
        if isinstance(value, list):
            for it in value:
                if not isinstance(it, dict):
                    continue
                p, c = it.get("path"), it.get("content")
                if isinstance(p, str) and isinstance(c, str):
                    item = {"path": _normalize_path(p), "content": c}
                    if isinstance(it.get("language"), str):
                        item["language"] = it["language"]
                    if isinstance(it.get("executable"), bool):
                        item["executable"] = it["executable"]
                    out.append(item)
            return out
        return out

    # 1) Scansiona i blocchi content
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text" and isinstance(block.get("text"), str):
            t = block["text"]
            text_parts.append(t)
            log.info("anthropic.normalize: text_block[%d] len=%d", i, len(t))
        elif btype == "tool_use":
            tool_uses.append(block)
            name = (block.get("name") or "").strip().lower()
            inp = block.get("input") or {}
            # Preferenza: input.files (lista o oggetto)
            if isinstance(inp, dict):
                if "files" in inp:
                    extracted = _coerce_files(inp["files"])
                    if extracted:
                        files_out.extend(extracted)
                        log.info("anthropic.normalize: tool_use[%d] files=%d", i, len(extracted))
                elif name == "emit_files" and isinstance(inp.get("file"), (dict, list, str)):
                    extracted = _coerce_files(inp["file"])
                    if extracted:
                        files_out.extend(extracted)
                        log.info("anthropic.normalize: tool_use[%d] single_file=%d", i, len(extracted))

    # 2) Unisci testo e cerca blocchi file embedded
    text_joined = "\n".join([t for t in text_parts if isinstance(t, str)]).strip()

    if text_joined:
        embedded = _extract_file_blocks_any(text_joined)
        if embedded:
            files_out.extend(embedded)

    # 3) Fallback: JSON puro nel testo {"files":[...]}
    if not files_out and text_joined:
        try:
            parsed = _extract_files_from_json_text(text_joined)
            if parsed:
                files_out = parsed
        except Exception as e:
            log.warning("anthropic.normalize: fallback JSON-in-text failed: %s", e)

    # 4) Deduplica finale per path (mantieni il contenuto più lungo)
    files_out = _dedupe_files_by_path(files_out or [])

    # 5) Politica text:
    #    - se abbiamo file → svuota text completamente (parità con openai_compat)
    #    - altrimenti ripulisci il testo da eventuali blocchi file residui
    if files_out:
        text_clean = ""
    else:
        text_clean = _strip_all_file_blocks(text_joined)

    finish_reason = (resp_json.get("stop_reason") or "") or ""
    usage = resp_json.get("usage") or {}

    raw = {
        "id": resp_json.get("id"),
        "model": resp_json.get("model"),
        "role": resp_json.get("role"),
        "stop_sequence": resp_json.get("stop_sequence"),
        "tool_uses": tool_uses,
    }

    log.info(
        "anthropic.normalize: result text_len=%d files=%d finish_reason=%s usage_out=%s",
        len(text_clean),
        len(files_out or []),
        finish_reason,
        usage.get("output_tokens"),
    )

    return _mk_unified_result(
        ok=True,
        text=text_clean,
        files=files_out or [],
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
    log.info("anthropic_complete_unified payload length: %s", len(payload))
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
