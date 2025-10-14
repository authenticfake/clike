# Phase services (SPEC/PLAN/KIT) orchestrating prompts, evals and runs.
# Iterations: each call may update documents and re-run gates.
# Branching (future): for KIT change-requests, create feature branches per request.
# Phase services (SPEC/PLAN/KIT/BUILD) orchestrating routing and gateway calls.
from __future__ import annotations
from typing import Dict, Any, Optional, List
import os, logging, time
from datetime import datetime


import httpx  # ensure available in requirements
from services.router import select_model_for_phase, Task

GATEWAY_URL = os.environ.get("CL_GATEWAY_URL", "http://gateway:8000")
log = logging.getLogger("orcehstrator:service:harper")
TIMEOUT =float(os.environ.get("TIMEOUT", 500.0))

from services.router import select_model_for_phase  # ← esiste già nel repo

async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GATEWAY_URL}{path}"
    start_time = time.time()

    log.info("POST %s keys=%s idea_md=%s core=%d atts=%d time=%.4f",
             url,
             ",".join(sorted(payload.keys())),
             bool(payload.get("idea_md")),
             len(payload.get("core") or []),
             len(payload.get("attachments") or []), start_time)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=payload)
        end_time = time.time()
        elapsed_time = end_time - start_time
        log.info(f"POST (elapsed): {elapsed_time:.4f} secondi.")


        r.raise_for_status()
        return r.json()
    
async def _normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    # --- Normalizzazione messages ---
    raw_msgs = msg.get("messages") or []
    norm_msgs = []
    for m in raw_msgs:
        if m is None:
            continue
        # Supporta: Pydantic model, oggetto con .dict(), o già dict
        if hasattr(m, "model_dump"):
            d = m.model_dump()
        elif hasattr(m, "dict"):
            d = m.dict()
        elif isinstance(m, dict):
            d = m
        else:
            # ignora elementi non conformi
            continue

        role = d.get("role")
        content = d.get("content")
        if isinstance(role, str) and isinstance(content, str):
            norm_msgs.append({"role": role, "content": content})

    if norm_msgs:
        msg["messages"] = norm_msgs
    else:
        # se vuoto rimuovi per lasciare al gateway la composizione di default
        msg.pop("messages", None)
    return dict(msg)

async def run_phase(phase: str, req_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Harper run: merge pass-through dei campi + routing modello basato su models.yaml.
    Precedenze:
      - se 'model' esplicito e != 'auto' → lo rispetta
      - altrimenti, usa select_model_for_phase(phase, profileHint)
    """
    # --- Normalizzazione in dict ---
    if hasattr(req_payload, "model_dump"):
        payload = req_payload.model_dump()   # pydantic -> dict
    elif isinstance(req_payload, dict):
        payload = dict(req_payload)          # copia difensiva
    else:
        # fallback estremo
        try:
            payload = dict(req_payload)      # tipo mapping-like
        except Exception:
            raise ValueError("Invalid request payload type for HarperService.run_phase")

    merged: Dict[str, Any] = dict(payload or {})
    merged["phase"] = phase
    merged.setdefault("cmd", phase)
    merged.setdefault("flags", {})
    merged = await _normalize_message(merged);
    if merged.get("phase") == "kit":
        kit = merged.get("kit") or {}
        targets = kit.get("targets") or []
        if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], str) or not targets[0].strip():
            raise ValueError("Harper /kit requires exactly one target REQ-ID in kit.targets, e.g. { kit: { targets: ['REQ-001'] } }")

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
