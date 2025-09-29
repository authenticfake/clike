# gateway/routes/chat.py
import os, httpx, asyncio, time, json, logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from providers import openai_compat as oai
from providers import anthropic as anth
from providers import deepseek as dsk
from providers import ollama as oll
from providers import vllm as vll


OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

VLLM_BASE = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1").rstrip("/")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
ANTHROPIC_BASE= os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")

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
    timeout: Optional[float] = None 

    provider: Optional[str] = Field(None, description="openai|anthropic|vllm|ollama")
    base_url: Optional[str] = None
    remote_name: Optional[str] = None
    max_completion_tokens: int | None = Field(None, description="GPT-5 style")

# ---------- Utils ----------

def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    # prefissi tipici che arrivano dal models.yaml come id
    if m.startswith("ollama:"): return "ollama"
    if m.startswith("vllm:"): return "vllm"
    return "openai"

def _json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)

# ---------- Endpoint ----------

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest,  request: Request):
    provider = (req.provider or request.headers.get("X-CLike-Provider") or _infer_provider(req.model) or "").lower().strip()

    # ----- Normalizza input per provider -----
    # ATTENZIONE: niente virgola -> niente tupla!
    model = req.model  # era: req.model,
    # Converte ChatMessage (pydantic) -> dict
    messages = []
    for m in (req.messages or []):
        try:
            messages.append(m.dict() if hasattr(m, "dict") else dict(m))
        except Exception:
            # fallback super-sicuro
            messages.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", "")})

    temperature = req.temperature
    max_tokens = req.max_tokens
    response_format = req.response_format
    tools = req.tools
    tool_choice = req.tool_choice
    remote = (req.remote_name or model)
    timeout = req.timeout

    # Logging solo con tipi JSON-safe (evita oggetti pydantic)
    log.info(
        "chat payload (safe) %s",
        _json({
            "provider": provider,
            "model": model,
            "remote": remote,
            "messages_len": len(messages),
            "has_tools": bool(tools),
            "has_tool_choice": bool(tool_choice),
            "has_response_format": bool(response_format),
            "max_tokens": max_tokens,
        })
    )


    # Routing per provider
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(401, "missing ANTHROPIC api key")
        data = await oai.chat(OPENAI_BASE, OPENAI_API_KEY, model, messages, temperature, max_tokens, response_format, tools, tool_choice, timeout) 
        return data
    if provider == "vllm":
        return await vll.chat(VLLM_BASE, model, messages, temperature, max_tokens, max_tokens, response_format, tools, tool_choice, timeout)
    if provider == "ollama":
        return await oll.chat(OLLAMA_BASE, model, messages, temperature, max_tokens, timeout)
    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise HTTPException(401, "missing ANTHROPIC api key")
            
        try:
            data = await anth.chat(ANTHROPIC_BASE, ANTHROPIC_API_KEY, model, messages, temperature,max_tokens, timeout)
            return data
        except httpx.HTTPStatusError as e:
            txt = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 502
            raise HTTPException(code, detail=f"provider error for model={model}: {txt}")
        except httpx.HTTPError as e:
            raise HTTPException(502, detail=f"provider connection error: {e}")
    else:
        raise HTTPException(400, f"unsupported provider for chat: {provider} for model '{req.model}")

