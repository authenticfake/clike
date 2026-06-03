from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


MAX_INVENTORY_ITEMS = 20
MAX_SNIPPET_CHARS_PER_ARTIFACT = 600
MAX_TOTAL_SNIPPET_CHARS = 3_000


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _render_list(items: Iterable[Any], *, empty: str = "none", limit: int = 12) -> str:
    values = [str(item) for item in list(items)[:limit] if str(item or "").strip()]
    return "; ".join(values) if values else empty


def _render_bullets(items: Iterable[Any], *, empty: str = "- none", limit: int = 12) -> List[str]:
    values = [str(item) for item in list(items)[:limit] if str(item or "").strip()]
    return [f"- {item}" for item in values] if values else [empty]


def _group_discovered_artifacts(discovered_artifacts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in discovered_artifacts[:MAX_INVENTORY_ITEMS]:
        if isinstance(item, dict):
            grouped[str(item.get("source_group") or "unknown")].append(item)
    return dict(grouped)


def _render_quality_contracts(quality_contracts: Dict[str, Any]) -> List[str]:
    if not quality_contracts:
        return []

    lines = [
        "### BMAD Quality Contract",
        "- These checks are deterministic review aids; they do not claim automatic quality improvement.",
        "- TECH_CONSTRAINTS.yaml remains authoritative for runtime, provider, deployment, identity, dependency, and command assumptions.",
        "- Do not assume runtime, framework, cloud, database, queue, UI, IaC, or deployment choices unless evidenced by canonical context.",
    ]

    principles = _as_list(quality_contracts.get("principles"))
    if principles:
        lines.append("- principles:")
        lines.extend(_render_bullets(principles, limit=6))

    for key in ["spec", "plan", "plan_json_req", "lane_guide"]:
        contract = quality_contracts.get(key)
        if not isinstance(contract, dict):
            continue
        checks = _as_list(contract.get("checks"))
        required_fields = _as_list(contract.get("required_fields"))
        lines.extend(
            [
                f"- contract: {key}",
                f"  artifact: {contract.get('artifact') or 'unknown'}",
                f"  review_expectation: {contract.get('review_expectation') or ''}",
            ]
        )
        if checks:
            lines.append(f"  checks: {_render_list(checks, limit=16)}")
        if required_fields:
            lines.append(f"  required_fields: {_render_list(required_fields, limit=24)}")

    lines.append("")
    return lines


def _render_active_output_contract(active_output_contract: Optional[dict]) -> List[str]:
    if not isinstance(active_output_contract, dict):
        return []

    required_outputs = _as_list(active_output_contract.get("required_outputs"))
    allowed_optional = _as_list(active_output_contract.get("allowed_optional_output_globs"))
    forbidden = _as_list(active_output_contract.get("forbidden_output_globs"))
    required_context = _as_list(active_output_contract.get("required_context_sections"))

    return [
        "### Active Output Contract",
        "- Emit or update every required output declared by this contract.",
        "- Emit each output as a BEGIN_FILE / END_FILE block.",
        "- Use exactly this wrapper:",
        "  BEGIN_FILE relative/path",
        "  full file content",
        "  END_FILE",
        "- Paths must be workspace-relative and must match the active output contract.",
        "- Markdown file contents may contain fenced code blocks such as YAML. Those internal fences are file content and must be preserved.",
        "- Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks.",
        "- Do not emit prose outside BEGIN_FILE / END_FILE blocks.",
        "- Existing fenced file:/path blocks may still be parsed for compatibility, but BEGIN_FILE / END_FILE is the preferred Harper cloud output format.",
        "- Additional outputs are allowed only under allowed optional output globs.",
        "- Never emit forbidden outputs.",
        "- Do not use file-count shortcuts such as minimum number of files.",
        "- Native CLike runs and BMAD runs have different active output contracts.",
        f"- phase: {active_output_contract.get('phase') or ''}",
        f"- runner: {active_output_contract.get('runner') or ''}",
        f"- methodology: {active_output_contract.get('methodology') or 'native_clike'}",
        f"- agent: {active_output_contract.get('agent') or 'none'}",
        f"- strict_missing_required_outputs: {bool(active_output_contract.get('strict_missing_required_outputs'))}",
        f"- conflict_resolution: {active_output_contract.get('conflict_resolution') or ''}",
        "- required_outputs:",
        *_render_bullets(required_outputs),
        "- allowed_optional_output_globs:",
        *_render_bullets(allowed_optional),
        "- forbidden_output_globs:",
        *_render_bullets(forbidden),
        "- required_context_sections:",
        *_render_bullets(required_context),
        "",
    ]


def render_methodology_context_for_cloud_prompt(
    methodology_context: Optional[dict],
    active_output_contract: Optional[dict] = None,
) -> str:
    """
    Render compact CLike-resolved methodology metadata for cloud Harper prompts.

    The orchestrator is the only resolver. Gateway only composes cloud LLM prompts
    from already-resolved context and never acts as a local-agent prompt builder.
    """
    active_contract_lines = _render_active_output_contract(active_output_contract)

    if not isinstance(methodology_context, dict) or not methodology_context.get("methodology"):
        return "\n".join(active_contract_lines)

    profile = methodology_context.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    allowed_agents = _as_list(methodology_context.get("allowed_agents"))
    workflow_focus = _as_list(methodology_context.get("workflow_focus"))
    required_context = _as_list(methodology_context.get("required_context"))
    companion_artifacts = _as_list(methodology_context.get("companion_artifacts"))
    discovered_artifacts = _as_list(methodology_context.get("discovered_companion_artifacts"))
    governance_boundaries = _as_list(methodology_context.get("governance_boundaries"))
    artifact_policy = methodology_context.get("artifact_policy") or {}
    if not isinstance(artifact_policy, dict):
        artifact_policy = {}
    quality_contracts = methodology_context.get("quality_contracts") or {}
    if not isinstance(quality_contracts, dict):
        quality_contracts = {}

    canonical_outputs = _as_list(artifact_policy.get("canonical_outputs"))
    mandatory_companion_outputs = _as_list(artifact_policy.get("mandatory_companion_outputs"))
    allowed_companion_roots = _as_list(artifact_policy.get("allowed_companion_root_globs"))
    forbidden_outputs = _as_list(artifact_policy.get("forbidden_outputs"))
    downstream_consumers = _as_list(artifact_policy.get("downstream_consumers"))
    conflict_resolution = artifact_policy.get("conflict_resolution") or "canonical-wins"

    lines = [
        *active_contract_lines,
        "### Governed Methodology Profile",
        f"- methodology: {methodology_context.get('methodology')}",
        f"- phase: {methodology_context.get('phase')}",
        f"- role: {methodology_context.get('agent') or 'none'}",
        f"- authority: {methodology_context.get('authority') or 'methodology_profile'}",
        f"- advisory_only: {bool(methodology_context.get('advisory_only'))}",
        f"- allowed_roles_for_phase: {', '.join(str(x) for x in allowed_agents) if allowed_agents else 'none'}",
        f"- role_summary: {profile.get('summary') or ''}",
        f"- workflow_summary: {methodology_context.get('workflow_summary') or ''}",
        f"- workflow_focus: {_render_list(workflow_focus, limit=8)}",
        f"- required_context: {_render_list(required_context, limit=8)}",
        f"- companion_artifacts: {_render_list(companion_artifacts, limit=8)}",
        "",
        "### BMAD Companion Artifact Contract",
        "- This BMAD contract extends the active output contract for this run.",
        "- Mandatory companion outputs must be emitted or updated unless explicitly marked unsupported by the current runner.",
        "- BMAD companion outputs do not replace the canonical artifact schema.",
        "- BMAD companion artifacts extend the active output contract, but they do not replace canonical Harper schemas.",
        "- The canonical artifact must pass the same phase validator as native Harper.",
        "- Companion artifacts should carry exploratory, advisory, or methodology-specific detail.",
        "- BMAD-specific details must be placed in companion artifacts.",
        "- Canonical artifacts must remain concise, coherent, and downstream-ready.",
        "- Companion artifacts are required by default for BMAD runs when the active phase policy declares mandatory companion outputs.",
        "- Companion artifacts are additive and non-authoritative.",
        "- canonical artifacts win on conflict.",
        "- Companion artifacts must improve downstream SPEC, PLAN, KIT, EVAL, or FINALIZE work.",
        "- If an artifact would not be useful downstream, explain why or avoid generating it.",
        f"- conflict_resolution: {conflict_resolution}",
        "- canonical_outputs:",
        *_render_bullets(canonical_outputs),
        "- mandatory_companion_outputs:",
        *_render_bullets(mandatory_companion_outputs or companion_artifacts),
        "- allowed_companion_roots:",
        *_render_bullets(allowed_companion_roots),
        "- forbidden_outputs:",
        *_render_bullets(forbidden_outputs),
        "",
    ]

    lines.append("### BMAD Companion Artifact Inventory")
    if not discovered_artifacts:
        lines.append("- none discovered")
    else:
        grouped = _group_discovered_artifacts(discovered_artifacts)
        snippet_chars = 0
        for source_group in sorted(grouped):
            lines.append(f"- source_group: {source_group}")
            for item in grouped[source_group]:
                path = str(item.get("path") or "")
                size_bytes = int(item.get("size_bytes") or 0)
                digest = str(item.get("sha256") or "")[:12]
                truncated = bool(item.get("truncated"))
                lines.append(
                    f"  - path: {path} | sha256: {digest} | size_bytes: {size_bytes} | truncated: {truncated}"
                )
                snippet = str(item.get("snippet") or "")
                if snippet and snippet_chars < MAX_TOTAL_SNIPPET_CHARS:
                    remaining = MAX_TOTAL_SNIPPET_CHARS - snippet_chars
                    bounded = snippet[: min(MAX_SNIPPET_CHARS_PER_ARTIFACT, remaining)].rstrip()
                    snippet_chars += len(bounded)
                    if bounded:
                        lines.append("    snippet: |")
                        lines.extend([f"      {line}" for line in bounded.splitlines()[:20]])
                        if len(snippet) > len(bounded):
                            lines.append("      ...[snippet truncated]")
        if len(discovered_artifacts) > MAX_INVENTORY_ITEMS:
            lines.append(f"- inventory_truncated: {len(discovered_artifacts) - MAX_INVENTORY_ITEMS} additional artifacts omitted")
        truncated_count = sum(
            1
            for item in discovered_artifacts
            if isinstance(item, dict) and bool(item.get("truncated"))
        )
        if truncated_count:
            lines.append(f"- companion_inventory_truncated_files: {truncated_count}")
    lines.append("")

    if (
        methodology_context.get("methodology") == "bmad"
        and methodology_context.get("phase") == "spec"
        and methodology_context.get("agent") == "ux"
        and bool(artifact_policy.get("companion_only"))
    ):
        allowed_roots = artifact_policy.get("allowed_companion_root_globs") or ["docs/harper/ux/**"]
        lines.extend(
            [
                "SPEC UX artifact policy:",
                "- companion-only: true",
                "- PM-owned canonical SPEC remains authoritative.",
                "- UX must produce companion artifacts only.",
                "- UX artifacts are consumed by /plan as bounded context.",
                "- allowed_outputs: " + _render_list(allowed_roots, limit=4),
                "- forbidden_output: docs/harper/SPEC.md",
                "",
            ]
        )

    if methodology_context.get("methodology") == "bmad":
        if methodology_context.get("phase") == "idea":
            lines.extend(
                [
                    "BMAD IDEA canonical schema rule:",
                    "- The canonical IDEA.md must use the stable Harper IDEA structure and pass native canonical validation.",
                    "- companion files do not replace canonical IDEA.md.",
                    "- Required canonical IDEA headings: # IDEA — <Project Name>; ## Vision; ## Problem Statement; ## Target Users & Context; ## Value & Outcomes; ## Out of Scope; ## Technology Constraints; ## Risks & Assumptions; ## Success Metrics.",
                    "- Put strategic fit, portability reasoning, PRFAQ notes, assumptions deep dives, research gaps, and /spec handoff readiness in BMAD companion artifacts, not in IDEA.md.",
                    "",
                ]
            )
        lines.extend(_render_quality_contracts(quality_contracts))

    lines.extend(
        [
            "### BMAD Governance Boundaries",
            *[
                f"- {item}"
                for item in (
                    governance_boundaries[:6]
                    or [
                        "CLike remains the governance runtime and source of truth.",
                        "Methodology guidance is not an executor selection mechanism.",
                        "Methodology guidance must not override CLike phase contracts, eval/gate policy, candidate isolation, or output schemas.",
                        "If methodology guidance conflicts with CLike rules, follow CLike.",
                    ]
                )
            ],
            "",
            "### BMAD Downstream Handoff",
            "- downstream_consumers:",
            *_render_bullets(downstream_consumers),
            "- Handoff companion artifacts as context only; do not treat them as canonical unless CLike canonical artifacts adopt them.",
            "- Later phases may inspect discovered companion artifacts, but CLike phase contracts and output schemas remain authoritative.",
            "",
        ]
    )
    return "\n".join(lines)


def render_current_canonical_validation_for_cloud_prompt(
    invalid_canonical_artifacts: Optional[List[Dict[str, Any]]],
) -> str:
    invalid = [
        item
        for item in (invalid_canonical_artifacts or [])
        if isinstance(item, dict)
    ]
    if not invalid:
        return ""

    lines = [
        "### Current Canonical Artifact Validation",
        "- current_canonical_invalid: true",
        "- The current canonical artifact must not be imitated structurally.",
        "- Generate a valid replacement that follows the canonical Harper schema.",
        "- Use facts from invalid material only when supported by attachments or repository evidence.",
    ]
    for item in invalid[:8]:
        lines.extend(
            [
                f"- invalid_path: {item.get('path')}",
                f"  failed_checks: {', '.join(str(x) for x in (item.get('failed_checks') or []))}",
                f"  diagnostic: {item.get('diagnostic') or 'Canonical artifact failed validation.'}",
            ]
        )
        snippet = str(item.get("untrusted_repair_material_snippet") or "").strip()
        if snippet:
            lines.append("  untrusted_repair_material_snippet: |")
            lines.extend([f"    {line}" for line in snippet.splitlines()[:40]])
    lines.append("")
    return "\n".join(lines)
