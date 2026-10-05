"""Local-agent package for /kit.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from services.context_envelope import build_context_envelope
from services.methodologies.active_output_contract import build_active_output_contract
from utils.namespace_paths import (
    namespace_materialization_context,
)

from services.kit_repair import acceptance_first_code_rules, acceptance_stage_rules
from services.local_agent.common import (
    _bmad_expected_outputs,
    _build_related_reqs,
    _build_workspace_inspection_policy,
    _capability_manifest_for_agent_context,
    _companion_documents_from_core_blobs,
    _core_doc_reference,
    _dedupe_rules,
    _documents_from_core_blobs_prefix,
    _ensure_selected_capability_context,
    _extract_capability_manifest,
    _extract_plan_json,
    _extract_req_dependencies,
    _extract_req_from_plan,
    _kit_repair_context,
    _local_agent_invocation,
    _methodology_context_for_local_agent,
    _package_envelope,
    _package_file,
    _raise_if_selected_capabilities_missing_for_agent,
    _render_compact_local_agent_prompt,
    _req_capability_list,
    _resolve_local_executor,
    _runtime_ecosystem_for_req,
    _safe_text,
    _selected_capability_summary,
)
from services.local_agent.kit_contracts import (
    _build_capability_integrity,
    _build_file_requirements,
    _build_target_contract,
)
from services.phase_definitions import phase_text


def _text(key: str) -> list:
    """Static text of this module, kept in phases/kit/text.yaml (WP8.5)."""
    return list(phase_text("kit")[key])


def _render_agent_input_audit_md(
    *,
    req_id: str,
    target_contract: Dict[str, Any],
    file_requirements: Dict[str, Any],
    capability_integrity: Dict[str, Any],
    workspace_inspection_policy: Dict[str, Any],
) -> str:
    """
    Render a human‑readable audit of what the local agent received.
    Includes REQ summary, selected capabilities, capability integrity,
    required/recommended outputs, provider obligations, workspace inspection,
    and acceptance criteria.
    """
    lines: List[str] = [
        f"# Agent Input Audit — {req_id}",
        "",
        "## Target",
        f"- REQ: `{req_id}`",
        f"- Title: {target_contract.get('title') or ''}",
        f"- Lane: `{target_contract.get('lane')}`",
        f"- Domain: `{target_contract.get('domain')}`",
        f"- Runtime profile: `{target_contract.get('runtime_profile')}`",
        f"- Main module boundary: `{target_contract.get('main_module_boundary')}`",
        "",
        "## Selected Capabilities",
        f"- Packs: `{', '.join(target_contract.get('packs') or []) or 'none'}`",
        f"- Skills: `{', '.join(target_contract.get('skills') or []) or 'none'}`",
        f"- Design profiles: `{', '.join(target_contract.get('design_profiles') or []) or 'none'}`",
        "",
        "## Capability Integrity",
        f"- Discovered skills: `{capability_integrity['discovered_counts']['skills']}`",
        f"- Discovered packs: `{capability_integrity['discovered_counts']['packs']}`",
        f"- Discovered design profiles: `{capability_integrity['discovered_counts']['design_profiles']}`",
        f"- Missing selected skills: `{', '.join(capability_integrity['missing_selected_skills']) or 'none'}`",
        f"- Missing selected packs: `{', '.join(capability_integrity['missing_selected_packs']) or 'none'}`",
        f"- Missing selected design profiles: `{', '.join(capability_integrity['missing_selected_design_profiles']) or 'none'}`",
        f"- Blocking gap: `{capability_integrity['missing_any_selected_capability']}`",
        "",
        "## Required Candidate Outputs",
    ]
    for item in file_requirements.get("required_candidate_outputs") or []:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Recommended Candidate Outputs"])
    for item in file_requirements.get("recommended_candidate_outputs") or []:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Provider Obligations"])
    obligations = file_requirements.get("provider_obligations") or []
    if obligations:
        for item in obligations:
            lines.append(f"- {item}")
    else:
        lines.append("- No extra provider realism obligations declared.")
    lines.extend(
        [
            "",
            "## Workspace Inspection",
            f"- Canonical source roots: `{', '.join(workspace_inspection_policy.get('canonical_promoted_source_roots') or [])}`",
            f"- Canonical test roots: `{', '.join(workspace_inspection_policy.get('canonical_promoted_test_roots') or [])}`",
            f"- Dependency KIT roots: `{', '.join(workspace_inspection_policy.get('dependency_kit_roots') or []) or 'none'}`",
            "",
            "## Acceptance Criteria",
        ]
    )
    for item in target_contract.get("acceptance") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def _kit_stage(req_id: str, payload: Dict[str, Any], repair_context: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    """Which KIT the agent runs: the acceptance-first stages, an auto-eval repair or a full KIT."""
    kit_options = payload.get("kit") if isinstance(payload.get("kit"), dict) else {}
    phases = [str(p).strip().lower() for p in (kit_options.get("phases") or [])]
    if phases == ["acceptance"]:
        return "acceptance", "ACCEPTANCE STAGE — tests first", acceptance_stage_rules(req_id)
    if kit_options.get("acceptance_first"):
        locked = [f"runs/kit/{req_id}/test/", f"runs/kit/{req_id}/ci/LTC.json"]
        return "code_after_locked_acceptance", "ACCEPTANCE-FIRST — implement against the locked tests", [
            *acceptance_first_code_rules(req_id), f"Locked: {', '.join(locked)} (already in the workspace)."]
    auto_eval = repair_context.get("auto_eval") if isinstance(repair_context, dict) else None
    if isinstance(auto_eval, dict):
        return "repair", "AUTO-EVAL REPAIR (failed checks in repair_context.auto_eval)", list(auto_eval.get("rules") or [])
    return "kit", "", []


def build_kit_local_agent_package(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for base /kit.

    The extension is only allowed to:
    - write package files;
    - execute the configured local CLI;
    - collect stdout/stderr/exit code and candidate files;
    - send the result back to the orchestrator.
    """

    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"kit-local-{req_id}"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload, phase_hint="kit")

    plan_json = _extract_plan_json(payload)
    req = _extract_req_from_plan(payload, req_id)
    dependencies = _extract_req_dependencies(req)
    related_reqs = _build_related_reqs(req_id, req, plan_json)
    workspace_inspection_policy = _build_workspace_inspection_policy(req_id, req)
    target_contract = _build_target_contract(req_id, req)
    payload = _ensure_selected_capability_context(
        payload,
        req_id=req_id,
        target_contract=target_contract,
    )
    capability_manifest = _extract_capability_manifest(payload)
    capability_integrity = _build_capability_integrity(req, capability_manifest)
    file_requirements = _build_file_requirements(
        req_id,
        req,
        capability_integrity,
        payload,
    )

    standalone_capability_manifest = str(capability_manifest.get("content") or "")
    standalone_capability_index = str(capability_manifest.get("index_content") or "")
    standalone_selected_capability_context = str(capability_manifest.get("selected_context_content") or "")
    standalone_selected_capability_context_json = str(capability_manifest.get("selected_context_json_content") or "")
    context_capability_manifest = _capability_manifest_for_agent_context(req_id, capability_manifest)

    include_agent_input_audit = bool(
        payload.get("includeAgentInputAudit")
        or payload.get("debugAgentInputAudit")
        or payload.get("include_agent_input_audit")
    )

    agent_input_audit_json = ""
    agent_input_audit_md = ""

    if include_agent_input_audit:
        agent_input_audit = {
            "schema_version": "clike.agent_input_audit.v1",
            "req_id": req_id,
            "target_contract": target_contract,
            "file_requirements": file_requirements,
            "capability_integrity": capability_integrity,
            "workspace_inspection_policy": workspace_inspection_policy,
        }
        agent_input_audit_json = json.dumps(agent_input_audit, indent=2, ensure_ascii=False)
        agent_input_audit_md = _render_agent_input_audit_md(
            req_id=req_id,
            target_contract=target_contract,
            file_requirements=file_requirements,
            capability_integrity=capability_integrity,
            workspace_inspection_policy=workspace_inspection_policy,
        )

    bmad_companion_docs = _companion_documents_from_core_blobs(payload, "docs/harper/bmad/")
    ux_companion_docs = _companion_documents_from_core_blobs(payload, "docs/harper/ux/")
    req_companion_docs = _companion_documents_from_core_blobs(payload, f"runs/kit/{req_id}/docs/")
    lane_guide_docs = _documents_from_core_blobs_prefix(payload, "docs/harper/lane-guides")
    bmad_expected_outputs = _bmad_expected_outputs(
        req_id=req_id,
        methodology_context=methodology_context,
        phase="kit",
    )
    active_output_contract = build_active_output_contract(
        phase="kit",
        runner="local_agent",
        methodology_context=methodology_context,
        req_id=req_id,
    )
    selected_capabilities = _selected_capability_summary(req, capability_manifest)
    runtime_ecosystem = _runtime_ecosystem_for_req(req, payload)
    namespace_materialization = (
        dict(file_requirements.get("namespace_materialization") or {})
        if isinstance(file_requirements, dict)
        else {}
    ) or namespace_materialization_context(
        main_module_boundary=req.get("main_module_boundary"),
        ecosystem=runtime_ecosystem,
        req_id=req_id,
    )
    context_envelope = build_context_envelope(
        phase="kit",
        req_id=req_id,
        execution_mode="local_agent",
        core_blobs=payload.get("core_blobs") or {},
        methodology_context=methodology_context,
        active_output_contract=active_output_contract,
        namespace_materialization=namespace_materialization,
        require_bmad_core_blobs=True,
    )
    _raise_if_selected_capabilities_missing_for_agent(
        phase="kit",
        req_id=req_id,
        methodology_context=methodology_context,
        selected_capabilities=selected_capabilities,
        capability_manifest=capability_manifest,
        capability_integrity=capability_integrity,
        context_envelope=context_envelope,
    )
    repair_context = _kit_repair_context(req_id, payload)
    kit_stage, stage_title, stage_rules = _kit_stage(req_id, payload, repair_context)
    allowed_write_roots = [
        f"runs/kit/{req_id}/src",
        f"runs/kit/{req_id}/test",
        f"runs/kit/{req_id}/ci",
        f"runs/kit/{req_id}/docs",
    ]
    if kit_stage == "acceptance":
        allowed_write_roots = [root for root in allowed_write_roots if not root.endswith("/src")]

    forbidden_paths = [
        "src",
        "test",
        "tests",
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        ".git",
    ]

    local_runtime = payload.get("localRuntime") or {}
    if not isinstance(local_runtime, dict):
        local_runtime = {}

    tool_hints = local_runtime.get("tool_hints") or {}
    if not isinstance(tool_hints, dict):
        tool_hints = {}

    local_runtime = {
        "shell": str(local_runtime.get("shell") or "zsh"),
        "implementation_runtime_policy": str(
            local_runtime.get("implementation_runtime_policy")
            or "infer_from_project_contracts"
        ),
        "dependency_strategy": str(
            local_runtime.get("dependency_strategy")
            or "use_existing_project_scripts_or_report_blocked"
        ),
        "package_install_policy": str(
            local_runtime.get("package_install_policy")
            or "never_install_global_packages"
        ),
        "tool_hints": {
            "node": str(tool_hints.get("node") or "node"),
            "npm": str(tool_hints.get("npm") or "npm"),
            "python": str(tool_hints.get("python") or "python3"),
            "java": str(tool_hints.get("java") or "java"),
            "go": str(tool_hints.get("go") or "go"),
            "ruby": str(tool_hints.get("ruby") or "ruby"),
            "rust": str(tool_hints.get("rust") or "rustc"),
            "php": str(tool_hints.get("php") or "php"),
            "dotnet": str(tool_hints.get("dotnet") or "dotnet"),
            "kubectl": str(tool_hints.get("kubectl") or "kubectl"),

        },
    }
               
    context = {
        "schema_version": "clike.local_agent_execution_context.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "kit",
        "run_id": run_id,
        "req_id": req_id,
        "executor_hint": local_executor,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_cloud_only_when_not_local_agent_only",
        },
        "workflow_owner": "orchestrator",
        "extension_role": "local_actuator_only",
        "active_output_contract": active_output_contract,
        "context_envelope": context_envelope,
        "selected_clike_capabilities": selected_capabilities,
        "selected_clike_packs": selected_capabilities["selected_packs"],
        "selected_clike_skills": selected_capabilities["selected_skills"],
        "selected_clike_design_profiles": selected_capabilities["selected_design_profiles"],
        "namespace_materialization": namespace_materialization,
        **({"methodology_context": methodology_context} if methodology_context else {}),
        **({"selected_skill_references": methodology_context.get("selected_skill_references") or []} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        **({"selected_skill_context": methodology_context.get("selected_skill_context") or {}} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        **({"skill_reference_policy": methodology_context.get("skill_reference_policy") or {}} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        **({"discovered_companion_artifact_inventory": methodology_context.get("discovered_companion_artifacts") or []} if methodology_context and methodology_context.get("discovered_companion_artifacts") else {}),
        "local_runtime": local_runtime,
        "req": req,
        "current_req": {
            "req_id": req_id,
            "req": req,
            "acceptance_criteria": list(req.get("acceptance") or []),
            "dependencies": dependencies,
            "related_reqs": related_reqs,
        },
        "plan_slice": {
            "plan_json_path": "docs/harper/plan.json",
            "target_req": req,
            "dependencies": dependencies,
            "related_reqs": related_reqs,
        },
        "source_documents": {
            "idea": _core_doc_reference(payload, "docs/harper/IDEA.md", "IDEA.md", 2500),
            "spec": _core_doc_reference(payload, "docs/harper/SPEC.md", "SPEC.md", 3500),
            "plan": _core_doc_reference(payload, "docs/harper/PLAN.md", "PLAN.md", 3500),
            "plan_json": {
                "path": "docs/harper/plan.json",
                "present": bool(plan_json),
                "relevant_slice": {
                    "target_req": req,
                    "dependencies": dependencies,
                    "related_reqs": related_reqs,
                },
            },
            "tech_constraints": _core_doc_reference(
                payload,
                "docs/harper/TECH_CONSTRAINTS.yaml",
                "TECH_CONSTRAINTS.yaml",
                6000,
            ),
            "lane_guides": {
                "root": "docs/harper/lane-guides",
                "present": bool(lane_guide_docs),
                "documents": lane_guide_docs,
            },
        },
        "companion_documents": {
            "bmad": {
                "root": "docs/harper/bmad",
                "documents": bmad_companion_docs,
            },
            "ux": {
                "root": "docs/harper/ux",
                "documents": ux_companion_docs,
            },
            "req_docs": {
                "root": f"runs/kit/{req_id}/docs",
                "documents": req_companion_docs,
            },
        },
        "capability_context": {
            "lane": req.get("lane"),
            "domain": req.get("domain"),
            "runtime_profile": req.get("runtime_profile"),
            "packs": _req_capability_list(req, "packs", nested_key="packs"),
            "skills": _req_capability_list(req, "skills", nested_key="skills"),
            "design_profiles": _req_capability_list(req, "design_profiles", "designProfiles", nested_key="design_profiles"),
            "gate_expectations": req.get("gate_expectations") or [],
            "main_module_boundary": req.get("main_module_boundary"),
            "future_compatibility_notes": req.get("future_compatibility_notes") or [],
            "manifest": context_capability_manifest,
            "integrity": capability_integrity,

        },
        "target_contract": target_contract,
        "file_requirements": file_requirements,
        "candidate_output_roots": {
            "root": f"runs/kit/{req_id}",
            "src": f"runs/kit/{req_id}/src",
            "test": f"runs/kit/{req_id}/test",
            "ci": f"runs/kit/{req_id}/ci",
            "docs": f"runs/kit/{req_id}/docs",
        },
        "candidate_contract_paths": {
            "target_contract": f"runs/kit/{req_id}/docs/TARGET_CONTRACT.json",
            "file_requirements": f"runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json",
        },
        "repair_context": repair_context,
        "project": {
            "project_id": payload.get("project_id"),
            "project_name": payload.get("project_name"),
            "doc_root": payload.get("docRoot") or "docs/harper",
            "workspace": payload.get("workspace") or {},
        },
        "inputs": {
            "idea_md_path": "docs/harper/IDEA.md",
            "spec_md_path": "docs/harper/SPEC.md",
            "plan_md_path": "docs/harper/PLAN.md",
            "plan_json_path": "docs/harper/plan.json",
            "tech_constraints_path": "docs/harper/TECH_CONSTRAINTS.yaml",
            "lane_guides_path": "docs/harper/lane-guides",
            "bmad_companion_root": "docs/harper/bmad",
            "ux_companion_root": "docs/harper/ux",
        },
        "workspace_inspection_policy": workspace_inspection_policy,
        "repository_analysis_required": {
            "must_read_plan": True,
            "must_read_plan_json": True,
            "must_identify_target_req_dependencies": True,
            "must_inspect_dependency_kits": True,
            "must_inspect_canonical_src": True,
            "must_inspect_canonical_tests": True,
            "dependency_req_ids": workspace_inspection_policy["dependency_req_ids"],
            "dependency_kit_roots": workspace_inspection_policy["dependency_kit_roots"],
            "canonical_source_roots": workspace_inspection_policy["canonical_promoted_source_roots"],
            "canonical_test_roots": workspace_inspection_policy["canonical_promoted_test_roots"],
            "promoted_source_roots_read_only": workspace_inspection_policy["canonical_promoted_source_roots"],
            "promoted_test_roots_read_only": workspace_inspection_policy["canonical_promoted_test_roots"],
            "target_candidate_root": workspace_inspection_policy["target_candidate_root"],
            "purpose": (
                "Generate candidate code that is directly promotable and consistent "
                "with dependency KITs and canonical promoted code."
            ),
        },
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "expected_outputs": {
            "required": [
                f"runs/kit/{req_id}/ci/LTC.json",
                f"runs/kit/{req_id}/ci/HOWTO.md",
                f"runs/kit/{req_id}/ci/<ecosystem-native-eval-manifest>",
                f"runs/kit/{req_id}/src/<execution-area>/<ecosystem-native-runtime-manifest> when the REQ creates or updates a runnable execution area",
            ],
            "recommended": [
                f"runs/kit/{req_id}/ci/package.json for Node/npm KITs when source/tests need npm scripts or dependencies",
                f"runs/kit/{req_id}/ci/requirements.txt only for Python KITs",
                f"runs/kit/{req_id}/ci/pom.xml only for Java KITs",
                f"runs/kit/{req_id}/ci/package.json only for Node KITs",
                
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
            **({"bmad": bmad_expected_outputs} if bmad_expected_outputs else {}),
        },
        "hard_rules": _text("package.hard_rules"),
        **({"kit_stage": {"stage": kit_stage, "rules": stage_rules}} if stage_rules else {}),
    }

    context["hard_rules"] = _dedupe_rules([*stage_rules, *(context.get("hard_rules") or [])])
    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    context_path = f"runs/kit/{req_id}/docs/AGENT_EXECUTION_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_PROMPT.md"
    prompt = _render_compact_local_agent_prompt(
        phase="kit",
        req_id=req_id,
        context_path=context_path,
        methodology_context=methodology_context,
        active_output_contract=active_output_contract,
        selected_capabilities=selected_capabilities,
        namespace_materialization=namespace_materialization,
        stage_rules=stage_rules,
        stage_title=stage_title,
    )

    return _package_envelope(
        phase="kit",
        echo=f"Local agent execution package prepared for {req_id}",
        summary="local-agent-package-prepared",
        extra_warnings=[],
        run_id=run_id,
        execution_policy=execution_policy,
        local_agent={
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:kit",
            "phase": "kit",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": _local_agent_invocation(local_executor, payload),
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "active_output_contract": active_output_contract,
            "expected_outputs": context["expected_outputs"],
            "package_files": [
                _package_file(context_path, context_json, "application/json"),
                _package_file(prompt_path, prompt, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/TARGET_CONTRACT.json", json.dumps(target_contract, indent=2, ensure_ascii=False), "application/json"),
                _package_file(f"runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json", json.dumps(file_requirements, indent=2, ensure_ascii=False), "application/json"),
                (
                    [
                        _package_file(f"runs/kit/{req_id}/docs/AGENT_INPUT_AUDIT.json", agent_input_audit_json, "application/json"),
                        _package_file(f"runs/kit/{req_id}/docs/AGENT_INPUT_AUDIT.md", agent_input_audit_md, "text/markdown"),
                    ]
                    if include_agent_input_audit
                    else []
                ),

                _package_file(f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_MANIFEST.md", standalone_capability_manifest, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json", standalone_capability_index, "application/json"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md", standalone_selected_capability_context, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json", standalone_selected_capability_context_json, "application/json"),
            ],
        },
    )
