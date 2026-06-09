import os
import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from config import load_models_cfg
from providers_availability import model_availability, provider_availability
from utils.model_catalog_validator import validate_catalog

router = APIRouter()
log = logging.getLogger("gateway.models")


def _build_aliases(models: List[Dict[str, Any]]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}

    for m in models or []:
        mid = str(m.get("id") or "").strip()
        name = str(m.get("name") or "").strip()
        remote = str(m.get("remote_name") or "").strip()

        if mid:
            aliases[mid] = mid
        if name and mid:
            aliases[name] = mid
        if remote and mid:
            aliases[remote] = mid

    return aliases


def _load_catalog() -> tuple[dict, list[dict], dict]:
    cfg_path = os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
    data, models = load_models_cfg(cfg_path)
    validation = validate_catalog(data, models)
    return data, models, validation


@router.get("/v1/providers")
async def list_providers():
    return await provider_availability()


@router.get("/v1/models")
async def list_models():
    data, models, validation = _load_catalog()

    availability = await provider_availability()

    annotated = []
    for m in models:
        ok, reason = model_availability(str(m.get("provider") or ""), availability)
        entry = dict(m)
        entry["available"] = ok
        entry["unavailable_reason"] = reason
        annotated.append(entry)

    return {
        "version": "2.3",
        "models": annotated,
        "providers": availability,
        "profiles": data.get("profiles") or {},
        "routing": data.get("routing") or {},
        "scoring": data.get("scoring") or {},
        "aliases": _build_aliases(models),
        "validation": validation,
    }


@router.get("/v1/models/validate")
async def validate_models():
    data, models, validation = _load_catalog()
    return {
        "version": "2.3",
        "validation": validation,
        "profiles": list((data.get("profiles") or {}).keys()),
        "routing": data.get("routing") or {},
        "model_ids": [m.get("id") for m in models if m.get("id")],
    }