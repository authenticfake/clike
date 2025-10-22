# --- begin: openai_compat unified imports/helpers ---
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
#TODO params filtering
CHAT_ALLOWED = {
    "model","messages","temperature","top_p","n","stream","stop",
    "presence_penalty","frequency_penalty","logit_bias","user",
    "tools","tool_choice","response_format","seed","max_tokens"  # Chat: usa max_tokens
}
#TODO params filtering
RESP_ALLOWED = {
    "model","input","metadata","temperature","top_p","n","stop",
    "response_format","audio","modalities","reasoning","tool_choice",
    "tools","seed","max_output_tokens"  # Responses: usa max_output_tokens
}
#TODO params filtering
def _normalize_and_validate(api_kind: str, payload: dict) -> dict:
    """api_kind: 'chat' | 'responses'"""
    out = dict(payload)  # shallow copy

    if api_kind == "chat":
        # Normalizza: se ci fosse 'max_completion_tokens', mappalo a 'max_tokens'
        if "max_completion_tokens" in out and "max_tokens" not in out:
            out["max_tokens"] = out.pop("max_completion_tokens")
        # Filtra i campi non permessi
        allowed = CHAT_ALLOWED
    else:  # responses
        # Normalizza: se c'è 'max_tokens', mappalo a 'max_output_tokens'
        if "max_tokens" in out and "max_output_tokens" not in out:
            out["max_output_tokens"] = out.pop("max_tokens")
        allowed = RESP_ALLOWED

    unknown = [k for k in out.keys() if k not in allowed]
    if unknown:
        # Fail-fast con messaggio chiaro
        raise ValueError(f"[payload-validation] Unknown parameter(s) for {api_kind}: {unknown}")

    return out

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
# --- end: openai_compat unified imports/helpers ---
# --- begin: payload builders ---
log = logging.getLogger("gateway.openai")

def _build_chat_payload(
    model: str,
    messages: List[Dict[str, str]],
    gen: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Costruisce il payload per /v1/chat/completions.
    - Usa max_completion_tokens (non max_output_tokens).
    - Pulisce i campi non supportati dal Chat endpoint.
    """
    out: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    # Sampling / behavior
   # if "temperature" in gen: out["temperature"] = gen["temperature"]
    #if "top_p" in gen: out["top_p"] = gen["top_p"]
    #if "stop" in gen and gen["stop"]: out["stop"] = gen["stop"]
    if "presence_penalty" in gen: out["presence_penalty"] = gen["presence_penalty"]
    #if "frequency_penalty" in gen: out["frequency_penalty"] = gen["frequency_penalty"]

    # Token budget (Chat)
    # Se arriva max_output_tokens per sbaglio, lo mappiamo → max_completion_tokens
    if "max_completion_tokens" in gen:
        out["max_completion_tokens"] = gen["max_completion_tokens"]
    elif "max_output_tokens" in gen:
        out["max_completion_tokens"] = gen["max_output_tokens"]
    elif "max_tokens" in gen:  # retro-compat, se proprio arriva
        out["max_completion_tokens"] = gen["max_tokens"]

    # Response format (solo se fornito e valido per Chat)
    if gen.get("response_format"):
        out["response_format"] = gen["response_format"]

    # Tools (se presenti nel tuo flusso)
    if gen.get("tools"): out["tools"] = gen["tools"]
    if gen.get("tool_choice"): out["tool_choice"] = gen["tool_choice"]

    return out


def _linearize_messages_for_responses(messages: List[Dict[str, str]]) -> Tuple[str, str]:
    """
    Converte i messaggi in:
    - instructions: somma dei messaggi system
    - input: conversazione user/assistant linearizzata (stateless)
    """
    systems = []
    turns = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            systems.append(content)
        elif role in ("user", "assistant"):
            turns.append(f"{role.upper()}:\n{content}")
        else:
            # altri ruoli: trattali come user per non perdere contenuto
            turns.append(f"{role.upper() or 'USER'}:\n{content}")
    instructions = "\n\n".join(systems).strip()
    linear_input = "\n\n---\n\n".join(turns).strip()
    return instructions, linear_input


def _build_responses_payload(
    model: str,
    messages: List[Dict[str, str]],
    gen: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Costruisce il payload per /v1/responses.
    - Usa max_output_tokens (non max_completion_tokens).
    - instructions ← sommatoria dei system
    - input ← linearizzazione user/assistant
    """
    instructions, linear_input = _linearize_messages_for_responses(messages)

    out: Dict[str, Any] = {
        "model": model,
        "instructions": instructions or None,
        "input": linear_input,
    }

    # Sampling / behavior
    #if "temperature" in gen: out["temperature"] = gen["temperature"]
    #if "top_p" in gen: out["top_p"] = gen["top_p"]
    #if "stop" in gen and gen["stop"]: out["stop"] = gen["stop"]
    # Responses supporta altre opzioni come truncation, parallel_tool_calls, ecc. se te le passi in gen
    if "truncation" in gen: out["truncation"] = gen["truncation"]
    if "parallel_tool_calls" in gen: out["parallel_tool_calls"] = gen["parallel_tool_calls"]

    # Token budget (Responses)
    if "max_output_tokens" in gen:
        out["max_output_tokens"] = gen["max_output_tokens"]
    elif "max_completion_tokens" in gen:  # fallback se arriva quello "chat"
        out["max_output_tokens"] = gen["max_completion_tokens"]
    elif "max_tokens" in gen:  # retro-compat
        out["max_output_tokens"] = gen["max_tokens"]

    # Tools / response_format (se utili nel tuo flusso)
    # if gen.get("response_format"):
    #     out["response_format"] = gen["response_format"]
    if gen.get("tools"): out["tools"] = gen["tools"]
    if gen.get("tool_choice"): out["tool_choice"] = gen["tool_choice"]

    # Ripulisci chiavi None per evitare 400 inutili
    return {k: v for k, v in out.items() if v is not None}

# --- end: payload builders ---
# --- begin: response normalizers ---

def _normalize_chat_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    text = ""
    finish_reason = ""
    usage = resp_json.get("usage") or {}
    files: List[Dict[str, Any]] = []

    try:
        choices = resp_json.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            finish_reason = choices[0].get("finish_reason") or ""
    except Exception as e:
        return _mk_unified_result(False, "", files, usage, finish_reason, resp_json, [f"normalize_chat: {e}"])

    return _mk_unified_result(True, text, files, usage, finish_reason, resp_json, [])


def _extract_responses_text(resp_json: Dict[str, Any]) -> str:
    """
    Estrae testo dai principali layout della Responses API:
    - output_text (diretto)
    - output / outputs / items con blocchi 'message' → 'content' → [{'type':'output_text'|'text','text':...}]
    - fallback su 'text' a livello item
    """
    # 0) shortcut: alcuni modelli espongono direttamente 'output_text'
    if isinstance(resp_json.get("output_text"), str):
        return (resp_json["output_text"] or "").strip()

    parts: List[str] = []

    # 1) supporta sia 'output' (singolare) che 'outputs' (plurale), oltre a 'items'/'content'
    for key in ("output", "outputs", "items", "content"):
        seq = resp_json.get(key)
        if not isinstance(seq, list):
            continue
        for itm in seq:
            if not isinstance(itm, dict):
                continue

            # a) path canonico: item.type == 'message' → content: [ {type: 'output_text'|'text', text: '...'} ]
            if itm.get("type") == "message":
                blocks = itm.get("content") or []
                if isinstance(blocks, list):
                    for b in blocks:
                        if isinstance(b, dict):
                            if b.get("type") in ("output_text", "text") and isinstance(b.get("text"), str):
                                parts.append(b["text"])

            # b) alcuni layout mettono 'message': {'output_text': '...'}
            msg = itm.get("message") or {}
            if isinstance(msg, dict):
                ot = msg.get("output_text")
                if isinstance(ot, str):
                    parts.append(ot)
                cnt = msg.get("content") or []
                if isinstance(cnt, list):
                    for c in cnt:
                        if isinstance(c, dict) and isinstance(c.get("text"), str):
                            parts.append(c["text"])

            # c) fallback: text diretto nell'item
            if isinstance(itm.get("text"), str):
                parts.append(itm["text"])

    return "\n".join(p.strip() for p in parts if isinstance(p, str) and p.strip())



def _normalize_responses_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    text = ""
    finish_reason = ""
    usage = resp_json.get("usage") or {}
    files: List[Dict[str, Any]] = []

    try:
        # testo
        text = _extract_responses_text(resp_json).strip()
        # finish_reason: se c'è uno stato/flag, altrimenti vuoto
        finish_reason = (
            resp_json.get("finish_reason")
            or resp_json.get("reason")
            or ""
        )
        # eventuali file artifacts (se la tua integrazione li prevede in Responses)
        if isinstance(resp_json.get("outputs"), list):
            for itm in resp_json["outputs"]:
                if isinstance(itm, dict) and itm.get("type") in ("file", "image", "artifact"):
                    files.append(itm)
    except Exception as e:
        return _mk_unified_result(False, "", files, usage, finish_reason, resp_json, [f"normalize_responses: {e}"])

    return _mk_unified_result(True, text, files, usage, finish_reason, resp_json, [])


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
    
async def chat(
    base: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    reasoning: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    timeout: Optional[float] = 240.0,
    top_p: Optional[float] = None,
    stop: Optional[List[str]] = None
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base.rstrip('/')}/chat/completions"
    gen = {}
    gen["temperature"] = temperature
    gen["max_tokens"] = max_tokens
    gen["response_format"] = response_format
    gen["reasoning"] = reasoning
    gen["tools"] = tools
    gen["tool_choice"] = tool_choice
    gen["top_p"] = top_p
    gen["stop"] = stop
    gen["api"] = "chat"

    return await openai_complete_unified(api_key=api_key, model=model, messages=messages, gen=gen, timeout_s=timeout)

# --- end: response normalizers ---
async def openai_complete_unified(
    
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    gen: Dict[str, Any],
    timeout_s: float,
) -> Dict[str, Any]:
    """
    Entry-point unificato per OpenAI.
    - Se gen["api"] == "responses" usa /v1/responses, altrimenti /v1/chat/completions.
    - Normalizza sempre il risultato a: { ok, text, files, usage, finish_reason, raw, errors }.
    - Comportamento deterministico: NESSUN retry, NESSUNA eccezione alzata; i non-200 ritornano ok=False con errori.
    """
    use_responses = (gen.get("api") == "responses")

    # Costruisci payload + normalizer + budget (telemetria)
    if use_responses:
        url = _OPENAI_RESPONSES_URL
        payload = _build_responses_payload(model, messages, gen)
        normalizer = _normalize_responses_response
        budget = payload.get("max_output_tokens")  # responses API
    else:
        url = _OPENAI_CHAT_URL
        payload = _build_chat_payload(model, messages, gen)
        normalizer = _normalize_chat_response
        budget = payload.get("max_completion_tokens")  # chat/completions
    
    #log.info(".openai_complete_unified resonseAPi %s, payload %s", use_responses, payload)
    # Chiamata deterministica (timeout: float va bene; se vuoi granularità usa httpx.Timeout(...))
    try:
        headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(url, headers=headers, json=payload)
                log.info("openai_complete_unified response %s", r.status_code)
                log.info("gateway._post_with_retries response text %s", r.text)
       
    except Exception as e:
        log.error("exception openai_complete_unified Error: %s", e, exc_info=True)
        # Errore infrastrutturale (rete/timeout): ritorno unificato ok=False
        return _mk_unified_result(
            ok=False,
            text="",
            files=[],
            usage={},
            finish_reason="",
            raw={"exception": f"{e.__class__.__name__}: {e}"},
            errors=[f"httpx:{e}"],
        )
    log.info("after calling...openai_complete_unified: %s", r.status_code)
    # Successo 200 → normalizza e ritorna
    if r.status_code == 200:
        try:
            return normalizer(r.json())
        except Exception as e:
            log.error("openai_complete_unified normalizer: %s", e) 

            # Body 200 ma non normalizzabile → fallback unificato ok=False
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

    # Non-200 → costruisco errore unificato senza alzare eccezioni
    log.error("111 openai_compact.openai_complete_unified text: %s", r.text)
    try:
        j = r.json()
        err = j.get("error", {}) if isinstance(j, dict) else {}
    except Exception:
        log.error("openai_compact.openai_complete_unified: %s", r)
        err = {}

    message = err.get("message") or f"HTTP {r.status_code}"
    code = err.get("code") or "unknown_error"
    param = err.get("param")

    return _mk_unified_result(
        ok=False,
        text="",
        files=[],
        usage={},
        finish_reason="",
        raw={
            "status_code": r.status_code,
            "url": str(r.url),
            "error": err or {"message": message, "code": code, "param": param},
            "payload_echo_bytes": len(json.dumps(payload, ensure_ascii=False)) if payload else 0,
            "budget": budget,
        },
        errors=[f"openai:{code}:{param}:{message}"],
    )

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