# gateway/routes/chat.py
import os, logging, time
import httpx
from typing import Set, List, Dict, Any
import os, json, time, uuid
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException

from config import load_models_cfg
from model_resolver import resolve_model
from providers import ollama as oll
from providers import openai_compat as oai
from providers import anthropic as ant
from providers import deepseek as dsk
from utils.openai_like import format_chat_response

router = APIRouter()
logger = logging.getLogger("gateway.chat")


DUMP_ENABLED = os.getenv("GATEWAY_DUMP", "0") not in ("0", "", "false", "False")
DUMP_DIR = os.getenv("GATEWAY_DUMP_DIR", "/app/runs/gateway_dumps")

def _dump_provider_json(kind: str, run_id: str, model: str, data: dict) -> str | None:
    if not DUMP_ENABLED:
        return None
    try:
        Path(DUMP_DIR).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        safe_model = (model or "unknown").replace(":", "_")
        name = f"{ts}_{kind}_{run_id}_{safe_model}.json"
        path = os.path.join(DUMP_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


@router.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    model_name = body.get("model", "auto")
    profile = body.get("profile")  # NEW (es. "plan.fast" / "code.strict")
    messages = body.get("messages", [])
    temperature = body.get("temperature", 0.2)
    max_tokens = body.get("max_tokens", 512)


    response_format = body.get("response_format")
    tools          = body.get("tools")
    tool_choice    = body.get("tool_choice")

    cfg, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
    try:
        m = resolve_model(cfg, models, model_name, profile=profile, want_modality="chat")
    except Exception as e:
        raise HTTPException(400, f"model resolution failed: {e}")

    provider = (m.get("provider") or "").lower()
    base = (m.get("base_url") or "").rstrip("/")
    remote = m.get("remote_name") or m.get("name")
    api_key_env = m.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    logger.info(f"[chat] provider={provider} model={m.get('name')} profile={profile} remote={remote} base={base}")
    try:
        # --- NEGOZIAZIONE GPT-5 / GPT-5-nano (OpenAI) ---
        if provider == "openai":
            try:
                if not api_key:
                    raise HTTPException(401, "missing OPENAI api key")
                # Scegli automaticamente snapshot o alias, in base a cosa vede la tua key
                remote = await _pick_openai_remote(base, api_key, remote)
            except HTTPException:
                raise  # 400 con messaggio esplicito se non disponibile
            except Exception as e:
                logger.exception("openai model negotiation failed: %s", e)
                raise HTTPException(502, f"openai model negotiation failed: {e}")

            try:
                if provider == "ollama":
                    content = await oll.chat(base, remote, messages, temperature, max_tokens)
                elif provider == "openai":
                    if not api_key:
                        raise HTTPException(401, "missing OPENAI api key")
                    content = await oai.chat(
                    base, api_key, remote, messages, temperature, max_tokens,
                        response_format=response_format, 
                        tools=tools, 
                        tool_choice=tool_choice,
                     )
                    
                elif provider == "vllm":
                    content = await oai.chat(base, api_key, remote, messages, temperature, max_tokens)
                elif provider == "deepseek":
                    content = await dsk.chat(base, api_key, remote, messages, temperature, max_tokens)
                elif provider == "anthropic":
                    if not api_key:
                        raise HTTPException(401, "missing ANTHROPIC api key")
                    content = await ant.chat(base, api_key, remote, messages, temperature, max_tokens)
                else:
                    raise HTTPException(400, f"unsupported provider for chat: {provider}")
            except HTTPException:
                # già mappato con status corretto
                raise
            except httpx.HTTPStatusError as e:
                # Propaga il vero status + body del provider (evita 502 generico)
                txt = e.response.text if e.response is not None else str(e)
                code = e.response.status_code if e.response is not None else 502
                logger.error("chat provider HTTP error: %s", txt)
                raise HTTPException(code, detail=f"provider error for model={remote}: {txt}")
            except Exception as e:
                logger.exception(f"chat provider error: {e}")
                raise HTTPException(502, f"upstream chat provider failed: {type(e).__name__}: {e}")

    
    except HTTPException:
        raise
    except Exception as e:
        txt = e.response.text if e.response is not None else str(e)
        code = e.response.status_code if e.response is not None else 502
        logger.error("chat provider HTTP error: %s", txt)
       
        raise HTTPException(502, f"upstream chat provider failed: {type(e).__name__}: {e}")

    return format_chat_response(m.get("name"), content or "")

# --- Helpers: normalizzazione nome modello e discovery modelli OpenAI ---

def _normalize_openai_name(name: str) -> str:
    """
    Accetta 'openai:gpt-5' e restituisce 'gpt-5'.
    """
    m = (name or "").strip()
    if ":" in m:
        prov, raw = m.split(":", 1)
        if prov.strip().lower() == "openai":
            return raw.strip()
    return m

# Preferenze snapshot (se disponibili per la key)
_SNAPSHOT_PREF = {
    "gpt-5": "gpt-5-2025-08-07",
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
}

# cache (TTL 60s) dei modelli disponibili lato OpenAI
_OAI_MODELS_CACHE: Dict[str, Any] = {"ts": 0.0, "set": set()}  # type: ignore

async def _get_openai_models(base_url: str, api_key: str | None) -> Set[str]:
    """
    Legge /v1/models dal base_url dato. Cache 60s.
    Se api_key assente o errore rete → ritorna set() per forzare errore esplicito più avanti.
    """
    now = time.time()
    if (now - _OAI_MODELS_CACHE["ts"]) < 60 and _OAI_MODELS_CACHE["set"]:
        return _OAI_MODELS_CACHE["set"]

    if not api_key:
        return set()

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{base_url}/models", headers=headers)
            r.raise_for_status()
            data = r.json() or {}
            ids = {m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")}
            _OAI_MODELS_CACHE["ts"] = now
            _OAI_MODELS_CACHE["set"] = ids
            return ids
    except httpx.HTTPError as e:
        logger.warning("openai models probe failed: %s", e)
        return set()

async def _pick_openai_remote(base_url: str, api_key: str | None, desired: str) -> str:
    """
    Per 'gpt-5' / 'gpt-5-nano' seleziona:
    1) snapshot preferito se disponibile,
    2) altrimenti alias semplice (es. 'gpt-5'),
    3) altrimenti HTTP 400 con elenco (parziale) disponibili.
    Per altri modelli, restituisce 'desired' invariato.
    """
    norm = _normalize_openai_name(desired)
    if not norm.startswith("gpt-5"):
        return norm

    avail = await _get_openai_models(base_url, api_key)
    #logging.info("available models: %s", avail)
    snap = _SNAPSHOT_PREF.get(norm)

    if snap and snap in avail:
        return snap
    if norm in avail:
        return norm

    examples = ", ".join(sorted([m for m in avail if isinstance(m, str) and m.startswith("gpt-")][:10])) or "(none)"
    raise HTTPException(400, detail=f"Model '{norm}' not available for this API key. Available examples: {examples}")
