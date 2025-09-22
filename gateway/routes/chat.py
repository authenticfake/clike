# gateway/routes/chat.py
import os, httpx, asyncio, time, json, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union

from providers import openai_compat as oai

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

VLLM_BASE = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1").rstrip("/")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")

router = APIRouter()
log = logging.getLogger("gateway.chat")

# ---------- Helpers comuni ----------

def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if ":" in m:
        prov, name = m.split(":", 1)
        if prov.strip().lower() == "openai":
            m = name.strip()
    return m


# Snapshot preferiti per OpenAI (se disponibili)
SNAPSHOT_ALIAS = {
    "gpt-5": "gpt-5-2025-08-07",
    "gpt-5-mini": "gpt-5-mini-2025-08-07",
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
}

_models_cache = {"ts": 0.0, "ids": []}  # list per JSON-friendliness

async def _get_openai_models() -> list[str]:
    now = time.time()
    if _models_cache["ids"] and (now - _models_cache["ts"] < 60):
        return _models_cache["ids"]
    if not OPENAI_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{OPENAI_BASE}/models", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"})
            r.raise_for_status()
            data = r.json()
            ids = [x.get("id") for x in (data.get("data") or []) if isinstance(x, dict) and x.get("id")]
            _models_cache["ts"] = now
            _models_cache["ids"] = ids
            return ids
    except httpx.HTTPError:
        return []

async def _pick_openai_remote(norm: str) -> str:
    avail = await _get_openai_models()
    snap = SNAPSHOT_ALIAS.get(norm)
    if snap and snap in avail:
        return snap
    if norm in avail:
        return norm
    examples = ", ".join(sorted([m for m in avail if isinstance(m, str) and m.startswith("gpt-")][:10])) or "(none)"
    raise HTTPException(400, detail=f"Model '{norm}' not available for this API key. Available examples: {examples}")

# --- Schemi ---------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # pass-through opzionali (usati solo se il provider li supporta)
    response_format: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    profile: Optional[str] = None  # solo per osservabilità
    provider: Optional[str] = None

# ---------- Provider: vLLM (OpenAI-compatible) ----------

async def _vllm_chat(model: str, messages: list[dict], temperature: float|None, max_tokens: int|None) -> dict:
    payload: Dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    # vLLM di solito non richiede Authorization
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{VLLM_BASE}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()

# ---------- Provider: Ollama (/api/chat) ----------

async def _ollama_chat(model: str, messages: list[dict], temperature: float|None, max_tokens: int|None) -> dict:
    # Ollama usa /api/chat con schema diverso; convertiamo a OpenAI-like
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    options ={}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens is not None:
        options["max_tokens"] = max_tokens
        options["num_predict"] = max_tokens
        
    body["options"] = options

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()  # tipicamente: { "message": { "role": "assistant", "content": "..." }, ... }
        msg = (data.get("message") or {})
        content = msg.get("content", "")
        return {
            "id": data.get("id") or "ollama-chat",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": msg.get("role", "assistant"), "content": content},
                "finish_reason": "stop"
            }],
            "created": int(time.time())
        }

# ---------- Endpoint ----------

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    log.info("chat route model %s" , req.model)
    prov =provider = (req.provider or req.headers.get("X-CLike-Provider") or "").lower().strip()

    name = req.model
    # Log d’ingresso (solo tipi serializzabili)
    log.info("chat route in %s", json.dumps({
        "provider": provider, "model":req.model,
        "has_tools": bool(req.tools), "has_resp_fmt": bool(req.response_format),
        "profile": req.profile or None
    }))

    # Routing per provider
    if provider == "openai":

        if not OPENAI_API_KEY:
            raise HTTPException(500, "OPENAI_API_KEY missing in gateway")

        norm = _normalize_model(req.model)
        remote = await _pick_openai_remote(norm)

        # Log (stringhe/liste, niente set)
        log.info("chat route decision %s", json.dumps({
            "provider": "openai",
            "model": norm,
            "remote": remote,
            "base": OPENAI_BASE
        }))
        try:
            data = await oai.chat(
                base=OPENAI_BASE,
                api_key=OPENAI_API_KEY,
                model=remote,
                messages=[m.dict() for m in req.messages],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                response_format=req.response_format,
                tools=req.tools,
                tool_choice=req.tool_choice,
            )
            return data
        except httpx.HTTPStatusError as e:
            txt = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 502
            raise HTTPException(code, detail=f"provider error for model={remote}: {txt}")
        except httpx.HTTPError as e:
            raise HTTPException(502, detail=f"provider connection error: {e}")

    elif provider == "vllm":
        # vLLM: OpenAI-compatible (niente response_format/tooling sofisticato)
        data = await _vllm_chat(name, [m.dict() for m in req.messages], req.temperature, req.max_tokens)
        return data

    elif provider == "ollama":
        # Ollama: /api/chat → convertiamo
        data = await _ollama_chat(name, [m.dict() for m in req.messages], req.temperature, req.max_tokens)
        return data

    # Provider sconosciuto
    raise HTTPException(400, detail=f"Unknown provider '{prov}' for model '{req.model}'")

