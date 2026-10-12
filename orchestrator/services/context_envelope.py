from __future__ import annotations

import json
from typing import Any, Dict, Optional

from services.methodologies.resolver import ensure_bmad_skill_context


def _as_list(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else []
    return [str(item) for item in raw if str(item or "").strip()]


def _selected_capability_candidates(core_blobs: Dict[str, Any] | None, suffix: str, req_id: Optional[str] = None):
    """Blobs ending with the selected-capability file name, best first: the one the orchestrator
    built for this run (bare name), then the target REQ's KIT copy, then any other. Copies of the
    file left in KITs by earlier runs come from the workspace and may be stale or truncated."""
    items = [(str(k or ""), v) for k, v in (core_blobs or {}).items() if str(k or "").lower().endswith(suffix)]
    req = str(req_id or "").lower()

    def rank(item):
        key = item[0].lower()
        if key == suffix:
            return 0
        if req and f"/{req}/" in key:
            return 1
        return 2

    return [v for _k, v in sorted(items, key=rank)]


def _load_selected_capability_json(core_blobs: Dict[str, Any] | None, req_id: Optional[str] = None) -> Dict[str, Any]:
    for value in _selected_capability_candidates(core_blobs, "clike_selected_capability_context.json", req_id):
        try:
            data = json.loads(str(value or ""))
        except Exception:
            continue  # truncated or invalid copy: try the next one
        if isinstance(data, dict):
            return data
    return {}


def _load_selected_capability_markdown(core_blobs: Dict[str, Any] | None, req_id: Optional[str] = None) -> str:
    for value in _selected_capability_candidates(core_blobs, "clike_selected_capability_context.md", req_id):
        if str(value or "").strip():
            return str(value)
    return ""


def _selected_names(group: Dict[str, Any]) -> list[str]:
    if not isinstance(group, dict):
        return []
    selected = _as_list(group.get("selected"))
    if selected:
        return selected
    resolved = group.get("resolved") if isinstance(group.get("resolved"), list) else []
    return [
        str(item.get("name"))
        for item in resolved
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def _selected_capability_names(selected_json: Dict[str, Any], key: str, legacy_key: str) -> list[str]:
    names = _selected_names(selected_json.get(key) or {})
    if names:
        return names
    return _as_list(selected_json.get(legacy_key))


def build_context_envelope(
    *,
    phase: str,
    req_id: Optional[str],
    execution_mode: str,
    core_blobs: Dict[str, Any] | None,
    methodology_context: Optional[Dict[str, Any]],
    active_output_contract: Optional[Dict[str, Any]],
    namespace_materialization: Optional[Dict[str, Any]] = None,
    require_bmad_core_blobs: bool = False,
) -> Dict[str, Any]:
    """Build a compact, Orchestrator-owned context envelope for cloud/local-agent paths."""
    selected_json = _load_selected_capability_json(core_blobs, req_id)
    selected_markdown = _load_selected_capability_markdown(core_blobs, req_id)
    methodology_context = methodology_context if isinstance(methodology_context, dict) else None
    methodology_context = ensure_bmad_skill_context(
        methodology_context,
        phase=phase,
        agent=(methodology_context or {}).get("agent"),
        core_blobs=core_blobs,
        require_bmad_core_blobs=require_bmad_core_blobs,
    )

    return {
        "schema_version": "clike.execution_context_envelope.v1",
        "phase": str(phase or ""),
        "req_id": req_id,
        "execution_mode": execution_mode,
        "methodology": (methodology_context or {}).get("methodology"),
        "agent": (methodology_context or {}).get("agent"),
        "clike_capabilities": {
            "selected_packs": _selected_capability_names(selected_json, "packs", "selected_packs"),
            "selected_skills": _selected_capability_names(selected_json, "skills", "selected_skills"),
            "selected_design_profiles": _selected_capability_names(
                selected_json,
                "design_profiles",
                "selected_design_profiles",
            ),
            "context_json": selected_json,
            "context_markdown": selected_markdown,
            "source": "CLIKE_SELECTED_CAPABILITY_CONTEXT" if selected_json or selected_markdown else None,
        },
        "bmad_methodology_skills": {
            "selected_skill_references": list((methodology_context or {}).get("selected_skill_references") or []),
            "selected_skill_context": dict((methodology_context or {}).get("selected_skill_context") or {}),
            "skill_reference_policy": dict((methodology_context or {}).get("skill_reference_policy") or {}),
        },
        "active_output_contract": active_output_contract or {},
        "namespace_materialization": namespace_materialization or {},
    }
