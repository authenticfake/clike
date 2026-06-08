from __future__ import annotations

from typing import Any, Dict, List, Optional


NATIVE_LOCAL_REQUIRED_OUTPUTS: Dict[str, List[str]] = {
    "idea": ["docs/harper/IDEA.md"],
    "spec": ["docs/harper/SPEC.md"],
    "plan": ["docs/harper/PLAN.md", "docs/harper/plan.json", "docs/harper/lane-guides/**"],
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
    "idea": ["attachments", "Harper chat history", "repository/RAG context"],
    "spec": ["IDEA.md", "Harper chat history", "RAG attachments", "TECH_CONSTRAINTS.yaml"],
    "plan": ["SPEC.md", "TECH_CONSTRAINTS.yaml", "prior PLAN.md", "prior plan.json", "Harper chat history"],
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

    context_sections = list(NATIVE_CONTEXT_SECTIONS.get(phase_name) or [])
    if runner_name == "local_agent":
        # Local-agent document phases are regenerative: same-phase prior outputs
        # are overwrite targets only, never source input. Drop them from the
        # advertised context so the agent does not reconcile stale outputs.
        # (Cloud keeps reconcile behavior — its runner is not "local_agent".)
        same_phase_prior = {
            "prior PLAN.md",
            "prior plan.json",
            "prior SPEC.md",
        }
        context_sections = [s for s in context_sections if s not in same_phase_prior]

    return {
        "phase": phase_name,
        "runner": runner_name,
        "methodology": methodology,
        "agent": context.get("agent"),
        "required_outputs": _dedupe([*(native if methodology == "bmad" else []), *canonical, *mandatory]),
        "allowed_optional_output_globs": optional,
        "forbidden_output_globs": forbidden,
        "required_context_sections": context_sections,
        "strict_missing_required_outputs": False,
        "conflict_resolution": conflict_resolution,
    }
