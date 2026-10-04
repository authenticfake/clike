"""Local-agent package for /extend.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
from typing import Any, Dict, List
from services.phase_definitions import phase_definition

from services.local_agent.common import (
    _local_agent_invocation,
    _materialize_attachments,
    _methodology_context_for_local_agent,
    _package_envelope,
    _package_file,
    _render_methodology_prompt_block,
    _resolve_local_executor,
    _safe_text,
)
from services.local_agent.document import (
    _DOCUMENT_PHASE_FORBIDDEN_PATHS,
    _render_canonical_parity_block,
)


def build_extend_local_agent_package(
    *,
    payload: Dict[str, Any],
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the local-agent execution package for Harper /extend.

    /extend is a documentation/planning mutation phase. It must append new REQs
    to existing Harper planning artifacts without modifying consolidated REQs or
    touching source/test/KIT/eval roots.
    """
    extend_def = phase_definition("extend")["local_agent"]
    run_id = _safe_text(payload.get("runId")) or "extend-local"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload, phase_hint="extend")

    extend_opts = dict(payload.get("extend") or payload.get("gen") or {})
    anchor_req = _safe_text(
        extend_opts.get("anchorReq")
        or extend_opts.get("anchor_req")
        or payload.get("anchorReq")
        or payload.get("anchor_req")
    ).upper()
    explicit_req = _safe_text(
        extend_opts.get("explicitReq")
        or extend_opts.get("explicit_req")
        or payload.get("explicitReq")
        or payload.get("explicit_req")
    ).upper()
    raw_input = _safe_text(
        extend_opts.get("rawInput")
        or extend_opts.get("raw_input")
        or payload.get("rawInput")
        or payload.get("raw_input")
    )
    from_attachment = bool(
        extend_opts.get("fromAttachment")
        or extend_opts.get("from_attachment")
        or payload.get("fromAttachment")
        or payload.get("from_attachment")
    )

    attachment_manifest, attachment_package_files = _materialize_attachments(payload, "extend")

    # --from attachment requires at least one current-run attachment. Fail safely
    # if the builder is called directly without one (the extension also blocks
    # this earlier, before any orchestrator call).
    if from_attachment and not attachment_manifest["present"]:
        raise ValueError(
            "Cannot run /extend --from attachment without at least one attached source file. "
            "Attach a source document and retry."
        )

    # Narrow, phase-owned write roots only. EXTEND files use a dynamic date/REQ
    # name, so the EXTEND_*.md glob is advertised; normalization is the real gate.
    allowed_write_roots = extend_def["allowed_write_roots"]

    forbidden_paths = list(_DOCUMENT_PHASE_FORBIDDEN_PATHS)

    context = {
        "schema_version": extend_def["schema_version"],
        "phase": "extend",
        "run_id": run_id,
        "anchor_req": anchor_req,
        "explicit_req": explicit_req,
        "raw_input": raw_input,
        "from_attachment": from_attachment,
        "input_sources": {
            "inline_text_present": bool(raw_input),
            "attachments_present": attachment_manifest["present"],
            "attachment_count": attachment_manifest["count"],
        },
        "attachments": attachment_manifest,
        **({"methodology_context": methodology_context} if methodology_context else {}),
        "mission": extend_def["mission"],
        "required_reads": extend_def["required_reads"],
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "output_contract": extend_def["output_contract"],
        "hard_rules": extend_def["hard_rules"],
        "validation_expectations": extend_def["validation_expectations"],
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)
    # Package internals live under run-scoped technical paths. docs/harper must
    # contain only canonical Harper artifacts, never AGENT_* package internals.
    context_path = "runs/extend/docs/AGENT_EXTEND_CONTEXT.json"
    prompt_path = "runs/extend/docs/AGENT_EXTEND_PROMPT.md"

    attachment_prompt_lines: List[str] = []
    if attachment_manifest["present"]:
        attachment_prompt_lines = [
            "",
            f"Attachments ({attachment_manifest['count']}) — current-run source (workspace-local copies):",
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
            "- Read every workspace_path listed above. Do NOT read original_path — it is metadata only and may be outside the workspace.",
        ]

    prompt = "\n".join(
        [
            "# Local Agent EXTEND Execution Package — Harper Plan Extension",
            "",
            "You are executing a CLike Harper /extend package.",
            "The orchestrator owns workflow state and policy. The local agent is only the workspace documentation actuator.",
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read before acting:",
            f"- {context_path}",
            "- docs/harper/IDEA.md when present",
            "- docs/harper/SPEC.md when present",
            "- docs/harper/PLAN.md",
            "- docs/harper/plan.json",
            "- docs/harper/lane-guides/*.md when present",
            "- docs/harper/TECH_CONSTRAINTS.yaml when present",
            *attachment_prompt_lines,
            *_render_canonical_parity_block("extend", "EXTEND"),
            "",
            "Mission:",
            "- Extend the current Harper plan by appending new requirements; /extend is a mutation/append phase, not a regeneration.",
            "- Existing IDEA.md, SPEC.md, PLAN.md, plan.json, and lane-guides are valid source inputs to preserve and update — read them, do not discard them.",
            "- Preserve existing consolidated REQs exactly; never rewrite, renumber, or delete them.",
            "- Always update PLAN.md and plan.json so they remain aligned, and always emit the EXTEND audit report.",
            "- Update IDEA.md only if the new requirement changes vision, target users, value/outcomes, out-of-scope, idea-level technology constraints, risks, assumptions, or success metrics (preserve the canonical IDEA schema).",
            "- Update SPEC.md only if the new REQs introduce new capability scope, domain terms, constraints, integrations, acceptance criteria, or user-visible behavior.",
            "- Update or create lane-guides only if new concern guidance is needed.",
            "- Return FULL file artifacts (complete updated content), never partial patches.",
            "",
            "Skills / capabilities discipline:",
            "- Treat selected skills, packs, and design profiles (from methodology context / .clike capabilities) as BINDING planning constraints, not decorative context.",
            "- Populate packs/skills/design_profiles on new plan.json REQs where applicable; never blanket-default to not_applicable when capabilities are selected; never invent fake capabilities.",
            "",
            "Allowed writes:",
            "- docs/harper/IDEA.md (conditional)",
            "- docs/harper/SPEC.md (conditional)",
            "- docs/harper/PLAN.md",
            "- docs/harper/plan.json",
            "- docs/harper/lane-guides/*.md (conditional)",
            "- docs/harper/EXTEND_*.md (mandatory audit report)",
            "",
            "Forbidden writes:",
            "- any other docs/harper path (including AGENT_* package files)",
            "- src/, test/, tests/",
            "- runs/kit/, runs/eval/, runs/gate/",
            "- .git/",
            "",
            "Append-only rules:",
            "- Do not regenerate the plan from scratch.",
            "- Do not modify existing REQ acceptance criteria.",
            "- Do not renumber existing REQs.",
            "- Do not change status/gate/promotion metadata of existing REQs.",
            "- Preserve the existing plan.json object shape and capability richness (packs/skills/design_profiles/implementation_directives/expected_source_roots/expected_test_roots/kit-eval-gate metadata).",
            "- Add new dependencies only for new REQs; dependencies must resolve to existing or newly added REQs.",
            "- If shared sections need updates, append minimal new entries only.",
            "",
            "Input:",
            f"- anchor_req: {anchor_req or '<auto-detect-last-req>'}",
            f"- explicit_req: {explicit_req or '<none>'}",
            f"- from_attachment: {from_attachment}",
            f"- raw_input: {raw_input or '<see chat/attachments/core context>'}",
            "",
            "EXTEND audit report (docs/harper/EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md) must include:",
            "- Command; Input Sources; Anchor; Explicit REQ-ID if provided; Added Requirements; Updated Files; Preserved Requirements;",
            "- Dependency Decisions; Capability/skills/packs/design-profile decisions;",
            "- IDEA.md updated yes/no and why; SPEC.md updated yes/no and why; PLAN.md updated yes/no; plan.json updated yes/no; lane-guides updated yes/no and why;",
            "- Validation performed; Risks / Follow-up.",
            "",
            "Before returning, validate: plan.json is valid JSON; every new REQ appears in PLAN.md and plan.json; every new REQ has acceptance criteria; new dependencies resolve; existing REQs preserved; no forbidden paths emitted.",
        ]
    )

    return _package_envelope(
        phase="extend",
        echo="Local agent extend package prepared for Harper plan extension",
        summary="local-agent-extend-package-prepared",
        extra_warnings=["extend_requires_harper_docs_mutation"],
        run_id=run_id,
        execution_policy=execution_policy,
        local_agent={
            "action": "local_agent_required",
            "package_id": f"{run_id}:SOLUTION:extend",
            "phase": "extend",
            "req_id": "SOLUTION",
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": _local_agent_invocation(local_executor, payload),
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "expected_outputs": context["output_contract"],
            "package_files": [
                _package_file(context_path, context_json, "application/json"),
                _package_file(prompt_path, prompt, "text/markdown"),
                # Current-run attachments materialized into the workspace so the
                # agent reads them from its cwd (no external-path approval).
                *attachment_package_files,
            ],
        },
    )
