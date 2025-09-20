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

def _first_message_content(data: dict) -> str:
    """
    Estrae testo dal primo choice; alcuni backend restituiscono 'content'
    come lista di segmenti, altri come stringa.
    """
    try:
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for seg in content:
                if isinstance(seg, dict):
                    if isinstance(seg.get("text"), str):
                        parts.append(seg["text"])
                    elif isinstance(seg.get("content"), str):
                        parts.append(seg["content"])
                elif isinstance(seg, str):
                    parts.append(seg)
            return "".join(parts).strip()
        return (content or "").strip()
    except Exception:
        return ""



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
    messages: list,
    temperature: float | None,
    max_tokens: int | None,
    *,
    response_format=None,
    tools=None,
    tool_choice=None
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # payload base
    payload = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        if not str(model).startswith("gpt-5"):
            payload["temperature"] = float(temperature)

    # Budget di default per evitare 400/“max_tokens …”
    budget = max(256, int(max_tokens or 0))
    # GPT-5 preferisce anche max_completion_tokens
    if str(model).startswith("gpt-5"):
        payload["max_completion_tokens"] = budget
    else:
        payload["max_tokens"] = budget

    # --- NUOVO: pass-through Structured Outputs / tools (se presenti) ---
    if response_format is not None:
        payload["response_format"] = response_format
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

        # content può essere stringa o lista segmenti; normalizziamo a stringa
        try:
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for seg in content:
                    if isinstance(seg, dict):
                        if isinstance(seg.get("text"), str):
                            parts.append(seg["text"])
                        elif isinstance(seg.get("content"), str):
                            parts.append(seg["content"])
                    elif isinstance(seg, str):
                        parts.append(seg)
                return "".join(parts).strip()
            if isinstance(content, str) and content.strip():
                return content.strip()
            # 2) Fallback legacy: lasciali
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            if "text" in data:
                return data["text"]
            return (content or "").strip()
        except Exception:
            return ""



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
