import os
import logging

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
    model_name = (body.get("model") or "").strip()
    input_raw = body.get("input", "")

    # 1) Normalize input
    if isinstance(input_raw, list):
        input_text = "\n\n".join([str(x) for x in input_raw if isinstance(x, (str, bytes))]).strip()
    else:
        input_text = str(input_raw or "").strip()

    if not input_text:
        raise HTTPException(400, "missing 'input' for embeddings")
    # Guardrail: avoid sending oversized local embedding payloads.
    # For large payloads, upstream callers should chunk before embedding.
    if len(input_text) > 12000:
        raise HTTPException(400, "embedding input too large; caller must chunk before embedding")
    
    # 2) Default model if not provided
        # 2) Load catalog first
    cfg, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))

    # 3) Default model if not provided:
    # prefer explicit env override, otherwise use catalog defaults.embedding_model
    if not model_name or model_name.lower() == "auto":
        model_name = (
            os.getenv("RAG_EMBED_MODEL")
            or (cfg.get("defaults") or {}).get("embedding_model")
            or "openai:text-embedding-3-small"
        )
    try:
        logger.debug("[emb] requested_model=%s", model_name)
        m = resolve_model(
            cfg,
            models,
            model_name,
            want_modality="embeddings",
        )
    except Exception as e:
        raise HTTPException(400, f"model resolution failed for '{model_name}': {e}")

    provider = str(m.get("provider") or "").lower()
    base = str(m.get("base_url") or "").rstrip("/") or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    remote = m.get("remote_name") or m.get("name")
    api_key_env = m.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    if provider in ("openai", "deepseek", "vllm") and api_key_env and not api_key:
        raise HTTPException(
            400,
            f"missing required embeddings API key env: {api_key_env}",
        )

    logger.debug(
        "[emb] provider=%s model=%s remote=%s base=%s input_len=%d",
        provider,
        m.get("name"),
        remote,
        base,
        len(input_text),
    )

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
        logger.exception(
            "emb provider error model=%s provider=%s remote=%s base=%s err=%s",
            model_name,
            provider,
            remote,
            base,
            e,
        )
        raise HTTPException(502, f"upstream embeddings provider failed: {type(e).__name__}: {e}")

    if not isinstance(vec, list) or not vec:
        raise HTTPException(502, f"embeddings provider returned an empty vector for model '{model_name}'")

    return format_embeddings_response(m.get("name"), vec)