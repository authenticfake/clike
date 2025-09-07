# -*- coding: utf-8 -*-
import os, json, datetime, uuid
from typing import Tuple, Any, Dict
from orchestrator.config import settings

def new_audit() -> Tuple[str, str]:
    audit_id = f"aud_{uuid.uuid4().hex[:12]}"
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = os.path.join(settings.RUNS_DIR, f"{ts}_{audit_id}")
    os.makedirs(run_dir, exist_ok=True)
    return audit_id, run_dir

def save_payload(run_dir: str, name: str, payload: Dict[str, Any]) -> None:
    path = os.path.join(run_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)