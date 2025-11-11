# FILE: anthropic.py
"""
anthropic.py — Unified adapter for Anthropic Claude APIs.

Obiettivi:
- Iso-funzionale con openai_compat: stesso envelope {ok, text, files, usage, finish_reason, raw, errors}.
- Gestione corretta di max_tokens (obbligatorio per Anthropic).
- Normalizzazione robusta dell'output: estrazione file, dedupe path, e (NOVITÀ) echo nel campo text
  quando è presente UN SOLO file, nel formato:
      BEGIN_FILE <path>
      <content>
      END_FILE
  così l’orchestratore non vede "0 chars" e non serve unified diff.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence
import json
import httpx
import re
import unicodedata
from functools import lru_cache

log = logging.getLogger("gateway.anthropic")

ANTHROPIC_VERSION = "2023-06-01"

CANON_4_5 = "claude-sonnet-4-5"
CANON_4_5_VERSION = "20250929"

_ALIAS_MAP = {
    "claude-4-5-sonnet": CANON_4_5,
    "claude-4.5-sonnet": CANON_4_5,
    "claude sonnet 4.5": CANON_4_5,
    "claude-sonnet-4.5": CANON_4_5,
    "sonnet-4.5": CANON_4_5,
    "sonnet-4-5": CANON_4_5,
    "claude-sonnet-4-0": "claude-sonnet-4-20250514",
    "claude-opus-4-0": "claude-opus-4-20250514",
}

# --- Regex per blocchi file (BEGIN_FILE/file:)
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

# Caratteri invisibili fastidiosi (es. ZWSP)
_INVISIBLES_RE = re.compile(r"[\u200B\u200C\u200D\uFEFF]")

def _normalize_unicode(s: str) -> str:
    # NFC + rimozione invisibili
    s = unicodedata.normalize("NFC", s or "")
    s = _INVISIBLES_RE.sub("", s)
    return s

def _normalize_path(p: str) -> str:
    p = _normalize_unicode(p or "")
    p = (p or "").strip().replace("\r", "")
    p = re.sub(r"[ \t]+$", "", p)
    p = re.sub(r"/{2,}", "/", p)
    # togli backticks o virgolette accidentalmente attaccate
    p = p.strip("`\"' \t")
    return p

def _to_rel_path(p: str) -> str:
    p = _normalize_path(p or "")
    p = p.replace("\\", "/")
    # rimuovi drive letter Windows e leading slash
    p = re.sub(r"^[A-Za-z]:", "", p)
    p = p.lstrip("/")
    # normalizza componenti ed elimina .. / .
    parts = []
    for seg in p.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def _extract_file_blocks_any(text: str) -> List[Dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return []
    text = _normalize_unicode(text)
    collected: List[Dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    def _scan(rx: re.Pattern):
        for m in rx.finditer(text):
            span = m.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            path = _normalize_path(m.group(1) or "")
            body = _normalize_unicode((m.group(2) or "").strip())
            if not path:
                continue
            collected.append({"path": path, "content": body})

    for rx in (
        _FILE_BLOCK_BEGIN_FENCED_RE,
        _FILE_BLOCK_BEGIN_PLAIN_RE,
        _FILE_BLOCK_FILE_FENCED_RE,
        _FILE_BLOCK_FILE_PLAIN_RE,
    ):
        _scan(rx)

    return _dedupe_files_by_path(collected)

def _canon_rel_key(p: str) -> str:
    """Chiave canonica per dedupe: path relativo, case-insensitive."""
    return (_to_rel_path(p) or "").lower()

def _try_json_minify(s: str) -> tuple[bool, str]:
    """Se s è JSON valido, ritorna (True, dump_minificato_con_sort_keys).
    Altrimenti (False, s_immutato)."""
    try:
        obj = json.loads(s)
        return True, json.dumps(obj, separators=(",", ":"), sort_keys=True)
    except Exception:
        return False, s

def _dedupe_files_by_path(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Dedupe robusto:
    - chiave = path relativo case-insensitive
    - JSON equivalenti (diversa spaziatura) collassati
    - se contenuti diversi, tiene quello più lungo
    """
    best_by_key: Dict[str, Dict[str, Any]] = {}
    for f in files or []:
        raw_p = f.get("path") or ""
        norm_p = _to_rel_path(raw_p)
        if not norm_p:
            continue
        key = _canon_rel_key(norm_p)
        content = _normalize_unicode(f.get("content") or "")

        # Normalizza JSON se possibile per confronti stabili
        is_json, content_norm = _try_json_minify(content)

        prev = best_by_key.get(key)
        if prev is None:
            keep = {"path": norm_p, "content": content}
            for k in ("language", "executable"):
                if k in f:
                    keep[k] = f[k]
            # Memorizza anche versione minificata per confronto interno
            if is_json:
                keep["_content_min"] = content_norm
            best_by_key[key] = keep
            continue

        # Confronto contro precedente
        prev_content = _normalize_unicode(prev.get("content") or "")
        prev_min = prev.get("_content_min")

        # Se entrambi JSON ed equivalenti -> salta (duplicato reale)
        if is_json and isinstance(prev_min, str):
            if content_norm == prev_min:
                continue
        elif not is_json:
            # Non JSON: se identico bit-a-bit, salta
            if content == prev_content:
                continue

        # Se diversi: scegli il più "ricco" (lunghezza)
        if len(content) > len(prev_content):
            keep = {"path": norm_p, "content": content}
            for k in ("language", "executable"):
                if k in f:
                    keep[k] = f[k]
            if is_json:
                keep["_content_min"] = content_norm
            best_by_key[key] = keep
        # altrimenti mantieni prev

    # Ripulisci campo interno _content_min prima di restituire
    out: List[Dict[str, Any]] = []
    for v in best_by_key.values():
        v.pop("_content_min", None)
        out.append(v)
    return out


def _strip_all_file_blocks(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text or ""
    s = _normalize_unicode(text)
    for rx in (
        _FILE_BLOCK_BEGIN_FENCED_RE,
        _FILE_BLOCK_BEGIN_PLAIN_RE,
        _FILE_BLOCK_FILE_FENCED_RE,
        _FILE_BLOCK_FILE_PLAIN_RE,
    ):
        s = rx.sub("", s)
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
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
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
    if _strip_version_suffix(canon) == CANON_4_5:
        canon = _ensure_version_suffix(CANON_4_5, CANON_4_5_VERSION)
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
    return {
        "ok": ok,
        "text": text or "",
        "files": files or [],
        "usage": usage or {},
        "finish_reason": finish_reason or "",
        "raw": raw or {},
        "errors": errors or [],
    }

_MESSAGES_ALLOWED = {
    "model","messages","system","metadata","stop_sequences",
    "max_tokens","max_output_tokens","temperature","top_p","top_k",
    "stream","tools","tool_choice","attachments",
    "thinking","betas","cache_control",
}

def _filter_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    unknown = [k for k in payload.keys() if k not in _MESSAGES_ALLOWED]
    if unknown:
        raise ValueError(f"[payload-validation] Unknown parameter(s) for Anthropic Messages: {unknown}")
    return payload

def _split_system_messages(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    systems: List[str] = []
    rest: List[Dict[str, Any]] = []
    for m in messages or []:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                systems.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and isinstance(b.get("text"), str):
                        systems.append(b["text"])
        else:
            rest.append(m)
    return ("\n\n".join(systems).strip() if systems else ""), rest

def _convert_tools_for_anthropic(tools: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        if "input_schema" in t and "name" in t and "description" in t:
            out.append(t); continue
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            fn = t["function"]
            out.append({
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
            continue
        out.append(t)
    return out

def _convert_tool_choice_for_anthropic(tool_choice: Any) -> Any:
    if tool_choice in ("auto", "none"):
        return {"type": str(tool_choice)}
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") in ("auto","none","tool") and ("name" in tool_choice or tool_choice["type"] in ("auto","none")):
            return tool_choice
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
    gen = dict(gen or {})
    sys_text, msg_wo_system = _split_system_messages(messages or [])
    if sys_text and not gen.get("system"):
        gen["system"] = sys_text

    out: Dict[str, Any] = {"model": model, "messages": msg_wo_system}

    # max_tokens obbligatorio
    tok = None
    if gen.get("max_tokens") is not None:
        tok = int(gen["max_tokens"])
    elif gen.get("max_output_tokens") is not None:
        tok = int(gen["max_output_tokens"])
    elif gen.get("default_max_tokens") is not None:
        tok = int(gen["default_max_tokens"])
    else:
        tok = 1024
    out["max_tokens"] = tok

    if "temperature" in gen:
        out["temperature"] = gen["temperature"]
    if "top_p" in gen:
        out["top_p"] = gen["top_p"]
    if "top_k" in gen:
        out["top_k"] = gen["top_k"]
    if gen.get("stop_sequences"):
        out["stop_sequences"] = gen["stop_sequences"]
    if gen.get("system"):
        out["system"] = gen["system"]
    if gen.get("tools"):
        out["tools"] = _convert_tools_for_anthropic(gen["tools"])
    if gen.get("tool_choice"):
        out["tool_choice"] = _convert_tool_choice_for_anthropic(gen["tool_choice"])
    if isinstance(gen.get("thinking"), dict):
        out["thinking"] = gen["thinking"]
    if gen.get("attachments"):
        out["attachments"] = gen["attachments"]
    if gen.get("cache_control"):
        out["cache_control"] = gen["cache_control"]

    try:
        if _strip_version_suffix(model) in ("claude-haiku-4-5",) and out.get("tools") and "tool_choice" not in out:
            out["tool_choice"] = "auto"
    except Exception:
        pass

    return _filter_payload(out)

def _extract_files_from_json_text(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(text, str):
        return out
    s = text.strip()
    if not s:
        return out
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return out
    try:
        data = json.loads(s)
    except Exception:
        return out

    candidates = []
    if isinstance(data, dict) and isinstance(data.get("files"), list):
        candidates = data["files"]
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("files"), list):
                candidates.extend(item["files"])

    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if isinstance(path, str) and isinstance(content, str):
            cleaned = {"path": _normalize_path(path), "content": _normalize_unicode(content)}
            if isinstance(item.get("language"), str):
                cleaned["language"] = item["language"]
            if isinstance(item.get("executable"), bool):
                cleaned["executable"] = item["executable"]
            out.append(cleaned)
    return out

def _normalize_messages_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    text_parts: List[str] = []
    tool_uses: List[Dict[str, Any]] = []
    files_out: List[Dict[str, Any]] = []
    #log.info("anthropic.normalize: resp_json=%s", resp_json)
    blocks = resp_json.get("content") or []
    log.info("anthropic.normalize: content_blocks=%d", len(blocks))

    def _coerce_files(value: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        # Se arriva come stringa JSON
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception as e:
                log.warning("anthropic.normalize: files string not JSON: %s", e)
                return out

        # Caso dict singolo {path, content} o dizionario con collezione
        if isinstance(value, dict):
            # singolo file
            p, c = value.get("path"), value.get("content")
            if isinstance(p, str) and isinstance(c, str):
                out.append({"path": _to_rel_path(p), "content": _normalize_unicode(c)})
                return out
            # collezioni comuni: "files": [...], "file": {...}, "items": [...]
            for key in ("files", "file", "items"):
                coll = value.get(key)
                if isinstance(coll, dict):
                    # alcune risposte Claude usano {"files": {"items": [...]}}
                    items = coll.get("items")
                    if isinstance(items, list):
                        coll = items
                if isinstance(coll, list):
                    for it in coll:
                        if not isinstance(it, dict):
                            continue
                        p, c = it.get("path"), it.get("content")
                        if isinstance(p, str) and isinstance(c, str):
                            out.append({"path": _to_rel_path(p), "content": _normalize_unicode(c)})
            return out

        # Caso lista diretta [{path, content}, ...]
        if isinstance(value, list):
            for it in value:
                if not isinstance(it, dict):
                    continue
                p, c = it.get("path"), it.get("content")
                if isinstance(p, str) and isinstance(c, str):
                    out.append({"path": _to_rel_path(p), "content": _normalize_unicode(c)})
            return out

        return out


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
            log.info("anthropic.normalize: tool_use[%d] name=%s keys=%s", i, name, list(inp.keys()) if isinstance(inp, dict) else type(inp))

            if isinstance(inp, dict):
                extracted: List[Dict[str, Any]] = []

                # Caso standard: input.files
                if "files" in inp:
                    extracted = _coerce_files(inp["files"])
                    log.info("anthropic.normalize: tool_use[%d] from=files -> %d file(s)", i, len(extracted))

                # Variante: input.items
                if not extracted and "items" in inp:
                    extracted = _coerce_files(inp["items"])
                    log.info("anthropic.normalize: tool_use[%d] from=items -> %d file(s)", i, len(extracted))

                # Variante: input.file (singolo o lista)
                if not extracted and "file" in inp:
                    extracted = _coerce_files(inp["file"])
                    log.info("anthropic.normalize: tool_use[%d] from=file -> %d file(s)", i, len(extracted))

                # Fallback: prova a coergere l'intero input dict
                if not extracted:
                    extracted = _coerce_files(inp)
                    log.info("anthropic.normalize: tool_use[%d] from=<dict-fallback> -> %d file(s)", i, len(extracted))

                if extracted:
                    files_out.extend(extracted)

    text_joined = _normalize_unicode("\n".join([t for t in text_parts if isinstance(t, str)]).strip())

    if text_joined:
        embedded = _extract_file_blocks_any(text_joined)
        if embedded:
            files_out.extend(embedded)

    if not files_out and text_joined:
        try:
            parsed = _extract_files_from_json_text(text_joined)
            if parsed:
                files_out = parsed
        except Exception as e:
            log.warning("anthropic.normalize: fallback JSON-in-text failed: %s", e)

    _files_out = _dedupe_files_by_path(files_out or [])


    # Allineamento a openai_compat: NESSUN echo file nel campo text.
    # Harper userà esclusivamente 'files' per scrivere gli artefatti.
    if files_out:
        text_clean = ""  # evita duplicazioni (files array è la fonte unica)
    else:
        # Nessun file estratto: pulisci eventuali blocchi spurii e passa solo prosa
        text_clean = _strip_all_file_blocks(text_joined)

    stop_reason = (resp_json.get("stop_reason") or "") or ""
    stop_seq = resp_json.get("stop_sequence")

    def _map_finish_reason(sr: str) -> str:
        sr = (sr or "").strip()
        if sr == "end_turn":
            return "stop"
        if sr == "max_tokens":
            return "length"  # allineato a OpenAI
        if sr == "stop_sequence":
            return "stop"
        return sr or ("stop" if stop_seq else "")

    finish_reason = _map_finish_reason(stop_reason)
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
        len(text_clean), len(files_out or []), finish_reason, usage.get("output_tokens"),
    )
    
    if len(files_out) > 1 and (text_clean or "") == "":
        log.info(
            "anthropic.normalize: text intentionally empty because multiple files=%d (use 'files' array). sample_paths=%s",
            len(files_out), [f["path"] for f in files_out[:3]]
        )
    elif len(files_out) == 1:
        log.info("anthropic.normalize: single file echoed into text (BEGIN_FILE...). path=%s", files_out[0]["path"])
    else:
        log.info("anthropic.normalize: no files extracted; text_len=%d", len(text_clean))

    return _mk_unified_result(
        ok=True, text=text_clean, files=files_out or [], usage=usage,
        finish_reason=finish_reason, raw=raw, errors=[]
    )

# ----------------------------- Public API -----------------------------------------

async def anthropic_complete_unified(
    base_url: str,
    api_key: Optional[str],
    model: str,
    messages: List[Dict[str, Any]],
    gen: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = 240.0,
) -> Dict[str, Any]:
    gen = dict(gen or {})
    log.info("anthropic_complete_unified model: %s", model)
    normalized_model = _normalize_model_id_for_anthropic(model, base_url, api_key)
    log.info("anthropic_complete_unified normalized_model: %s", normalized_model)

    payload = _build_messages_payload(normalized_model, messages, gen or {})
    betas = (gen or {}).get("betas") or []
    log.info("anthropic_complete_unified betas: %s", betas)
    log.info("anthropic_complete_unified payload length: %s", len(payload))
    #log.info("anthropic_complete_unified payload: %s", payload)

    headers = {"Content-Type": "application/json", "anthropic-version": ANTHROPIC_VERSION}
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
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"}, errors=[f"httpx:{e}"],
        )

    if r.status_code >= 400:
        try:
            response_body = r.text
        except Exception:
            response_body = "Impossible to read response."
        log.error(
            "Anthropic API Error (Status: %d) - URL: %s\nError Message API:\n%s",
            r.status_code, r.url, response_body
        )
        return _mk_unified_result(
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"body_preview": r.text[:800]}, errors=[f"httpx:{r.status_code}"],
        )

    # 200
    try:
        j = r.json()
        try:
            _content_types = [b.get("type") for b in (j.get("content") or []) if isinstance(b, dict)]
        except Exception:
            _content_types = []
        log.info(
            "anthropic_complete_unified 200: stop_reason=%s content_types=%s",
            j.get("stop_reason"), _content_types,
        )
        normalized = _normalize_messages_response(j)
        # [LOG] verifica contenuto unified prima del ritorno
        try:
            _files_n = len(normalized.get("files") or [])
            _paths = [f.get("path") for f in (normalized.get("files") or [])[:3]]
            log.info("anthropic_complete_unified normalized-summary: files=%d sample_paths=%s", _files_n, _paths)
        except Exception:
            pass

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
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"body_preview": body_preview}, errors=[f"normalize:{e}"],
        )

# Compat API (stessa firma logica di openai_compat.chat)
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
    reasoning: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
    top_p: Optional[float] = None,
    stop: Optional[List[str]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    gen = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": response_format,  # ignorato da Anthropic
        "tools": tools,
        "tool_choice": tool_choice,
        "top_p": top_p,
        "stop_sequences": stop if stop else None,
        "thinking": kwargs.get("thinking"),
        "attachments": kwargs.get("attachments"),
        "cache_control": kwargs.get("cache_control"),
        "betas": kwargs.get("betas"),
    }
    gen = {k: v for k, v in gen.items() if v is not None}

    return await anthropic_complete_unified(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        gen=gen,
        timeout=timeout,
    )

async def embeddings(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return _mk_unified_result(
        ok=False, text="", files=[], usage={}, finish_reason="",
        raw={"note": "Anthropic embeddings are not available via Messages API."},
        errors=["unsupported:embeddings"],
    )

# (facoltativo) SDK Agent — invariato
async def agent_task_unified(
    *,
    task: str,
    goal: Optional[str] = None,
    code_workspace: Optional[str] = None,
    sdk_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        from claude_agent_sdk import ClaudeSDKClient  # type: ignore
    except Exception as e:
        return _mk_unified_result(
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=["agent-sdk:not-installed"],
        )

    try:
        client = ClaudeSDKClient(**(sdk_config or {}))
        result = await client.query(task=task, goal=goal, code_workspace=code_workspace)  # type: ignore
        text = (getattr(result, "text", None) or result.get("text") if isinstance(result, dict) else "") or ""
        usage = getattr(result, "usage", None) or (result.get("usage") if isinstance(result, dict) else {}) or {}
        raw = result if isinstance(result, dict) else {"result": str(result)}
        return _mk_unified_result(ok=True, text=text, files=[], usage=usage, finish_reason="", raw=raw, errors=[])
    except Exception as e:
        log.exception("agent_task_unified error")
        return _mk_unified_result(
            ok=False, text="", files=[], usage={}, finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=["agent-sdk:runtime-error"],
        )
