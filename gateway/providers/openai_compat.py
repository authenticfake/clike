# --- begin: openai_compat unified imports/helpers ---
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

log = logging.getLogger("openai")

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
#TODO params filtering
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

def _is_reasoning_model_name(model: Optional[str]) -> bool:
    """
    Riconosce i modelli 'reasoning' di OpenAI (GPT-5.1, Codex, o-series, ecc.)
    per i quali parametri come temperature/top_p non sono supportati.
    """
    if not model:
        return False
    m = model.lower()
    return any(
        tag in m
        for tag in (
            "gpt-5",
            "gpt-5.4",
            "gpt-5.4-pro"
            "gpt-5.1",       # gpt-5.1, gpt-5.1-chat, gpt-5.1-codex, etc.
            "gpt-5.1-codex",   # gpt-5.1-codex family
            "codex",         # catch-all codex models
            "o1", "o3"       # o1, o3 reasoning series
        )
    )

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
    
    # --- Filtra parametri non supportati dai modelli "reasoning" ---
    model_name = str(out.get("model") or "")
    if _is_reasoning_model_name(model_name):
        # I modelli reasoning (GPT-5.1, GPT-5.1-codex, o-series, ecc.)
        # NON supportano temperature/top_p/presence_penalty/frequency_penalty.
        # Vedi doc Azure/OpenAI:
        # - gpt-5.1-chat: "does not support parameters like temperature"
        #   https://learn.microsoft.com/.../openai/how-to/reasoning
        out.pop("temperature", None)
        out.pop("top_p", None)
        out.pop("presence_penalty", None)
        out.pop("frequency_penalty", None)

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

def _normalize_responses_tools(tools: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """
    Convert Chat Completions-style tools into Responses API-style tools.

    Chat style:
      {
        "type": "function",
        "function": {
          "name": "...",
          "description": "...",
          "parameters": {...}
        }
      }

    Responses style:
      {
        "type": "function",
        "name": "...",
        "description": "...",
        "parameters": {...}
      }
    """
    out: List[Dict[str, Any]] = []

    for t in tools or []:
        if not isinstance(t, dict):
            continue

        t_type = t.get("type")
        fn = t.get("function")

        if t_type == "function" and isinstance(fn, dict):
            item: Dict[str, Any] = {
                "type": "function",
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters") or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            }
            out.append(item)
        else:
            out.append(t)

    return out


def _normalize_responses_tool_choice(tool_choice: Any) -> Any:
    """
    Convert Chat Completions-style tool_choice into Responses API-style tool_choice.
    Normalize empty / invalid values to None so they are omitted from the payload.
    """
    if tool_choice is None:
        return None

    if isinstance(tool_choice, str):
        value = tool_choice.strip().lower()
        if value == "":
            return None
        if value in {"none", "auto", "required"}:
            return value
        return None

    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            fn = tool_choice.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                if not name:
                    return None
                return {
                    "type": "function",
                    "name": name,
                }
        t = tool_choice.get("type")
        if t in {"none", "auto", "required"}:
            return {"type": t}
        return None

    return None

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

    # Structured outputs for Responses API:
    # In Responses API, Structured Outputs are configured via text.format
    # instead of the top-level response_format parameter used by Chat.
    rf = gen.get("response_format")
    text_cfg: Dict[str, Any] = {}
    if rf:

        # Typical Chat-style structured outputs:
        # {
        #   "type": "json_schema",
        #   "json_schema": {
        #       "name": "FilesBundle",
        #       "schema": { ... },
        #       "strict": true
        #   }
        # }
        if isinstance(rf, dict) and rf.get("type") == "json_schema":
            js = rf.get("json_schema") or {}

            text_format: Dict[str, Any] = {"type": "json_schema"}

            # Prefer top-level values if already present (future-proof),
            # otherwise fall back to json_schema.* as produced for Chat API.
            name = rf.get("name") or js.get("name")
            schema = rf.get("schema") or js.get("schema")
            strict = rf.get("strict") if "strict" in rf else js.get("strict")

            if name is not None:
                text_format["name"] = name
            if schema is not None:
                text_format["schema"] = schema
            if strict is not None:
                text_format["strict"] = strict

            text_cfg["format"] = text_format
        else:
            # Non json_schema formats (e.g. {"type": "json_object"})
            # can be passed through as-is; the Responses API accepts
            # text.format = { "type": "json_object" } etc.
            text_cfg["format"] = rf


    norm_tools = _normalize_responses_tools(gen.get("tools"))
    if norm_tools:
        out["tools"] = norm_tools

    norm_tool_choice = _normalize_responses_tool_choice(gen.get("tool_choice"))
    if norm_tool_choice is not None:
        out["tool_choice"] = norm_tool_choice
    model_lower = (model or "").lower()
    is_codex = "codex" in model_lower
      
    if _is_reasoning_model_name(model_lower) or is_codex:
        # Default CLike per Codex: reasoning "low".
        # Se vuoi zero reasoning nascosto, cambia in {"effort": "none"}.
        out["reasoning"] = {"effort": "medium"}
        if "format" not in text_cfg:
            text_cfg["format"] = {"type": "text"}

        text_cfg["verbosity"] = "medium"

    if text_cfg:
        out["text"] = text_cfg    
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

    def _try_parse_json(value: Any) -> Any:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return None

    try:
        # 1) Extract plain text if present
        text = _extract_responses_text(resp_json).strip()

        # 2) Finish reason
        finish_reason = (
            resp_json.get("finish_reason")
            or (resp_json.get("incomplete_details") or {}).get("reason")
            or resp_json.get("reason")
            or ""
        )

        # 3) Extract artifacts / files if already present
        outputs = resp_json.get("output") or resp_json.get("outputs") or []
        if isinstance(outputs, list):
            for itm in outputs:
                if not isinstance(itm, dict):
                    continue

                itm_type = str(itm.get("type") or "").lower()

                # Native artifacts / files
                if itm_type in {"file", "image", "artifact"}:
                    files.append(itm)
                    continue

                # Responses API function calls
                if itm_type in {"function_call", "tool_call"}:
                    fn_name = itm.get("name") or (itm.get("function") or {}).get("name")
                    raw_args = (
                        itm.get("arguments")
                        or itm.get("input")
                        or itm.get("call_arguments")
                        or (itm.get("function") or {}).get("arguments")
                    )

                    parsed_args = _try_parse_json(raw_args)
                    if fn_name == "emit_files" and isinstance(parsed_args, dict):
                        maybe_files = parsed_args.get("files")
                        if isinstance(maybe_files, list):
                            files.extend(maybe_files)

        # 4) If still no files, try to parse text as JSON bundle
        if not files and text:
            parsed_text = _try_parse_json(text)
            if isinstance(parsed_text, dict):
                maybe_files = parsed_text.get("files")
                if isinstance(maybe_files, list):
                    files.extend(maybe_files)

    except Exception as e:
        text = str(resp_json)
        finish_reason = finish_reason or ""
        return _mk_unified_result(False, text, files, usage, finish_reason, resp_json, [f"normalize_responses: {e}"])

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
    gen: Dict[str, Any] = {}
    gen["temperature"] = temperature
    gen["max_tokens"] = max_tokens
    gen["response_format"] = response_format
    gen["reasoning"] = reasoning
    gen["tools"] = tools
    gen["tool_choice"] = tool_choice
    gen["top_p"] = top_p
    gen["stop"] = stop

    low_model = (model or "").lower()

    # All GPT-5 family and Codex family must go through Responses API.
    if low_model.startswith("gpt-5") or "codex" in low_model or _is_reasoning_model_name(low_model):
        gen["api"] = "responses"
    else:
        gen["api"] = "chat"

    return await openai_complete_unified(
        api_key=api_key,
        model=model,
        messages=messages,
        gen=gen,
        timeout_s=timeout,
    )
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
    log.info("openai_complete_unified %s", use_responses)
    log.info("openai_complete_unified (gen.get(api)) %s", gen.get("api"))
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
                #LOG RESPONSE OPENAI 
                #log.info("gateway._post_with_retries response text %s", r.text)
       
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
    else:
        raise RuntimeError("missing API key for OpenAI-compatible embeddings provider")

    payload = {
        "model": model,
        "input": input_text,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/embeddings",
            json=payload,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json() or {}

    vec = (data.get("data") or [{}])[0].get("embedding")
    if not isinstance(vec, list) or not vec:
        raise RuntimeError("OpenAI-compatible embeddings provider returned an empty vector")
    return vec