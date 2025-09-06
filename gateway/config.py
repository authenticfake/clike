import os
import yaml
from typing import Any, Dict, List, Tuple

def load_models_cfg(path: str | None = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    cfg_path = path or os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    models = data.get("models") or []
    return data, models
