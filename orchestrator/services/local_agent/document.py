"""Local-agent packages for the document phases (idea, spec, plan) and their completeness checks.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import fnmatch
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from services.capabilities import (
    build_capability_metadata_map,
)
from services.phase_definitions import phase_definition, shared_definitions
from services.methodologies.active_output_contract import build_active_output_contract

from services.local_agent.common import (
    _capability_index_names,
    _local_agent_invocation,
    _materialize_attachments,
    _methodology_context_for_local_agent,
    _normalize_relative_path,
    _package_envelope,
    _package_file,
    _render_methodology_prompt_block,
    _resolve_local_executor,
    _safe_text,
)


# Early Harper document phases (/idea, /spec, /plan) reuse one generic
# local-agent document builder. Only the per-phase output files, allowed write
# paths, canonical reads, and prompt guidance differ. Everything else
# (envelope shape, methodology context, executor resolution, fallback handling)
# is shared with the existing local-agent phases.
_DOCUMENT_PHASE_FORBIDDEN_PATHS: List[str] = shared_definitions()["document_phase_forbidden_paths"]


# Document-phase definitions live in orchestrator/phases/<phase>/phase.yaml (WP8.3).
_DOCUMENT_PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    phase: phase_definition(phase)["local_agent"] for phase in ("idea", "spec", "plan")
}


# Canonical phase expectations derived verbatim from the gateway phase system
# prompts (gateway/prompts/harper/{idea,spec,plan}_system.md). The orchestrator
# and the gateway run in separate containers, so instead of reading the gateway
# files at runtime we embed a bounded set of canonical anchors and inject them
# into the local-agent document prompt. This keeps the local-agent path
# isofunctional with the cloud path (same quality bar, same output contract).
# Tests cross-check that each anchor still exists in the gateway prompt file so
# this stays derived from — not divergent with — the canonical cloud prompt.
_DOCUMENT_PHASE_CANONICAL_EXPECTATIONS: Dict[str, List[str]] = {
    phase: phase_definition(phase)["canonical_expectations"] for phase in ("idea", "spec", "plan", "extend")
}


_ACCEPTED_RESULT_PATHS: Dict[str, List[str]] = {
    phase: phase_definition(phase)["accepted_result_paths"] for phase in ("idea", "spec", "plan", "extend")
}


def _path_accepted(phase: str, file_path: Any) -> bool:
    """True when a local-agent result path matches the phase's accepted_result_paths."""
    p = _normalize_relative_path(file_path)
    if not p:
        return False
    return any(fnmatch.fnmatchcase(p, pattern) for pattern in _ACCEPTED_RESULT_PATHS.get(phase, ()))


def _render_canonical_parity_block(phase_norm: str, title: str) -> List[str]:
    """Inject gateway-derived canonical expectations so local output meets or
    exceeds the cloud artifact's expressive power and machine-readability."""
    expectations = _DOCUMENT_PHASE_CANONICAL_EXPECTATIONS.get(phase_norm) or []
    if not expectations:
        return []
    return [
        "",
        f"## Canonical Harper {title} contract (cloud parity — authoritative)",
        f"These expectations are the canonical cloud /{phase_norm} contract. The local",
        "artifact must be isofunctional with the cloud artifact and never weaker:",
        *[f"- {item}" for item in expectations],
        "Match or exceed the cloud artifact: be more explicit, more traceable to the",
        "previous phase, richer in acceptance criteria/constraints/risks/verification",
        "hooks, and downstream-ready — but never skeletal and never heading-only.",
    ]


def _build_plan_capability_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Surface the CLike capability context to the local-agent /plan agent so it can
    populate per-REQ packs/skills/design_profiles instead of defaulting to
    "not_applicable". Mirrors the cloud path, which exposes the capability
    manifest/index in the prompt; here we embed the names in the agent context
    (the in-memory blobs are not on disk for the agent to read).
    """
    core_blobs = payload.get("core_blobs") or {}
    envelope = payload.get("context_envelope") or {}
    clike = envelope.get("clike_capabilities") if isinstance(envelope, dict) else {}
    clike = clike if isinstance(clike, dict) else {}

    available = {
        "packs": _capability_index_names(core_blobs, "packs"),
        "skills": _capability_index_names(core_blobs, "skills"),
        "design_profiles": _capability_index_names(core_blobs, "design_profiles"),
    }
    selected = {
        "packs": [str(x) for x in (clike.get("selected_packs") or []) if str(x or "").strip()],
        "skills": [str(x) for x in (clike.get("selected_skills") or []) if str(x or "").strip()],
        "design_profiles": [
            str(x) for x in (clike.get("selected_design_profiles") or []) if str(x or "").strip()
        ],
    }
    has_capabilities = any(available.values()) or any(selected.values())
    return {
        "available": available,
        "selected": selected,
        "manifest_present": "CLIKE_CAPABILITY_MANIFEST.md" in core_blobs,
        "index_present": "CLIKE_CAPABILITY_INDEX.json" in core_blobs,
        "has_capabilities": has_capabilities,
    }


def build_document_phase_local_agent_package(
    *,
    phase: str,
    payload: Dict[str, Any],
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local-agent package for early Harper document
    phases /idea, /spec, /plan.

    These phases produce canonical Harper documents only. The orchestrator owns
    workflow state, policy, and validation; the local agent is the bounded
    document actuator. The package shape is identical to the other local-agent
    phases (kit/eval/finalize/extend); only the phase-owned outputs, allowed
    write paths, canonical reads, and prompt guidance differ.
    """
    phase_norm = str(phase or "").strip().lower()
    spec = _DOCUMENT_PHASE_SPECS.get(phase_norm)
    if not spec:
        raise ValueError(f"Unsupported document phase for local agent: {phase!r}")

    run_id = _safe_text(payload.get("runId")) or f"{phase_norm}-local"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload, phase_hint=phase_norm)
    active_output_contract = build_active_output_contract(
        phase=phase_norm,
        runner="local_agent",
        methodology_context=methodology_context,
    )

    allowed_write_roots = list(spec["allowed_write_roots"])
    forbidden_paths = list(_DOCUMENT_PHASE_FORBIDDEN_PATHS)
    title = spec["title"]
    attachment_manifest, attachment_package_files = _materialize_attachments(payload, phase_norm)

    # /idea source-of-truth is current-run attachments only. Fail safely if the
    # builder is called directly without attachments (the VS Code extension also
    # blocks this earlier, before any orchestrator call).
    if phase_norm == "idea" and not attachment_manifest["present"]:
        raise ValueError(
            "Cannot run /idea without at least one attached source file. "
            "Attach an IDEA/source document and retry."
        )

    # /plan must populate per-REQ packs/skills/design_profiles from the CLike
    # capability context (cloud parity). Expose it to the agent and add the
    # capability source files to the reads. Plan-only: /idea and /spec are
    # unchanged.
    plan_capability_context: Optional[Dict[str, Any]] = None
    plan_capability_metadata: Optional[Dict[str, Any]] = None
    required_reads = list(spec["required_reads"])
    if phase_norm == "plan":
        plan_capability_context = _build_plan_capability_context(payload)
        try:
            raw_index = (payload.get("core_blobs") or {}).get("CLIKE_CAPABILITY_INDEX.json")
            plan_capability_metadata = build_capability_metadata_map(
                json.loads(raw_index) if raw_index else None
            )
        except Exception:
            plan_capability_metadata = None
        if plan_capability_context["has_capabilities"]:
            required_reads = required_reads + [
                ".clike/capabilities.yaml or .clike/capabilities.yml when present",
                ".clike/packs/** when present",
                ".clike/skills/** when present",
                ".clike/design-profiles/** when present",
            ]

    context = {
        "schema_version": spec["schema_version"],
        "phase": phase_norm,
        "run_id": run_id,
        "input_sources": {
            "idea_md_present": bool(payload.get("idea_md")),
            "spec_md_present": bool(payload.get("spec_md")),
            "plan_md_present": bool(payload.get("plan_md")),
            "attachments_present": attachment_manifest["present"],
            "attachment_count": attachment_manifest["count"],
        },
        "attachments": attachment_manifest,
        **({"capabilities": plan_capability_context} if plan_capability_context else {}),
        **({"methodology_context": methodology_context} if methodology_context else {}),
        "mission": spec["mission"],
        "required_reads": required_reads,
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "output_contract": spec["output_contract"],
        "active_output_contract": active_output_contract,
        "hard_rules": list(spec["hard_rules"]),
        "validation_expectations": list(spec["validation_expectations"]),
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)
    # Package internals live under run-scoped technical paths. The canonical
    # docs/harper directory must contain only canonical Harper artifacts.
    context_path = f"runs/{phase_norm}/docs/AGENT_{title}_CONTEXT.json"
    prompt_path = f"runs/{phase_norm}/docs/AGENT_{title}_PROMPT.md"

    attachment_prompt_lines: List[str] = []
    if attachment_manifest["present"]:
        attachment_prompt_lines = [
            "",
            f"Attachments ({attachment_manifest['count']}) — current-run source of truth (workspace-local copies):",
            *[
                "- "
                + " ".join(
                    part
                    for part in (
                        item.get("workspace_path") or item.get("name") or "",
                        f"({item['mime']})" if item.get("mime") else "",
                    )
                    if part
                )
                for item in attachment_manifest["items"]
            ],
            "- Read every workspace_path listed above before producing output. Multiple attachments are allowed and all must be read.",
            "- workspace_path entries are inside the current working directory; read those. Do NOT read original_path — it is metadata only and may be outside the workspace.",
            "- For PDF attachments, read and extract their full textual content and use it as primary evidence.",
            "- For image attachments (png/jpg/jpeg/gif/webp/svg/...), use vision to describe precisely what the image shows — UI screens, layouts, components, diagrams, charts, labels, and any visible text — and use that description as evidence.",
            "- If an attachment cannot be opened or understood (unsupported binary), state it explicitly as a gap; never invent its content.",
        ]
        if phase_norm == "idea":
            attachment_prompt_lines += [
                "- These current-run materialized attachments are the ONLY source of truth for /idea; do not rely only on RAG.",
                "- Do not use stale workspace files or old uploads. Do not read ORI.IDEA.md or any IDEA* variant unless it is explicitly listed above as a current-run attachment workspace_path.",
                "- Any existing docs/harper/IDEA.md is the overwrite target only, never a source.",
            ]
        else:
            attachment_prompt_lines.append(
                f"- Attachments are the primary source of truth for /{phase_norm}; do not rely only on RAG.",
            )

    capability_prompt_lines: List[str] = []
    if plan_capability_context and plan_capability_context["has_capabilities"]:
        avail = plan_capability_context["available"]
        sel = plan_capability_context["selected"]

        def _cap_line(label: str, kind: str) -> str:
            chosen = sel.get(kind) or avail.get(kind) or []
            return f"- {label}: {', '.join(chosen) if chosen else '(none available)'}"

        capability_prompt_lines = [
            "",
            "CLike capability context (BINDING planning constraints — populate per REQ):",
            _cap_line("available/selected packs", "packs"),
            _cap_line("available/selected skills", "skills"),
            _cap_line("available/selected design_profiles", "design_profiles"),
            "- For every REQ in plan.json, set packs/skills/design_profiles to the applicable capabilities above (arrays of names). Read .clike/capabilities.yaml and .clike/{packs,skills,design-profiles}/** to choose correctly.",
            "- Do NOT default packs/skills/design_profiles to \"not_applicable\" when capabilities are available; use \"not_applicable\" only when no listed capability genuinely applies to that REQ.",
            "- Never invent capabilities that are not in the lists above.",
        ]

    prompt = "\n".join(
        [
            f"# Local Agent {title} Execution Package — Harper {title}",
            "",
            f"You are executing a CLike Harper /{phase_norm} package.",
            "The orchestrator owns workflow state, policy, and validation. The local agent is only the workspace document actuator.",
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read before acting:",
            f"- {context_path}",
            *[f"- {item}" for item in required_reads],
            *attachment_prompt_lines,
            *capability_prompt_lines,
            *_render_canonical_parity_block(phase_norm, title),
            "",
            *spec["prompt_lines"],
            "",
            "Forbidden writes:",
            "- any docs/harper path other than the allowed writes above",
            "- src/, test/, tests/",
            "- runs/kit/, runs/eval/, runs/gate/",
            "- .git/",
            "",
            "Execution rules:",
            "- Follow AGENT_*_CONTEXT.json as the source of truth.",
            "- Do not run git commands.",
            "- Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.",
            "- Do not invent facts, vendors, APIs, endpoints, project keys, or frameworks not evidenced by inputs.",
            "",
            "At the end, print a concise summary with files changed, validation performed, and unresolved gaps.",
        ]
    )

    return _package_envelope(
        phase=phase_norm,
        echo=f"Local agent {phase_norm} package prepared for Harper {title}",
        summary=f"local-agent-{phase_norm}-package-prepared",
        extra_warnings=[f"{phase_norm}_requires_harper_docs_mutation"],
        run_id=run_id,
        execution_policy=execution_policy,
        local_agent={
            "action": "local_agent_required",
            "package_id": f"{run_id}:SOLUTION:{phase_norm}",
            "phase": phase_norm,
            "req_id": "SOLUTION",
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": _local_agent_invocation(local_executor, payload),
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "active_output_contract": active_output_contract,
            "expected_outputs": context["output_contract"],
            # Surface available capabilities so completion can detect plan.json
            # that degrades every REQ to "not_applicable" despite real options,
            # and the capability metadata map so completion can deterministically
            # enrich the structured `capabilities` block (cloud parity).
            **(
                {"available_capabilities": plan_capability_context["available"]}
                if plan_capability_context and plan_capability_context["has_capabilities"]
                else {}
            ),
            **(
                {"capability_metadata": plan_capability_metadata}
                if plan_capability_metadata
                and any(plan_capability_metadata.get(k) for k in ("packs", "skills", "design_profiles"))
                else {}
            ),
            "package_files": [
                _package_file(context_path, context_json, "application/json"),
                _package_file(prompt_path, prompt, "text/markdown"),
                # Current-run attachments are materialized into the workspace so
                # the agent reads them from its cwd (no external-path approval).
                *attachment_package_files,
            ],
        },
    )


def _markdown_section_body(text: str, heading_variants: List[str]) -> Optional[str]:
    """Return the body after the first matching `## Heading`, up to the next `##`.

    Returns None when no variant heading is present.
    """
    for heading in heading_variants:
        pattern = re.compile(r"^\s*" + re.escape(heading) + r"\s*$", re.IGNORECASE | re.MULTILINE)
        match = pattern.search(text)
        if not match:
            continue
        rest = text[match.end():]
        nxt = re.search(r"^\s*##\s+", rest, re.MULTILINE)
        return rest[: nxt.start()] if nxt else rest
    return None


def _count_markdown_bullets(section_text: str) -> int:
    count = 0
    for line in (section_text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+[.)]\s+", stripped):
            count += 1
    return count


def _validate_document_phase_completeness(
    phase: str,
    content_by_path: Dict[str, str],
    available_capabilities: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[str]]:
    """Deterministic non-skeletal validation for document-phase outputs.

    Thresholds mirror the canonical gateway phase prompts so the local-agent
    artifacts stay isofunctional with the cloud path (and never heading-only).
    Returns (errors, warnings); errors is non-empty only when an output is
    structurally incomplete.
    """
    warnings: List[str] = []
    incomplete = False

    if phase == "idea":
        content = content_by_path.get("docs/harper/IDEA.md", "") or ""
        canonical_sections = [
            ["## Vision"],
            ["## Problem Statement"],
            ["## Target Users & Context"],
            ["## Value & Outcomes", "## Value & Outcomes (with initial targets)"],
            ["## Out of Scope", "## Out of Scope (slice-1)"],
            ["## Technology Constraints", "## Technology Constraints (SPEC-ready)"],
            ["## Risks & Assumptions"],
            ["## Success Metrics"],
        ]
        for variants in canonical_sections:
            body = _markdown_section_body(content, variants)
            if body is None:
                incomplete = True
                warnings.append(f"idea:missing_section:{variants[0]}")
            elif len(body.strip()) < 30:
                incomplete = True
                warnings.append(f"idea:empty_section:{variants[0]}")
        if not re.search(r"^```ya?ml\s*$", content, re.IGNORECASE | re.MULTILINE):
            incomplete = True
            warnings.append("idea:missing_fenced_yaml_under_technology_constraints")

    elif phase == "spec":
        content = content_by_path.get("docs/harper/SPEC.md", "") or ""
        acceptance_body = _markdown_section_body(content, ["## Acceptance Criteria"])
        if acceptance_body is None:
            incomplete = True
            warnings.append("spec:missing_section:## Acceptance Criteria")
        else:
            bullets = _count_markdown_bullets(acceptance_body)
            if bullets < 5:
                incomplete = True
                warnings.append(f"spec:acceptance_criteria_below_minimum:{bullets}")
        for variants in (["## Functional Requirements"], ["## Non-Functional Requirements"]):
            body = _markdown_section_body(content, variants)
            if body is None or len(body.strip()) < 30:
                incomplete = True
                warnings.append(f"spec:empty_or_missing_section:{variants[0]}")
        if "SPEC_END" not in content:
            incomplete = True
            warnings.append("spec:missing_SPEC_END")

    elif phase == "plan":
        plan_md = content_by_path.get("docs/harper/PLAN.md", "") or ""
        plan_json_text = content_by_path.get("docs/harper/plan.json", "") or ""

        if not re.search(r"\bREQ-\d+", plan_md):
            incomplete = True
            warnings.append("plan:missing_req_ids_in_plan_md")
        if not re.search(r"verification|checkpoint|acceptance", plan_md, re.IGNORECASE):
            incomplete = True
            warnings.append("plan:missing_verification_checkpoints_in_plan_md")

        try:
            plan_data = json.loads(plan_json_text)
        except Exception:
            incomplete = True
            warnings.append("plan:plan_json_invalid_json")
            plan_data = None

        if isinstance(plan_data, dict):
            reqs = plan_data.get("reqs") or plan_data.get("requirements") or plan_data.get("items")
            json_req_ids: set = set()
            # Track whether any REQ populated each capability field with a real
            # value (not "not_applicable"/empty), to detect blanket degradation.
            capability_populated = {"packs": False, "skills": False, "design_profiles": False}

            def _capability_is_populated(value: Any) -> bool:
                if isinstance(value, list):
                    return any(
                        str(v).strip() and str(v).strip().lower() != "not_applicable" for v in value
                    )
                if isinstance(value, str):
                    return bool(value.strip()) and value.strip().lower() != "not_applicable"
                return False

            if not isinstance(reqs, list) or not reqs:
                incomplete = True
                warnings.append("plan:plan_json_missing_reqs")
            else:
                for index, req in enumerate(reqs):
                    if not isinstance(req, dict):
                        incomplete = True
                        warnings.append(f"plan:plan_json_req_{index}_not_object")
                        continue
                    rid = _safe_text(req.get("id"))
                    if rid:
                        json_req_ids.add(rid.upper())
                    acceptance = req.get("acceptance")
                    if acceptance is None:
                        acceptance = req.get("acceptance_criteria")
                    has_acceptance = bool(
                        (isinstance(acceptance, list) and any(str(a).strip() for a in acceptance))
                        or (isinstance(acceptance, str) and acceptance.strip())
                    )
                    if not has_acceptance:
                        incomplete = True
                        warnings.append(f"plan:plan_json_req_{rid or index}_empty_acceptance")
                    for kind in capability_populated:
                        if _capability_is_populated(req.get(kind)):
                            capability_populated[kind] = True

            # Every REQ-ID referenced in PLAN.md must exist in plan.json
            # (plan.json is the machine-readable source of truth for /kit).
            plan_md_req_ids = {m.upper() for m in re.findall(r"\bREQ-\d+", plan_md)}
            missing_in_json = sorted(plan_md_req_ids - json_req_ids)
            if missing_in_json:
                incomplete = True
                warnings.append(
                    "plan:plan_md_reqs_missing_from_plan_json:" + ",".join(missing_in_json[:20])
                )

            # Capability degradation: every REQ defaulted a field to
            # "not_applicable"/empty while real capabilities were available.
            # Warning-level (non-blocking) to avoid false rejects when no listed
            # capability genuinely applies.
            if isinstance(available_capabilities, dict) and isinstance(reqs, list) and reqs:
                for kind in ("packs", "skills", "design_profiles"):
                    available = available_capabilities.get(kind) or []
                    if available and not capability_populated[kind]:
                        warnings.append(
                            f"plan:all_reqs_{kind}_not_applicable_despite_available_capabilities"
                        )
        elif plan_data is not None:
            incomplete = True
            warnings.append("plan:plan_json_not_object")

    errors = ["document_phase_output_incomplete"] if incomplete else []
    return errors, warnings
