from __future__ import annotations

from typing import Any, Dict, List, Optional


NATIVE_LOCAL_REQUIRED_OUTPUTS: Dict[str, List[str]] = {
    "kit": [
        "runs/kit/<REQ-ID>/src/**",
        "runs/kit/<REQ-ID>/test/**",
        "runs/kit/<REQ-ID>/ci/**",
        "runs/kit/<REQ-ID>/docs/TARGET_CONTRACT.json",
        "runs/kit/<REQ-ID>/docs/FILE_REQUIREMENTS.json",
    ],
    "eval": ["runs/kit/<REQ-ID>/reports/BMAD_EVAL_REPAIR_NOTES.md"],
}

NATIVE_CONTEXT_SECTIONS: Dict[str, List[str]] = {
    "kit": ["current REQ", "SPEC.md", "PLAN.md", "plan.json", "TECH_CONSTRAINTS.yaml", "TARGET_CONTRACT.json", "FILE_REQUIREMENTS.json"],
    "eval": ["canonical eval evidence", "LTC.json", "HOWTO.md", "candidate files", "TECH_CONSTRAINTS.yaml"],
}


def _replace_req_id(items: List[Any], req_id: Optional[str]) -> List[str]:
    req = str(req_id or "<REQ-ID>")
    return [str(item).replace("<REQ-ID>", req) for item in items if str(item or "").strip()]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def build_active_output_contract(
    *,
    phase: str,
    runner: str,
    methodology_context: Optional[Dict[str, Any]] = None,
    req_id: Optional[str] = None,
) -> Dict[str, Any]:
    phase_name = str(phase or "").strip().lower()
    runner_name = str(runner or "local_agent").strip().lower()
    context = methodology_context if isinstance(methodology_context, dict) else {}
    policy = context.get("artifact_policy") if isinstance(context.get("artifact_policy"), dict) else {}
    methodology = "bmad" if context.get("methodology") == "bmad" and policy else "native_clike"

    if methodology == "bmad":
        native = [] if policy.get("companion_only") else _replace_req_id(
            list(NATIVE_LOCAL_REQUIRED_OUTPUTS.get(phase_name) or []),
            req_id,
        )
        canonical = _replace_req_id(list(policy.get("canonical_outputs") or []), req_id)
        mandatory = _replace_req_id(list(policy.get("mandatory_companion_outputs") or []), req_id)
        optional = _replace_req_id(list(policy.get("allowed_companion_root_globs") or []), req_id)
        forbidden = _replace_req_id(list(policy.get("forbidden_outputs") or []), req_id)
        conflict_resolution = str(policy.get("conflict_resolution") or "canonical-wins")
    else:
        canonical = _replace_req_id(list(NATIVE_LOCAL_REQUIRED_OUTPUTS.get(phase_name) or []), req_id)
        mandatory = []
        optional = []
        forbidden = []
        conflict_resolution = "native-clike-contract-wins"

    return {
        "phase": phase_name,
        "runner": runner_name,
        "methodology": methodology,
        "agent": context.get("agent"),
        "required_outputs": _dedupe([*(native if methodology == "bmad" else []), *canonical, *mandatory]),
        "allowed_optional_output_globs": optional,
        "forbidden_output_globs": forbidden,
        "required_context_sections": list(NATIVE_CONTEXT_SECTIONS.get(phase_name) or []),
        "strict_missing_required_outputs": False,
        "conflict_resolution": conflict_resolution,
    }
