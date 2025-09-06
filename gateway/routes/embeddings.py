import os, logging
from fastapi import APIRouter, Request, HTTPException
from config import load_models_cfg
from model_resolver import resolve_model
from providers import ollama as oll
from providers import openai_compat as oai
from providers import deepseek as dsk
from utils.openai_like import format_embeddings_response

router = APIRouter()
logger = logging.getLogger("gateway.embeddings")

@router.post("/v1/embeddings")
async def embeddings(req: Request):
    body = await req.json()
    model_name = body.get("model", "auto")
    input_text = body.get("input", "")

    _, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
    try:
        m = resolve_model(models, model_name, want_modality="embeddings")
    except Exception as e:
        raise HTTPException(400, f"model resolution failed: {e}")

    provider = (m.get("provider") or "").lower()
    base = (m.get("base_url") or "").rstrip("/")
    remote = m.get("remote_name") or m.get("name")
    api_key_env = m.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    logger.info(f"[emb] provider={provider} model={m.get('name')} remote={remote} base={base}")

    try:
        if provider == "ollama":
            vec = await oll.embeddings(base, remote, input_text)
        elif provider in ("openai", "vllm"):
            vec = await oai.embeddings(base, api_key, remote, input_text)
        elif provider == "deepseek":
            vec = await dsk.embeddings(base, api_key, remote, input_text)
        elif provider == "anthropic":
            raise HTTPException(400, "anthropic provider does not support embeddings")
        else:
            raise HTTPException(400, f"unsupported provider for embeddings: {provider}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"emb provider error: {e}")
        raise HTTPException(502, f"upstream embeddings provider failed: {type(e).__name__}: {e}")

    return format_embeddings_response(m.get("name"), vec)
