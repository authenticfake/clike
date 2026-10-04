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
from services.phase_definitions import phase_text


def _text(key: str) -> list:
    """Static text of this module, kept in phases/extend/text.yaml (WP8.5)."""
    return list(phase_text("extend")[key])


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
            *_text("package.lines"),
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read before acting:",
            f"- {context_path}",
            *_text("package.lines.2"),
            *attachment_prompt_lines,
            *_render_canonical_parity_block("extend", "EXTEND"),
            *_text("package.lines.3"),
            f"- anchor_req: {anchor_req or '<auto-detect-last-req>'}",
            f"- explicit_req: {explicit_req or '<none>'}",
            f"- from_attachment: {from_attachment}",
            f"- raw_input: {raw_input or '<see chat/attachments/core context>'}",
            *_text("package.lines.4"),
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
