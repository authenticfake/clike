# gateway/routes/chat.py
import os, httpx, asyncio, time, json, logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from providers import openai_compat as oai
from providers import anthropic as anth
from providers import deepseek as dsk
from providers import ollama as oll


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

# ---------- Provider: vLLM (OpenAI-compatible) ----------

async def _call_vllm(req: ChatRequest) -> Dict[str, Any]:
    base = (req.base_url or VLLM_BASE).rstrip("/")
    remote = (req.remote_name or req.model)

    payload: Dict[str, Any] = {
        "model": remote,
        "messages": [m.dict() for m in req.messages],
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens
    if req.tools is not None:
        payload["tools"] = req.tools
    if req.tool_choice is not None:
        payload["tool_choice"] = req.tool_choice

    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{base}/chat/completions", json=payload)
        txt = r.text
        ms = int((time.time() - t0)*1000)
        log.info("vllm.request %s", _json({"url": f"{base}/chat/completions", "model": remote}))
        if r.is_success:
            log.info("vllm.response %s", _json({"status": r.status_code, "latency_ms": ms}))
            return r.json()
        else:
            log.error("vllm.response %s", _json({"status": r.status_code, "latency_ms": ms, "error_text": txt[:2000]}))
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(e.response.status_code, detail=e.response.text)

# ---------- Provider: Ollama (/api/chat) ----------
    
async def _call_ollama(req: ChatRequest) -> Dict[str, Any]:
    base = (req.base_url or OLLAMA_BASE).rstrip("/")
    remote = (req.remote_name or req.model)

    # Ollama chat API è simile a OpenAI: /api/chat con messages
    payload: Dict[str, Any] = {
        "model": remote,
        "messages": [m.dict() for m in req.messages],
        "stream": False
    }
    options ={}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    if req.max_tokens is not None:
        options["max_tokens"] = req.max_tokens
        options["num_predict"] = req.max_tokens
        
    payload["options"] = options

    headers = {"Content-Type": "application/json"}

    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{base}/api/chat", json=payload, headers=headers)
        txt = r.text
        ms = int((time.time() - t0)*1000)
        log.info("ollama.request %s", _json({"url": f"{base}/api/chat", "model": remote}))
        if r.is_success:
            log.info("ollama.response %s", _json({"status": r.status_code, "latency_ms": ms}))
            data = r.json()
            # Normalizza in OpenAI-like
            content = ""
            try:
                content = (data.get("message") or {}).get("content") or ""
            except Exception:
                content = ""
            return {
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content}
                }],
                "usage": {}
            }
        else:
            log.error("ollama.response %s", _json({"status": r.status_code, "latency_ms": ms, "error_text": txt[:2000]}))
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(e.response.status_code, detail=e.response.text)

# ---------- Provider: OPENAI (/api/chat) ----------
async def _call_openai(req: ChatRequest) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY missing in gateway")

    # helper per avere sempre /v1 in coda all'OPENAI_BASE
    def _oai_base():
        base = OPENAI_BASE.rstrip("/")
        return base if base.endswith("/v1") else (base + "/v1")
    base = _oai_base().rstrip("/")
    norm_model = _normalize_model(req.model)

    remote = (req.remote_name or norm_model)
    
    
    payload: Dict[str, Any] = {
        "model": remote,
        "messages": [m.dict() for m in req.messages],
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    # normalizza budget token
    if req.max_completion_tokens is not None:
        payload["max_completion_tokens"] = req.max_completion_tokens
    elif req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens
    if req.response_format is not None:
        payload["response_format"] = req.response_format
    if req.tools is not None:
        payload["tools"] = req.tools
    if req.tool_choice is not None:
        payload["tool_choice"] = req.tool_choice

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
        txt = r.text
        ms = int((time.time() - t0)*1000)
        log.info("openai.request %s", _json({"url": f"{base}/chat/completions", "model": remote, "has_response_format": req.response_format is not None, "has_tools": req.tools is not None, "has_tool_choice": req.tool_choice is not None, "budget": req.max_completion_tokens or req.max_tokens}))
        if r.is_success:
            log.info("openai.response %s", _json({"status": r.status_code, "latency_ms": ms}))
            try:
                data = r.json()
                log.debug("openai.response.body %s", txt[:4000])
            except Exception:
                log.debug("openai.response.text %s", txt[:4000])
            return r.json()
        else:
            log.error("openai.response %s", _json({"status": r.status_code, "latency_ms": ms, "error_text": txt[:2000]}))
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(e.response.status_code, detail=e.response.text)
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
        data = await oai.chat(OPENAI_BASE, OPENAI_API_KEY, model, messages, temperature, max_tokens, response_format, tools, tool_choice) 
        return data
    if provider == "vllm":
        return await _call_vllm(req)
    if provider == "ollama":
        return await oll.chat(OLLAMA_BASE, model, messages, temperature, max_tokens)
    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise HTTPException(401, "missing ANTHROPIC api key")
            
        try:
            data = await anth.chat(ANTHROPIC_BASE, ANTHROPIC_API_KEY, model, messages, temperature,max_tokens)
            return data
        except httpx.HTTPStatusError as e:
            txt = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 502
            raise HTTPException(code, detail=f"provider error for model={model}: {txt}")
        except httpx.HTTPError as e:
            raise HTTPException(502, detail=f"provider connection error: {e}")
    else:
        raise HTTPException(400, f"unsupported provider for chat: {provider} for model '{req.model}")

