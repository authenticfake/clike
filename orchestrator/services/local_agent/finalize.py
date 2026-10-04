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
        "required_common": [
            "README.md",
            ".env.example when runtime configuration exists or is expected",
            "docs/harper/HOWTO_RUN.md",
            "docs/harper/SANITY_CHECKS.md",
            "docs/harper/INFRA_READINESS.md when infra_profile.infra_detected is true",
            "docs/harper/RELEASE_NOTES.md",
            "docs/harper/TODO_NEXT.md",
            "docs/harper/PR_BODY.md",
        ],
        "required_scripts_when_runnable_code_exists": [
            "scripts/check_solution_local.sh",
            "scripts/check_solution_local.ps1",
            "runtime-specific run scripts for backend/frontend/workers only when those execution areas exist",
        ],
        "required_scripts_when_infra_profile_detected": infra_profile["safe_required_outputs"],
        "required_scripts_when_runtime_services_detected": [
            "scripts/check_runtime_services.sh",
            "scripts/check_runtime_services.ps1",
        ] if runtime_service_profile["services_detected"] else [],
        "required_scripts_when_cloud_detected": cloud_provisioning_profile[
            "required_outputs_when_cloud_detected"
        ],
        "conditional_solution_artifacts": [
            "composition root per execution area when missing or incomplete",
            "settings/env loader when runtime configuration exists",
            "dependency/repository factory when existing modules need wiring",
            "DB/session factory when datastore access exists",
            "local-dev profile when the solution has runnable services",
            "route/API parity check when backend HTTP and frontend API calls both exist",
            "ecosystem-native manifests only when the detected stack needs them",
            "docs/harper/INFRA_READINESS.md when infra/deploy/vendor-platform evidence exists",
            "scripts/check_infra_prereqs.sh and scripts/check_infra_prereqs.ps1 when infra/deploy evidence exists",
            "scripts/provision_plan.sh and scripts/provision_plan.ps1 when provisioning evidence exists and a safe plan/validate mode can be expressed",
            "scripts/check_deployment.sh and scripts/check_deployment.ps1 when deployment evidence exists",
            "infra/, deploy/, ops/, config/, schemas/, connectors/, jobs/, pipelines/, packages/, model/, or models/ artifacts only when supported by TECH_CONSTRAINTS, PLAN/SPEC, or repository evidence",
        ],
    }

    readme_release_contract = {
        "schema_version": "clike.finalize_readme_release_contract.v1",
        "purpose": (
            "Make local-agent /finalize produce the same polished, release-grade README.md style "
            "as the cloud finalize path, while keeping every claim evidence-based."
        ),
        "visual_style": [
            "README.md must use polished release-grade Markdown, not a minimal checklist.",
            "Use a clean H1 title followed by a badge row.",
            "Use a concise executive summary blockquote immediately after the badges.",
            "Use stable H2 sections with short, substantive paragraphs.",
            "Prefer Markdown tables for release scope, requirements coverage, configuration, sanity checks, and generated artifacts.",
            "Use fenced code blocks for runnable commands.",
            "Use a repository tree block when it helps explain the final artifact layout.",
            "Avoid raw dumps, noisy bullet spam, placeholder text, and vague marketing language.",
        ],
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
            "evidence_rules": [
                "Badge values must be derived from finalize context, eval/gate reports, PLAN.md, plan.json, runtime manifests, scripts, or generated artifacts.",
                "Do not claim eval-passing or gate-passing unless passing evidence is available.",
                "If eval or gate evidence is missing, use neutral not-verified/not-run badges.",
                "If runtime cannot be detected from manifests or source evidence, use a neutral runtime-unknown badge.",
            ],
            "examples": [
                "![Status](https://img.shields.io/badge/status-finalized-brightgreen)",
                "![Clike](https://img.shields.io/badge/clike-blue)",
                "![Harper](https://img.shields.io/badge/Harper-blue)",
                "![Eval](https://img.shields.io/badge/eval-passing-brightgreen)",
                "![Gate](https://img.shields.io/badge/gate-not--verified-lightgrey)",
                "![Runtime](https://img.shields.io/badge/runtime-detected-lightgrey)",
            ],
        },
        "required_readme_sections": [
            "Project Overview",
            "Release Scope",
            "Architecture",
            "Repository Structure",
            "Requirements Coverage",
            "Configuration",
            "How to Run",
            "How to Test",
            "Sanity Checks",
            "Generated Artifacts",
            "Operational Notes",
            "Known Limitations",
            "Next Steps",
        ],
        "content_rules": [
            "README.md must reflect the final accepted artifact set, not stale KIT output or earlier fallback docs.",
            "Requirement coverage must be based on PLAN.md, plan.json, gate/eval evidence, or finalized artifacts.",
            "Configuration must list only evidenced environment variables and safe placeholders.",
            "How to Run and How to Test must include only commands backed by real files/scripts/manifests, or clearly mark them as environment-blocked.",
            "Known Limitations must be concrete and evidence-based.",
            "Next Steps must be practical and aligned with TODO_NEXT.md.",
            "Do not invent routes, ports, services, providers, credentials, deployment targets, eval results, or gate results.",
            "Do not leave placeholder sections such as TBD, TODO, lorem ipsum, or fill this in.",
        ],
        "recommended_readme_skeleton": [
            "# <Project Name>",
            "",
            "![Status](https://img.shields.io/badge/status-finalized-brightgreen) ![Clike](https://img.shields.io/badge/clike-blue) ![Harper](https://img.shields.io/badge/Harper-blue) ![Eval](https://img.shields.io/badge/eval-not--verified-lightgrey) ![Gate](https://img.shields.io/badge/gate-not--verified-lightgrey) ![Runtime](https://img.shields.io/badge/runtime-detected-lightgrey)",
            "",
            "> Concise executive summary of what the finalized solution provides.",
            "",
            "## Project Overview",
            "## Release Scope",
            "## Architecture",
            "## Repository Structure",
            "## Requirements Coverage",
            "## Configuration",
            "## How to Run",
            "## How to Test",
            "## Sanity Checks",
            "## Generated Artifacts",
            "## Operational Notes",
            "## Known Limitations",
            "## Next Steps",
        ],
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
            "examples_only": [
                "DATABASE_URL",
                "DB_HOST",
                "DB_PORT",
                "DB_NAME",
                "DB_USER",
                "DB_PASSWORD",
                "SQLALCHEMY_DATABASE_URL",
                "JDBC_DATABASE_URL",
                "AUTH_PROVIDER",
                "AUTH_ISSUER_URL",
                "AUTH_CLIENT_ID",
                "AUTH_CLIENT_SECRET",
                "AUTH_AUDIENCE",
                "AUTH_JWKS_URL",
                "OIDC_ISSUER_URL",
                "OIDC_CLIENT_ID",
                "OIDC_CLIENT_SECRET",
                "OIDC_AUDIENCE",
                "OIDC_JWKS_URL",
                "SAML_METADATA_URL",
                "SAML_ENTITY_ID",
                "SAML_ACS_URL",
                "KAFKA_BOOTSTRAP_SERVERS",
                "AWS_REGION",
                "AWS_ACCOUNT_ID",
                "AZURE_SUBSCRIPTION_ID",
                "GCP_PROJECT_ID",
            ],
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
            "runnability_rules": [
                "Detect runtime areas, languages, frameworks, manifests, entrypoints, launchers, build commands, and test commands from TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, manifests, and repository evidence.",
                "Reuse existing canonical composition roots and launchers before creating new ones.",
                "Do not create a parallel demo/dev runtime as the primary finalize runtime when an evidenced canonical runtime can be completed.",
                "If no canonical runtime exists but an execution area is evidenced, create the stack-native minimal runtime entrypoint required by the evidenced stack.",
                "If a database service is evidenced, local run must remain database-configurable. Do not silently replace the evidenced database boundary with in-memory persistence.",
                "If auth is evidenced, local login may be bypassed only through an explicit local/dev configuration seam. Do not require interactive login for local smoke boot unless the project contract explicitly requires it.",
                "Business routers/controllers/handlers should be mounted when their dependencies can be wired safely. If a dependency is unavailable, expose controlled configuration-required failures instead of crashing import/boot.",
                "README/HOWTO/SANITY may claim runnability only for commands backed by real files and checked or clearly environment-blocked scripts.",
            ],
            "must_not": [
                "Do not rewrite the whole solution.",
                "Do not create parallel duplicated services, adapters, controllers, handlers, routers, launchers, or composition roots.",
                "Do not create a parallel dev/demo runtime when the canonical runtime can be patched.",
                "Do not replace external service boundaries with in-memory state when external services are evidenced.",
                "Do not hardcode credential-like database URLs, tokens, provider accounts, or real endpoints in source defaults.",
                "Do not assume Python, FastAPI, Node, Java, .NET, Go, Rust, PHP, SQLAlchemy, Express, Spring, or any stack unless evidenced.",
                "Do not fake runnability in docs without source/config/scripts support.",
                "Do not claim that source behavior was unchanged when finalize emits or collects source/config/runtime files.",
                "Do not claim that manifests, run scripts, route evidence, or runtime boundaries are missing when they are present in emitted or collected artifacts.",
            ],
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
            "forbidden_patterns": [
                "parallel dev/demo runtime as primary runtime",
                "in-memory persistence as implicit replacement for evidenced database",
                "README claiming runnable APIs that are not mounted or guarded",
                "TODO_NEXT containing core runtime/launcher/DB/auth wiring that finalize could safely complete",
                "stack-specific files or commands emitted without evidence from TECH_CONSTRAINTS.yaml, manifests, or repository structure",
            ],
        },
        "infra_profile": infra_profile,
        "runtime_service_profile": runtime_service_profile,
        "cloud_provisioning_profile": cloud_provisioning_profile,
        "infra_readiness_policy": {
            "enabled_when": "infra_profile.infra_detected == true",
            "detect_do_not_assume": True,
            "source_of_truth_order": [
                "TECH_CONSTRAINTS.yaml / TECH_CONSTRAINTS.yml / constraints.json",
                "docs/harper/PLAN.md",
                "docs/harper/plan.json",
                "docs/harper/SPEC.md",
                "repository source tree and manifests",
                "selected skills, packs, and design profiles",
            ],
            "required_when_detected": [
                "docs/harper/INFRA_READINESS.md",
                "scripts/check_infra_prereqs.sh",
                "scripts/check_infra_prereqs.ps1",
                "scripts/provision_plan.sh",
                "scripts/provision_plan.ps1",
                "scripts/check_deployment.sh",
                "scripts/check_deployment.ps1",
            ],
            "safe_by_default": True,
            "forbidden": infra_profile["forbidden_actions"],
        },
        "runtime_service_boundary_policy": {
            "enabled_when": "runtime_service_profile.services_detected == true",
            "detect_do_not_assume": True,
            "source_of_truth_order": [
                "TECH_CONSTRAINTS.yaml / TECH_CONSTRAINTS.yml / constraints.json",
                "docs/harper/PLAN.md",
                "docs/harper/plan.json",
                "docs/harper/SPEC.md",
                "repository source tree and manifests",
                "selected skills, packs, and design profiles",
            ],
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
            "source_of_truth_order": [
                "TECH_CONSTRAINTS.yaml / TECH_CONSTRAINTS.yml / constraints.json",
                "docs/harper/PLAN.md",
                "docs/harper/plan.json",
                "docs/harper/SPEC.md",
                "repository source tree and manifests",
                "selected skills, packs, and design profiles",
            ],
            "detect_do_not_assume": True,
            "safe_by_default": True,
            "provider_agnostic": True,
            "supported_detection_targets_examples_only": [
                "aws",
                "azure",
                "gcp",
                "kubernetes",
                "docker-compose",
                "terraform",
                "pulumi",
                "cloudformation",
                "bicep",
                "helm",
                "confluent-kafka",
                "cloudera",
                "mendix",
                "informatica",
                "plc",
                "scada",
                "on-prem",
                "hybrid",
                "vendor-managed-platform",
            ],
            "allowed_actions": [
                "detect_infra_stack_from_contracts_and_sources",
                "create_or_update_docs_harper_INFRA_READINESS_md",
                "create_or_update_safe_prereq_check_scripts",
                "create_or_update_validate_or_plan_scripts",
                "create_or_update_deploy_runbooks",
                "create_or_update_env_or_parameter_examples",
                "create_or_update_provider_or_platform_templates_when_evidenced",
                "document_blocked_checks_with_exact_missing_tool_or_context",
            ],
            "forbidden_actions": [
                "do_not_run_terraform_apply",
                "do_not_run_cloud_mutating_commands",
                "do_not_create_or_delete_live_cloud_resources",
                "do_not_write_real_secrets_or_credentials",
                "do_not_invent_cloud_account_region_tenant_project_or_networking",
                "do_not_grant_wildcard_admin_permissions",
                "do_not_assume_terraform_aws_kubernetes_or_docker_when_not_evidenced",
            ],
            "required_evidence_when_infra_exists": [
                "detected provider/platform/runtime",
                "required operator tools",
                "required environment variables or parameter files",
                "provisioning mode: none, manual, dry-run, plan, validate, vendor-tool, or managed-platform",
                "safe validation commands",
                "blocked checks and exact reasons",
                "deployment risks and rollback notes",
            ],
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
        "hard_rules": [
            "Do not run git commands.",
            "Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.", 
            "Do not commit, branch, push, tag, or open pull requests.",
            "Do not write secrets, credentials, private keys, or real .env files.",
            "Do not write under .git, node_modules, .venv, __pycache__, __MACOSX, .next, dist, build, .ruff_cache, or .mypy_cache.",
            "Do not rewrite the solution from scratch.",
            "Do not duplicate business logic, repositories, services, adapters, routers, controllers, handlers, or launchers already present.",
            "Do not create a parallel composition root if a valid one already exists; patch or complete the existing one.",
            "Do not create a parallel dev/demo runtime as the primary finalize runtime when the evidenced canonical runtime can be patched.",
            "Do not create a new launcher when an existing launcher can be made correct with a small patch.",
            "Detect canonical composition roots, launchers, package managers, build commands, and run commands from TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, manifests, scripts, and repository structure.",
            "Do not assume Python, FastAPI, app.py, main.py, db.py, SQLAlchemy, Node, Express, Spring, .NET, Go, Rust, PHP, or any framework/runtime unless evidenced.",
            "If a database service is evidenced, local run must stay database-configurable. Do not replace the evidenced database boundary with implicit in-memory persistence unless the project contract explicitly allows mock-only mode.",
            "If auth is evidenced, local login bypass is allowed only through an explicit local/dev auth configuration seam; do not require interactive login for local smoke boot unless the project contract explicitly requires it.",
            "Do not force Python, FastAPI, Node, Next.js, PostgreSQL, Docker, or any specific stack.",
            "Infer languages, frameworks, package managers, runtime profiles, and services from repository manifests, source files, PLAN/SPEC, and TECH_CONSTRAINTS.",
            "Python/FastAPI and Node/Next are reference adapters only, not defaults.",
            "Cloud and agent finalize must share the same final artifact names and meanings.",
            "Do not claim runnability unless sanity checks were run or explicitly marked environment-blocked with exact reasons.",
            "Docs must reflect real files, real scripts, real routes, real env vars, and real manifests.",
            "If a runnable E2E solution cannot be completed safely, document the blocking gap in TODO_NEXT.md and PR_BODY.md instead of faking success.",
            "If infra_profile.infra_detected is true, create or update docs/harper/INFRA_READINESS.md and the safe_required_outputs listed in infra_profile.",
            "Infra scripts must be provider/platform-native only when that provider/platform is evidenced by TECH_CONSTRAINTS, PLAN/SPEC, plan.json, repository files, or selected capabilities.",
            "Infra scripts must be safe-by-default: use validate, plan, dry-run, describe, lint, schema-check, package-integrity-check, or equivalent non-mutating vendor-tool commands.",
            "Do not run or generate default scripts that mutate live cloud or vendor infrastructure. Do not run terraform apply, pulumi up, cloud create/update/delete operations, destructive commands, secret writes, or privileged IAM changes.",
            "Do not invent provider account IDs, regions, tenants, projects, clusters, namespaces, VPCs, subnets, security groups, service principals, managed identities, credentials, or network topology.",
            "If infra, cloud, deployment, vendor platform, PLC/SCADA, Mendix, Informatica, Kafka, Cloudera, Kubernetes, or IaC scope is detected, create or update infra readiness documentation and safe validation/plan scripts only when supported by TECH_CONSTRAINTS, PLAN/SPEC, repository evidence, or selected capabilities.",
            "Do not run or generate scripts that perform live cloud mutation by default. Scripts must be safe-by-default and prefer validate, plan, dry-run, describe, lint, schema check, package integrity check, or vendor-tool validation modes.",
            "Never run terraform apply, pulumi up, cloud resource create/delete/update commands, destructive commands, secret writes, or privileged IAM changes from finalize.",
            "Do not invent provider account IDs, regions, tenants, projects, clusters, namespaces, VPCs, subnets, security groups, service principals, managed identities, credentials, or network topology. Use placeholders in examples and document missing values as operator-provided configuration.",
            "Do not assume AWS, Azure, GCP, Kubernetes, Terraform, Docker, Cloudera, Confluent Kafka, PLC, SCADA, Mendix, Informatica, or any vendor platform unless vendor-anchored evidence exists in TECH_CONSTRAINTS, PLAN/SPEC, repository files, manifests, or selected capabilities. Generic words such as workflow, mapping, namespace, parameter file, or connection object are not enough to infer a vendor platform.",
            "If runtime_service_profile.services_detected is true, create or update runtime service boundary docs, env placeholders, and safe checks listed in runtime_service_profile.required_outputs_when_detected.",
            "If runtime_service_profile detects a database service, do not document in-memory persistence as production-complete and do not park the DB boundary in TODO_NEXT merely because real credentials are missing. Provide safe generic DB configuration placeholders, DB readiness checks, and a stack-native DB boundary/configuration seam whenever source changes are allowed. Add engine-specific details only when runtime_service_profile.service_details.database.engines provides evidence.",
            "If runtime_service_profile detects an auth service, do not document no-auth or hardcoded-auth behavior as production-complete and do not park auth configuration in TODO_NEXT merely because real credentials are missing. Provide auth environment placeholders, issuer/client/JWKS/audience/realm or SAML metadata guidance as applicable, safe auth readiness checks, and a stack-native auth configuration seam whenever source changes are allowed. Add provider-specific details only when runtime_service_profile.service_details.auth.providers provides evidence.",
            "If cloud_provisioning_profile.cloud_detected is true, create or update every output listed in cloud_provisioning_profile.required_outputs_when_cloud_detected.",
            "Cloud inventory scripts must discover current state using non-mutating provider-native commands such as describe/list/show/status equivalents.",
            "Cloud provision plan scripts must prepare or validate the provisioning path without mutating live infrastructure by default.",
            "Cloud apply scripts are allowed only as guarded operator scripts and must fail closed unless CLIKE_ALLOW_CLOUD_MUTATION=1 is set.",
            "README.md must preserve useful existing README content and merge it with IDEA/SPEC/PLAN facts, runtime evidence, configuration, local run, infra/deploy readiness, checks, and known gaps.",
            "README.md must follow finalize_contract.readme_release_contract: cloud-style badge row, polished release-grade Markdown, required sections, evidence-based content, useful tables, fenced commands, and no minimal checklist-style README.",
            "README badges must be evidence-based: do not claim eval-passing, gate-passing, runtime, provider, route, or deployment status unless supported by available reports, manifests, scripts, PLAN/SPEC, or finalized artifacts.",
            ".env.example or ecosystem-native equivalent must include every evidenced runtime/auth/database/broker/cache/object-storage/secrets/cloud/deploy variable with safe placeholders.",
        ], 
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            "# Local Agent FINALIZE Execution Package — SOLUTION",
            "",
            "You are executing a CLike Harper /finalize package.",
            "The orchestrator owns workflow state and policy. The VS Code extension is only the local actuator.",
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read this file before acting:",
            "- runs/finalize/docs/AGENT_FINALIZE_CONTEXT.json",
            "",
            "Mission:",
            "- Make the promoted solution locally runnable as far as repository evidence allows, with small, conservative, completed, well formed code, repository-aware patches.",
            "- Patch source/config/runtime files under allowed_write_roots when required to make the solution coherent, configurable, boundary-complete, and runnable. Do not limit finalize to documentation if source wiring is incomplete.",
            "- Detect the stack-native runtime profile from TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, manifests, scripts, and repository structure. Complete the evidenced canonical entrypoints and launchers for that profile instead of assuming a language or framework.",
            "- Prefer completing canonical runtime files over creating parallel demo files. Do not emit stack-specific files or commands unless the stack is evidenced.",
            "- Treat README.md as a final merged project overview: preserve useful existing README content and merge it with IDEA.md, SPEC.md, PLAN.md, runtime evidence, configuration, local run, infra/deploy readiness, checks, and known gaps.",
            "- README.md must use the same polished release-grade Markdown style as the cloud finalize path: H1 title, badge row, executive summary blockquote, stable H2 sections, useful tables, fenced commands, repository tree where helpful, concrete operational notes, and no placeholder text.",
            "- README.md badges are required but must be evidence-based: use passing eval/gate badges only when reports prove it; otherwise use neutral not-verified/not-run badges.",
            "- README.md must include these sections when applicable: Project Overview, Release Scope, Architecture, Repository Structure, Requirements Coverage, Configuration, How to Run, How to Test, Sanity Checks, Generated Artifacts, Operational Notes, Known Limitations, and Next Steps.",
            "- Do not produce a minimal checklist-style README. Produce a polished final release document suitable for technical stakeholder review.",
            "- Reuse before create; patch before replace; complete before regenerate.",
            "- Produce truthful final documentation and local sanity scripts.",
            "- Final README, HOWTO_RUN, RELEASE_NOTES, PR_BODY, SANITY_CHECKS, and TODO_NEXT must describe the final accepted artifact set, not an earlier fallback or conservative partial snapshot. If source files, manifests, run scripts, or routes are emitted or collected, documentation must reflect them truthfully.",
            "- Keep the implementation language/framework/runtime agnostic and constraint-driven.",
            "",
            "Required first-pass inspection:",
            "- Read docs/harper/IDEA.md, SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS.yaml, TECH_CONSTRAINTS.yml, and constraints.json when present.",
            "- Treat TECH_CONSTRAINTS and repository evidence as the primary source of truth for runtime, provider, deployment, infra, and vendor-platform decisions.",
            "- Inspect src/, test/, tests/, scripts/, README.md, .env.example, root manifests, and docs/harper.",
            "- Inspect infra/deploy/ops/config/configs/schemas/connectors/jobs/pipelines/packages/model/models roots when present.",
            "- Inspect runs/kit only as read-only historical evidence; do not rewrite historical KIT artifacts unless explicitly required by the context.",
            "- Detect execution areas: backend, frontend, worker, CLI, service, IaC, data platform, integration platform, vendor platform, document-only, or mixed.",
            "- Detect manifests and descriptors: package.json, pyproject.toml, requirements.txt, pom.xml, go.mod, Cargo.toml, csproj/sln, Dockerfile, docker-compose.yml, Makefile, Terraform, Pulumi, CloudFormation, Bicep, Helm, Kubernetes YAML, Kafka connector configs, schema descriptors, Mendix metadata, Informatica descriptors, PLC/SCADA package/config exports, or equivalents.",
            "- Detect infra/deployment scope only from evidence. Do not assume cloud, Kubernetes, Terraform, Docker, Kafka, Cloudera, Mendix, Informatica, PLC, SCADA, or any vendor platform.",
            "",
             "Allowed writes:",
            "- Only write inside allowed_write_roots from AGENT_FINALIZE_CONTEXT.json.",
            "- Treat allowed_write_roots as detected or declared canonical solution roots, not as Python/Node-specific folders.",
            "- Platform/vendor-native roots such as Mendix, PLC, SCADA, Kafka, Cloudera, Informatica, ETL/ELT, IaC, deployment, connector, schema, package, or model roots are allowed only when declared by the project contract or present in allowed_write_roots.",
            "- Write real workspace files for final solution integration; do not stage output under runs/kit.",
            "",
            "Mandatory finalize outputs when applicable:",
            "- README.md",
            "- .env.example or ecosystem-native equivalent when runtime configuration exists or is expected, including placeholders for DB/auth/broker/cache/object-storage/secrets/cloud/deploy variables evidenced by TECH_CONSTRAINTS, PLAN/SPEC, plan.json, sources, or manifests",
            "- docs/harper/HOWTO_RUN.md",
            "- docs/harper/SANITY_CHECKS.md",
            "- docs/harper/INFRA_READINESS.md when infra_profile.infra_detected is true",
            "- docs/harper/RELEASE_NOTES.md",
            "- docs/harper/TODO_NEXT.md",
            "- docs/harper/PR_BODY.md",
            "- scripts/check_solution_local.sh and scripts/check_solution_local.ps1 when runnable code exists",
            "- runtime-specific run scripts for backend/frontend/workers only when those execution areas exist",
            "",
            "README.md release-grade format:",
            "- Start with '# <Project Name>'.",
            "- Add a single badge row using shields.io Markdown image badges.",
            "- Include at least status, Harper phase, eval, gate, and runtime badges.",
            "- Add a concise executive summary blockquote after the badge row.",
            "- Use the required section order from finalize_contract.readme_release_contract.required_readme_sections.",
            "- Use tables for release scope, requirements coverage, configuration, sanity checks, and generated artifacts when useful.",
            "- Use fenced code blocks for commands.",
            "- Keep every claim tied to repository evidence, PLAN/SPEC, eval/gate reports, manifests, scripts, or finalized artifacts.",
            "- Use neutral badges such as eval-not--verified or gate-not--verified when evidence is missing.",
            "- Never invent passing gates, runtime status, providers, routes, ports, credentials, or deployment targets.",
            "",
            "- scripts/check_infra_prereqs.sh and scripts/check_infra_prereqs.ps1 when infra_profile.infra_detected is true",
            "- scripts/provision_plan.sh and scripts/provision_plan.ps1 when infra_profile.infra_detected is true",
            "- scripts/check_deployment.sh and scripts/check_deployment.ps1 when infra_profile.infra_detected is true",
            "- scripts/check_runtime_services.sh and scripts/check_runtime_services.ps1 when runtime_service_profile.services_detected is true",
            "- scripts/cloud_inventory.sh and scripts/cloud_inventory.ps1 when cloud_provisioning_profile.cloud_detected is true",
            "- scripts/provision_cloud_plan.sh and scripts/provision_cloud_plan.ps1 when cloud_provisioning_profile.cloud_detected is true",
            "- scripts/provision_cloud_apply.sh and scripts/provision_cloud_apply.ps1 when cloud_provisioning_profile.cloud_detected is true",
            "- scripts/check_deployment.sh and scripts/check_deployment.ps1 when cloud_provisioning_profile.cloud_detected is true",
            "",
             "Solution integration duties, only when applicable:",
            "- Complete the canonical composition root if existing modules are not wired. Do not create a parallel dev/demo composition root when the canonical root can be patched.",
            "- Detect stack-native composition roots, launchers, manifests, run commands, build commands, and test commands from TECH_CONSTRAINTS.yaml, SPEC, PLAN, plan.json, scripts, manifests, and repository structure.",
            "- Add or complete settings/env loader if runtime config exists.",
            "- Add or complete dependency/repository/service factory only if existing modules require wiring.",
            "- Add or complete a stack-native DB configuration/session/client boundary only if datastore access exists.",
            "- When a database service is evidenced, local run must remain database-configurable. Missing live credentials may block runtime checks, but must not silently downgrade the app to implicit in-memory persistence.",
            "- Add or complete explicit local/dev auth configuration only if auth is evidenced. Local login bypass is allowed only when configuration makes it explicit and non-production.",
            "- Add route/API parity check only if backend HTTP and frontend API calls both exist.",
            "- If infra_profile.infra_detected is true, use infra_profile.detected_targets to create stack-native but safe-by-default infra readiness docs and scripts.",
            "- If runtime_service_profile.services_detected is true, use runtime_service_profile.detected_services and categories to create or update DB/auth/broker/cache/object-storage/secrets boundary docs, env placeholders, and safe checks.",
            "- If a database service is detected, provide a real database boundary: stack-native connection/config placeholders, DB readiness checks, and migration/init guidance when evidenced. Do not leave production docs describing only in-memory persistence unless explicitly allowed by the project contract. Do not move the DB boundary to TODO_NEXT merely because real credentials are unavailable; use safe placeholders and source/config seams.",
            "- If a migration tool is evidenced, emit or preserve the stack-native migration runner configuration and migration environment file required by that tool. For Alembic only when evidenced, emit root alembic.ini plus the evidenced migrations env.py under the migrations root, reusing existing profile/env modules such as src/**/profiles/env.py when present.",
            "- For Python projects, if a database service is detected and no source-level DB boundary exists, create or update a small stack-native boundary module such as src/**/db.py or src/**/database.py. When SQLAlchemy is evidenced, prefer an env-driven engine/session boundary with database_url(), engine/session factory, and session_scope()/get_session(). Do not hardcode PostgreSQL-specific behavior unless the engine is evidenced.",
            "- For database-backed projects, if a database service is detected and no source-level DB boundary exists, create or update a small stack-native boundary module or configuration file dedicated to data persistence. When an ORM or data mapper is evidenced, prefer an env-driven connection/session boundary with a connection string parser, connection/session factory, and session context manager. Do not hardcode engine-specific behavior unless that specific database engine is evidenced.",
            "- If an auth service is detected, provide a real authentication configuration boundary: issuer/client/JWKS/audience/realm/SAML metadata placeholders as applicable, auth readiness checks, and truthful blocked checks when the provider is unavailable. Do not move auth configuration to TODO_NEXT merely because real credentials are unavailable; use safe placeholders and source/config seams.",
            "- If cloud_provisioning_profile.cloud_detected is true, use cloud_provisioning_profile.detected_cloud_targets to generate cloud inventory, provision plan, guarded apply, and deployment check scripts. Generate these scripts even when no infra/ or deploy/ root exists yet; in that case, produce an operator-actionable placeholder-driven plan rather than a tools-only blocked report.",
            "- For cloud/vendor/platform infra, prefer prereq checks, validate, plan, dry-run, describe, lint, schema-check, package-integrity-check, or vendor-tool verification commands.",
            "- Do not assume Terraform just because cloud is detected. Use Terraform only if evidenced by TECH_CONSTRAINTS, PLAN/SPEC, plan.json, repository files, or existing manifests.",
            "- Do not assume AWS/Azure/GCP/Kubernetes/Docker/Kafka/Mendix/Informatica/PLC/SCADA unless present in infra_profile.detected_targets with vendor-anchored detection evidence or directly evidenced by files. Generic words such as workflow, mapping, namespace, parameter file, or connection object are not enough to infer a vendor platform.",
            "- Clean junk artifacts only inside allowed paths.",
            "",
            "Sanity gates to run or document as environment-blocked:",
            "- manifest_parse_gate",
            "- app_import_or_boot_gate",
            "- backend_route_gate when backend HTTP exists",
            "- frontend_manifest_gate when frontend exists",
            "- frontend_build_gate when frontend exists and scripts are available",
            "- route_parity_gate when backend and frontend exist",
            "- script_presence_gate",
            "- junk_artifact_gate",
            "- docs_truthfulness_gate",
            "- provider_boundary_gate when provider SDK boundaries are relevant",
            "- infra_readiness_gate when infra, cloud, deployment, vendor-platform, PLC/SCADA, Mendix, Informatica, Kafka, Cloudera, Kubernetes, Docker, or IaC evidence exists",
            "- runtime_service_boundary_gate when DB, auth, broker, cache, object storage, or secret manager evidence exists",
            "- cloud_provisioning_gate when AWS, Azure, GCP, or another cloud provider is evidenced",
            "",
            "At the end, print a concise summary with:",
            "- detected stack and execution areas;",
            "- existing components reused;",
            "- files created/updated;",
            "- scripts/checks run;",
            "- checks passed;",
            "- checks blocked by environment with exact reason;",
            "- unresolved gaps, if any.",
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
