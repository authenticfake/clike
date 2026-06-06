from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
BMAD_MANIFEST_PATH = REPO_ROOT / "orchestrator" / "methodologies" / "bmad" / "manifest.json"

SPEC_QUALITY_TOPICS: Dict[str, Sequence[str]] = {
    "completeness": ("complete", "overview", "requirement", "scope"),
    "testability": ("test", "verification", "measurable", "deterministic check"),
    "acceptance_criteria_precision": ("acceptance", "criteria", "given", "when", "then"),
    "functional_requirement_clarity": ("functional", "behavior", "must", "shall"),
    "ux_user_journey_quality": ("ux", "user journey", "journey", "accessibility", "experience"),
    "non_functional_requirements": ("non-functional", "performance", "reliability", "availability", "scalability"),
    "security_privacy_compliance": ("security", "privacy", "compliance", "auth", "authorization"),
    "observability_operations": ("observability", "operation", "logging", "metrics", "alert"),
    "scope_and_non_goals": ("non-goal", "out of scope", "scope", "defer"),
    "traceability": ("idea", "trace", "companion", "source"),
}

PLAN_JSON_REQ_FIELDS = [
    "id",
    "title",
    "status",
    "dependsOn",
    "lane",
    "domain",
    "runtime_profile",
    "functional_scope",
    "technical_scope",
    "non_functional_requirements",
    "security_requirements",
    "operational_requirements",
    "integration_contracts",
    "data_contracts",
    "acceptance",
    "test_strategy",
    "risk_notes",
    "main_module_boundary",
    "gate_expectations",
    "kit_readiness",
]

LANE_GUIDE_REQUIRED_TOPICS: Dict[str, Sequence[str]] = {
    "lane_purpose": ("lane purpose", "purpose"),
    "runtime_constraints": ("runtime constraints", "runtime"),
    "expected_files": ("expected files", "files"),
    "test_commands": ("test commands", "test command"),
    "lint_type_build_security_commands": (
        "lint command",
        "type command",
        "build command",
        "security command",
        "lint/type/build/security commands",
    ),
    "contract_boundaries": ("contract boundaries", "boundary"),
    "integration_points": ("integration points", "integration"),
    "forbidden_shortcuts": ("forbidden shortcuts", "shortcut"),
    "eval_gate_expectations": ("eval/gate expectations", "gate expectations", "eval expectations"),
}


def load_bmad_quality_contracts() -> Dict[str, Any]:
    with BMAD_MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    contracts = manifest.get("quality_contracts") or {}
    return contracts if isinstance(contracts, dict) else {}


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def evaluate_spec_quality(spec_text: str) -> Dict[str, Any]:
    text = str(spec_text or "")
    missing_topics = [
        topic
        for topic, keywords in SPEC_QUALITY_TOPICS.items()
        if not _contains_any(text, keywords)
    ]
    covered_topics = [topic for topic in SPEC_QUALITY_TOPICS if topic not in missing_topics]
    total = len(SPEC_QUALITY_TOPICS)
    score = len(covered_topics) / total if total else 1.0

    return {
        "artifact": "SPEC.md",
        "passed": not missing_topics,
        "score": round(score, 3),
        "covered_topics": covered_topics,
        "missing_topics": missing_topics,
        "warnings": [f"SPEC is missing BMAD quality topic: {topic}" for topic in missing_topics],
    }


def _parse_plan_json(plan_json: Any) -> Dict[str, Any]:
    if isinstance(plan_json, str):
        return json.loads(plan_json)
    if isinstance(plan_json, Mapping):
        return dict(plan_json)
    raise TypeError("plan_json must be a JSON string or mapping")


def _plan_reqs(plan_data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_reqs = plan_data.get("reqs") or plan_data.get("requirements") or []
    if not isinstance(raw_reqs, list):
        return []
    return [dict(item) for item in raw_reqs if isinstance(item, Mapping)]


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _has_required_field_value(req: Mapping[str, Any], field: str) -> bool:
    if field == "dependsOn":
        return field in req and isinstance(req.get(field), list)
    return _has_value(req.get(field))


def evaluate_plan_json_structure(plan_json: Any) -> Dict[str, Any]:
    plan_data = _parse_plan_json(plan_json)
    reqs = _plan_reqs(plan_data)
    if not reqs:
        return {
            "artifact": "plan.json",
            "passed": False,
            "score": 0.0,
            "req_count": 0,
            "missing_by_req": {"<none>": PLAN_JSON_REQ_FIELDS},
            "warnings": ["plan.json contains no machine-readable REQs."],
        }

    missing_by_req: Dict[str, List[str]] = {}
    present_count = 0
    total_count = len(reqs) * len(PLAN_JSON_REQ_FIELDS)

    for index, req in enumerate(reqs):
        req_id = str(req.get("id") or f"<req-{index + 1}>")
        missing = [field for field in PLAN_JSON_REQ_FIELDS if not _has_required_field_value(req, field)]
        if missing:
            missing_by_req[req_id] = missing
        present_count += len(PLAN_JSON_REQ_FIELDS) - len(missing)

    score = present_count / total_count if total_count else 0.0
    warnings = [
        f"REQ {req_id} is missing plan.json quality fields: {', '.join(fields)}"
        for req_id, fields in missing_by_req.items()
    ]

    return {
        "artifact": "plan.json",
        "passed": not missing_by_req,
        "score": round(score, 3),
        "req_count": len(reqs),
        "required_fields": PLAN_JSON_REQ_FIELDS,
        "missing_by_req": missing_by_req,
        "warnings": warnings,
    }


def evaluate_lane_guide_structure(lane_guide_text: str) -> Dict[str, Any]:
    text = str(lane_guide_text or "")
    missing_topics = [
        topic
        for topic, keywords in LANE_GUIDE_REQUIRED_TOPICS.items()
        if not _contains_any(text, keywords)
    ]
    covered_topics = [topic for topic in LANE_GUIDE_REQUIRED_TOPICS if topic not in missing_topics]
    total = len(LANE_GUIDE_REQUIRED_TOPICS)
    score = len(covered_topics) / total if total else 1.0

    return {
        "artifact": "lane-guide",
        "passed": not missing_topics,
        "score": round(score, 3),
        "covered_topics": covered_topics,
        "missing_topics": missing_topics,
        "warnings": [f"lane-guide is missing BMAD quality topic: {topic}" for topic in missing_topics],
    }
