from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple

from config import settings
from services.llm_contracts import load_catalog_local, resolve_llm_selection

log = logging.getLogger("router")

_TASK_TO_MODE = {
    "chat": ("free", None),
    "free": ("free", None),
    "spec": ("harper", "spec"),
    "plan": ("harper", "plan"),
    "kit": ("harper", "kit"),
    "build": ("coding", "kit"),
    "coding": ("coding", "kit"),
    "eval": ("harper", "eval"),
    "gate": ("harper", "gate"),
    "finalize": ("harper", "finalize"),
}


def _base_url() -> str:
    return str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")


def _task_to_mode_phase(task: str) -> tuple[str, Optional[str]]:
    t = (task or "chat").strip().lower()
    return _TASK_TO_MODE.get(t, ("free", None))


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("legacy sync router shim cannot run inside an active event loop")


def _load_cfg() -> Dict[str, Any]:
    """
    Legacy-compatible config loader.
    Source of truth is the local catalog structure used by llm_contracts.
    """
    return load_catalog_local()


def resolve(
    task: str,
    hint: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> Tuple[Dict[str, Any], list[str]]:
    """
    Legacy-compatible resolve(...) API.
    Delegates to the new shared resolver.
    """
    mode, phase = _task_to_mode_phase(task)
    sel = _run_async(
        resolve_llm_selection(
            base_url=_base_url(),
            mode=mode,
            phase=phase,
            requested_model=model or "auto",
            requested_provider=provider,
            profile_hint=hint,
        )
    )
    chosen = dict(sel.get("catalog_entry") or {})
    if sel.get("model"):
        chosen.setdefault("id", sel["model"])
        chosen.setdefault("name", chosen.get("name") or sel["model"])
    if sel.get("provider"):
        chosen["provider"] = sel["provider"]
    if sel.get("remote_name"):
        chosen["remote_name"] = sel["remote_name"]
    if sel.get("profile"):
        chosen["profile"] = sel["profile"]

    warnings: list[str] = []
    return chosen, warnings


def resolve_explain(
    task: str,
    hint: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    mode, phase = _task_to_mode_phase(task)
    sel = _run_async(
        resolve_llm_selection(
            base_url=_base_url(),
            mode=mode,
            phase=phase,
            requested_model=model or "auto",
            requested_provider=provider,
            profile_hint=hint,
        )
    )
    return {
        "task": task,
        "hint": hint,
        "requested": {
            "model": model or "auto",
            "provider": provider,
        },
        "resolved": {
            "model": sel.get("model"),
            "provider": sel.get("provider"),
            "remote_name": sel.get("remote_name"),
            "profile": sel.get("profile"),
            "mode_contract": sel.get("mode_contract"),
        },
        "catalog_entry": sel.get("catalog_entry") or {},
    }


def select_model_for_phase(
    task: str,
    profile_hint: Optional[str],
    model_override: Optional[str],
) -> Tuple[str, str]:
    """
    Legacy-compatible API kept only for backward compatibility.
    """
    mode, phase = _task_to_mode_phase(task)
    sel = _run_async(
        resolve_llm_selection(
            base_url=_base_url(),
            mode=mode,
            phase=phase,
            requested_model=model_override or "auto",
            requested_provider=None,
            profile_hint=profile_hint,
        )
    )
    return (sel.get("model") or model_override or "auto"), (sel.get("profile") or "default")