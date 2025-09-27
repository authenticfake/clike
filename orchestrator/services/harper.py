# Phase services (SPEC/PLAN/KIT) orchestrating prompts, evals and runs.
# Iterations: each call may update documents and re-run gates.
# Branching (future): for KIT change-requests, create feature branches per request.
# Phase services (SPEC/PLAN/KIT/BUILD) orchestrating routing and gateway calls.
from __future__ import annotations
from typing import Dict, Any, Optional, List
import os, logging
from datetime import datetime

import httpx  # ensure available in requirements
from services.router import select_model_for_phase, Task

GATEWAY_URL = os.environ.get("CL_GATEWAY_URL", "http://gateway:8000")
log = logging.getLogger("orcehstrator:service:harper")
def _new_run_id(phase: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{phase}"

async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GATEWAY_URL.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

async def run_phase(phase: Task, req) -> Dict[str, Any]:
    """Resolve model/profile and run phase via gateway."""
    # 1) Resolve model with hint (only when model=='auto')
    model_id, profile_used = select_model_for_phase(
        task=phase,
        profile_hint=getattr(req, "profile_hint", None),
        model_override=getattr(req, "model", None),
    )
    is_manual = (str(getattr(req, "model", "auto")).lower() != "auto")
    route_msg = f"router={'manual' if is_manual else (getattr(req,'profile_hint',None) or 'auto')} → {model_id}"

    # 2) Build payload for gateway (propagate profile)
    payload = {
        "phase": phase,
        "mode": getattr(req, "mode", None),
        "model": model_id,
        "profile": getattr(req, "profile_hint", None),
        "docRoot": getattr(req, "doc_root", "docs/harper"),
        "core": getattr(req, "core", []) or [],
        "attachments": getattr(req, "attachments", []) or [],
        "flags": getattr(req, "flags", {}) or {},
        "runId": getattr(req, "run_id", None) or _new_run_id(phase),
    }

    # 3) Inline docs (for early MVP; gateway may ignore/consume)
    #    Keep field names as you already defined in request models
    if phase == "spec":
        payload["idea_md"] = getattr(req, "idea_md", None)
    elif phase == "plan":
        payload["spec_md"] = getattr(req, "spec_md")
    elif phase == "kit":
        payload["spec_md"] = getattr(req, "spec_md")
        payload["plan_md"] = getattr(req, "plan_md")
        payload["todo_ids"] = getattr(req, "todo_ids", None)
    elif phase == "build":
        payload["spec_md"] = getattr(req, "spec_md")
        payload["plan_md"] = getattr(req, "plan_md")
    
    
    log.info("run_phase %s: %s", phase, payload)
    # 4) Call gateway
    out = await _post_json("/v1/harper/run", payload)

    # 5) Enrich echo for transparency
    if isinstance(out, dict):
        prev = out.get("echo", "")
        out["echo"] = (prev + " | " if prev else "") + route_msg
    return out
