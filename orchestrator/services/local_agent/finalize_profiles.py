"""Finalize evidence: declared roots, infra / runtime-service / cloud provisioning profiles, write policy.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
import re
from typing import Any, Dict, List

from services.local_agent.common import (
    _extract_core_blob,
    _normalize_relative_path,
    _safe_text,
)
from services.local_agent.kit_contracts import (
    _has_any_term,
)


def _is_safe_finalize_root(value: Any) -> bool:
    """Return true when a declared finalize root is safe enough to expose to agents."""
    path = _normalize_relative_path(value)
    if not path:
        return False

    forbidden_parts = {
        ".git",
        "node_modules",
        ".venv",
        "__pycache__",
        "__MACOSX",
        ".next",
        "dist",
        "build",
        ".ruff_cache",
        ".mypy_cache",
        "secrets",
        "credentials",
    }

    if path in {".env", ".env.local", ".env.production", ".DS_Store"}:
        return False

    if any(part in forbidden_parts for part in path.split("/")):
        return False

    forbidden_fragments = (
        "private_key",
        "id_rsa",
        "id_ed25519",
        "credential",
        "secret",
    )
    lowered = path.lower()
    return not any(fragment in lowered for fragment in forbidden_fragments)


def _collect_declared_finalize_roots_from_node(node: Any) -> List[str]:
    """Collect finalize roots from structured payload/plan fields."""
    root_field_names = {
        "solution_roots",
        "canonical_solution_roots",
        "finalize_write_roots",
        "allowed_finalize_roots",
        "platform_roots",
        "runtime_roots",
        "deployment_roots",
        "artifact_roots",
        "source_roots",
        "script_roots",
        "docs_roots",
        "manifest_roots",
    }

    found: List[str] = []

    def add(value: Any) -> None:
        path = _normalize_relative_path(value)
        if path and _is_safe_finalize_root(path) and path not in found:
            found.append(path)

    def walk(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_norm = _safe_text(key).lower()
                if key_norm in root_field_names:
                    walk(child, key_norm)
                else:
                    walk(child, key_norm)
            return

        if isinstance(value, list):
            for item in value:
                walk(item, key_hint)
            return

        if isinstance(value, str) and key_hint in root_field_names:
            for part in re.split(r"\s*(?:,|;|\n)\s*", value):
                add(part)

    walk(node)
    return found


def _extract_declared_finalize_roots(payload: Dict[str, Any]) -> List[str]:
    """
    Extract solution roots declared by the project contract.

    This keeps /finalize agnostic: enterprise/vendor roots such as mendix/,
    plc/, scada/, kafka/, cloudera/, informatica/, deploy/, infra/, packages/,
    model/, connectors/, schemas/, jobs/, or pipelines/ should come from
    plan.json, payload metadata, TECH_CONSTRAINTS-derived structured fields,
    or future repository manifests, not from hardcoded runtime assumptions.
    """
    found: List[str] = []

    def add_many(items: List[str]) -> None:
        for item in items:
            path = _normalize_relative_path(item)
            if path and _is_safe_finalize_root(path) and path not in found:
                found.append(path)

    add_many(_collect_declared_finalize_roots_from_node(payload))

    plan_json_text = _extract_core_blob(payload, "plan.json")
    if plan_json_text:
        try:
            plan = json.loads(plan_json_text)
            add_many(_collect_declared_finalize_roots_from_node(plan))
        except Exception:
            pass

    return found


def _finalize_evidence_blob(payload: Dict[str, Any]) -> str:
    """Build an evidence blob for finalize detection from contracts and source summaries."""
    parts = [
        _extract_core_blob(payload, "TECH_CONSTRAINTS.yaml"),
        _extract_core_blob(payload, "TECH_CONSTRAINTS.yml"),
        _extract_core_blob(payload, "constraints.json"),
        _extract_core_blob(payload, "SPEC.md"),
        _extract_core_blob(payload, "PLAN.md"),
        _extract_core_blob(payload, "plan.json"),
        _safe_text(payload.get("repo_summary")),
        _safe_text(payload.get("repository_summary")),
        _safe_text(payload.get("workspace_summary")),
        _safe_text(payload.get("project_summary")),
    ]
    return "\n".join(part for part in parts if part).lower()


def _detect_finalize_infra_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect infra/deploy/vendor-platform scope from evidence.

    Providers and platforms are never defaults. Vendor platforms require
    vendor-anchored evidence; generic words such as workflow, mapping,
    namespace, or parameter file must not trigger a vendor detector alone.
    """
    blob = _finalize_evidence_blob(payload)

    detectors = {
        "aws": (
            "aws",
            "amazon web services",
            "ecs",
            "fargate",
            "lambda",
            "ecr",
            "rds",
            "cloudformation",
            "cloudwatch",
            "aws secrets manager",
            "s3",
            "sqs",
            "sns",
            "vpc",
            "iam role",
        ),
        "azure": (
            "azure",
            "azurerm",
            "azure resource group",
            "azure app service",
            "azure container apps",
            "aks",
            "azure key vault",
            "azure service bus",
            "azure sql",
            "managed identity",
            "bicep",
            "arm template",
        ),
        "gcp": (
            "gcp",
            "google cloud",
            "cloud run",
            "gke",
            "artifact registry",
            "cloud sql",
            "pub/sub",
            "google secret manager",
            "iam service account",
        ),
        "kubernetes": (
            "kubernetes",
            "k8s",
            "kubectl",
            "helm",
            "kubernetes namespace",
            "deployment.yaml",
            "service.yaml",
            "ingress.yaml",
        ),
        "terraform": (
            "terraform",
            ".tf",
            "tfvars",
            "terraform plan",
            "terraform validate",
            "opentofu",
        ),
        "docker_compose": (
            "docker compose",
            "docker-compose",
            "compose.yml",
            "compose.yaml",
        ),
        "podman_compose": (
            "podman compose",
            "podman-compose",
            "compose.yml",
            "compose.yaml",
        ),
        "confluent_kafka": (
            "confluent",
            "apache kafka",
            "kafka",
            "schema registry",
            "kafka connect",
            "connector config",
            "consumer group",
        ),
        "cloudera": (
            "cloudera",
            "hdfs",
            "hive",
            "impala",
            "oozie",
            "spark job",
            "yarn queue",
        ),
        "mendix": (
            "mendix",
            "mendix microflow",
            "mendix nanoflow",
            "mendix domain model",
            "mx model",
            "mda",
        ),
        "informatica": (
            "informatica",
            "informatica powercenter",
            "powercenter",
            "informatica cloud",
            "informatica iics",
            "iics",
            "informatica mapping",
            "informatica workflow",
            "informatica parameter file",
            "informatica connection object",
        ),
        "plc_scada": (
            "plc",
            "scada",
            "ladder logic",
            "structured text",
            "hmi",
            "tag map",
            "alarm definition",
            "historian",
        ),
    }

    detected: List[str] = []
    detection_details: Dict[str, List[str]] = {}

    for name, terms in detectors.items():
        matched_terms = [term for term in terms if _has_any_term(blob, (term,))]
        if not matched_terms:
            continue

        # Vendor-platform detectors must be anchored by vendor-specific evidence.
        if name == "informatica" and not _has_any_term(
            blob,
            (
                "informatica",
                "powercenter",
                "iics",
                "informatica cloud",
            ),
        ):
            continue

        if name == "mendix" and not _has_any_term(blob, ("mendix", "mx model", "mda")):
            continue

        detected.append(name)
        detection_details[name] = matched_terms[:10]

    infra_detected = bool(detected)

    safe_required_outputs = []
    if infra_detected:
        safe_required_outputs = [
            "docs/harper/INFRA_READINESS.md",
            "scripts/check_infra_prereqs.sh",
            "scripts/check_infra_prereqs.ps1",
            "scripts/provision_plan.sh",
            "scripts/provision_plan.ps1",
            "scripts/check_deployment.sh",
            "scripts/check_deployment.ps1",
        ]

        if any(target in detected for target in ("aws", "azure", "gcp")):
            safe_required_outputs.extend(
                [
                    "scripts/cloud_inventory.sh",
                    "scripts/cloud_inventory.ps1",
                    "scripts/provision_cloud_plan.sh",
                    "scripts/provision_cloud_plan.ps1",
                    "scripts/provision_cloud_apply.sh",
                    "scripts/provision_cloud_apply.ps1",
                ]
            )

    return {
        "schema_version": "clike.finalize_infra_profile.v1",
        "infra_detected": infra_detected,
        "detected_targets": detected,
        "detection_details": detection_details,
        "detection_policy": (
            "Detected only from TECH_CONSTRAINTS, PLAN/SPEC, plan.json, source evidence, "
            "repository summaries, manifests, or selected capabilities. No provider, vendor, "
            "language, framework, or IaC tool is assumed as a default. Vendor platforms require "
            "vendor-anchored evidence; generic workflow/mapping/namespace terms are insufficient."
        ),
        "safe_required_outputs": safe_required_outputs,
        "safe_actions_only": [
            "detect",
            "document",
            "validate",
            "plan",
            "dry-run",
            "describe",
            "lint",
            "schema-check",
            "package-integrity-check",
            "vendor-tool-check",
        ],
        "forbidden_actions": [
            "terraform apply",
            "pulumi up",
            "cloud resource create/update/delete",
            "destructive operations",
            "secret writes",
            "privileged IAM changes",
            "real deployment without explicit user approval",
        ],
    }


def _detect_finalize_runtime_service_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect runtime services from TECH_CONSTRAINTS, PLAN/SPEC, plan.json and repository evidence.

    The primary contract is category-based and agnostic: database, auth, broker,
    cache, object_storage, secrets. Product/vendor/engine names are captured as
    service_details, never as the primary required-service identity.
    """
    blob = _finalize_evidence_blob(payload)

    engine_detectors = {
        "postgresql": (
            "postgresql",
            "postgres",
            "pgvector",
            "jdbc:postgresql",
            "asyncpg",
            "psycopg",
        ),
        "mysql": (
            "mysql",
            "mariadb",
            "jdbc:mysql",
        ),
        "sqlserver": (
            "sql server",
            "mssql",
            "jdbc:sqlserver",
        ),
        "oracle": (
            "oracle database",
            "oracle db",
            "jdbc:oracle",
        ),
        "sqlite": (
            "sqlite",
            "sqlite3",
        ),
        "mongodb": (
            "mongodb",
            "mongodb atlas",
        ),
        "minio": (
            "minio",
            "minio server",
        ),
    }

    auth_provider_detectors = {
        "keycloak": (
            "keycloak",
            "keycloak_realm",
            "keycloak_client_id",
        ),
        "oidc": (
            "oidc",
            "openid connect",
            "jwks",
            "issuer url",
            "oidc_issuer_url",
            "oidc_client_id",
        ),
        "oauth2": (
            "oauth2",
            "oauth 2",
        ),
        "saml": (
            "saml",
            "saml metadata",
            "saml_entity_id",
        ),
    }

    service_details: Dict[str, Any] = {
        "database": {"engines": [], "evidence": []},
        "auth": {"providers": [], "evidence": []},
        "broker": {"providers": [], "evidence": []},
        "cache": {"providers": [], "evidence": []},
        "object_storage": {"providers": [], "evidence": []},
        "secrets": {"providers": [], "evidence": []},
    }

    migration_tool_details: Dict[str, Any] = {"tools": [], "evidence": []}
    migration_tool_detectors = {
        "alembic": ("alembic", "alembic.ini", "script_location", "env.py", "versions/"),
        "flyway": ("flyway", "flyway.conf", "db/migration", "V1__", "baselineOnMigrate"),
        "liquibase": ("liquibase", "changelog", "databaseChangeLog", "liquibase.properties"),
        "prisma": ("prisma", "schema.prisma", "prisma migrate"),
        "knex": ("knex", "knexfile", "knex migrate"),
        "ef-core": ("entity framework", "ef migrations", "dotnet ef", "DbContext"),
        "rails": ("rails db:migrate", "ActiveRecord::Migration"),
    }
    for tool, terms in migration_tool_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            migration_tool_details["tools"].append(tool)
            migration_tool_details["evidence"].extend(matched[:5])

    for engine, terms in engine_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["database"]["engines"].append(engine)
            service_details["database"]["evidence"].extend(matched[:5])

    generic_database_terms = (
        "database_url",
        "docuzen_database_url",
        "sqlalchemy",
        "alembic",
        "jdbc:",
        "datasource",
        "connection string",
        "db_host",
        "db_name",
    )
    generic_database_matches = [
        term for term in generic_database_terms if _has_any_term(blob, (term,))
    ]
    if generic_database_matches:
        service_details["database"]["evidence"].extend(generic_database_matches[:5])

    for provider, terms in auth_provider_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["auth"]["providers"].append(provider)
            service_details["auth"]["evidence"].extend(matched[:5])

    broker_detectors = {
        "kafka": ("kafka", "confluent", "schema registry", "kafka connect", "bootstrap servers"),
        "rabbitmq": ("rabbitmq", "amqp", "amazon mq"),
        "sqs": ("sqs", "sqs_queue_url"),
        "sns": ("sns", "sns_topic_arn"),
    }
    for provider, terms in broker_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["broker"]["providers"].append(provider)
            service_details["broker"]["evidence"].extend(matched[:5])

    cache_detectors = {
        "redis": ("redis", "redis_url", "redis_host"),
        "valkey": ("valkey",),
        "elasticache": ("elasticache",),
    }
    for provider, terms in cache_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["cache"]["providers"].append(provider)
            service_details["cache"]["evidence"].extend(matched[:5])

    object_storage_detectors = {
        "s3": ("s3", "s3_bucket", "s3_endpoint_url"),
        "s3-compatible": ("s3-compatible", "object storage", "bucket"),
        "minio": ("minio",),
        "blob-storage": ("blob storage",),
    }
    for provider, terms in object_storage_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["object_storage"]["providers"].append(provider)
            service_details["object_storage"]["evidence"].extend(matched[:5])

    secrets_detectors = {
        "aws-secrets-manager": ("aws secrets manager", "aws_secret_id"),
        "vault": ("vault", "vault_addr", "vault_secret_path"),
        "external-secrets": ("external secrets", "secret provider"),
        "key-vault": ("key vault",),
        "secret-manager": ("secret manager",),
    }
    for provider, terms in secrets_detectors.items():
        matched = [term for term in terms if _has_any_term(blob, (term,))]
        if matched:
            service_details["secrets"]["providers"].append(provider)
            service_details["secrets"]["evidence"].extend(matched[:5])

    detected_services = [
        name
        for name, details in service_details.items()
        if any(details.get(key) for key in ("engines", "providers", "evidence"))
    ]

    categories = {name: (name in detected_services) for name in service_details}

    required_outputs: List[str] = []
    if detected_services:
        required_outputs.extend(
            [
                ".env.example with runtime service placeholders",
                "docs/harper/HOWTO_RUN.md runtime services setup section",
                "docs/harper/SANITY_CHECKS.md runtime service checks",
                "docs/harper/INFRA_READINESS.md runtime services section",
                "scripts/check_runtime_services.sh",
                "scripts/check_runtime_services.ps1",
            ]
        )

    return {
        "schema_version": "clike.finalize_runtime_service_profile.v1",
        "services_detected": bool(detected_services),
        "detected_services": detected_services,
        "categories": categories,
        "service_details": service_details,
        "migration_tool_profile": {
            "tools_detected": bool(migration_tool_details["tools"]),
            "detected_tools": sorted(set(migration_tool_details["tools"])),
            "evidence": sorted(set(migration_tool_details["evidence"])),
            "policy": (
                "When a migration tool is evidenced, finalize must emit or preserve the stack-native migration configuration "
                "and migration environment files required to run migrations. Do not assume a migration tool without evidence."
            ),
        },
        "required_outputs_when_detected": sorted(set(required_outputs)),
        "policy": (
            "When runtime services are evidenced, finalize must make the solution boundary-ready: "
            "configuration placeholders, truthful docs, safe non-mutating checks, and integration seams. "
            "Engine/vendor names are details, not the primary service contract."
        ),
        "boundary_rules": [
            "Detect services from TECH_CONSTRAINTS, PLAN/SPEC, plan.json, repository evidence, manifests, and selected capabilities only.",
            "Do not assume a database engine, auth provider, broker, cache, object store, or secret manager without evidence.",
            "If a database is evidenced, in-memory persistence is not a production-complete boundary.",
            "If enterprise auth is evidenced, hardcoded/no-auth local behavior is not a production-complete auth boundary.",
            "Finalize may create local-dev templates and safe checks, but must not write real secrets or provision live services automatically.",
            "Use generic service placeholders by default and add engine/provider-specific placeholders only when that engine/provider is evidenced.",
        ],
    }


def _detect_finalize_cloud_provisioning_profile(
    payload: Dict[str, Any],
    infra_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect cloud provisioning obligations from evidence.

    This remains provider-agnostic: cloud provisioning is enabled only when
    TECH_CONSTRAINTS, PLAN/SPEC, plan.json, repository evidence, or selected
    capabilities identify a cloud provider or deployment target.
    """
    detected_targets = set(infra_profile.get("detected_targets") or [])
    cloud_targets = [
        item for item in ("aws", "azure", "gcp")
        if item in detected_targets
    ]

    cloud_detected = bool(cloud_targets)

    required_outputs: List[str] = []
    if cloud_detected:
        required_outputs = [
            "docs/harper/INFRA_READINESS.md",
            "scripts/cloud_inventory.sh",
            "scripts/cloud_inventory.ps1",
            "scripts/provision_cloud_plan.sh",
            "scripts/provision_cloud_plan.ps1",
            "scripts/provision_cloud_apply.sh",
            "scripts/provision_cloud_apply.ps1",
            "scripts/check_deployment.sh",
            "scripts/check_deployment.ps1",
        ]

    return {
        "schema_version": "clike.finalize_cloud_provisioning_profile.v1",
        "cloud_detected": cloud_detected,
        "detected_cloud_targets": cloud_targets,
        "required_outputs_when_cloud_detected": required_outputs,
        "policy": (
            "When cloud is evidenced, finalize must produce a safe cloud provisioning package even if no infra/ or deploy/ root exists yet: "
            "inventory, plan, guarded apply, deployment checks, and INFRA_READINESS documentation. "
            "The scripts must be provider-native only for detected providers and must not assume a provider by default. "
            "When concrete IaC manifests are absent, the plan script must produce an operator-actionable provisioning plan using placeholders instead of silently downgrading to a tools-only check."
        ),
        "script_policy": {
            "inventory": "Inventory scripts may run non-mutating describe/list/show/status commands to discover what currently exists.",
            "plan": "Plan scripts may validate templates, show planned actions, or generate operator-visible commands without mutating live resources.",
            "apply_guarded": (
                "Apply scripts are allowed only as guarded operator tools. They must fail closed unless "
                "CLIKE_ALLOW_CLOUD_MUTATION=1 is set, and they must print the detected provider/account/project/tenant before running."
            ),
            "deployment_check": "Deployment check scripts may run non-mutating health, describe, status, logs, or endpoint checks.",
        },
        "forbidden_defaults": [
            "Do not run mutating cloud commands automatically.",
            "Do not embed real account IDs, project IDs, tenant IDs, subscription IDs, secrets, tokens, credentials, VPC IDs, subnet IDs, or security group IDs.",
            "Do not grant wildcard admin privileges.",
            "Do not assume Terraform, Kubernetes, Docker, or any cloud provider unless evidenced.",
            "Do not make apply the default path; plan/inventory/check must be the default path.",
        ],
    }


def _build_finalize_write_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build write policy for /finalize.

    Default roots cover common software repositories. Declared roots extend the
    policy for vendor/platform solutions without hardcoding those platforms as
    universal defaults.
    """
    default_allowed_write_roots = [
        "src",
        "scripts",
        "docs/harper",
        "README.md",
        ".env.example",

        # Runtime/deployment roots. These are platform-neutral containers for
        # safe-by-default provisioning plans, deploy templates, validation
        # scripts, and vendor/package descriptors. They do not imply a specific
        # cloud, language, framework, or IaC tool.
        "infra",
        "deploy",
        "ops",
        "config",
        "configs",
        "schemas",
        "migrations",
        "db",
        "database",
        "connectors",
        "jobs",
        "pipelines",
        "packages",
        "model",
        "models",

        # Ecosystem-native root manifests. The agent/cloud must use only the
        # manifests supported by TECH_CONSTRAINTS, PLAN/SPEC, and repository evidence.
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "requirements.txt",
        "pom.xml",
        "build.gradle",
        "settings.gradle",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "docker-compose.yml",
        "Dockerfile",
        "Makefile",
    ]

    declared_roots = _extract_declared_finalize_roots(payload)

    allowed_write_roots: List[str] = []
    for item in [*default_allowed_write_roots, *declared_roots]:
        path = _normalize_relative_path(item)
        if path and _is_safe_finalize_root(path) and path not in allowed_write_roots:
            allowed_write_roots.append(path)

    forbidden_paths = [
        ".git",
        "node_modules",
        ".venv",
        "__pycache__",
        "__MACOSX",
        ".DS_Store",
        ".next",
        "dist",
        "build",
        ".ruff_cache",
        ".mypy_cache",
        "secrets",
        ".env",
        ".env.local",
        ".env.production",
        "credentials",
        "credential",
        "private_key",
        "id_rsa",
        "id_ed25519",
    ]

    return {
        "schema_version": "clike.finalize_write_policy.v1",
        "policy": (
            "Finalize may write only inside detected or declared canonical solution roots. "
            "Default roots are intentionally minimal. Platform/vendor-native roots must be "
            "declared by plan.json, payload metadata, TECH_CONSTRAINTS-derived structured fields, "
            "repository manifests, skills, packs, or design profiles."
        ),
        "default_allowed_write_roots": default_allowed_write_roots,
        "declared_allowed_write_roots": declared_roots,
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
    }
