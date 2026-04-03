from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
import logging

from config import settings
from services.llm_contracts import load_catalog, resolve_llm_selection

log = logging.getLogger("router")
router = APIRouter(prefix="/v1/router", tags=["router"])


@router.get("/resolve")
async def router_resolve(
    task: str = Query(..., description="Task hint: free|coding|harper|spec|plan|kit|build|chat"),
    hint: Optional[str] = Query(None, description="Profile hint (e.g. plan.fast)"),
    model: Optional[str] = Query("auto", description="Explicit model id/name/remote_name, or auto"),
    provider: Optional[str] = Query(None, description="Optional explicit provider override"),
) -> Dict[str, Any]:
    """
    Returns the routing decision according to the new shared resolver.
    """
    try:
        mode = "free"
        phase = None

        task_norm = (task or "").strip().lower()
        if task_norm in {"free", "chat"}:
            mode = "free"
        elif task_norm in {"coding", "codegen", "build"}:
            mode = "coding"
            phase = "kit"
        elif task_norm in {"harper", "spec", "plan", "kit","promotion_normalizer", "eval", "gate", "finalize"}:
            mode = "harper"
            phase = task_norm if task_norm != "harper" else None

        base_url = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")

        catalog = await load_catalog(base_url)
        selection = await resolve_llm_selection(
            base_url=base_url,
            mode=mode,
            phase=phase,
            requested_model=model or "auto",
            requested_provider=provider,
            profile_hint=hint,
        )

        entry = selection.get("catalog_entry") or {}

        return {
            "task": task_norm,
            "mode": mode,
            "phase": phase,
            "requested": {
                "model": model or "auto",
                "provider": provider,
                "hint": hint,
            },
            "resolved": {
                "model": selection.get("model"),
                "provider": selection.get("provider"),
                "remote_name": selection.get("remote_name"),
                "profile": selection.get("profile"),
                "mode_contract": selection.get("mode_contract"),
            },
            "catalog_entry": entry,
            "catalog_version": catalog.get("version"),
        }
    except Exception as e:
        log.exception("router.resolve failed")
        raise HTTPException(500, f"router.resolve failed: {type(e).__name__}: {e}")