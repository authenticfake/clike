from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROMPT_TEMPLATE_PHRASES = [
    "Print EXCLUSIVELY " + "one file block",
    "Produce only " + "the single",
    "single " + "BEGIN_FILE",
    "No additional " + "files",
]

UNRESOLVED_PLACEHOLDERS = [
    "<Project Name>",
    "<X min",
    "<...>",
    "My Solution Name",
]

GENERIC_TEMPLATE_ONLY_VALUES = [
    "aws-eks",
    "my-project-key",
    "https://api.openai.com",
]

BMAD_IDEA_EXTRA_SECTIONS = [
    "## Deployment Portability Rule",
    "## Technology Constraints Profile Rule",
    "## Strategic Fit",
    "## /spec Handoff Readiness",
]


def _result(path: str, checks: List[str], diagnostic: str) -> Dict[str, Any]:
    return {
        "ok": not checks,
        "path": path,
        "failed_checks": checks,
        "diagnostic": diagnostic if checks else "",
        "error_code": "invalid_canonical_artifact" if checks else None,
    }


def _contains_case_insensitive(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def _has_heading(text: str, heading: str) -> bool:
    pattern = rf"(?im)^\s*{re.escape(heading)}\s*$"
    return re.search(pattern, text) is not None


def _heading_index(text: str, heading: str) -> int:
    match = re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", text)
    return match.start() if match else -1


def _has_any_heading(text: str, headings: Iterable[str]) -> bool:
    return any(_has_heading(text, heading) for heading in headings)


def _starts_with_heading(text: str, prefix: str) -> bool:
    first = str(text or "").lstrip().splitlines()[0] if str(text or "").strip() else ""
    return first.startswith(prefix)


def _common_markdown_failures(content: str, evidence_text: str = "") -> List[str]:
    text = str(content or "")
    failures: List[str] = []
    if "BEGIN_FILE" in text:
        failures.append("contains_BEGIN_FILE")
    if "END_FILE" in text:
        failures.append("contains_END_FILE")
    for phrase in PROMPT_TEMPLATE_PHRASES:
        if _contains_case_insensitive(text, phrase):
            failures.append(f"contains_prompt_template_phrase:{phrase}")
    for placeholder in UNRESOLVED_PLACEHOLDERS:
        if placeholder in text:
            failures.append(f"contains_unresolved_placeholder:{placeholder}")
    for value in GENERIC_TEMPLATE_ONLY_VALUES:
        if value in text and value not in str(evidence_text or ""):
            failures.append(f"contains_unevidenced_template_value:{value}")
    return failures


def _looks_like_fenced_yaml(text: str) -> bool:
    return re.search(r"(?im)^```ya?ml\s*$", text) is not None


def _section_after(text: str, heading: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", text)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"(?m)^\s*##\s+", rest)
    return rest[: next_heading.start()] if next_heading else rest


def validateIdeaMarkdown(
    content: str,
    *,
    path: str = "docs/harper/IDEA.md",
    evidence_text: str = "",
) -> Dict[str, Any]:
    text = str(content or "")
    stripped = text.lstrip()
    failures = _common_markdown_failures(text, evidence_text)

    if not (stripped.startswith("# IDEA — ") or stripped.startswith("# IDEA - ")):
        failures.append("missing_idea_h1")
    if stripped.startswith("```") or stripped.lower().startswith("tech_constraints:"):
        failures.append("starts_with_raw_yaml_or_fence")

    primary_headings = [
        "## Vision",
        "## Problem Statement",
        "## Target Users & Context",
        ("## Value & Outcomes", "## Value & Outcomes (with initial targets)"),
        ("## Out of Scope", "## Out of Scope (slice-1)"),
        ("## Technology Constraints", "## Technology Constraints (SPEC-ready)"),
        "## Risks & Assumptions",
    ]

    primary_indexes: List[int] = []
    for item in primary_headings:
        if isinstance(item, tuple):
            found = [idx for idx in (_heading_index(text, option) for option in item) if idx >= 0]
            if not found:
                failures.append("missing_heading:" + "|".join(item))
            else:
                primary_indexes.append(min(found))
        else:
            idx = _heading_index(text, item)
            if idx < 0:
                failures.append(f"missing_heading:{item}")
            else:
                primary_indexes.append(idx)

    if primary_indexes and primary_indexes != sorted(primary_indexes):
        failures.append("primary_idea_sections_out_of_order")

    tech_section = _section_after(text, "## Technology Constraints") or _section_after(text, "## Technology Constraints (SPEC-ready)")
    if not _looks_like_fenced_yaml(tech_section):
        failures.append("missing_fenced_yaml_after_technology_constraints")

    if not re.search(r"(?im)^\s*##\s+.*success metrics", text):
        failures.append("missing_success_metrics_section")

    core_opening_indexes = [
        idx
        for heading in ["## Vision", "## Problem Statement", "## Target Users & Context"]
        for idx in [_heading_index(text, heading)]
        if idx >= 0
    ]
    if core_opening_indexes:
        last_core_opening = max(core_opening_indexes)
        for heading in BMAD_IDEA_EXTRA_SECTIONS:
            idx = _heading_index(text, heading)
            if 0 <= idx < last_core_opening:
                failures.append(f"bmad_extra_section_before_primary:{heading}")

    return _result(path, failures, "IDEA.md failed canonical Harper structure validation.")


def validateSpecMarkdown(content: str, *, path: str = "docs/harper/SPEC.md") -> Dict[str, Any]:
    text = str(content or "")
    lower = text.lower()
    failures = _common_markdown_failures(text)
    if not _starts_with_heading(text, "# SPEC"):
        failures.append("missing_spec_h1")
    if not any(term in lower for term in ["problem", "scope", "objective", "requirement"]):
        failures.append("missing_problem_scope_or_requirements")
    if not any(term in lower for term in ["acceptance criteria", "testability", "test strategy"]):
        failures.append("missing_acceptance_or_testability")
    if not any(term in lower for term in ["constraint", "non-functional", "non functional"]):
        failures.append("missing_constraints_or_non_functional_requirements")
    if "spec_ux_appendix" in lower or "user journey" in lower and "functional requirement" not in lower:
        failures.append("looks_like_companion_only_ux_content")
    return _result(path, failures, "SPEC.md failed canonical Harper structure validation.")


def validatePlanMarkdown(content: str, *, path: str = "docs/harper/PLAN.md") -> Dict[str, Any]:
    text = str(content or "")
    lower = text.lower()
    failures = _common_markdown_failures(text)
    if not _starts_with_heading(text, "# PLAN"):
        failures.append("missing_plan_h1")
    if "REQ-" not in text:
        failures.append("missing_req_ids")
    if not any(term in lower for term in ["dependencies", "dependson", "ordering", "depends on"]):
        failures.append("missing_dependencies_or_ordering")
    if not any(term in lower for term in ["/kit", "kit readiness", "kit-readiness", "implementation readiness"]):
        failures.append("missing_kit_or_implementation_readiness")
    return _result(path, failures, "PLAN.md failed canonical Harper structure validation.")


def validatePlanJson(content: str, *, path: str = "docs/harper/plan.json") -> Dict[str, Any]:
    text = str(content or "")
    failures: List[str] = []
    if text.lstrip().startswith("#") or "```" in text:
        failures.append("looks_like_markdown")
    try:
        data = json.loads(text)
    except Exception:
        return _result(path, [*failures, "invalid_json"], "plan.json must be valid JSON.")

    if not isinstance(data, dict):
        failures.append("json_root_not_object")
        return _result(path, failures, "plan.json root must be an object.")

    reqs = data.get("reqs") or data.get("requirements") or data.get("items")
    if not isinstance(reqs, list) or not reqs:
        failures.append("missing_requirements_list")
    else:
        for index, req in enumerate(reqs):
            if not isinstance(req, dict):
                failures.append(f"req_{index}_not_object")
                continue
            for field in ["id", "title", "status", "acceptance"]:
                if not req.get(field):
                    failures.append(f"req_{index}_missing_{field}")
            if "dependsOn" not in req and "dependencies" not in req and "depends_on" not in req:
                failures.append(f"req_{index}_missing_dependencies")

    return _result(path, failures, "plan.json failed canonical Harper structure validation.")


def validateLaneGuideMarkdown(content: str, *, path: str = "docs/harper/lane-guides/<lane>.md") -> Dict[str, Any]:
    text = str(content or "")
    lower = text.lower()
    failures = _common_markdown_failures(text)
    if not text.lstrip().startswith("#"):
        failures.append("missing_heading")
    if not any(term in lower for term in ["lane purpose", "purpose", "scope"]):
        failures.append("missing_lane_purpose_or_scope")
    if not any(term in lower for term in ["expected files", "boundaries", "boundary"]):
        failures.append("missing_expected_files_or_boundaries")
    if not any(term in lower for term in ["test command", "validation command", "commands"]):
        failures.append("missing_test_or_validation_commands")
    if not any(term in lower for term in ["eval/gate", "eval expectations", "gate expectations"]):
        failures.append("missing_eval_gate_expectations")
    return _result(path, failures, "Lane guide failed canonical Harper structure validation.")


def validate_canonical_harper_artifact(path: str, content: str, *, evidence_text: str = "") -> Optional[Dict[str, Any]]:
    normalized = str(path or "").replace("\\", "/").lstrip("./").lstrip("/")
    bare_to_canonical = {
        "IDEA.md": "docs/harper/IDEA.md",
        "SPEC.md": "docs/harper/SPEC.md",
        "PLAN.md": "docs/harper/PLAN.md",
        "plan.json": "docs/harper/plan.json",
    }
    normalized = bare_to_canonical.get(normalized, normalized)
    if normalized == "docs/harper/IDEA.md":
        return validateIdeaMarkdown(content, path=normalized, evidence_text=evidence_text)
    if normalized == "docs/harper/SPEC.md":
        return validateSpecMarkdown(content, path=normalized)
    if normalized == "docs/harper/PLAN.md":
        return validatePlanMarkdown(content, path=normalized)
    if normalized == "docs/harper/plan.json":
        return validatePlanJson(content, path=normalized)
    if re.fullmatch(r"docs/harper/lane-guides/[^/]+\.md", normalized):
        return validateLaneGuideMarkdown(content, path=normalized)
    return None


def validate_canonical_harper_files(
    files: List[Dict[str, Any]],
    *,
    evidence_text: str = "",
) -> Dict[str, Any]:
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    rejected_source_files: List[Dict[str, Any]] = []
    for item in files or []:
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        validation = validate_canonical_harper_artifact(path, content, evidence_text=evidence_text)
        if validation and not validation.get("ok"):
            rejected.append(validation)
            rejected_source_files.append(item)
            continue
        accepted.append(item)
    return {
        "accepted_files": accepted,
        "rejected": rejected,
        "rejected_source_files": rejected_source_files,
    }


def safe_rejected_artifact_name(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").lstrip("./").lstrip("/")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "__", normalized)
    safe = re.sub(r"[.]{2,}", "_", safe).strip("_")
    return (safe[:180] or "artifact") + ".invalid.md"


def rejected_artifact_debug_path(
    *,
    telemetry_root: str | Path,
    project_id: str,
    run_id: str | None,
    phase: str,
    artifact_path: str,
) -> Path:
    def safe_part(value: str, fallback: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or fallback))
        cleaned = re.sub(r"[.]{2,}", "_", cleaned).strip("._")
        return cleaned or fallback

    root = Path(telemetry_root).resolve()
    candidate = (
        root
        / "rejected"
        / safe_part(project_id, "default")
        / safe_part(run_id or "n-a", "n-a")
        / safe_part(phase, "phase")
        / safe_rejected_artifact_name(artifact_path)
    )
    resolved = candidate.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Rejected artifact debug path escaped telemetry root.")
    return resolved


def attach_rejected_artifact_debug_refs(
    rejected: List[Dict[str, Any]],
    *,
    telemetry_root: str | Path,
    project_id: str,
    run_id: str | None,
    phase: str,
    files: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_path = {
        str((item or {}).get("path") or ""): str((item or {}).get("content") or "")
        for item in files or []
    }
    enriched: List[Dict[str, Any]] = []
    for item in rejected or []:
        cloned = dict(item)
        artifact_path = str(cloned.get("path") or "")
        content = by_path.get(artifact_path, "")
        try:
            debug_path = rejected_artifact_debug_path(
                telemetry_root=telemetry_root,
                project_id=project_id,
                run_id=run_id,
                phase=phase,
                artifact_path=artifact_path,
            )
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(content, encoding="utf-8")
            cloned["debug_path"] = debug_path.as_posix()
            cloned["rejected_artifact_ref"] = debug_path.as_posix()
        except Exception as exc:
            cloned["debug_path_error"] = str(exc)
        enriched.append(cloned)
    return enriched


def validate_current_canonical_core_blobs(
    core_blobs: Dict[str, str] | None,
) -> Dict[str, Any]:
    trusted: Dict[str, str] = {}
    invalid: List[Dict[str, Any]] = []
    for key, value in (core_blobs or {}).items():
        validation = validate_canonical_harper_artifact(str(key), str(value or ""))
        if validation and not validation.get("ok"):
            item = dict(validation)
            item["current_canonical_invalid"] = True
            item["untrusted_repair_material_snippet"] = str(value or "")[:2000]
            invalid.append(item)
            continue
        trusted[str(key)] = str(value or "")
    return {"trusted_core_blobs": trusted, "invalid_canonical": invalid}
