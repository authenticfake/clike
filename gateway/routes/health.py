import os
from fastapi import APIRouter
from config import load_models_cfg

router = APIRouter()

@router.get("/health")
async def health():
    return {"clike gateway status": "ok"}

@router.get("/v1/models")
async def list_models():
    _, models = load_models_cfg(os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml"))
    return {"data": [{"id": m.get("name"), "object": "model"} for m in models if m.get("enabled", True)]}
