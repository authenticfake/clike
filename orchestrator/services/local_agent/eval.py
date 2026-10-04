"""Local-agent package for /eval (pre-pass before the canonical EvalRunner).

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict
from services.context_envelope import build_context_envelope
from services.methodologies.active_output_contract import build_active_output_contract
from utils.namespace_paths import (
    namespace_materialization_context,
)

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
    _local_agent_invocation,
    _methodology_context_for_local_agent,
    _package_envelope,
    _package_file,
    _parse_json_core_blob,
    _previous_eval_report_references,
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
    _build_recommended_outputs,
    _build_target_contract,
)


def build_eval_local_agent_package(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for /eval hardening.

    The local agent is not the judge.
    It must execute the REQ-local LTC/HOWTO checks when possible, repair
    deterministic candidate failures under runs/kit/<REQ-ID>/, rerun the
    repaired checks, and leave canonical CLike EvalRunner as the final judge.
    """
    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"eval-local-{req_id}"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload, phase_hint="eval")

    plan_json = _extract_plan_json(payload)
    req = _extract_req_from_plan(payload, req_id)
    dependencies = _extract_req_dependencies(req)
    related_reqs = _build_related_reqs(req_id, req, plan_json)
    workspace_inspection_policy = _build_workspace_inspection_policy(req_id, req)
    target_contract = _parse_json_core_blob(payload, "TARGET_CONTRACT.json") or _build_target_contract(req_id, req)
    payload = _ensure_selected_capability_context(
        payload,
        req_id=req_id,
        target_contract=target_contract,
    )
    capability_manifest = _extract_capability_manifest(payload)
    capability_integrity = _build_capability_integrity(req, capability_manifest)
    file_requirements = _parse_json_core_blob(payload, "FILE_REQUIREMENTS.json")
    bmad_companion_docs = _companion_documents_from_core_blobs(payload, "docs/harper/bmad/")
    ux_companion_docs = _companion_documents_from_core_blobs(payload, "docs/harper/ux/")
    req_companion_docs = _companion_documents_from_core_blobs(payload, f"runs/kit/{req_id}/docs/")
    lane_guide_docs = _documents_from_core_blobs_prefix(payload, "docs/harper/lane-guides")
    bmad_expected_outputs = _bmad_expected_outputs(
        req_id=req_id,
        methodology_context=methodology_context,
        phase="eval",
    )
    active_output_contract = build_active_output_contract(
        phase="eval",
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
        phase="eval",
        req_id=req_id,
        execution_mode="local_agent",
        core_blobs=payload.get("core_blobs") or {},
        methodology_context=methodology_context,
        active_output_contract=active_output_contract,
        namespace_materialization=namespace_materialization,
        require_bmad_core_blobs=True,
    )
    _raise_if_selected_capabilities_missing_for_agent(
        phase="eval",
        req_id=req_id,
        methodology_context=methodology_context,
        selected_capabilities=selected_capabilities,
        capability_manifest=capability_manifest,
        capability_integrity=capability_integrity,
        context_envelope=context_envelope,
    )

    standalone_capability_manifest = str(capability_manifest.get("content") or "")
    standalone_capability_index = str(capability_manifest.get("index_content") or "")
    standalone_selected_capability_context = str(capability_manifest.get("selected_context_content") or "")
    standalone_selected_capability_context_json = str(capability_manifest.get("selected_context_json_content") or "")
    context_capability_manifest = _capability_manifest_for_agent_context(req_id, capability_manifest)

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
            or "infer_from_ltc_howto_and_project_contracts"
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
    allowed_write_roots = [
        f"runs/kit/{req_id}/src",
        f"runs/kit/{req_id}/test",
        f"runs/kit/{req_id}/ci",
        f"runs/kit/{req_id}/docs",
        f"runs/kit/{req_id}/reports",
    ]

    read_only_roots = [
        "docs/harper",
        "src",
        "test",
        "tests",
        "runs/kit",
    ]

    forbidden_paths = [
        "src",
        "test",
        "tests",
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        ".git",
    ]

    context = {
        "schema_version": "clike.local_agent_eval_context.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "eval",
        "run_id": run_id,
        "req_id": req_id,
        "executor_hint": local_executor,
        "workflow_owner": "orchestrator",
        "extension_role": "local_actuator_only",
        "agent_role": "pre_eval_hardener_only",
        "canonical_eval_owner": "clike",
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
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_canonical_eval_only_when_not_local_agent_only",
        },
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
            "lane_guides_path": "docs/harper/lane-guides",
            "tech_constraints_path": "docs/harper/TECH_CONSTRAINTS.yaml",
            "bmad_companion_root": "docs/harper/bmad",
            "ux_companion_root": "docs/harper/ux",
            "ltc_json_path": f"runs/kit/{req_id}/ci/LTC.json",
            "howto_md_path": f"runs/kit/{req_id}/ci/HOWTO.md",
            "kit_notes_path": f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            "readme_path": f"runs/kit/{req_id}/docs/README_{req_id}.md",
        },
        "workspace_inspection_policy": workspace_inspection_policy,
        "candidate_roots": {
            "root": f"runs/kit/{req_id}",
            "src": f"runs/kit/{req_id}/src",
            "test": f"runs/kit/{req_id}/test",
            "ci": f"runs/kit/{req_id}/ci",
            "docs": f"runs/kit/{req_id}/docs",
            "reports": f"runs/kit/{req_id}/reports",
        },
        "candidate_eval_inputs": {
            "ltc_path": f"runs/kit/{req_id}/ci/LTC.json",
            "howto_path": f"runs/kit/{req_id}/ci/HOWTO.md",
            "target_contract_paths": [
                f"runs/kit/{req_id}/ci/TARGET_CONTRACT.json",
                f"runs/kit/{req_id}/docs/TARGET_CONTRACT.json",
            ],
            "file_requirements_paths": [
                f"runs/kit/{req_id}/ci/FILE_REQUIREMENTS.json",
                f"runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json",
            ],
            "target_contract": target_contract,
            "file_requirements": file_requirements,
        },
        "previous_eval_reports": _previous_eval_report_references(req_id),
        "repair_intent": {
            "requested": bool((payload.get("kit") or {}).get("repair") or (payload.get("eval") or {}).get("repair")),
            "source": "kit.repair_or_eval.repair",
        },
        "bmad_developer_docs": {
            "root": f"runs/kit/{req_id}/docs",
            "expected_paths": [
                f"runs/kit/{req_id}/docs/BMAD_DEV_STORY.md",
                f"runs/kit/{req_id}/docs/IMPLEMENTATION_NOTES.md",
                f"runs/kit/{req_id}/docs/SELF_REVIEW.md",
                f"runs/kit/{req_id}/docs/RUNBOOK.md",
            ],
            "documents": [
                item
                for item in req_companion_docs
                if item.get("path") in {
                    f"runs/kit/{req_id}/docs/BMAD_DEV_STORY.md",
                    f"runs/kit/{req_id}/docs/IMPLEMENTATION_NOTES.md",
                    f"runs/kit/{req_id}/docs/SELF_REVIEW.md",
                    f"runs/kit/{req_id}/docs/RUNBOOK.md",
                }
            ],
            "read_as_repair_context": True,
        },
        "bmad_qa_advisory_output_targets": bmad_expected_outputs,
        "local_repair_policy": {
            "scope": "candidate_owned_files_only",
            "allowed_write_roots": allowed_write_roots,
            "notes_output_path": f"runs/kit/{req_id}/reports/BMAD_EVAL_REPAIR_NOTES.md",
            "canonical_eval_remains_required": True,
            "environment_blockers_require_exact_evidence": True,
            "do_not_weaken": [
                "tests",
                "LTC.json",
                "HOWTO.md",
                "typecheck",
                "lint",
                "security checks",
                "gate policy",
            ],
        },
        "repository_analysis_required": {
            "must_read_plan": True,
            "must_read_plan_json": True,
            "must_identify_target_req_dependencies": True,
            "must_inspect_dependency_kits": True,
            "must_inspect_candidate_src": True,
            "must_inspect_candidate_tests": True,
            "must_inspect_candidate_ci": True,
            "must_inspect_canonical_src": True,
            "must_inspect_canonical_tests": True,
            "dependency_req_ids": workspace_inspection_policy["dependency_req_ids"],
            "dependency_kit_roots": workspace_inspection_policy["dependency_kit_roots"],
            "candidate_source_roots": [workspace_inspection_policy["target_candidate_source_root"]],
            "candidate_test_roots": [workspace_inspection_policy["target_candidate_test_root"]],
            "candidate_ci_roots": [workspace_inspection_policy["target_candidate_ci_root"]],
            "canonical_source_roots": workspace_inspection_policy["canonical_promoted_source_roots"],
            "canonical_test_roots": workspace_inspection_policy["canonical_promoted_test_roots"],
            "promoted_source_roots_read_only": workspace_inspection_policy["canonical_promoted_source_roots"],
            "promoted_test_roots_read_only": workspace_inspection_policy["canonical_promoted_test_roots"],
            "dependency_kit_roots_read_only": workspace_inspection_policy["dependency_kit_roots"],
            "target_candidate_root": workspace_inspection_policy["target_candidate_root"],
            "purpose": (
                "Harden candidate code and tests so canonical CLike eval can execute "
                "against promotable artifacts consistent with dependency KITs and canonical code."
            ),
        },
        "allowed_read_roots": read_only_roots,
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "expected_eval_inputs": {
            "required": [
                f"runs/kit/{req_id}/ci/LTC.json",
                f"runs/kit/{req_id}/ci/HOWTO.md",
                f"runs/kit/{req_id}/src",
                f"runs/kit/{req_id}/test",
            ],
            "recommended": [
                *_build_recommended_outputs(req_id, req, payload),
                f"runs/kit/{req_id}/reports/BMAD_EVAL_REPAIR_NOTES.md",
            ],
            **({"bmad": bmad_expected_outputs} if bmad_expected_outputs else {}),
        },
        "eval_hardening_policy": {
            "enabled": True,
            "role": "pre_canonical_eval_repair",
            "must_execute_ltc_cases": True,
            "must_repair_deterministic_failures": True,
            "must_rerun_failed_or_repaired_checks": True,
            "max_repair_cycles_inside_agent": 3,
            "allowed_failure_after_repair": [
                "environment_blocked",
                "missing_external_infrastructure",
                "explicit_unresolved_gap_with_evidence"
            ],
            "forbidden_repairs": [
                "removing meaningful assertions",
                "weakening gate_policy",
                "marking code failures as environment-blocked",
                "disabling typecheck globally",
                "removing tests to pass eval",
                "creating unconditional secondary overlays",
                "modifying canonical src/test/tests roots"
            ],
            "typescript_checkjs_guidance": {
                "applies_when": [
                    "TS2339",
                    "TS18046",
                    "catch variable is unknown",
                    "dynamic Error.code access",
                    "JSDoc checkJs validation failures"
                ],
                "required_behavior": [
                    "repair candidate tests or CI scripts with narrow JSDoc casts or local helper guards",
                    "preserve meaningful assertions",
                    "do not relax tsconfig to hide source/test failures",
                    "do not remove checkJs from product source",
                    "do not use @ts-nocheck on candidate source or tests"
                ],
                "allowed_exception": (
                    "@ts-nocheck is allowed only for generated CI utility scripts when the failure is "
                    "inside the validator script itself and the script is already syntax-checked separately."
                )
            },
            "success_condition": "After repair, rerun the same LTC/HOWTO checks that failed or were modified. If they pass, report the commands and files changed. If they still fail with candidate-owned diagnostics and repair cycles remain, continue focused repair. If repair cycles are exhausted, report the exact unresolved file:line diagnostics without hiding them."
        },
        "allowed_test_doubles_policy": {
            "allowed": True,
            "scope": "tests_only",
            "allowed_for": [
                "external infrastructure boundaries",
                "object storage adapters",
                "queue adapters",
                "event transport adapters",
                "secret providers",
                "identity providers",
                "observability sinks",
                "network clients outside this candidate slice",
            ],
            "forbidden_for": [
                "business logic under test",
                "domain rules",
                "state transition rules",
                "validation rules",
                "public contracts being evaluated",
            ],
            "rule": (
                "Mocks and stubs are allowed only for external infrastructure boundaries "
                "and only inside candidate test files. They must not hide missing business logic."
            ),
        },
        "hard_rules": [
            "This is an eval hardening pass, not the canonical eval judge.",
            "For typecheck failures where tests access fields that are missing on one variant of a union response, do not silence the checker with broad casts. First decide whether the field is part of the stable public contract. If yes, repair the producer/service response so every success variant exposes the stable field. If no, repair the test with explicit narrowing before accessing variant-specific fields.",
            "For workflow orchestration responses, fields such as workflowRun, job, idempotency, artifacts, and trace must have a stable documented success contract when acceptance criteria require trace continuity, idempotency reuse, and job/artifact linkage. Prefer repairing the producer shape over weakening tests when downstream REQs depend on those fields.",
            "For caught errors typed as unknown, repair with a narrow helper or typed error adapter and preserve assertions on classification, retryable, status/statusCode, and domain failure categories.",
            "For Node/JavaScript checkJs failures inside assert.throws() or assert.rejects() callbacks, do not weaken the test and do not cast before validation. First assert `error instanceof ExpectedError`, then add `const typedError = /** @type {ExpectedError} */ (error);` and access custom fields such as `issues`, `code`, `classification`, `retryable`, `statusCode`, or `metadata` through the typed variable.",
            "When a typecheck diagnostic reports exact candidate-owned file:line locations, those diagnostics are the repair queue. Patch the listed files and rerun the same command until it passes or max_repair_cycles_inside_agent is exhausted.",
            "Do not stop after partially reducing diagnostics when the same blocking command still fails on candidate-owned files and repair cycles remain.",
            "Before returning, execute the REQ-local LTC/HOWTO checks when possible.",
            "If a check fails for deterministic candidate code, test, or CI reasons, repair the smallest related files under allowed_write_roots.",
            "After a repair, rerun the failed or modified checks once and record the commands and outcomes.",
            "Run or inspect LTC/HOWTO checks when possible, identify the first deterministic failure, and repair only candidate-owned files under allowed_write_roots.",
            "Do not mark candidate code failures as environment-blocked. Environment blockers require exact evidence such as missing toolchain, network, registry, filesystem, sandbox, or policy failure.",
            "Rerun the same failing command after repair and produce concise evidence useful for canonical EvalRunner.",
            f"Write a structured advisory or repair summary to runs/kit/{req_id}/reports/BMAD_EVAL_REPAIR_NOTES.md when BMAD methodology context is present or when repair guidance is useful.",
            "After this hardening pass, CLike canonical /eval must still run and decide pass/fail.",
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
            "Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.",
            "Do not commit, branch, push, tag, or open pull requests.",
            "Respect capability_context from AGENT_EVAL_CONTEXT.json: lane, domain, runtime_profile, packs, skills, design_profiles, gate_expectations, main_module_boundary, future_compatibility_notes, manifest content, and capability index content when available.",
            "Patch operations are allowed only under allowed_write_roots.",
            "Do not create or modify files outside runs/kit/<REQ-ID>/ for this phase.",
            "Do not install packages globally or into the system runtime.",
            "Do not infer the application implementation language from local_runtime.tool_hints.",
            "Infer the implementation runtime from SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, and repository evidence.",
            "Use local_runtime.tool_hints only as optional command hints after the implementation runtime is known.",
            "If package.json and npm scripts are present, prefer repository-native npm scripts for checks.",
            "If dependency installation is unavailable, report checks as environment-blocked and run repository-native smoke checks.",
            "Never install undeclared packages; only use dependencies declared by the project or the generated REQ-local validation contract.",
            "Before changing code, read docs/harper/PLAN.md and docs/harper/plan.json to identify target REQ dependencies.",
            "Before changing code, inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when they exist.",
            "Before changing code, inspect candidate source and test roots for this REQ.",
            "Before changing tests, inspect canonical promoted test roots under test/ and tests/ when they exist.",
            "Before changing code, inspect canonical promoted source roots under src/ when they exist.",
            "Generated or repaired code must be immediately promotable into canonical src/test roots without changing public contracts unexpectedly.",
            "For typed or statically checked runtimes, if EVAL/typecheck fails because candidate source, tests, or CI scripts access fields on generic object shapes such as {}, object, unknown, Any, untyped dictionaries, or Readonly<{}>, repair the candidate file by preserving an explicit language-native shape at the producer/helper boundary.",
            "When repairing schema normalization, payload validation, adapter response mapping, or immutable/frozen object creation, prefer a small local DTO/typedef/interface/type alias/dataclass/record/struct return shape over downstream casts scattered at each field access.",
            "Preserve runtime behavior and public contracts. Do not remove fields, remove assertions, disable type checking, relax compiler/linter settings, or convert the whole module to untyped code.",
            "Treat generic-object field-access failures as deterministic repairable candidate defects, not as environment-blocked checks.",
            "Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical src/test roots.",
            "Reuse dependency KIT contracts and canonical source contracts whenever they exist.",
            "If tests are insufficient, extend tests under runs/kit/<REQ-ID>/test only.",
            "Mocks/stubs are allowed only for external infrastructure boundaries and only inside candidate tests.",
            "Do not mock the business logic under test.",
            "If a dependency KIT or canonical source root is missing, explicitly report it as an implementation assumption or gap.",
            "Produce repository-aware, dependency-aware, promotable candidate code and tests.",
            "Prefer the smallest safe repair only when the implementation already covers the REQ correctly; otherwise complete the implementation so it fully satisfies the REQ acceptance criteria with readable, repository-aligned code, structure, and tests.",
        ],
    }

    context["hard_rules"] = _dedupe_rules(context.get("hard_rules") or [])
    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    context_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_PROMPT.md"
    prompt = _render_compact_local_agent_prompt(
        phase="eval",
        req_id=req_id,
        context_path=context_path,
        methodology_context=methodology_context,
        active_output_contract=active_output_contract,
        selected_capabilities=selected_capabilities,
        namespace_materialization=namespace_materialization,
    )

    return _package_envelope(
        phase="eval",
        echo=f"Local agent eval pre-pass package prepared for {req_id}",
        summary="local-agent-eval-package-prepared",
        extra_warnings=["canonical_eval_still_required"],
        run_id=run_id,
        execution_policy=execution_policy,
        local_agent={
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:eval",
            "phase": "eval",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": _local_agent_invocation(local_executor, payload),
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "active_output_contract": active_output_contract,
            "expected_outputs": {
                "required": [
                    f"runs/kit/{req_id}/ci/LTC.json",
                    f"runs/kit/{req_id}/ci/HOWTO.md",
                ],
                "recommended": [
                    f"runs/kit/{req_id}/reports",
                    f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
                    f"runs/kit/{req_id}/docs/README_{req_id}.md",
                ],
                **({"bmad": bmad_expected_outputs} if bmad_expected_outputs else {}),
            },
            "package_files": [
                _package_file(context_path, context_json, "application/json"),
                _package_file(prompt_path, prompt, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_MANIFEST.md", standalone_capability_manifest, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json", standalone_capability_index, "application/json"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md", standalone_selected_capability_context, "text/markdown"),
                _package_file(f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json", standalone_selected_capability_context_json, "application/json"),
            ],
        },
    )
