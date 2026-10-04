"""Unified provider result: the shape every provider call returns to the Harper and chat routes."""

from typing import Any, Dict, List, Optional

UNIFIED_RESULT_KEYS = ("ok", "text", "files", "usage", "finish_reason", "raw", "errors")


def _mk_unified_result(
    ok: bool,
    text: str,
    files: Optional[List[Dict[str, Any]]] = None,
    usage: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "text": text or "",
        "files": files or [],
        "usage": usage or {},
        "finish_reason": finish_reason or "",
        "raw": raw or {},
        "errors": errors or [],
    }
