"""KIT contracts for local agents: target contract, obligations, FILE_REQUIREMENTS.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from services.local_agent.common import (
    _capability_index_names,
    _extract_core_blob,
    _req_capability_list,
    _safe_text,
)
from services.phase_definitions import phase_text


def _text(key: str) -> list:
    """Static text of this module, kept in phases/_shared_text.yaml (WP8.5)."""
    return list(phase_text("_shared")[key])


def _build_capability_integrity(req: Dict[str, Any], capability_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Compare selected capabilities with discovered capabilities."""
    selected_skills = _req_capability_list(req, "skills", nested_key="skills")
    selected_packs = _req_capability_list(req, "packs", nested_key="packs")
    selected_design = _req_capability_list(req, "design_profiles", "designProfiles", nested_key="design_profiles")

    discovered_skills = _capability_index_names(capability_manifest, "skills")
    discovered_packs = _capability_index_names(capability_manifest, "packs")
    discovered_design = _capability_index_names(capability_manifest, "design_profiles")

    missing_skills = [x for x in selected_skills if x.lower() not in discovered_skills]
    missing_packs = [x for x in selected_packs if x.lower() not in discovered_packs]
    missing_design = [x for x in selected_design if x.lower() not in discovered_design]

    missing_any = bool(missing_skills or missing_packs or missing_design)

    return {
        "selected": {
            "skills": selected_skills,
            "packs": selected_packs,
            "design_profiles": selected_design,
        },
        "discovered_counts": {
            "skills": len(discovered_skills),
            "packs": len(discovered_packs),
            "design_profiles": len(discovered_design),
        },
        "missing_selected_skills": missing_skills,
        "missing_selected_packs": missing_packs,
        "missing_selected_design_profiles": missing_design,
        "missing_any_selected_capability": missing_any,
        "policy": (
            "Selected capabilities must be backed by discovered capability files. "
            "If missing, the agent must report a blocking capability-context gap and must not silently relax obligations."
        ),
    }


def _technical_scope_requires_real_provider_wiring(req: Dict[str, Any]) -> bool:
    blob = _req_text_blob(req)
    provider_tokens = (
        "aws",
        "azure",
        "gcp",
        "microsoft",
        "google",
        "apigee",
        "wso2",
        "s3",
        "sqs",
        "sns",
        "secrets manager",
        "cloudwatch",
        "opentelemetry",
        "prometheus",
        "vault",
        "minio",
        "ceph",
        "sdk",
        "provider",
        "adapter",
        "runtime profile",
        "on-prem",
        "onprem",
    )
    return any(token in blob for token in provider_tokens)


def _add_obligation_name(items: List[str], value: Any) -> None:
    """Add a normalized obligation name while preserving display readability."""
    text = _safe_text(value).strip().strip("'\"")
    if not text:
        return

    text = re.sub(r"\s+", " ", text)
    lowered = text.lower()

    ignored = {
        "true",
        "false",
        "dev",
        "uat",
        "prod",
        "tests",
        "lint",
        "types",
        "security",
        "build",
        "backend",
        "frontend",
        "infra",
        "data",
        "enterprise",
        "hybrid",
    }
    if lowered in ignored or len(text) < 3:
        return

    if lowered not in {item.lower() for item in items}:
        items.append(text)


def _collect_structured_obligation_names(value: Any) -> List[str]:
    """Collect explicit dependency/tool names from structured contract fields.

    This is the preferred path. Future PLAN/spec generation should populate
    fields such as external_runtime_obligations instead of relying on text
    heuristics.
    """
    found: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            name = node.get("name") or node.get("tool") or node.get("library") or node.get("engine") or node.get("sdk")
            if name:
                _add_obligation_name(found, name)
            for child in node.values():
                walk(child)
            return

        if isinstance(node, list):
            for child in node:
                walk(child)
            return

        if isinstance(node, str):
            for part in re.split(r"\s*(?:\+|/|,|;|\band\b|\bor\b)\s*", node):
                _add_obligation_name(found, part)

    walk(value)
    return found


def _collect_explicit_req_obligations(req: Dict[str, Any]) -> List[str]:
    """Collect obligations explicitly attached to the current REQ."""
    fields = (
        "external_runtime_obligations",
        "external_library_obligations",
        "runtime_obligations",
        "runtime_libraries",
        "external_libraries",
        "libraries",
        "engines",
        "tools",
        "sdks",
        "model_runtimes",
    )

    found: List[str] = []
    for field in fields:
        for item in _collect_structured_obligation_names(req.get(field)):
            _add_obligation_name(found, item)
    return found


def _collect_tech_constraints_obligations(payload: Dict[str, Any], req_blob: str) -> List[str]:
    """Extract relevant named tools from TECH_CONSTRAINTS without hardcoding a catalog.

    TECH_CONSTRAINTS is declarative. Values from technology_stack-like sections
    become obligations only when they are also relevant to the current REQ text.
    """
    raw = (
        _extract_core_blob(payload, "TECH_CONSTRAINTS.yaml")
        or _extract_core_blob(payload, "TECH_CONSTRAINTS.yml")
        or _extract_core_blob(payload, "constraints.json")
    )
    if not raw:
        return []

    relevant_text = str(req_blob or "").lower()
    found: List[str] = []

    for raw_line in str(raw).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        value = ""
        if ":" in line:
            _, value = line.split(":", 1)
        elif line.startswith("-"):
            value = line[1:]

        value = value.strip().strip("'\"")
        if not value:
            continue

        # Split common declarative values such as "Tesseract + PaddleOCR/docTR".
        for part in re.split(r"\s*(?:\+|/|,|;|\band\b|\bor\b)\s*", value):
            candidate = part.strip().strip("'\"")
            if not candidate:
                continue
            lowered = candidate.lower()

            # Avoid applying the entire platform stack to every REQ.
            if lowered in relevant_text:
                _add_obligation_name(found, candidate)

    return found


def _extract_named_tools_from_req_text(req: Dict[str, Any]) -> List[str]:
    """Deprecated no-op fallback for narrative text extraction.

    External runtime obligations must come from structured REQ fields or
    TECH_CONSTRAINTS values relevant to the current REQ. Broad narrative
    extraction produced noisy obligations such as "Deliver", "Processing",
    "Successful", and "Sensitive", so it is intentionally disabled.
    """
    return []


def _named_external_runtime_obligations(req: Dict[str, Any], payload: Dict[str, Any]) -> List[str]:
    """Return external libraries/engines that must become implementation obligations.

    Definitive source order:
    1. structured REQ fields,
    2. TECH_CONSTRAINTS values relevant to the current REQ.

    Deprecated: closed hardcoded known_terms catalogs and broad narrative text
    extraction. SPEC/PLAN text remains model context, not a noisy obligation
    source of truth.
    """
    found: List[str] = []

    for item in _collect_explicit_req_obligations(req):
        _add_obligation_name(found, item)

    req_blob = _req_text_blob(req)
    for item in _collect_tech_constraints_obligations(payload, req_blob):
        _add_obligation_name(found, item)

    return found


def _classify_lane_semantics(lane: Any) -> Dict[str, Any]:
    """Classify the REQ lane without turning it into an implementation language."""
    value = _safe_text(lane).lower()

    data_concern_lanes = {"sql", "sqlite", "database", "data", "persistence", "migration"}
    frontend_lanes = {"frontend", "react", "nextjs", "vue", "angular"}
    backend_lanes = {"backend", "api", "service"}
    # language_lanes = {
    #     "python",
    #     "javascript",
    #     "typescript",
    #     "java",
    #     "dotnet",
    #     "go",
    #     "rust",
    #     "cpp",
    #     "c",
    # }
    language_lanes = {
    # Programming Languages
    "python", "javascript", "typescript", "java", "dotnet", 
    "go", "rust", "cpp", "c", "kotlin", "swift", "php", "ruby",
    
    # Industrial/PLC/SCADA specific
    "ladder_logic", "structured_text", "fbd", "vbscript", 
    
    # Enterprise & PLM/Low-Code
    "mendix", "teamcenter_api", "sql",
    
    # Infrastructure & Shell
    "bash", "powershell", "zsh", "lua", "terraform", "yaml"
}

    if value in data_concern_lanes:
        return {
            "lane_kind": "data_concern",
            "lane_is_implementation_language": False,
            "lane_interpretation": (
                "This lane describes datastore/schema/persistence scope. "
                "It must be implemented using the project stack declared by SPEC.md, "
                "PLAN.md, TECH_CONSTRAINTS, and repository evidence."
            ),
        }

    if value in frontend_lanes:
        return {
            "lane_kind": "frontend_concern",
            "lane_is_implementation_language": False,
            "lane_interpretation": (
                "This lane describes frontend/UI scope. Use the repository frontend stack."
            ),
        }

    if value in backend_lanes:
        return {
            "lane_kind": "backend_concern",
            "lane_is_implementation_language": False,
            "lane_interpretation": (
                "This lane describes backend/service scope. Use the repository backend stack."
            ),
        }

    if value in language_lanes:
        return {
            "lane_kind": "implementation_language",
            "lane_is_implementation_language": True,
            "lane_interpretation": (
                "This lane may identify an implementation language, but repository evidence "
                "and TECH_CONSTRAINTS still take precedence."
            ),
        }

    return {
        "lane_kind": "project_concern",
        "lane_is_implementation_language": False,
        "lane_interpretation": (
            "This lane is a planning concern. Do not infer implementation language from it alone."
        ),
    }


def _build_target_contract(req_id: str, req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a standalone target contract for the local agent package.

    The lane is preserved, but explicitly classified so an agent does not treat
    lanes such as `sql` as an implementation language.
    """
    lane_semantics = _classify_lane_semantics(req.get("lane"))

    return {
        "schema_version": "clike.target_contract.v1",
        "req_id": req_id,
        "title": req.get("title"),
        "functional_scope": req.get("functional_scope"),
        "technical_scope": req.get("technical_scope"),
        "acceptance": req.get("acceptance") or [],
        "dependsOn": req.get("dependsOn") or req.get("depends_on") or [],
        "lane": req.get("lane"),
        "lane_semantics": lane_semantics,
        "domain": req.get("domain"),
        "runtime_profile": req.get("runtime_profile"),
        "packs": _req_capability_list(req, "packs", nested_key="packs"),
        "skills": _req_capability_list(req, "skills", nested_key="skills"),
        "design_profiles": _req_capability_list(req, "design_profiles", "designProfiles", nested_key="design_profiles"),
        "test_profile": req.get("test_profile"),
        "gate_policy_ref": req.get("gate_policy_ref"),
        "gate_expectations": req.get("gate_expectations") or [],
        "main_module_boundary": req.get("main_module_boundary"),
        "out_of_scope": req.get("out_of_scope") or [],
        "future_compatibility_notes": req.get("future_compatibility_notes") or [],
        "implementation_runtime_policy": (
            "Infer implementation runtime from SPEC.md, PLAN.md, TECH_CONSTRAINTS, "
            "TARGET_CONTRACT, FILE_REQUIREMENTS, and repository evidence. "
            "Do not infer it from lane alone."
        ),
    }


def _req_text_blob(req: Dict[str, Any]) -> str:
    """Build a compact text blob from REQ fields for lightweight stack hints."""
    values: List[str] = [
        _safe_text(req.get("title")),
        _safe_text(req.get("functional_scope")),
        _safe_text(req.get("technical_scope")),
        _safe_text(req.get("test_profile")),
        _safe_text(req.get("main_module_boundary")),
        _safe_text(req.get("lane")),
    ]
    values.extend(_safe_text(item) for item in (req.get("acceptance") or []))
    values.extend(_safe_text(item) for item in (req.get("gate_expectations") or []))
    return " ".join(values).lower()


def _project_contract_text_blob(payload: Dict[str, Any]) -> str:
    """
    Build a compact text blob from project-level contracts.

    This prevents a data-concern lane such as `sql` from hiding the real
    implementation stack declared by SPEC.md, PLAN.md, TECH_CONSTRAINTS, or
    repository evidence.
    """
    parts = [
        _extract_core_blob(payload, "SPEC.md"),
        _extract_core_blob(payload, "PLAN.md"),
        _extract_core_blob(payload, "TECH_CONSTRAINTS.yaml"),
        _extract_core_blob(payload, "TECH_CONSTRAINTS.yml"),
        _extract_core_blob(payload, "constraints.json"),
        _safe_text(payload.get("repo_summary")),
        _safe_text(payload.get("repository_summary")),
        _safe_text(payload.get("workspace_summary")),
    ]
    return "\n".join(part for part in parts if part).lower()


def _has_any_term(blob: str, terms: tuple[str, ...]) -> bool:
    """Return true when any term appears as a token or explicit phrase.

    Execution-area detection must not use raw substring checks. Short tokens
    such as "api" and "ui" commonly appear inside unrelated words and can
    incorrectly require launchers for library/foundation REQs.
    """
    text = str(blob or "").lower()
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized:
            continue
        if " " in normalized or "-" in normalized or "/" in normalized:
            if normalized in text:
                return True
            continue
        if re.search(rf"(?<![a-z0-9_]){re.escape(normalized)}(?![a-z0-9_])", text):
            return True
    return False


def _build_recommended_outputs(
    req_id: str,
    req: Dict[str, Any],
    payload: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Build role-based recommended outputs without inferring a language or ecosystem.

    CLike core must not choose package.json, requirements.txt, pyproject.toml,
    go.mod, pom.xml, Cargo.toml, build.gradle, or any ecosystem-specific manifest
    from keyword catalogs. The active runtime is inferred by the agent from
    SPEC, PLAN, TECH_CONSTRAINTS, FILE_REQUIREMENTS, LTC/HOWTO, and repository
    evidence.
    """
    return [
        f"runs/kit/{req_id}/docs/README_{req_id}.md",
        f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
        (
            f"runs/kit/{req_id}/ci/<runtime-native-eval-manifest> "
            "when REQ-local eval commands require declared tools, scripts, or dependencies"
        ),
    ]


def _build_file_requirements(
    req_id: str,
    req: Dict[str, Any],
    capability_integrity: Dict[str, Any],
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build standalone file requirements and provider obligations.

    The contract is runtime-agnostic: it requires runnable composition and
    runtime-native manifests without forcing Node, Python, React, Express, Vite,
    or any specific framework. SPEC, PLAN, TECH_CONSTRAINTS and repository
    evidence remain the source of truth.
    """
    payload = payload or {}
    provider_realism_required = _technical_scope_requires_real_provider_wiring(req)
    named_external_runtime_obligations = _named_external_runtime_obligations(req, payload)

    req_blob = _req_text_blob(req)
    project_blob = _project_contract_text_blob(payload)
    evidence_blob = f"{req_blob}\n{project_blob}"

    owns_composition = req.get("owns_execution_area_composition")
    execution_areas: List[str] = []

    backend_terms = (
        "backend",
        "rest api",
        "api endpoint",
        "http endpoint",
        "route",
        "router",
        "handler",
        "controller",
        "server",
        "fastapi",
        "express",
        "worker",
        "consumer",
        "cli",
        "mendix-be",
    )
    frontend_terms = (
        "frontend",
        "user interface",
        "browser app",
        "react",
        "angular",
        "vite",
        "mendix-fe",
    )
    fullstack_terms = (
        "web_application",
        "web application",
        "fullstack",
        "full-stack",
    )

    foundation_terms = (
        "adapter",
        "adapters",
        "profile",
        "profiles",
        "provider",
        "providers",
        "runtime profile",
        "storage",
        "queue",
        "eventing",
        "secrets",
        "observability",
        "schema",
        "contract",
        "contracts",
        "migration",
        "foundation",
    )

    executable_terms = backend_terms + frontend_terms + fullstack_terms

    looks_like_foundation_slice = (
        owns_composition is not True
        and _has_any_term(req_blob, foundation_terms)
        and not _has_any_term(req_blob, executable_terms)
    )

    # Execution-area ownership is a property of the current REQ, not of the
    # whole project. Project-level SPEC/PLAN text may mention future backend,
    # frontend, API, UI, Mendix, PLC, SCADA, or other executable areas; that
    # must not make a library/foundation REQ require launchers or
    # promotion-ready runtime manifests.
    if owns_composition is not False and not looks_like_foundation_slice:
        if _has_any_term(req_blob, backend_terms):
            execution_areas.append("backend")
        if _has_any_term(req_blob, frontend_terms):
            execution_areas.append("frontend")
        if not execution_areas and _has_any_term(req_blob, fullstack_terms):
            execution_areas.extend(["backend", "frontend"])

    if owns_composition is True and not execution_areas:
        execution_areas.append("backend")

    required_candidate_outputs = [
        f"runs/kit/{req_id}/src/",
        f"runs/kit/{req_id}/test/",
        f"runs/kit/{req_id}/ci/LTC.json",
        f"runs/kit/{req_id}/ci/HOWTO.md",
        f"runs/kit/{req_id}/ci/<ecosystem-native-eval-manifest>",
        f"runs/kit/{req_id}/src/<execution-area>/<ecosystem-native-runtime-manifest> when the REQ creates or updates a runnable execution area",

    ]

    recommended_outputs = _build_recommended_outputs(req_id, req, payload)

    runtime_manifest_policy = {
        "required": True,
        "scope": "KIT_EVAL_ONLY",
        "runtime_manifest_required": True,
        "policy": (
            "If the KIT emits runnable source or tests, it must emit the runtime-native "
            "manifest needed to run the KIT evaluation harness under ci/. This file is "
            "functional for KIT/EVAL execution and is distinct from any promotion-ready "
            "runtime manifest under the candidate source execution area."
        ),
        "runtime_area_manifest_policy": (
            "If the KIT creates or updates a runnable execution area, it must also emit "
            "the ecosystem-native promotion-ready runtime manifest under "
            "runs/kit/<REQ-ID>/src/<execution-area>/. CLike is runtime-agnostic: the model "
            "must infer the manifest type from SPEC, PLAN, TECH_CONSTRAINTS, FILE_REQUIREMENTS, "
            "and repository evidence. The manifest choice must be easy to run locally and consistent "
            "with the selected ecosystem; do not force pyproject.toml, package.json, pom.xml, go.mod, "
            "or any other manifest unless the execution area actually requires it."
        ),
        "launcher_policy": (
            "If the KIT emits executable backend/frontend/service modules, it must provide "
            "one coherent launcher/composition entry per executable area only when the REQ owns "
            "composition or when no existing launcher exists. Do not create one launcher per REQ. "
            "Do not replace an existing composition root when the REQ only contributes feature modules."
        ),
        "reuse_before_create_policy": (
            "Before creating shared contracts, adapters, launchers, manifests, enums, or helpers, "
            "inspect dependency KITs and canonical promoted roots. Reuse or extend existing concepts "
            "before creating new ones."
        ),
        "examples": [
            f"runs/kit/{req_id}/ci/package.json for Node/npm ecosystems",
            f"runs/kit/{req_id}/ci/requirements.txt or ci/pyproject.toml for Python ecosystems",
            f"runs/kit/{req_id}/ci/pom.xml for Maven ecosystems",
            f"runs/kit/{req_id}/ci/go.mod for Go ecosystems",
            f"runs/kit/{req_id}/ci/RUNTIME_MANIFEST.md when the ecosystem has no standard manifest",
        ],
        "must_not": [
            f"Do not create eval-only runtime manifests under runs/kit/{req_id}/src/**.",
            *_text("build_file_requirements.must_not"),
        ],
    }

    solution_launcher_policy = {
        "required_when_executable_area_exists": True,
        "scope": "SOLUTION_COMPOSITION_ROOT",
        "execution_areas_detected": execution_areas,
        "policy": (
            "When emitted code exposes an executable application area, generate or "
            "regenerate one coherent composition root per execution area. A launcher "
            "belongs to the execution area, not to the individual REQ and not to a "
            "feature/domain namespace. One launcher per execution area is allowed "
            "and expected when required. Do not create REQ-local app mains. Reuse existing "
            "repository launcher conventions when present; otherwise infer the minimal "
            "runtime-native launcher shape from SPEC, PLAN and TECH_CONSTRAINTS."
        ),
        "must_cover": _text("build_file_requirements.must_cover"),
         "must_not": _text("build_file_requirements.must_not.2"),
        "runtime_native_examples_only": {
            "node_express_backend": [
                f"runs/kit/{req_id}/src/backend/app.js",
                f"runs/kit/{req_id}/src/backend/server.js",
            ],
            "react_vite_frontend": [
                f"runs/kit/{req_id}/src/frontend/index.html",
                f"runs/kit/{req_id}/src/frontend/src/main.jsx",
                f"runs/kit/{req_id}/src/frontend/src/App.jsx",
            ],
            "python_fastapi_backend": [
                f"runs/kit/{req_id}/src/backend/app.py",
                f"runs/kit/{req_id}/src/backend/main.py",
                f"runs/kit/{req_id}/src/app.py only when the repository uses a flat source-root launcher convention",

            ],
        },
    }

    required_outputs = [
        {
            "role": "source_root",
            "path_hint": f"runs/kit/{req_id}/src/",
            "kind": "source",
            "required": True,
            "purpose": "Candidate source files for the target REQ, directly promotable into canonical src roots.",
            "must_cover": ["REQ acceptance criteria", "declared canonical module boundaries"],
        },
        {
            "role": "test_root",
            "path_hint": f"runs/kit/{req_id}/test/",
            "kind": "test",
            "required": True,
            "purpose": "Candidate tests for the target REQ, directly promotable into canonical test roots.",
            "must_cover": ["acceptance criteria", "regression-sensitive behavior", "runtime smoke where applicable"],
        },
        {
            "role": "execution_contract",
            "path_hint": f"runs/kit/{req_id}/ci/LTC.json",
            "kind": "ci",
            "required": True,
            "purpose": "Executable local test contract for /eval.",
            "must_cover": ["tests", "lint or syntax checks", "build or runtime smoke when the implementation is runnable"],
        },
        {
            "role": "execution_howto",
            "path_hint": f"runs/kit/{req_id}/ci/HOWTO.md",
            "kind": "ci_doc",
            "required": True,
            "purpose": "Copy-paste execution guide aligned with LTC.",
            "must_cover": ["local setup", "container or restricted-runner notes when applicable", "troubleshooting"],
        },
        {
            "role": "runtime_eval_manifest",
            "path_hint": f"runs/kit/{req_id}/ci/<runtime-native-dependency-manifest>",
            "kind": "ci",
            "required": True,
            "purpose": "Runtime-native manifest for KIT/EVAL dependencies and scripts.",
            "must_cover": runtime_manifest_policy["examples"],
            "must_not_contain": runtime_manifest_policy["must_not"],
        },
        {
            "role": "external_library_obligation",
            "path_hint": f"runs/kit/{req_id}/src/<canonical-module-family>/<runtime-native-adapters-or-engines>",
            "kind": "source",
            "required": bool(named_external_runtime_obligations),
            "purpose": (
                "Production-facing adapter/factory implementation for explicit external libraries, SDKs, "
                "engines, or tools named by SPEC, PLAN, TECH_CONSTRAINTS, or this REQ. "
                "Do not stop at Protocol/interface-only code when named libraries are in scope."
            ),
            "named_obligations": named_external_runtime_obligations,
            "must_cover": _text("build_file_requirements.must_cover.2"),
            "must_not_contain": _text("build_file_requirements.must_not_contain"),
        },
        {
            "role": "execution_area_runtime_manifest",
            "path_hint": f"runs/kit/{req_id}/src/<execution-area>/<ecosystem-native-runtime-manifest>",
            "kind": "source",
            "required": bool(execution_areas),
            "purpose": (
                "Promotion-ready runtime manifest for a runnable execution area. "
                "This is distinct from the ci/ eval manifest and must be inferred "
                "from SPEC, PLAN, TECH_CONSTRAINTS, FILE_REQUIREMENTS, and repository evidence."
            ),
            "must_cover": _text("build_file_requirements.must_cover.3"),
            "must_not_contain": [
                "runs/kit paths",
                "ci-only paths",
                "temporary eval overlay paths",
                "REQ-specific eval scripts",
            ],
        },
        {
            "role": "solution_composition_root",
            "path_hint": f"runs/kit/{req_id}/src/<execution-area-composition-root>",
            "kind": "source",
            "required": bool(execution_areas),
            "purpose": (
                "One coherent launcher/composition root per executable area, solution-scoped rather than REQ-scoped. "
                "When required, this file may live outside main_module_boundary, but only under the allowed candidate src root."
            ),
            "must_cover": solution_launcher_policy["must_cover"] + [
                "create the minimal runnable composition root when this role is required and no existing canonical launcher is available",
                "wire or expose the emitted feature module through the execution area without duplicating business logic",
            ],
            "must_not_contain": solution_launcher_policy["must_not"],
        },
    ]

    provider_obligations: List[str] = []
    if provider_realism_required:
        provider_obligations.extend(
            _text("build_file_requirements.lines")
        )

    return {
        "schema_version": "clike.file_requirements.v2",
        "req_id": req_id,
        "required_candidate_outputs": required_candidate_outputs,
        "recommended_candidate_outputs": recommended_outputs,
        "required_outputs": required_outputs,
        "runtime_manifest_policy": runtime_manifest_policy,
        "solution_launcher_policy": solution_launcher_policy,
        "dependency_manifest_policy": (
            "Use the runtime-native dependency manifest required to run the KIT evaluation harness. "
            "Examples: ci/package.json for Node/npm, ci/requirements.txt or ci/pyproject.toml for Python, "
            "pom.xml for Maven, go.mod for Go. Do not emit Python requirements.txt for non-Python projects. "
            "Do not omit the manifest when generated source/tests require scripts or dependencies."
        ),
        "provider_realism_required": provider_realism_required,
        "provider_obligations": provider_obligations,
        "external_library_obligations": named_external_runtime_obligations,
        "external_library_policy": {
            "required": bool(named_external_runtime_obligations),
            "policy": (
                "Explicit external libraries, engines, SDKs, tools, or model runtimes named by SPEC, PLAN, "
                "TECH_CONSTRAINTS, structured REQ fields, or the current REQ are implementation obligations. "
                "The KIT must emit production-facing adapters/factories and dependency declarations, while "
                "tests may use deterministic fixtures to avoid downloads or external services."
            ),
            "detection_policy": (
                "Structured external_runtime_obligations are preferred. TECH_CONSTRAINTS values relevant to "
                "the current REQ are binding. Text-name extraction is deprecated fallback only."
            ),
            "boundary_rules": _text("build_file_requirements.boundary_rules"),
        },
        "provider_sdk_policy": {
            "official_or_consolidated_sdks_preferred": True,
            "policy": (
                "When a REQ names concrete providers or runtime services, official or widely adopted ecosystem SDKs "
                "must be used inside adapter/infrastructure boundaries unless SPEC explicitly forbids them."
            ),
            "boundary_rules": _text("build_file_requirements.boundary_rules.2"),
            "examples_by_ecosystem": {
                "python_aws": ["boto3", "botocore"],
                "python_postgres": ["sqlalchemy", "psycopg"],
                "python_vault": ["hvac"],
                "python_redis": ["redis"],
                "python_kafka": ["confluent-kafka", "aiokafka"],
                "node_aws": ["@aws-sdk/client-s3", "@aws-sdk/client-sqs", "@aws-sdk/client-sns", "@aws-sdk/client-secrets-manager"],
                "java_aws": ["AWS SDK for Java v2"],
                "go_aws": ["AWS SDK for Go v2"],
            },
        },
        "missing_selected_capabilities_blocking": bool(
            capability_integrity.get("missing_any_selected_capability")
        ),
        "forbidden": _text("build_file_requirements.forbidden"),
    }
