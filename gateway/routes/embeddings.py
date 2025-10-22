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
    model_name = (body.get("model") or "").strip()
    input_raw = body.get("input", "")

    # 1) Normalizza input: accetta stringa o lista -> stringa unica
    if isinstance(input_raw, list):
        # tipicamente per query RAG è una stringa; se arriva lista, unisci
        input_text = "\n\n".join([str(x) for x in input_raw if isinstance(x, (str, bytes))]).strip()
    else:
        input_text = str(input_raw or "").strip()

    if not input_text:
        raise HTTPException(400, "missing 'input' for embeddings")

    # 2) Default modello se non specificato
    if not model_name or model_name.lower() == "auto":
        # prova ENV esplicite, poi un alias utile di default
        model_name = (
            os.getenv("RAG_EMBED_MODEL") or
            os.getenv("OLLAMA_EMBED_MODEL") or
            "ollama:nomic-embed-text"
        )

    # 3) Resolve dal models.yaml (modality embeddings)
    _, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
    try:
        m = resolve_model(models, model_name, want_modality="embeddings")
    except Exception as e:
        raise HTTPException(400, f"model resolution failed for '{model_name}': {e}")

    provider = (m.get("provider") or "").lower()
    base = (m.get("base_url") or "").rstrip("/") or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
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

