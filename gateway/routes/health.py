import os
from fastapi import APIRouter
from config import load_models_cfg

router = APIRouter()

@router.get("/health")
async def health():
    return {"clike gateway status": "ok"}

