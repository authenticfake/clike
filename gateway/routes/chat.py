# gateway/routes/chat.py
import os, httpx, asyncio, time, json, logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from providers import openai_compat as oai
from providers import anthropic as anth
from config import load_models_cfg

OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE= os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
# Ollama (and any OpenAI-compatible local server) is served through openai_compat (decision D3).
OLLAMA_OPENAI_BASE = OLLAMA_BASE if OLLAMA_BASE.endswith("/v1") else f"{OLLAMA_BASE}/v1"
DEFAULT_CHAT_TIMEOUT_S = float(os.getenv("CHAT_TIMEOUT_S", "240"))


def provider_error_status(result: Any) -> int:
    """HTTP status for a failed unified provider result: 429 stays 429, everything else is 502."""
    raw = (result or {}).get("raw") if isinstance(result, dict) else None
    upstream = (raw or {}).get("status_code") if isinstance(raw, dict) else None
    return 429 if upstream == 429 else 502


def provider_not_configured(provider: str) -> HTTPException:
    """The gateway has no credentials for ``provider``: a server configuration problem (503), not a
    client authentication failure, so it is never reported as 401 (the extension reserves 401/503
    with a top-level ``code`` for the service token)."""
    env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider, f"{provider.upper()}_API_KEY")
    return HTTPException(503, detail={
        "code": "provider_not_configured",
        "message": f"provider '{provider}' is not configured on the gateway ({env} is not set)",
    })


def raise_for_provider_failure(result: Any, model: str) -> Any:
    """Unified results with ok=False become HTTP errors (they used to be returned as 200)."""
    if isinstance(result, dict) and result.get("ok") is False:
        errors = result.get("errors") or []
        raise HTTPException(
            provider_error_status(result),
            detail={"message": f"provider call failed for model={model}", "errors": errors[:5]},
        )
    return result

router = APIRouter()
log = logging.getLogger("gateway.chat")

# ---------- Helpers comuni ----------
def _sanitize_generation_api(provider: str, api: str | None) -> str:
    """
    Normalize the 'api' selector for providers.
    - OpenAI/ AzureOpenAI can use 'responses' or 'chat'.
    - Anthropic, Ollama, vLLM: force 'chat' (gateway implements OpenAI-compat /v1/chat/completions).
    """
    if not api:
        return "chat"
    p = (provider or "").lower()
    a = (api or "").lower()
    if p in ("openai", "azure") and a in ("responses", "chat"):
        return a
    # For Anthropic (and others) never use 'responses'
    return "chat"

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

def _sanitize_mode_contract_payload(provider: str, mode_contract: dict | None, response_format, tools, tool_choice) -> dict:
    contract = dict(mode_contract or {})
    mode = str(contract.get("mode") or "free").lower()
    allow_file_output = bool(contract.get("allow_file_output", False))

    rf = response_format
    tl = tools
    tc = tool_choice

    if mode == "free" and not allow_file_output:
        rf = None
        tl = None
        tc = None

    prov = str(provider or "").lower().strip()

    # In free chat, never allow file-generation contract.
    # In coding/harper, do NOT strip tools for OpenAI, because GPT-5 family
    # is more reliable with tool-calling than with long textual JSON output.
    if mode == "free" and prov in {"openai", "azure_openai"} and tl:
        tl = None
        tc = None

    # Tool-oriented providers should not receive response_format.
    if prov in {"anthropic", "ollama", "deepseek", "vllm"} and rf:
        rf = None

    return {
        "response_format": rf,
        "tools": tl,
        "tool_choice": tc,
    }
# --- Schemi ---------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    profile: Optional[str] = None
    timeout: Optional[float] = None

    provider: Optional[str] = Field(None, description="openai|anthropic|vllm|ollama|deepseek")
    base_url: Optional[str] = None
    remote_name: Optional[str] = None
    max_completion_tokens: Optional[int] = Field(None, description="GPT-5 style")
    mode_contract: Optional[Dict[str, Any]] = None

# ---------- Utils ----------

def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    # prefissi tipici che arrivano dal models.yaml come id
    if m.startswith("ollama:"): return "ollama"
    return "openai"

def _json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)

def _load_model_catalog() -> list[dict]:
    try:
        _, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
        return models or []
    except Exception:
        return []

def _match_model_entry(model_name: str) -> dict | None:
    wanted = (model_name or "").strip().lower()
    if not wanted:
        return None

    for m in _load_model_catalog():
        mid = str(m.get("id") or "").strip().lower()
        name = str(m.get("name") or "").strip().lower()
        remote = str(m.get("remote_name") or "").strip().lower()

        if wanted in {mid, name, remote}:
            return m

        # Accept "provider:name"
        if ":" in wanted and wanted == mid:
            return m

    return None
# ---------- Endpoint ----------
@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest,  request: Request):
    resolved_entry = _match_model_entry(req.model)

    provider = (
        req.provider
        or request.headers.get("X-CLike-Provider")
        or (resolved_entry or {}).get("provider")
        or _infer_provider(req.model)
        or ""
    ).lower().strip()

    model = (
        req.remote_name
        or (resolved_entry or {}).get("remote_name")
        or (resolved_entry or {}).get("name")
        or req.model
    )
    # Converte ChatMessage (pydantic) -> dict
    messages = []
    for m in (req.messages or []):
        try:
            messages.append(m.dict() if hasattr(m, "dict") else dict(m))
        except Exception:
            # fallback super-sicuro
            messages.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", "")})

    temperature = 0.4 if req.temperature is None else req.temperature  # 0 is a valid value
    max_tokens = req.max_tokens
    response_format = req.response_format
    tools = req.tools
    tool_choice = req.tool_choice
    sanitized = _sanitize_mode_contract_payload(
        provider=provider,
        mode_contract=req.mode_contract,
        response_format=response_format,
        tools=tools,
        tool_choice=tool_choice,
    )
    response_format = sanitized["response_format"]
    tools = sanitized["tools"]
    tool_choice = sanitized["tool_choice"]
    remote = (req.remote_name or model)
    timeout = req.timeout or DEFAULT_CHAT_TIMEOUT_S  # never unlimited

    # Logging solo con tipi JSON-safe (evita oggetti pydantic)
    log.info(
        "chat payload (safe) %s",
        _json({
            "provider": provider,
            "req_model": req.model,
            "resolved_model": model,
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
            raise provider_not_configured("openai")
        data = await oai.chat(OPENAI_BASE, OPENAI_API_KEY, model, messages, temperature=temperature,
                                                                            max_tokens=max_tokens,
                                                                            tools=tools,
                                                                            tool_choice=tool_choice,
                                                                            response_format=response_format,
                                                                            timeout=timeout) 
        return raise_for_provider_failure(data, model)
    if provider == "ollama":
        data = await oai.chat(OLLAMA_OPENAI_BASE, "ollama", model, messages, temperature=temperature,
                              max_tokens=max_tokens, tools=tools, tool_choice=tool_choice,
                              response_format=response_format, timeout=timeout)
        return raise_for_provider_failure(data, model)
    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise provider_not_configured("anthropic")
            
        try:
            data = await anth.chat(
                ANTHROPIC_BASE, 
                ANTHROPIC_API_KEY, 
                model, 
                messages, 
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                timeout=timeout)
            return raise_for_provider_failure(data, model)
        except httpx.HTTPStatusError as e:
            txt = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 502
            raise HTTPException(code, detail=f"provider error for model={model}: {txt}")
        except httpx.HTTPError as e:
            raise HTTPException(502, detail=f"provider connection error: {e}")
    else:
        raise HTTPException(400, f"unsupported provider for chat: {provider} for model '{req.model}")

