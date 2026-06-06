from __future__ import annotations

import json
from typing import Any, Dict, Optional

from services.methodologies.resolver import ensure_bmad_skill_context


def _as_list(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else []
    return [str(item) for item in raw if str(item or "").strip()]


def _load_selected_capability_json(core_blobs: Dict[str, Any] | None) -> Dict[str, Any]:
    for key, value in (core_blobs or {}).items():
        if str(key or "").lower().endswith("clike_selected_capability_context.json"):
            try:
                data = json.loads(str(value or ""))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _load_selected_capability_markdown(core_blobs: Dict[str, Any] | None) -> str:
    for key, value in (core_blobs or {}).items():
        if str(key or "").lower().endswith("clike_selected_capability_context.md"):
            return str(value or "")
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
    selected_json = _load_selected_capability_json(core_blobs)
    selected_markdown = _load_selected_capability_markdown(core_blobs)
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
