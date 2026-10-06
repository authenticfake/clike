"""Normalization of local-agent results (POST /v1/harper/local-agent/complete).

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
from typing import Any, Dict, List
from services.capabilities import (
    build_capability_coverage,
    enrich_plan_json_text,
)

from services.local_agent.common import (
    _normalize_relative_path,
    _safe_text,
)
from services.local_agent.document import (
    _DOCUMENT_PHASE_SPECS,
    _path_accepted,
    _validate_document_phase_completeness,
)
from services.local_agent.finalize_profiles import (
    _build_finalize_write_policy,
    _is_safe_finalize_root,
)


def normalize_local_agent_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize the extension actuator result back into a Harper-compatible envelope.
    """
    phase = (_safe_text(payload.get("phase")) or "kit").lower()
    req_id = (_safe_text(payload.get("req_id")) or ("SOLUTION" if phase in {"finalize", "extend"} else "")).upper()
    run_id = _safe_text(payload.get("runId")) or _safe_text(payload.get("run_id"))

    files = payload.get("files") or []
    stdout = _safe_text(payload.get("stdout"))
    stderr = _safe_text(payload.get("stderr"))
    exit_code = payload.get("exit_code")

    def _extend_allowed_path(file_path: str) -> bool:
        # AGENT_* package internals and any path not declared in phases/extend/phase.yaml are
        # rejected (package internals live under runs/extend/, not docs/harper).
        return _path_accepted("extend", file_path)

    def _document_phase_allowed_path(doc_phase: str, file_path: str) -> bool:
        return doc_phase in ("idea", "spec", "plan") and _path_accepted(doc_phase, file_path)

    def _finalize_allowed_path(file_path: str) -> bool:
        p = _normalize_relative_path(file_path)
        if not p or not _is_safe_finalize_root(p):
            return False

        dynamic_roots = payload.get("allowed_write_roots") or payload.get("finalizeAllowedWriteRoots") or []
        if not isinstance(dynamic_roots, list):
            dynamic_roots = []

        fallback_roots = _build_finalize_write_policy({})["allowed_write_roots"]
        allowed_roots = []

        for item in [*fallback_roots, *dynamic_roots]:
            root = _normalize_relative_path(item)
            if root and _is_safe_finalize_root(root) and root not in allowed_roots:
                allowed_roots.append(root)

        for root in allowed_roots:
            if p == root or p.startswith(f"{root}/"):
                return True

        return False

    expected_prefix = f"runs/kit/{req_id}/"
    bad_paths: List[str] = []
    normalized_files: List[Dict[str, Any]] = []

    for item in files:
        if not isinstance(item, dict):
            continue
        file_path = _safe_text(item.get("path")).replace("\\", "/").lstrip("/")
        content = item.get("content")
        if not file_path:
            continue
        if phase == "finalize":
            allowed = _finalize_allowed_path(file_path)
        elif phase == "extend":
            allowed = _extend_allowed_path(file_path)
        elif phase in {"idea", "spec", "plan"}:
            allowed = _document_phase_allowed_path(phase, file_path)
        else:
            allowed = file_path.startswith(expected_prefix)
        if not allowed:
            bad_paths.append(file_path)
            continue

        if isinstance(content, str):
            normalized_files.append(
                {
                    "path": file_path,
                    "content": content,
                    "mime": item.get("mime"),
                    "encoding": item.get("encoding") or "utf-8",
                }
            )

    errors: List[str] = []
    warnings: List[str] = [
        "execution_selected:local_agent",
        "local_agent_result:normalized_by_orchestrator",
    ]

    ok = True
    exit_code_non_zero = exit_code not in (0, "0", None)

    if exit_code_non_zero:
        warnings.append(f"local_agent_exit_code:{exit_code}")
        warnings.append(
            "local_agent_non_zero_exit_will_be_accepted_if_candidate_artifacts_are_valid"
        )

    if bad_paths:
        ok = False
        errors.append("local_agent_wrote_outside_allowed_roots")
        warnings.append("blocked_paths:" + ",".join(bad_paths[:20]))

    if phase == "finalize":
        returned_paths = {
            str(item.get("path") or "").replace("\\", "/").lstrip("/")
            for item in normalized_files
        }
        content_by_path = {
            str(item.get("path") or "").replace("\\", "/").lstrip("/"): str(item.get("content") or "")
            for item in normalized_files
        }

        combined_finalize_text = "\n".join(
            content_by_path.get(path, "")
            for path in (
                "README.md",
                "docs/harper/HOWTO_RUN.md",
                "docs/harper/SANITY_CHECKS.md",
                "docs/harper/TODO_NEXT.md",
                "docs/harper/PR_BODY.md",
            )
        )
        combined_finalize_text_lower = combined_finalize_text.lower()

        parallel_demo_runtime_terms = (
            "dev_app.py",
            "demo_app.py",
            "sample_app.py",
            "mock_app.py",
            "fake_app.py",
            "dev_server.js",
            "demo_server.js",
            "sample_server.js",
            "mock_server.js",
            "fake_server.js",
            "dev_server.ts",
            "demo_server.ts",
            "sample_server.ts",
            "mock_server.ts",
            "fake_server.ts",
        )

        parallel_demo_paths = sorted(
            path
            for path in returned_paths
            if any(path.endswith(term) or path == term for term in parallel_demo_runtime_terms)
        )
        if parallel_demo_paths:
            ok = False
            errors.append("finalize_parallel_demo_runtime_forbidden")
            warnings.append(
                "parallel_demo_runtime_is_not_allowed_as_primary_finalize_runtime:"
                + ",".join(parallel_demo_paths)
            )

        referenced_demo_terms = [
            term for term in parallel_demo_runtime_terms if term in combined_finalize_text_lower
        ]
        if referenced_demo_terms:
            ok = False
            errors.append("finalize_docs_reference_parallel_demo_runtime")
            warnings.append(
                "finalize_docs_must_reference_canonical_stack_native_runtime_not_parallel_demo:"
                + ",".join(sorted(set(referenced_demo_terms)))
            )

        required_paths = {
            "README.md",
            "docs/harper/HOWTO_RUN.md",
            "docs/harper/SANITY_CHECKS.md",
            "docs/harper/RELEASE_NOTES.md",
            "docs/harper/TODO_NEXT.md",
            "docs/harper/PR_BODY.md",
        }

        infra_profile = payload.get("infra_profile") or {}
        runtime_service_profile = payload.get("runtime_service_profile") or {}
        cloud_provisioning_profile = payload.get("cloud_provisioning_profile") or {}

        infra_detected = bool(infra_profile.get("infra_detected"))
        runtime_services_detected = bool(runtime_service_profile.get("services_detected"))
        cloud_detected = bool(cloud_provisioning_profile.get("cloud_detected"))

        detected_services = {
            str(item or "").strip()
            for item in (runtime_service_profile.get("detected_services") or [])
            if str(item or "").strip()
        }
        service_details = runtime_service_profile.get("service_details") or {}
        categories = runtime_service_profile.get("categories") or {}

        database_detected = (
            "database" in detected_services
            or bool(categories.get("database"))
            or bool((service_details.get("database") or {}).get("engines"))
        )
        auth_detected = (
            "auth" in detected_services
            or bool(categories.get("auth"))
            or bool((service_details.get("auth") or {}).get("providers"))
        )

        if infra_detected:
            required_paths.update(
                {
                    "docs/harper/INFRA_READINESS.md",
                    "scripts/check_infra_prereqs.sh",
                    "scripts/check_infra_prereqs.ps1",
                    "scripts/provision_plan.sh",
                    "scripts/provision_plan.ps1",
                    "scripts/check_deployment.sh",
                    "scripts/check_deployment.ps1",
                }
            )

        if runtime_services_detected:
            required_paths.update(
                {
                    ".env.example",
                    "docs/harper/INFRA_READINESS.md",
                    "scripts/check_runtime_services.sh",
                    "scripts/check_runtime_services.ps1",
                }
            )

        if cloud_detected:
            required_paths.update(
                {
                    ".env.example",
                    "docs/harper/INFRA_READINESS.md",
                    "scripts/cloud_inventory.sh",
                    "scripts/cloud_inventory.ps1",
                    "scripts/provision_cloud_plan.sh",
                    "scripts/provision_cloud_plan.ps1",
                    "scripts/provision_cloud_apply.sh",
                    "scripts/provision_cloud_apply.ps1",
                    "scripts/check_deployment.sh",
                    "scripts/check_deployment.ps1",
                }
            )

        missing_paths = sorted(path for path in required_paths if path not in returned_paths)
        if missing_paths:
            ok = False
            errors.append("finalize_required_outputs_missing")
            warnings.append("missing_finalize_outputs:" + ",".join(missing_paths))

        env_example = content_by_path.get(".env.example", "")
        env_upper = env_example.upper()

        if database_detected:
            database_env_markers = (
                "DATABASE_URL",
                "DB_HOST",
                "DB_PORT",
                "DB_NAME",
                "DB_USER",
                "DB_PASSWORD",
                "SQLALCHEMY_DATABASE_URL",
                "JDBC_DATABASE_URL",
                "POSTGRES_URL",
                "POSTGRES_URL_REF",
                "POSTGRES_CONNECTION",
                "POSTGRES_CONNECTION_REF",
                "POSTGRES_CONNECTION_SECRET_REF",
            )
            if not any(marker in env_upper for marker in database_env_markers):
                ok = False
                errors.append("finalize_database_env_placeholders_missing")
                warnings.append(
                    "missing_database_env_placeholders:"
                    + ",".join(database_env_markers)
                )

        if auth_detected:
            auth_env_markers = (
                "AUTH_PROVIDER",
                "AUTH_ISSUER_URL",
                "AUTH_CLIENT_ID",
                "AUTH_CLIENT_SECRET",
                "AUTH_AUDIENCE",
                "AUTH_JWKS_URL",
                "OIDC_ISSUER",
                "OIDC_ISSUER_URL",
                "OIDC_AUDIENCE",
                "OIDC_CLIENT_ID",
                "OIDC_CLIENT_SECRET",
                "OIDC_JWKS_URI",
                "OIDC_JWKS_URL",
                "SAML_METADATA_URL",
                "SAML_ENTITY_ID",
            )
            if not any(marker in env_upper for marker in auth_env_markers):
                ok = False
                errors.append("finalize_auth_env_placeholders_missing")
                warnings.append(
                    "missing_auth_env_placeholders:"
                    + ",".join(auth_env_markers)
                )

            source_auth_evidence = any(
                path.startswith("src/")
                and any(
                    marker in content.lower()
                    for marker in (
                        "auth_provider",
                        "auth_mode",
                        "auth_issuer",
                        "auth_audience",
                        "issuer_url",
                        "client_id",
                        "client_secret",
                        "jwks",
                        "oidc",
                        "oauth",
                        "saml",
                        "identity",
                        "rbac",
                        "required_group",
                        "required_groups",
                        "local_auth",
                        "auth_bypass",
                        "login_bypass",
                        "disabled-local",
                        "local-disabled",
                    )
                )
                for path, content in content_by_path.items()
            )

            todo_text = content_by_path.get("docs/harper/TODO_NEXT.md", "").lower()
            auth_boundary_parked_patterns = (
                "implement auth boundary",
                "implement authentication boundary",
                "add auth boundary",
                "add authentication boundary",
                "create auth boundary",
                "create authentication boundary",
                "wire auth configuration",
                "wire authentication configuration",
                "add auth configuration seam",
                "add authentication configuration seam",
                "auth boundary missing",
                "authentication boundary missing",
                "auth not implemented",
                "authentication not implemented",
                "configure auth later",
                "configure authentication later",
            )
            auth_parked_in_todo = any(pattern in todo_text for pattern in auth_boundary_parked_patterns)

            if auth_parked_in_todo and not source_auth_evidence:
                ok = False
                errors.append("finalize_auth_boundary_parked_in_todo")
                warnings.append(
                    "auth_boundary_must_be_configured_with_placeholders_not_moved_to_TODO_NEXT"
                )

            if auth_detected and not source_auth_evidence:
                ok = False
                errors.append("finalize_auth_source_boundary_missing")
                warnings.append(
                    "auth_source_boundary_missing:finalize_must_patch_or_return_stack_native_auth_config_seam_when_auth_is_detected"
                )

        if cloud_detected:
            apply_script = "\n".join(
                [
                    content_by_path.get("scripts/provision_cloud_apply.sh", ""),
                    content_by_path.get("scripts/provision_cloud_apply.ps1", ""),
                ]
            )
            if "CLIKE_ALLOW_CLOUD_MUTATION" not in apply_script:
                ok = False
                errors.append("finalize_cloud_apply_guard_missing")
                warnings.append(
                    "provision_cloud_apply_must_fail_closed_without_CLIKE_ALLOW_CLOUD_MUTATION"
                )

        if database_detected:
            source_db_evidence = any(
                path.startswith("src/")
                and any(
                    marker in content.lower()
                    for marker in (
                        "database_url",
                        "db_url",
                        "connection_string",
                        "connectionsecretref",
                        "connection_secret_ref",
                        "connectionref",
                        "datasource",
                        "create_engine",
                        "sessionmaker",
                        "session_scope",
                        "get_session",
                        "sqlalchemy",
                        "jdbc",
                        "postgres",
                        "postgresql",
                        "createpostgresprovider",
                        "database provider",
                        "db provider",
                    )
                )
                for path, content in content_by_path.items()
            )
            if not source_db_evidence:
                todo_text = content_by_path.get("docs/harper/TODO_NEXT.md", "").lower()
                parked_in_todo = (
                    "database" in todo_text
                    or "database-backed" in todo_text
                    or "database backed" in todo_text
                    or "db boundary" in todo_text
                    or "persistence configuration" in todo_text
                    or "db configuration" in todo_text
                )
                if parked_in_todo:
                    ok = False
                    errors.append("finalize_database_boundary_parked_in_todo")
                    warnings.append(
                        "database_boundary_must_be_created_or_reused_with_placeholders_not_moved_to_TODO_NEXT"
                    )
                else:
                    ok = False
                    errors.append("finalize_database_source_boundary_missing")
                    warnings.append(
                        "database_source_boundary_missing:finalize_must_patch_or_return_stack_native_db_boundary_when_database_is_detected"
                    )

            credential_like_db_defaults = [
                path
                for path, content in content_by_path.items()
                if path.startswith("src/")
                and "DEFAULT_DATABASE_URL" in content
                and "://" in content
                and "@" in content
                and "<" not in content
                and "placeholder" not in content.lower()
            ]
            if credential_like_db_defaults:
                ok = False
                errors.append("finalize_database_credential_like_default_forbidden")
                warnings.append(
                    "database_boundary_must_not_hardcode_credential_like_default_urls:"
                    + ",".join(credential_like_db_defaults[:10])
                )

    document_phase_required_outputs = {
        doc_phase: list(spec["output_contract"]["always"]) for doc_phase, spec in _DOCUMENT_PHASE_SPECS.items()
    }
    if phase in document_phase_required_outputs:
        returned_paths = {
            _normalize_relative_path(item.get("path")) for item in normalized_files
        }
        missing_outputs = [
            required
            for required in document_phase_required_outputs[phase]
            if required not in returned_paths
        ]
        if missing_outputs:
            ok = False
            errors.append("document_phase_required_outputs_missing")
            warnings.append("missing_required_outputs:" + ",".join(missing_outputs))
            if exit_code_non_zero:
                errors.append(f"local_agent_exit_code:{exit_code}")
        else:
            # Required outputs are present; enforce the canonical quality bar so
            # local-agent documents are substantive, not skeletal heading-only.
            content_by_path = {
                _normalize_relative_path(item.get("path")): str(item.get("content") or "")
                for item in normalized_files
            }
            completeness_errors, completeness_warnings = _validate_document_phase_completeness(
                phase, content_by_path, payload.get("available_capabilities")
            )
            # Always surface advisory warnings (e.g. capability degradation),
            # even when there is no hard completeness error.
            warnings.extend(completeness_warnings)
            if completeness_errors:
                ok = False
                errors.extend(completeness_errors)

            # Deterministic capability enrichment (parity with cloud /plan):
            # expand per-REQ selected capability names into the structured
            # `capabilities` block on the normalized plan.json content.
            if phase == "plan":
                capability_metadata = payload.get("capability_metadata")
                for item in normalized_files:
                    if _normalize_relative_path(item.get("path")) == "docs/harper/plan.json" and isinstance(
                        item.get("content"), str
                    ):
                        item["content"] = enrich_plan_json_text(item["content"], capability_metadata)
                        warnings.append("plan:capabilities_enriched")
                        # Read-only coverage diagnostic for parity with cloud.
                        try:
                            coverage = build_capability_coverage(
                                json.loads(item["content"]), capability_metadata
                            )
                            if coverage.get("unresolved_capability_ids"):
                                warnings.append(
                                    "capability_unresolved:"
                                    + ",".join(coverage["unresolved_capability_ids"][:20])
                                )
                            if coverage.get("reqs_without_capabilities"):
                                warnings.append(
                                    "capability_uncovered_reqs:"
                                    + ",".join(coverage["reqs_without_capabilities"][:20])
                                )
                        except Exception:  # pragma: no cover - defensive
                            pass

    if phase == "extend":
        returned_paths = {
            _normalize_relative_path(item.get("path")) for item in normalized_files
        }
        content_by_path = {
            _normalize_relative_path(item.get("path")): str(item.get("content") or "")
            for item in normalized_files
        }
        has_audit = any(
            p.startswith("docs/harper/EXTEND_") and p.endswith(".md") for p in returned_paths
        )
        missing_outputs = []
        if "docs/harper/PLAN.md" not in returned_paths:
            missing_outputs.append("docs/harper/PLAN.md")
        if "docs/harper/plan.json" not in returned_paths:
            missing_outputs.append("docs/harper/plan.json")
        if not has_audit:
            missing_outputs.append("docs/harper/EXTEND_<date>_<first_req>_<last_req>.md")

        if missing_outputs:
            ok = False
            errors.append("extend_required_outputs_missing")
            warnings.append("missing_required_outputs:" + ",".join(missing_outputs))
            if exit_code_non_zero:
                errors.append(f"local_agent_exit_code:{exit_code}")
        else:
            # Mutated plan must remain valid: plan.json parses, has reqs with
            # acceptance, and every PLAN.md REQ-ID exists in plan.json.
            ext_errors, ext_warnings = _validate_document_phase_completeness(
                "plan", content_by_path, payload.get("available_capabilities")
            )
            audit_text = next(
                (content_by_path[p] for p in returned_paths if p.startswith("docs/harper/EXTEND_")),
                "",
            )
            if len(audit_text.strip()) < 40:
                ext_errors = list(ext_errors) + ["document_phase_output_incomplete"]
                ext_warnings = list(ext_warnings) + ["extend:audit_report_empty_or_too_short"]
            # Always surface advisory warnings, even without a hard error.
            warnings.extend(ext_warnings)
            if ext_errors:
                ok = False
                errors.append("extend_output_incomplete")

    if not normalized_files:
        ok = False
        # Document phases report missing required outputs above; the generic kit
        # REQ-ID message would be misleading (req_id is SOLUTION, not a kit REQ).
        if phase not in document_phase_required_outputs and phase != "extend":
            errors.append(f"no_candidate_files_returned_for:{req_id}")
            if exit_code_non_zero:
                errors.append(f"local_agent_exit_code:{exit_code}")
    elif exit_code_non_zero and ok:
        warnings.append(
            "local_agent_exit_code_accepted_because_candidate_files_were_returned"
        )

    return {
        "ok": ok,
        "phase": phase,
        "echo": f"Local agent result normalized for {req_id}",
        "text": "\n".join(
            [
                "Local agent execution completed.",
                "",
                "STDOUT:",
                stdout[:4000],
                "",
                "STDERR:",
                stderr[:4000],
            ]
        ).strip(),
        "files": normalized_files,
        "diffs": [],
        "tests": {
            "passed": 0,
            "failed": 0 if ok else 1,
            "summary": "local-agent-normalized" if ok else "local-agent-normalization-failed",
        },
        "warnings": warnings,
        "errors": errors,
        "runId": run_id,
        "execution": {
            "requested": payload.get("executionPreference"),
            "selected": "local_agent",
            "reason": "extension_actuator_completed_and_orchestrator_normalized_result",
            "phase_supported": True,
        },
    }
