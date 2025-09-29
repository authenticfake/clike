# gateway/providers/openai_compat.py
# OpenAI-compatible Chat Completions client with multi-model fallback:
# 1) Structured Outputs (JSON Schema) when "files" scenario is detected
# 2) Tool/Function calling (emit_files) strict
# 3) Plain JSON (system instruction) + robust JSON extraction
#
# Works with GPT-5/4/3.x and vLLM OpenAI-compatible backends.
from __future__ import annotations
import httpx, json
from typing import Any, List, Dict, Tuple, Optional, Union
import logging, time as _time
from copy import deepcopy as _deepcopy

log = logging.getLogger("gateway.openai")
# -------- JSON schema used for file outputs (harper coding/KIT) -------------
FILES_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "minLength": 1},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"],
                "additionalProperties": False
            }
        },
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role":    {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["role", "content"],
                "additionalProperties": False
            }
        }
    },
    "required": ["files"],
    "additionalProperties": False
}

#used for harper cenario for homologte the oai raw reposndse to clki reposnse
# --- normalizzazione esito LLM (allineata a Free/Coding) ---
def coerce_text_and_usage(raw: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Accetta: dict OpenAI, stringa JSON, stringa testo puro.
    Restituisce sempre (text, usage).
    Non solleva eccezioni.
    """
    try:
        # Caso 1: dict già parsato (OpenAI compat)
        if isinstance(raw, dict):
            if "choices" in raw and raw["choices"]:
                msg = raw["choices"][0].get("message", {}) or {}
                content = msg.get("content") or ""
                usage = raw.get("usage") or {}
                return str(content or "").strip(), (usage if isinstance(usage, dict) else {})
            # altri tipi di dict → stringify prudente
            return str(raw).strip(), {}
        # Caso 2: stringa
        if isinstance(raw, str):
            s = raw.strip()
            # se sembra JSON, prova a fare json.loads
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    j = json.loads(s)
                    if isinstance(j, dict) and "choices" in j and j["choices"]:
                        msg = j["choices"][0].get("message", {}) or {}
                        content = msg.get("content") or ""
                        usage = j.get("usage") or {}
                        return str(content or "").strip(), (usage if isinstance(usage, dict) else {})
                    return str(j).strip(), {}
                except Exception:
                    # non è JSON valido → trattalo come testo
                    return s, {}
            # plain text
            return s, {}
        # fallback generico
        return str(raw or "").strip(), {}
    except Exception:
        # ultima rete di salvataggio
        return "", {}

#deprecated
def extract_text_and_usage_from_openai(obj) -> tuple[str, dict]:
    """
    Accetta: dict OpenAI, stringa JSON, oppure stringa plain.
    Ritorna: (text, usage_dict)
    """
    usage = {}
    # dict già parsato
    if isinstance(obj, dict):
        try:
            text = obj.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = obj.get("usage", {}) or {}
            return (text or "", usage)
        except Exception:
            # fallback: repr del dict se malformato
            return (str(obj), usage)
    # stringa: prova JSON → altrimenti plain
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                data = json.loads(s)
                return _extract_text_and_usage_from_openai(data)
            except Exception:
                # non è JSON valido → consideralo testo "grezzo"
                return (s, usage)
        # potrebbe essere repr Python di un dict (come visto nei log)
        if s.startswith("{'") and "choices" in s and "message" in s:
            try:
                # tentativo prudente: sostituisci quotes singoli → doppi e parse
                j = s.replace("'", '"')
                data = json.loads(j)
                return _extract_text_and_usage_from_openai(data)
            except Exception:
                return (s, usage)
        return (s, usage)
    # altri tipi (None, ecc.)
    return ("", usage)

def _shrink(s: str, n: int = 2000) -> str:
    return s if len(s) <= n else (s[:n] + "…")
# -------------------------- Public API --------------------------------------
async def chat(
    base: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    timeout: Optional[float] = 240.0,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base.rstrip('/')}/chat/completions"

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        if not model.startswith("gpt-5"):
            payload["temperature"] = temperature

    # GPT-5 usa max_completion_tokens sulla Chat Completions API; le altre famiglie restano su max_tokens
    if model.startswith("gpt-5"):
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
    else:
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

    if response_format is not None:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    log.info("openai.request %s", json.dumps({
        "url": url, "model": model,
        "has_response_format": bool(response_format),
        "has_tools": bool(tools),
        "has_tool_choice": tool_choice is not None,
        "budget": max_tokens,
        "payload": payload
    }))

    t0 = _time.time()
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
    ms = int((_time.time() - t0) * 1000)

    txt = r.text
    if r.is_success:
        log.info("openai.response %s", json.dumps({"status": r.status_code, "latency_ms": ms}))
        try:
            data = r.json()
            log.debug("openai.response.body %s", _shrink(json.dumps(data, ensure_ascii=False), 4000))
        except Exception:
            log.debug("openai.response.text %s", _shrink(txt, 4000))
        # **ritorna l'intero JSON** (con tool_calls)
        return r.json()
    else:
        log.error("openai.response %s", json.dumps({
            "status": r.status_code, "latency_ms": ms, "error_text": _shrink(txt, 2000)
        }))
        r.raise_for_status()


async def embeddings(base_url: str, api_key: str | None, model: str, input_text: str):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "input": input_text}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url.rstrip('/')}/s", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return (data.get("data") or [{}])[0].get("embedding")
