# gateway/routes/chat.py
import os, httpx, asyncio, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Set

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

router = APIRouter()

# --- Helpers ---------------------------------------------------------------

def _normalize_model(model: str) -> str:
    """Accetta 'openai:gpt-5' e restituisce 'gpt-5'."""
    m = (model or "").strip()
    if ":" in m:
        prov, name = m.split(":", 1)
        if prov.strip().lower() == "openai":
            m = name.strip()
    return m

# snapshot suggeriti da doc/screenshot; usati solo come preferenza
SNAPSHOT_ALIAS = {
    "gpt-5": "gpt-5-2025-08-07",
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
}

# cache semplice dei modelli disponibili lato OpenAI (TTL 60s)
_openai_models_cache: Dict[str, Any] = {"ts": 0.0, "set": set()}  # type: ignore

async def _get_openai_models() -> Set[str]:
    now = time.time()
    if (now - _openai_models_cache["ts"]) < 60 and _openai_models_cache["set"]:
        return _openai_models_cache["set"]

    if not OPENAI_API_KEY:
        # senza key non possiamo validare: restituisci set vuoto per far fallire in modo chiaro
        return set()

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{OPENAI_BASE}/models", headers=headers)
            r.raise_for_status()
            data = r.json()
            ids = {m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")}
            _openai_models_cache["ts"] = now
            _openai_models_cache["set"] = ids
            return ids
    except httpx.HTTPError:
        # in caso di errore di rete non blocchiamo: tornerà set vuoto, e l'endpoint restituirà 502/400 con messaggio chiaro
        return set()

async def _pick_openai_remote(norm: str) -> str:
    """
    Sceglie il 'remote' migliore per OpenAI:
    1) preferisci snapshot se disponibile per la key
    2) altrimenti usa l'alias (es. 'gpt-5')
    In assenza totale -> solleva HTTP 400 con elenco parziale dei modelli disponibili.
    """
    avail = await _get_openai_models()
    # preferenza: snapshot suggerito
    snap = SNAPSHOT_ALIAS.get(norm)
    if snap and snap in avail:
        return snap
    # alias semplice
    if norm in avail:
        return norm
    # non disponibile: costruisci messaggio utile
    examples = ", ".join(sorted([m for m in avail if isinstance(m, str) and m.startswith("gpt-")][:10])) or "(none)"
    raise HTTPException(400, detail=f"Model '{norm}' not available for this API key. Available examples: {examples}")

# --- Schemi ---------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None

# --- Endpoint -------------------------------------------------------------

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY missing in gateway")

    norm = _normalize_model(req.model)

    # provider: openai (unico in questo router)
    try:
        remote = await _pick_openai_remote(norm)
    except HTTPException as he:
        # error 400 chiaro se il modello non è disponibile per la key
        raise he

    payload = {
        "model": remote,
        "messages": [m.dict() for m in req.messages],
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{OPENAI_BASE}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        # Propaga il vero status e il body del provider (evita 502 generici)
        txt = e.response.text if e.response is not None else str(e)
        code = e.response.status_code if e.response is not None else 502
        raise HTTPException(code, detail=f"provider error for model={remote}: {txt}")
    except httpx.HTTPError as e:
        raise HTTPException(502, detail=f"provider connection error: {e}")
