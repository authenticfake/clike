# routes/models.py
import os, logging
from fastapi import APIRouter
from config import load_models_cfg

router = APIRouter()
log = logging.getLogger("gateway.models")

@router.get("/v1/models")
async def list_models():
    cfg_path = os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
    data, models = load_models_cfg(cfg_path)
    return {"version": "1.0", "models": models}
