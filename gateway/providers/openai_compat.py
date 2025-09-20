# gateway/providers/openai_compat.py
# OpenAI-compatible Chat Completions client with multi-model fallback:
# 1) Structured Outputs (JSON Schema) when "files" scenario is detected
# 2) Tool/Function calling (emit_files) strict
# 3) Plain JSON (system instruction) + robust JSON extraction
#
# Works with GPT-5/4/3.x and vLLM OpenAI-compatible backends.

from __future__ import annotations
import httpx, json, re
from typing import Any, List, Dict, Tuple, Optional

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

# -------------------------- Heuristics --------------------------------------
def _looks_like_files_req(messages: List[dict]) -> bool:
    """
    Returns True if prompt looks like it requests structured 'files' output.
    (Heuristics only: presence of "files" or explicit Return {...} hints.)
    """
    try:
        for m in messages or []:
            role = (m.get("role") or "").lower()
            if role not in ("system", "user"):
                continue
            c = (m.get("content") or "").lower()
            if '"files"' in c or "return: {\"files\"" in c or "return: {'files'" in c:
                return True
            # lightweight hint keywords
            if "emit files" in c or "generate files" in c or "files:[" in c:
                return True
    except Exception:
        pass
    return False

# -------------------------- JSON extraction ---------------------------------
def _peel_json_block(s: str) -> Optional[str]:
    """
    Extract first JSON object/array from a free-form string.
    Supports fenced code blocks ```json ... ``` or raw {...} / [...]
    """
    if not isinstance(s, str) or not s:
        return None

    # 1) ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        if cand.startswith("{") or cand.startswith("["):
            try:
                json.loads(cand)
                return cand
            except Exception:
                pass

    # 2) Rough brace scan for first balanced JSON object/array
    #    (simple stack-based scan; safe enough for assistant outputs)
    for opener, closer in [("{", "}"), ("[", "]")]:
        stack = []
        start = None
        for i, ch in enumerate(s):
            if ch == opener:
                if not stack:
                    start = i
                stack.append(ch)
            elif ch == closer and stack:
                stack.pop()
                if not stack and start is not None:
                    cand = s[start:i+1]
                    try:
                        json.loads(cand)
                        return cand
                    except Exception:
                        start = None
                        continue
    return None

# -------------------------- Attempt runners ---------------------------------
async def _run_chat(
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    r = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

def _first_message_content(data: Dict[str, Any]) -> str:
    """
    Estrae testo dal primo choice. Alcuni backend OpenAI-compat
    restituiscono 'content' come lista di segmenti.
    """
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    content = msg.get("content", "")
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, dict):
                if "text" in seg and isinstance(seg["text"], str):
                    parts.append(seg["text"])
                elif "content" in seg and isinstance(seg["content"], str):
                    parts.append(seg["content"])
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts).strip()
    return (content or "").strip()


def _first_tool_args_as_json(data: Dict[str, Any]) -> Optional[str]:
    try:
        call = ((data.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
        if not call:
            return None
        fn = (call[0] or {}).get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, (dict, list)):
            return json.dumps(args, ensure_ascii=False)
        if isinstance(args, str) and args.strip():
            # validate if it's JSON string
            try:
                _ = json.loads(args)
                return args
            except Exception:
                # not JSON, wrap it
                return json.dumps({"files": [], "messages": [{"role":"assistant","content": args}]}, ensure_ascii=False)
    except Exception:
        pass
    return None

# -------------------------- Public API --------------------------------------
async def chat(
    base_url: str,
    api_key: str | None,
    model: str,
    messages: List[dict],
    temperature: float | None,
    max_tokens: int | None
) -> str:
    """
    Returns ALWAYS a string:
      - plain assistant text (normal chat), OR
      - JSON string (when file-generation scenario is detected).
    Compatible with GPT-5/4/3.x and vLLM OpenAI-compatible backends.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # base payload
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        if not (model or "").startswith("gpt-5"):
            payload["temperature"] = temperature

    # Token param differences (GPT-5 vs older/vLLM)
    # Token params (default sicuri)
    budget = max(256, int(max_tokens or 0))  # se None/0 → 256
    if (model or "").startswith("gpt-5"):
        # per compat massima, invia ENTRAMBI i parametri
        payload["max_completion_tokens"] = budget
        
    else:
        payload["max_tokens"] = budget

    want_files = _looks_like_files_req(messages)
        
    async with httpx.AsyncClient(timeout=120) as client:
        # ---------- Attempt 1: Structured Outputs (broad models: 5.x, 4o, some backends) ----------
        if want_files:
            structured_payload = dict(payload)
            structured_payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "clike_files",
                    "strict": True,
                    "schema": FILES_JSON_SCHEMA
                }
            }
            try:
                data = await _run_chat(client, base_url, headers, structured_payload)
                # content should already be valid JSON as string
                content = _first_message_content(data)
                if content.strip():
                    # sanity: verify JSON to avoid 422 upstream
                    json.loads(content)
                    return content
            except httpx.HTTPStatusError as e:
                # If provider/back-end doesn't support response_format → fall through
                err = (e.response.text if e.response is not None else str(e)).lower()
                if "response_format" not in err and "json_schema" not in err:
                    # other hard error → re-raise (to be mapped by gateway)
                    raise

        # ---------- Attempt 2: Tool/Function calling (widely supported, incl. many vLLM) ----------
        if want_files:
            tools_payload = dict(payload)
            tools_payload["tools"] = [{
                "type": "function",
                "function": {
                    "name": "emit_files",
                    "description": "Return the generated files",
                    "parameters": FILES_JSON_SCHEMA
                }
            }]
            tools_payload["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
            try:
                data = await _run_chat(client, base_url, headers, tools_payload)
                tool_json = _first_tool_args_as_json(data)
                if tool_json:
                    # validate
                    obj = json.loads(tool_json)
                    if isinstance(obj, dict) and "files" in obj:
                        return tool_json
            except httpx.HTTPStatusError as e:
                # If tools not supported → fall through
                err = (e.response.text if e.response is not None else str(e)).lower()
                if "tools" not in err and "tool_choice" not in err and "function" not in err:
                    raise

        # ---------- Attempt 3: Plain JSON instruction (works everywhere) ----------
        # We prepend a system instruction to emit only JSON adhering to schema.
        if want_files:
            json_payload = dict(payload)
            json_payload["messages"] = [
                {"role": "system",
                 "content": (
                    "You must answer ONLY as strict JSON matching this schema: "
                    + json.dumps(FILES_JSON_SCHEMA, ensure_ascii=False)
                    + ". Do not add prose. No code fences. No comments."
                 )},
            ] + (payload.get("messages") or [])

            data = await _run_chat(client, base_url, headers, json_payload)
            content = _first_message_content(data)
            # some backends may return a dict/list as content with structured outputs
            if not isinstance(content, str):
                try:
                    content = json.dumps(content, ensure_ascii=False)
                except Exception:
                    content = ""

            if content.strip():
                # sanity: verify JSON to avoid 422 upstream
                json.loads(content)
                return content

            # As very last resort, wrap text
            return json.dumps({"files": [], "messages": [{"role": "assistant", "content": content}]}, ensure_ascii=False)

        # ---------- Normal chat (no files scenario) ----------
        data = await _run_chat(client, base_url, headers, payload)
        content = _first_message_content(data)
        return content


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
