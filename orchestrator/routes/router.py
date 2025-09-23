# orchestrator/routes/router.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
import logging

from services.router import resolve as resolve_basic, resolve_explain

log = logging.getLogger("router")

router = APIRouter(prefix="/v1/router", tags=["router"])

@router.get("/resolve")
async def router_resolve(
    task: str = Query(..., description="Task hint: spec|plan|kit|build|chat"),
    hint: Optional[str] = Query(None, description="Profile hint (e.g. plan.fast)")
) -> Dict[str, Any]:
    """
    Returns the routing decision with explainability:
    - chosen: the model used (id/provider/remote/base/tags)
    - profile: resolved profile for the task
    - policy: policy flags applied (redaction/local/frontier, etc.)
    - candidates: list of eligible models considered (ids and brief notes)
    - warnings: any routing warnings emitted
    """
    try:
        info = resolve_explain(task=task, hint=hint)
        return info
    except Exception as e:
        log.exception("router.resolve failed")
        raise HTTPException(500, f"router.resolve failed: {type(e).__name__}: {e}")
