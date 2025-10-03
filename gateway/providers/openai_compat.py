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
import asyncio
import random
import httpx

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


RETRYABLE_STATUS = {429, 500, 502, 503, 504}

def _build_llm_timeout(read_s: float) -> httpx.Timeout:
    # connect=10s, read/write adattivi, no timeout pool
    rs = float(read_s or 120.0)
    return httpx.Timeout(connect=10.0, read=rs, write=rs, pool=10.0)
    

async def _post_with_retries(url: str, json_payload: dict, headers: dict,
                             read_timeout_s: float,
                             max_attempts: int = 3) -> httpx.Response:
    """
    POST robusto con retry ed exponential backoff jitter sui codici 429/5xx.
    """
    backoff_base = 0.8
    for attempt in range(1, max_attempts + 1):
        try:
            log.info("gateway._post_with_retries attempt %s", attempt)
            async with httpx.AsyncClient(timeout=_build_llm_timeout(read_timeout_s)) as client:
                r = await client.post(url, headers=headers, json=json_payload)
                log.info("gateway._post_with_retries response %s", r.status_code)

            if r.status_code in RETRYABLE_STATUS and attempt < max_attempts:
                # backoff con jitter
                sleep_s = (backoff_base ** -attempt) * (0.5 + random.random() * 0.7)
                await asyncio.sleep(sleep_s)
                continue
            r.raise_for_status()
            return r
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            log.error("gateway._post_with_retries: %s", e)

            if attempt >= max_attempts:
                raise
            sleep_s = (backoff_base ** -attempt) * (0.7 + random.random() * 0.7)
            await asyncio.sleep(sleep_s)
            # ritenta
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
                sleep_s = (backoff_base ** -attempt) * (0.7 + random.random() * 0.7)
                await asyncio.sleep(sleep_s)
                continue
            raise

# --- Calcolo timeout adattivo e invocazione robusta ---

# Stima tokens prompt (se hai già una funzione usa la tua)
def _approx_tokens_from_chars(s: str) -> int:
    # euristico: ~4 char/token
    if not s:
        return 0
    return max(1, int(len(s) / 4))

def _messages_concat_for_estimate(msgs: list[dict]) -> str:
    out = []
    for m in msgs or []:
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
    return "\n".join(out)

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
        "payload length": len(json.dumps(payload))
    }))

    t0 = _time.time()
    # 1) Timeout adattivo
    _est_chars = _messages_concat_for_estimate(payload.get("messages", []))
    _est_prompt_tokens = _approx_tokens_from_chars(_est_chars)
    _requested_max = int(payload.get("max_completion_tokens") or payload.get("max_tokens") or 2048)

    # Base 45s + 0.02s/token prompt + 0.03s/token output richiesto (togli/ritocca se vuoi)
    read_timeout_s = 45.0 + (0.02 * _est_prompt_tokens) + (0.03 * _requested_max)
    # Clamping sensato
    read_timeout_s = float(min(240.0, max(70.0, read_timeout_s)))

    try:
        r = await _post_with_retries(url,json_payload=payload,headers=headers, read_timeout_s=read_timeout_s, max_attempts=2)
    except Exception:
        # tentativo 2: fallback riducendo max tokens
        fallback_payload = dict(payload)
        if "max_completion_tokens" in fallback_payload:
            fallback_payload["max_completion_tokens"] = max(1024, int(_requested_max / 2))
        elif "max_tokens" in fallback_payload:
            fallback_payload["max_tokens"] = max(1024, int(_requested_max / 2))

        r = await _post_with_retries(
            "https://api.openai.com/v1/chat/completions",
            json_payload=fallback_payload,
            headers=headers,
            read_timeout_s=min(240.0, read_timeout_s + 30.0),  # leggermente più largo
            max_attempts=2,
        )
    # async with httpx.AsyncClient(timeout=timeout) as client:
    #     r = await client.post(url, headers=headers, json=payload)
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
