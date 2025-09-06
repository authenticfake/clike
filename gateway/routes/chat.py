import os, logging
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

@router.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    model_name = body.get("model", "auto")
    messages = body.get("messages", [])
    temperature = body.get("temperature", 0.2)
    max_tokens = body.get("max_tokens", 512)

    _, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
    try:
        m = resolve_model(models, model_name, want_modality="chat")
    except Exception as e:
        raise HTTPException(400, f"model resolution failed: {e}")

    provider = (m.get("provider") or "").lower()
    base = (m.get("base_url") or "").rstrip("/")
    remote = m.get("remote_name") or m.get("name")
    api_key_env = m.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    logger.info(f"[chat] provider={provider} model={m.get('name')} remote={remote} base={base}")

    try:
        if provider == "ollama":
            content = await oll.chat(base, remote, messages, temperature, max_tokens)
        elif provider in ("openai", "vllm"):
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
        raise
    except Exception as e:
        logger.exception(f"chat provider error: {e}")
        raise HTTPException(502, f"upstream chat provider failed: {type(e).__name__}: {e}")

    return format_chat_response(m.get("name"), content or "")
