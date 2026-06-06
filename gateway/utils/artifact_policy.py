from __future__ import annotations

import re

from typing import Any, Dict, List, Optional


def _normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./").lstrip("/")


def _matches_policy_path(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path).lower()
    normalized_pattern = _normalize_path(pattern).lower()
    if not normalized_path or not normalized_pattern:
        return False
    if "<req-id>" in normalized_pattern:
        regex = re.escape(normalized_pattern)
        regex = regex.replace(re.escape("<req-id>"), r"req-[a-z0-9._-]+")
        regex = regex.replace(re.escape("**"), r".*")
        return re.fullmatch(regex, normalized_path) is not None
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/") + "/"
        return normalized_path.startswith(prefix)
    return normalized_path == normalized_pattern


def filter_files_by_methodology_artifact_policy(
    files: List[Dict[str, Any]],
    *,
    phase: str,
    methodology_context: Optional[Dict[str, Any]],
    warnings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Enforce CLike-resolved methodology artifact policy on Gateway outputs.

    The Orchestrator resolves methodology_context. Gateway only applies the
    already-resolved output policy to cloud-generated files.
    """
    if not isinstance(methodology_context, dict):
        return files or []
    if methodology_context.get("methodology") != "bmad":
        return files or []

    policy = methodology_context.get("artifact_policy") or {}
    if not isinstance(policy, dict):
        return files or []

    canonical_outputs = list(policy.get("canonical_outputs") or [])
    allowed_companion_roots = list(policy.get("allowed_companion_root_globs") or [])
    forbidden_outputs = list(policy.get("forbidden_outputs") or [])
    companion_only = bool(policy.get("companion_only", False))
    agent = str(methodology_context.get("agent") or "").strip().lower()

    allowed_patterns = canonical_outputs + allowed_companion_roots
    if not allowed_patterns:
        return files or []

    kept: List[Dict[str, Any]] = []
    dropped_paths: List[str] = []

    for item in files or []:
        path = _normalize_path(str((item or {}).get("path") or ""))
        if not path:
            continue

        forbidden = any(_matches_policy_path(path, pattern) for pattern in forbidden_outputs)
        allowed = any(_matches_policy_path(path, pattern) for pattern in allowed_patterns)

        if forbidden or not allowed:
            dropped_paths.append(path)
            continue

        kept.append(item)

    if dropped_paths and warnings is not None:
        if agent == "ux" and companion_only:
            warnings.append(
                "bmad_spec_ux_companion_only: dropped outputs outside docs/harper/ux/**; PM-owned canonical SPEC remains authoritative."
            )
        else:
            warnings.append(
                f"bmad_{str(phase or '').strip().lower()}_artifact_policy: dropped outputs outside resolved BMAD artifact policy."
            )
        warnings.append("bmad_artifact_policy_dropped: " + ", ".join(dropped_paths[:8]))

    return kept
