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

from services.router import select_model_for_phase  # ← esiste già nel repo

async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GATEWAY_URL}{path}"
    log.info("POST %s keys=%s idea_md=%s core=%d atts=%d",
             url,
             ",".join(sorted(payload.keys())),
             bool(payload.get("idea_md")),
             len(payload.get("core") or []),
             len(payload.get("attachments") or []))
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

async def run_phase(phase: str, req_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Harper run: merge pass-through dei campi + routing modello basato su models.yaml.
    Precedenze:
      - se 'model' esplicito e != 'auto' → lo rispetta
      - altrimenti, usa select_model_for_phase(phase, profileHint)
    """
    merged: Dict[str, Any] = dict(req_payload or {})
    merged["phase"] = phase
    merged.setdefault("cmd", phase)
    merged.setdefault("flags", {})

    # --- routing modello (unica fonte di verità) ---
    model_override = merged.get("model")
    profile_hint = merged.get("profileHint")

    try:
        model_id, profile_used = select_model_for_phase(task=phase, profile_hint=profile_hint, model_override=model_override)
        if model_id:
            merged["model"] = model_id
        # opzionale ma utile per telemetry
        merged["profileHint"] = profile_used if profile_used else profile_hint
        log.info("harper.routing resolved model=%s profile=%s (override=%s)",
                 merged.get("model"), merged.get("profileHint"), model_override)
    except Exception as e:
        log.warning("harper.routing failed (%s) → proceeding with provided 'model'=%s", e, model_override)

    # runId di default se manca
    merged.setdefault("runId", f"{phase}")

    out = await _post_json("/v1/harper/run", merged)
    log.info("GATEWAY RES keys=%s files=%d text=%s",
             ",".join(sorted(out.keys())),
             len(out.get("files") or []),
             "yes" if out.get("text") else "no")
    return out
