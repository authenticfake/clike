from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


NATIVE_CLOUD_REQUIRED_OUTPUTS: Dict[str, List[str]] = {
    "idea": ["docs/harper/IDEA.md"],
    "spec": ["docs/harper/SPEC.md"],
    "plan": ["docs/harper/PLAN.md", "docs/harper/plan.json", "docs/harper/lane-guides/**"],
    "finalize": [
        "README.md",
        "docs/harper/HOWTO_RUN.md",
        "docs/harper/RELEASE_NOTES.md",
        "docs/harper/SANITY_CHECKS.md",
        "docs/harper/TODO_NEXT.md",
        "docs/harper/PR_BODY.md",
    ],
}

NATIVE_CLOUD_OPTIONAL_OUTPUTS: Dict[str, List[str]] = {
    "plan": ["docs/harper/lane-guides/**"],
    "finalize": [
        ".env.example",
        "docs/harper/**",
        "scripts/**",
        "src/**",
        "infra/**",
        "deploy/**",
        "ops/**",
        "config/**",
        "configs/**",
        "schemas/**",
        "migrations/**",
        "db/**",
        "database/**",
        "connectors/**",
        "jobs/**",
        "pipelines/**",
        "packages/**",
        "model/**",
        "models/**",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "requirements.txt",
        "pom.xml",
        "build.gradle",
        "settings.gradle",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "docker-compose.yml",
        "Dockerfile",
        "Makefile",
    ],
}

NATIVE_FORBIDDEN_OUTPUTS: Dict[str, List[str]] = {
    "idea": ["src/**", "test/**", "tests/**", "runs/**"],
    "spec": ["src/**", "test/**", "tests/**", "runs/**"],
    "plan": ["src/**", "test/**", "tests/**", "runs/**"],
}

NATIVE_CONTEXT_SECTIONS: Dict[str, List[str]] = {
    "idea": ["attachments", "chat", "technology constraints"],
    "spec": ["IDEA.md", "TECH_CONSTRAINTS.yaml", "companion artifacts when present"],
    "plan": ["SPEC.md", "TECH_CONSTRAINTS.yaml", "plan.json", "lane guides"],
    "kit": ["SPEC.md", "PLAN.md", "plan.json", "TARGET_CONTRACT.json", "FILE_REQUIREMENTS.json"],
    "eval": ["EvalRunner evidence", "LTC.json", "HOWTO.md", "candidate files"],
    "finalize": ["PLAN.md", "plan.json", "eval reports", "gate reports", "candidate/final artifacts"],
}


def normalize_output_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./").lstrip("/")


def output_path_matches(path: str, pattern: str) -> bool:
    normalized_path = normalize_output_path(path).lower()
    normalized_pattern = normalize_output_path(pattern).lower()
    if not normalized_path or not normalized_pattern:
        return False
    regex = re.escape(normalized_pattern)
    regex = regex.replace(re.escape("<req-id>"), r"req-[a-z0-9._-]+")
    regex = regex.replace(re.escape("**"), r".*")
    return re.fullmatch(regex, normalized_path) is not None


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
    runner_name = str(runner or "cloud").strip().lower()
    context = methodology_context if isinstance(methodology_context, dict) else {}
    policy = context.get("artifact_policy") if isinstance(context.get("artifact_policy"), dict) else {}
    methodology = "bmad" if context.get("methodology") == "bmad" and policy else "native_clike"

    if methodology == "bmad":
        companion_only = bool(policy.get("companion_only"))
        native_required = [] if companion_only else list(NATIVE_CLOUD_REQUIRED_OUTPUTS.get(phase_name) or [])
        native_optional = [] if companion_only else list(NATIVE_CLOUD_OPTIONAL_OUTPUTS.get(phase_name) or [])
        native_forbidden = list(NATIVE_FORBIDDEN_OUTPUTS.get(phase_name) or [])
        canonical = _replace_req_id(list(policy.get("canonical_outputs") or []), req_id)
        mandatory = _replace_req_id(list(policy.get("mandatory_companion_outputs") or []), req_id)
        optional = _dedupe([*native_optional, *_replace_req_id(list(policy.get("allowed_companion_root_globs") or []), req_id)])
        forbidden = _dedupe([*native_forbidden, *_replace_req_id(list(policy.get("forbidden_outputs") or []), req_id)])
        required = _dedupe([*native_required, *canonical, *mandatory])
        conflict_resolution = str(policy.get("conflict_resolution") or "canonical-wins")
        strict_missing = phase_name in {"idea", "spec", "plan", "finalize", "kit"} and runner_name == "cloud"
    else:
        required = list(NATIVE_CLOUD_REQUIRED_OUTPUTS.get(phase_name) or [])
        optional = list(NATIVE_CLOUD_OPTIONAL_OUTPUTS.get(phase_name) or [])
        forbidden = list(NATIVE_FORBIDDEN_OUTPUTS.get(phase_name) or [])
        conflict_resolution = "native-clike-contract-wins"
        strict_missing = phase_name in {"idea", "spec", "plan"} and runner_name == "cloud"

    return {
        "phase": phase_name,
        "runner": runner_name,
        "methodology": methodology,
        "agent": context.get("agent"),
        "required_outputs": required,
        "allowed_optional_output_globs": optional,
        "forbidden_output_globs": forbidden,
        "required_context_sections": list(NATIVE_CONTEXT_SECTIONS.get(phase_name) or []),
        "strict_missing_required_outputs": bool(strict_missing),
        "conflict_resolution": conflict_resolution,
    }


def validate_files_against_active_output_contract(
    files: List[Dict[str, Any]],
    contract: Dict[str, Any],
) -> Dict[str, Any]:
    paths = [normalize_output_path(str((item or {}).get("path") or "")) for item in files or []]
    required = list(contract.get("required_outputs") or [])
    optional = list(contract.get("allowed_optional_output_globs") or [])
    forbidden = list(contract.get("forbidden_output_globs") or [])
    allowed_patterns = [*required, *optional]

    missing = [
        pattern
        for pattern in required
        if not any(output_path_matches(path, pattern) for path in paths)
    ]
    forbidden_paths = [
        path
        for path in paths
        if any(output_path_matches(path, pattern) for pattern in forbidden)
    ]
    extra_disallowed = [
        path
        for path in paths
        if allowed_patterns and not any(output_path_matches(path, pattern) for pattern in allowed_patterns)
    ]

    return {
        "ok": not missing and not forbidden_paths and not extra_disallowed,
        "missing_required_outputs": missing,
        "forbidden_outputs": forbidden_paths,
        "disallowed_outputs": extra_disallowed,
    }
