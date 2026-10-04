"""Local-agent package for /finalize.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict
from services.context_envelope import build_context_envelope

from services.local_agent.common import (
    _extract_capability_manifest,
    _local_agent_invocation,
    _methodology_context_for_local_agent,
    _package_envelope,
    _package_file,
    _render_methodology_prompt_block,
    _resolve_local_executor,
    _safe_text,
)
from services.local_agent.finalize_profiles import (
    _build_finalize_write_policy,
    _detect_finalize_cloud_provisioning_profile,
    _detect_finalize_infra_profile,
    _detect_finalize_runtime_service_profile,
)
from services.phase_definitions import phase_text


def _text(key: str) -> list:
    """Static text of this module, kept in phases/finalize/text.yaml (WP8.5)."""
    return list(phase_text("finalize")[key])


def build_finalize_local_agent_package(
    *,
    payload: Dict[str, Any],
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for /finalize.

    /finalize is solution-scoped, not REQ-scoped. The local agent may patch the
    real workspace only inside explicit solution write roots, with reuse-first
    and language-agnostic constraints.
    """
    run_id = _safe_text(payload.get("runId")) or "finalize-local"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload, phase_hint="finalize")

    capability_manifest = _extract_capability_manifest(payload)

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

    finalize_write_policy = _build_finalize_write_policy(payload)
    infra_profile = _detect_finalize_infra_profile(payload)
    runtime_service_profile = _detect_finalize_runtime_service_profile(payload)
    cloud_provisioning_profile = _detect_finalize_cloud_provisioning_profile(
        payload,
        infra_profile,
    )
    allowed_write_roots = finalize_write_policy["allowed_write_roots"]
    forbidden_paths = finalize_write_policy["forbidden_paths"]

    final_outputs = {
        "required_common": _text("package.required_common"),
        "required_scripts_when_runnable_code_exists": _text("package.required_scripts_when_runnable_code_exists"),
        "required_scripts_when_infra_profile_detected": infra_profile["safe_required_outputs"],
        "required_scripts_when_runtime_services_detected": [
            "scripts/check_runtime_services.sh",
            "scripts/check_runtime_services.ps1",
        ] if runtime_service_profile["services_detected"] else [],
        "required_scripts_when_cloud_detected": cloud_provisioning_profile[
            "required_outputs_when_cloud_detected"
        ],
        "conditional_solution_artifacts": _text("package.conditional_solution_artifacts"),
    }

    readme_release_contract = {
        "schema_version": "clike.finalize_readme_release_contract.v1",
        "purpose": (
            "Make local-agent /finalize produce the same polished, release-grade README.md style "
            "as the cloud finalize path, while keeping every claim evidence-based."
        ),
        "visual_style": _text("package.visual_style"),
        "badge_policy": {
            "required": True,
            "style": "shields.io markdown image badges",
            "required_badges": [
                "status",
                "Clike",
                "Harper phase",
                "eval",
                "gate",
                "runtime",
            ],
            "evidence_rules": _text("package.evidence_rules"),
            "examples": _text("package.examples"),
        },
        "required_readme_sections": _text("package.required_readme_sections"),
        "content_rules": _text("package.content_rules"),
        "recommended_readme_skeleton": _text("package.recommended_readme_skeleton"),
    }

    finalize_contract = {
        "schema_version": "clike.finalize_contract.v1",
        "phase": "finalize",
        "scope": "solution",
        "language_agnostic": True,
        "reuse_policy": {
            "reuse_before_create": True,
            "patch_before_replace": True,
            "complete_before_regenerate": True,
            "wire_existing_components_before_creating_new_ones": True,
            "no_massive_regeneration": True,
            "no_unnecessary_refactor": True,
        },
        "cloud_agent_compatibility": {
            "shared_final_artifact_contract": True,
            "cloud_finalize_role": "documentation_finalize_and_architecture_reasoning",
            "local_agent_finalize_role": "workspace_solution_integration_and_runnability_hardening",
            "no_fake_success": True,
        },
        "readme_merge_policy": {
            "required": True,
            "sources": [
                "README.md when present",
                "docs/harper/IDEA.md when present",
                "docs/harper/SPEC.md when present",
                "docs/harper/PLAN.md when present",
            ],
            "policy": (
                "README.md must be the final human-facing project overview. It must preserve useful existing README content "
                "and merge it with IDEA/SPEC/PLAN facts: vision, scope, architecture, runtime, configuration, local run, "
                "infra/deploy readiness, checks, and known gaps. Do not overwrite useful README content blindly."
            ),
        },
        "readme_release_contract": readme_release_contract,
        "env_completeness_policy": {
            "required": True,
            "policy": (
                ".env.example or ecosystem-native equivalent must include every runtime, auth, database, broker, cache, "
                "object storage, secret manager, cloud, and deployment variable required by the final solution. Values must be "
                "safe placeholders only. Missing real values must be documented as operator-provided configuration."
            ),
            "examples_only": _text("package.examples_only"),
        },
        "source_completion_policy": {
            "enabled": True,
            "policy": (
                "Finalize may patch source files under allowed_write_roots when required to make the final solution coherent, "
                "runnable, configurable, or boundary-complete. This includes wiring real DB/auth/service boundaries, settings/env loading, "
                "composition roots, runtime manifests, and local run scripts. Changes must be minimal, repository-aware, evidence-based, "
                "and driven by TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, manifests, and repository structure. Finalize is a runnable-solution "
                "hardening step: when executable backend/frontend/worker/CLI/service areas are evidenced, it must make the evidenced canonical "
                "entrypoints and launchers runnable instead of producing documentation-only readiness."
            ),
            "runnability_rules": _text("package.runnability_rules"),
            "must_not": _text("package.must_not"),
        },
         "finalize_runnability_policy": {
            "enabled": True,
            "goal": (
                "After /finalize, the solution should be locally runnable as far as repository evidence allows. "
                "Local runnability means stack-native canonical launchers exist, evidenced entrypoints do not crash, documented run scripts exist, "
                "database configuration is explicit when a database is evidenced, and missing external services fail with controlled, truthful messages."
            ),
            "runtime_detection_rule": (
                "TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, manifests, scripts, and repository structure decide language, framework, "
                "entrypoints, launchers, package managers, DB tooling, auth tooling, and deployment tooling. CLike must be constraint-driven, not convention-driven."
            ),
            "canonical_runtime_rule": (
                "Patch the evidenced canonical composition root and launcher for each execution area. Create a new runtime only when no evidenced canonical runtime exists, "
                "and only using the stack-native conventions of the detected technology profile."
            ),
            "database_rule": (
                "When a database service is evidenced, the final solution must include a source-level DB boundary/configuration seam and "
                "a local database configuration path. Missing live credentials may block runtime service checks, but must not justify replacing "
                "the database with implicit in-memory persistence."
            ),
            "auth_rule": (
                "When auth is evidenced, the final solution must include an auth configuration seam. Local/dev login bypass is allowed only "
                "when explicit in configuration and documented as non-production."
            ),
            "business_router_rule": (
                "When backend routers/controllers/handlers and services are evidenced, finalize should mount them through the canonical composition root. "
                "Unavailable dependencies should produce controlled configuration-required errors instead of import-time crashes."
            ),
            "forbidden_patterns": _text("package.forbidden_patterns"),
        },
        "infra_profile": infra_profile,
        "runtime_service_profile": runtime_service_profile,
        "cloud_provisioning_profile": cloud_provisioning_profile,
        "infra_readiness_policy": {
            "enabled_when": "infra_profile.infra_detected == true",
            "detect_do_not_assume": True,
            "source_of_truth_order": _text("package.source_of_truth_order"),
            "required_when_detected": _text("package.required_when_detected"),
            "safe_by_default": True,
            "forbidden": infra_profile["forbidden_actions"],
        },
        "runtime_service_boundary_policy": {
            "enabled_when": "runtime_service_profile.services_detected == true",
            "detect_do_not_assume": True,
            "source_of_truth_order": _text("package.source_of_truth_order.2"),
            "required_when_detected": runtime_service_profile["required_outputs_when_detected"],
            "rules": runtime_service_profile["boundary_rules"],
        },
        "cloud_provisioning_policy": {
            "enabled_when": "cloud_provisioning_profile.cloud_detected == true",
            "detect_do_not_assume": True,
            "required_when_detected": cloud_provisioning_profile[
                "required_outputs_when_cloud_detected"
            ],
            "script_policy": cloud_provisioning_profile["script_policy"],
            "forbidden_defaults": cloud_provisioning_profile["forbidden_defaults"],
        },
        
        "infra_readiness": {
            "enabled_when_evidence_exists": True,
            "source_of_truth_order": _text("package.source_of_truth_order.3"),
            "detect_do_not_assume": True,
            "safe_by_default": True,
            "provider_agnostic": True,
            "supported_detection_targets_examples_only": _text("package.supported_detection_targets_examples_only"),
            "allowed_actions": _text("package.allowed_actions"),
            "forbidden_actions": _text("package.forbidden_actions"),
            "required_evidence_when_infra_exists": _text("package.required_evidence_when_infra_exists"),
        },
        "solution_sanity_gates": [
            {
                "name": "manifest_parse_gate",
                "policy": "Parse only manifests that exist: pyproject.toml, package.json, pom.xml, go.mod, Cargo.toml, csproj/sln, yaml/json.",
            },
            {
                "name": "app_import_or_boot_gate",
                "policy": "Use detected ecosystem checks: Python import/app boot, npm scripts, go test/build, cargo check, dotnet build, Java build, or equivalent.",
            },
            {
                "name": "backend_route_gate",
                "policy": "When backend HTTP exists, verify exposed routes using the framework adapter detected from repository evidence; FastAPI is only one adapter.",
            },
            {
                "name": "frontend_manifest_gate",
                "policy": "When frontend exists, validate package/runtime manifest and available typecheck/lint/build scripts.",
            },
            {
                "name": "frontend_build_gate",
                "policy": "Run typecheck/lint/build only when scripts and dependencies are present; otherwise document environment-blocked evidence.",
            },
            {
                "name": "route_parity_gate",
                "policy": "When backend and frontend exist, compare frontend API calls with backend exposed routes using non-fragile framework-aware extraction.",
            },
            {
                "name": "script_presence_gate",
                "policy": "Create or validate Linux/macOS and PowerShell local scripts when runnable code exists.",
            },
            {
                "name": "junk_artifact_gate",
                "policy": "Block __MACOSX, .DS_Store, __pycache__, *.pyc, node_modules, .next, .venv, .ruff_cache, .mypy_cache.",
            },
            {
                "name": "docs_truthfulness_gate",
                "policy": "HOWTO_RUN and README must not declare commands, ports, env vars, routes, or services unsupported by actual files.",
            },
            {
                "name": "provider_boundary_gate",
                "policy": "If provider SDKs exist and the project requires adapter boundaries, business services must not import provider SDKs directly.",
            },
            {
                "name": "infra_readiness_gate",
                "policy": (
                    "When infra_profile.infra_detected is true, finalize must produce INFRA_READINESS.md "
                    "and safe-by-default prereq/plan/deployment-check scripts. The scripts must use only "
                    "non-mutating commands by default and must not assume a provider/tool not evidenced by "
                    "TECH_CONSTRAINTS, PLAN/SPEC, plan.json, repository files, or selected capabilities."
                ),
            },
            {
                "name": "runtime_service_boundary_gate",
                "policy": (
                    "When runtime_service_profile.services_detected is true, finalize must produce service boundary "
                    "configuration, environment placeholders, docs, and safe non-mutating checks. If an external DB, "
                    "auth provider, broker, cache, object store, or secret manager is evidenced, finalize must not "
                    "leave the solution documented as production-complete with only in-memory state or missing service configuration."
                ),
            },
            {
                "name": "cloud_provisioning_gate",
                "policy": (
                    "When cloud_provisioning_profile.cloud_detected is true, finalize must produce cloud inventory, "
                    "provision plan, guarded apply, and deployment check scripts for the detected provider. The scripts "
                    "must be provider-native only for evidenced providers and must fail closed for mutating actions unless "
                    "an explicit operator-controlled environment variable enables them."
                ),
            },     
        ],
        "required_outputs": final_outputs,
    }

    context = {
        "schema_version": "clike.local_agent_finalize_context.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "finalize",
        "run_id": run_id,
        "req_id": "SOLUTION",
        "executor_hint": local_executor,
        "workflow_owner": "orchestrator",
        "extension_role": "local_actuator_only",
        "agent_role": "solution_integrator_and_runnability_hardener",
        **({"methodology_context": methodology_context} if methodology_context else {}),
        **({"selected_skill_references": methodology_context.get("selected_skill_references") or []} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        **({"selected_skill_context": methodology_context.get("selected_skill_context") or {}} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        **({"skill_reference_policy": methodology_context.get("skill_reference_policy") or {}} if methodology_context and methodology_context.get("methodology") == "bmad" else {}),
        "context_envelope": build_context_envelope(
            phase="finalize",
            req_id="SOLUTION",
            execution_mode="local_agent",
            core_blobs=payload.get("core_blobs") or {},
            methodology_context=methodology_context,
            active_output_contract={},
            namespace_materialization={},
            require_bmad_core_blobs=True,
        ),
        "local_runtime": local_runtime,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_cloud_finalize_only_when_not_local_agent_only",
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
            "tech_constraints_paths": [
                "docs/harper/TECH_CONSTRAINTS.yaml",
                "TECH_CONSTRAINTS.yaml",
                "docs/harper/constraints.json",
            ],
            "promoted_source_roots": ["src"],
            "promoted_test_roots": ["test", "tests"],
            "runtime_and_infra_evidence_roots": [
                "infra",
                "deploy",
                "ops",
                "config",
                "configs",
                "schemas",
                "connectors",
                "jobs",
                "pipelines",
                "packages",
                "model",
                "models",
            ],
            "historical_kit_roots_read_only": ["runs/kit"],
            "gate_eval_evidence_roots_read_only": ["runs/eval", "runs/gate"],
        },
        "capability_context": {
            "manifest": capability_manifest,
        },
        "finalize_contract": finalize_contract,
        "infra_profile": infra_profile,
        "runtime_service_profile": runtime_service_profile,
        "cloud_provisioning_profile": cloud_provisioning_profile,
        "solution_write_policy": finalize_write_policy,
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "hard_rules": _text("package.hard_rules"), 
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            *_text("package.lines"),
            _render_methodology_prompt_block(methodology_context),
            *_text("package.lines.2"),
        ]
    )

    context_path = "runs/finalize/docs/AGENT_FINALIZE_CONTEXT.json"
    prompt_path = "runs/finalize/docs/AGENT_FINALIZE_PROMPT.md"

    return _package_envelope(
        phase="finalize",
        echo="Local agent finalize package prepared for SOLUTION",
        summary="local-agent-finalize-package-prepared",
        extra_warnings=["solution_finalize_requires_workspace_mutation"],
        run_id=run_id,
        execution_policy=execution_policy,
        local_agent={
            "action": "local_agent_required",
            "package_id": f"{run_id}:SOLUTION:finalize",
            "phase": "finalize",
            "req_id": "SOLUTION",
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": _local_agent_invocation(local_executor, payload),
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "expected_outputs": final_outputs,
            "infra_profile": infra_profile,
            "runtime_service_profile": runtime_service_profile,
            "cloud_provisioning_profile": cloud_provisioning_profile,
            "package_files": [
                _package_file(context_path, context_json, "application/json"),
                _package_file(prompt_path, prompt, "text/markdown"),
            ],
        },
    )
