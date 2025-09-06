from __future__ import annotations
import os, yaml
from typing import Dict, Any, List, Optional

LOCAL_PROVIDERS = {"ollama", "vllm"}

def _load_cfg() -> Dict[str, Any]:
    cfg_path = os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _enabled(m: Dict[str, Any]) -> bool:
    return bool(m.get("enabled", False))

def _is_local(m: Dict[str, Any]) -> bool:
    return (m.get("provider") or "").lower() in LOCAL_PROVIDERS

def _cap_score(m: Dict[str, Any]) -> int:
    cap = (m.get("capability") or "medium").lower()
    return {"high": 0, "medium": 1, "low": 2}.get(cap, 1)

def choose_model(task: str = "codegen", modality: Optional[str] = None, name_or_auto: str = "auto") -> Dict[str, Any]:
    cfg = _load_cfg()
    models: List[Dict[str, Any]] = cfg.get("models", [])
    candidates = [m for m in models if _enabled(m)]
    if modality:
        candidates = [m for m in candidates if m.get("modality") == modality]
    if not candidates:
        raise RuntimeError("no enabled models matching filters")

    if name_or_auto != "auto":
        for m in candidates:
            if m.get("name") == name_or_auto:
                return m
        raise RuntimeError(f"model '{name_or_auto}' not found or disabled")

    if task == "codegen":
        local = [m for m in candidates if _is_local(m)]
        if local:
            candidates = local

    candidates.sort(key=_cap_score)
    return candidates[0]
