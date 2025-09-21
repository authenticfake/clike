# gateway/routes/chat.py
import os, httpx, asyncio, time, json, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union

from providers import openai_compat as oai  # assicurati che esista

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

router = APIRouter()
log = logging.getLogger("gateway.chat")

# --- Helpers ---------------------------------------------------------------

def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if ":" in m:
        prov, name = m.split(":", 1)
        if prov.strip().lower() == "openai":
            m = name.strip()
    return m

# snapshot preferiti (se disponibili)
SNAPSHOT_ALIAS = {
    "gpt-5": "gpt-5-2025-08-07",
    "gpt-5-mini": "gpt-5-mini-2025-08-07",
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
}

_models_cache = {"ts": 0.0, "ids": set()}

async def _get_openai_models() -> set:
    now = time.time()
    if _models_cache["ids"] and (now - _models_cache["ts"] < 60):
        return _models_cache["ids"]
    if not OPENAI_API_KEY:
        return set()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{OPENAI_BASE}/models", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"})
            r.raise_for_status()
            data = r.json()
            ids = {x.get("id") for x in (data.get("data") or []) if isinstance(x, dict)}
            _models_cache.update(ts=now, ids=ids)
            return ids
    except httpx.HTTPError:
        return set()

async def _pick_openai_remote(norm: str) -> str:
    avail = await _get_openai_models()
    pref = SNAPSHOT_ALIAS.get(norm)
    if pref and pref in avail:
        return pref
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
    # nuovi campi (opzionali) pass-through
    response_format: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    profile: Optional[str] = None

# --- Endpoint -------------------------------------------------------------

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
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
        # **IMPORTANTE**: ritorniamo il JSON del provider (contiene tool_calls)
        return data
    except HTTPException as he:
        raise he
    except httpx.HTTPStatusError as e:
        txt = e.response.text if e.response is not None else str(e)
        code = e.response.status_code if e.response is not None else 502
        raise HTTPException(code, detail=f"provider error for model={remote}: {txt}")
    except httpx.HTTPError as e:
        raise HTTPException(502, detail=f"provider connection error: {e}")
