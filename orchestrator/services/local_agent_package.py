from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_core_blob(payload: Dict[str, Any], suffix: str) -> str:
    core_blobs = payload.get("core_blobs") or {}
    suffix_norm = suffix.lower().strip()

    for key, value in core_blobs.items():
        if str(key or "").lower().strip().endswith(suffix_norm):
            return str(value or "")

    return ""

def _compact_capability_index_for_agent(raw_index: str, max_chars: int) -> str:
    """
    Keep the capability index JSON-valid for local agents.

    Character-level truncation corrupts JSON and makes capability discovery
    fail closed (zero discovered skills/packs/design profiles). For local-agent
    packaging we prefer a compact, JSON-safe projection over a broken truncated blob.
    """
    text = str(raw_index or "").strip()
    if not text:
        return ""

    try:
        data = json.loads(text)
    except Exception:
        # If upstream content is already invalid, preserve it unchanged so the
        # failure remains diagnosable instead of making it worse.
        return text

    def _project(items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        projected: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            projected.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "description": item.get("description"),
                    "metadata": item.get("metadata") or {},
                }
            )
        return projected

    compact = {
        "schema_version": data.get("schema_version"),
        "repo_root": data.get("repo_root"),
        "skills": _project(data.get("skills")),
        "packs": _project(data.get("packs")),
        "design_profiles": _project(data.get("design_profiles")),
    }

    compact_text = json.dumps(compact, ensure_ascii=False, indent=2)
    if len(compact_text) <= max_chars:
        return compact_text

    names_only = {
        "schema_version": compact.get("schema_version"),
        "repo_root": compact.get("repo_root"),
        "skills": [{"name": item.get("name")} for item in compact["skills"]],
        "packs": [{"name": item.get("name")} for item in compact["packs"]],
        "design_profiles": [{"name": item.get("name")} for item in compact["design_profiles"]],
    }
    return json.dumps(names_only, ensure_ascii=False, indent=2)


def _extract_capability_manifest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a compact capability manifest for local agents.

    Cloud/gateway prompts receive core blobs directly. Local agents need the same
    operational power inside AGENT_*_CONTEXT.json, otherwise they only see the
    selected capability names without the actual guidance.
    """
    manifest = _extract_core_blob(payload, "CLIKE_CAPABILITY_MANIFEST.md")
    raw_index = _extract_core_blob(payload, "CLIKE_CAPABILITY_INDEX.json")
    selected_context = _extract_core_blob(payload, "CLIKE_SELECTED_CAPABILITY_CONTEXT.md")
    selected_context_json = _extract_core_blob(payload, "CLIKE_SELECTED_CAPABILITY_CONTEXT.json")

    max_manifest_chars = 18_000
    max_index_chars = 24_000

    if len(manifest) > max_manifest_chars:
        manifest = manifest[:max_manifest_chars].rstrip() + "\n\n...[truncated]\n"

    index = _compact_capability_index_for_agent(raw_index, max_index_chars)

    return {
        "available": bool(manifest),
        "manifest_name": "CLIKE_CAPABILITY_MANIFEST.md",
        "index_name": "CLIKE_CAPABILITY_INDEX.json",
        "index_available": bool(index),
        "content": manifest,
        "index_content": index,
        "selected_context_name": "CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
        "selected_context_json_name": "CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
        "selected_context_available": bool(selected_context),
        "selected_context_content": selected_context,
        "selected_context_json_content": selected_context_json,
    }

def _extract_req_from_plan(payload: Dict[str, Any], req_id: str) -> Dict[str, Any]:
    plan_json_text = _extract_core_blob(payload, "plan.json")
    if not plan_json_text:
        return {"id": req_id}

    try:
        plan = json.loads(plan_json_text)
    except Exception:
        return {"id": req_id}

    reqs = plan.get("reqs") or plan.get("req") or plan.get("requirements") or []
    if not isinstance(reqs, list):
        return {"id": req_id}

    req_id_norm = req_id.upper()
    for item in reqs:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").upper() == req_id_norm:
            return item

    return {"id": req_id}

def _extract_req_dependencies(req: Dict[str, Any]) -> List[str]:
    """
    Return normalized dependency REQ IDs from the target REQ.

    Supports both current and legacy plan.json field names.
    """
    raw = (
        req.get("dependsOn")
        or req.get("depends_on")
        or req.get("dependencies")
        or []
    )

    if not isinstance(raw, list):
        return []

    out: List[str] = []
    for item in raw:
        dep = _safe_text(item).upper()
        if dep and dep.startswith("REQ-") and dep not in out:
            out.append(dep)

    return out


def _build_workspace_inspection_policy(req_id: str, req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the read/write policy used by local agents.

    The agent may inspect promoted code and dependency KITs, but it may write
    only inside the target candidate KIT root.
    """
    dependency_req_ids = _extract_req_dependencies(req)

    return {
        "purpose": (
            "Before writing or repairing candidate files, inspect promoted code "
            "and dependency KITs so the target REQ remains E2E-compatible with "
            "already validated or previously generated work."
        ),
        "canonical_promoted_source_roots": ["src"],
        "canonical_promoted_test_roots": ["test", "tests"],
        "dependency_req_ids": dependency_req_ids,
        "dependency_kit_roots": [f"runs/kit/{dep}" for dep in dependency_req_ids],
        "target_candidate_root": f"runs/kit/{req_id}",
        "target_candidate_source_root": f"runs/kit/{req_id}/src",
        "target_candidate_test_root": f"runs/kit/{req_id}/test",
        "target_candidate_ci_root": f"runs/kit/{req_id}/ci",
        "target_candidate_docs_root": f"runs/kit/{req_id}/docs",
        "read_policy": (
            "Read canonical promoted roots and dependency KIT roots when present. "
            "Treat missing roots as explicit assumptions or gaps, not as permission "
            "to invent incompatible contracts."
        ),
        "write_policy": (
            "Write only inside the target candidate root. Never modify canonical "
            "src/, test/, tests/, docs/harper, dependency KIT roots, or git metadata."
        ),
    }

def _resolve_local_executor(payload: Dict[str, Any]) -> str:
    """
    Resolve a concrete local executor from the request payload.

    The extension is the actuator, so the orchestrator must return a concrete
    executor that the extension can actually run.
    """
    raw = _safe_text(payload.get("localAgentExecutor")).strip().lower()

    if raw in {"codex", "gpt-codex"}:
        raw = "gpt_codex"
    elif raw in {"claude", "claude-code"}:
        raw = "claude_code"

    capabilities = payload.get("localAgentCapabilities") or {}
    if not isinstance(capabilities, dict):
        capabilities = {}

    def available(name: str) -> bool:
        item = capabilities.get(name) or {}
        return bool(item.get("available"))

    if raw in {"claude_code", "gpt_codex"}:
        if available(raw) or not capabilities:
            return raw

    preferred = _safe_text(payload.get("localAgentPreferredExecutor")).strip().lower()
    if preferred in {"codex", "gpt-codex"}:
        preferred = "gpt_codex"
    elif preferred in {"claude", "claude-code"}:
        preferred = "claude_code"

    if preferred in {"claude_code", "gpt_codex"} and available(preferred):
        return preferred

    for candidate in ("claude_code", "gpt_codex"):
        if available(candidate):
            return candidate

    # Last fallback keeps backward compatibility for older clients that do not
    # send localAgentCapabilities.
    return "gpt_codex"


def _capability_index_names(capability_manifest: Dict[str, Any], kind: str) -> List[str]:
    """Return discovered capability names from CLIKE_CAPABILITY_INDEX.json content."""
    raw = str(capability_manifest.get("index_content") or "").strip()
    if not raw:
        return []

    try:
        index = json.loads(raw)
    except Exception:
        return []

    items = index.get(kind) or []
    if not isinstance(items, list):
        return []

    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            name = _safe_text(item.get("name")).lower()
            if name and name not in names:
                names.append(name)
    return names


def _build_capability_integrity(req: Dict[str, Any], capability_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Compare selected capabilities with discovered capabilities."""
    selected_skills = [str(x).strip() for x in (req.get("skills") or []) if str(x).strip()]
    selected_packs = [str(x).strip() for x in (req.get("packs") or []) if str(x).strip()]
    selected_design = [str(x).strip() for x in (req.get("design_profiles") or []) if str(x).strip()]

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
    """
    Return True if the REQ explicitly asks for concrete provider/runtime wiring.
    Looks for tokens such as boto3, aiobotocore, S3, SQS, SNS, Secrets Manager,
    CloudWatch, MinIO, Vault, or phrases like 'AWS implementations use' or
    'On‑prem implementations use' in functional/technical scope and acceptance.
    """
    chunks: List[str] = [
        _safe_text(req.get("technical_scope")),
        _safe_text(req.get("functional_scope")),
        _safe_text(req.get("main_module_boundary")),
    ]
    acceptance = req.get("acceptance") or []
    if isinstance(acceptance, list):
        chunks.extend([_safe_text(x) for x in acceptance])
    haystack = " ".join(chunks).lower()
    trigger_tokens = [
        "boto3", "aiobotocore", "s3", "sqs", "sns",
        "secrets manager", "cloudwatch",
        "minio", "vault", "vault‑compatible",
        "sdk", "aws implementations use", "on‑prem implementations use",
    ]
    return any(token in haystack for token in trigger_tokens)



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
        "packs": req.get("packs") or [],
        "skills": req.get("skills") or [],
        "design_profiles": req.get("design_profiles") or [],
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


def _build_recommended_outputs(
    req_id: str,
    req: Dict[str, Any],
    payload: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Build runtime-neutral recommended outputs.

    Dependency manifests must follow the project/runtime evidence.
    """
    payload = payload or {}
    blob = f"{_req_text_blob(req)}\n{_project_contract_text_blob(payload)}"

    recommended = [
        f"runs/kit/{req_id}/docs/README_{req_id}.md",
        f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
    ]

    node_markers = (
        "node",
        "node.js",
        "nodejs",
        "npm",
        "npm run",
        "package.json",
        "javascript",
        "typescript",
        "react",
        "vite",
        "express",
        "better-sqlite3",
    )
    python_markers = (
        "python",
        "pytest",
        "ruff",
        "mypy",
        "fastapi",
        "pyproject.toml",
        "requirements.txt",
    )

    if any(token in blob for token in node_markers):
        recommended.append(
            f"runs/kit/{req_id}/ci/package.json when REQ-local npm scripts or dependencies are needed"
        )
    elif any(token in blob for token in python_markers):
        recommended.append(
            f"runs/kit/{req_id}/ci/requirements.txt only when the target implementation stack is Python"
        )
    else:
        recommended.append(
            f"runs/kit/{req_id}/ci/<runtime-native-dependency-manifest> only when needed"
        )

    return recommended



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

    evidence_blob = f"{_req_text_blob(req)}\n{_project_contract_text_blob(payload)}"

    execution_areas: List[str] = []
    if any(token in evidence_blob for token in ("backend", "api", "rest",  "mendix-be", "server")):
        execution_areas.append("backend")
    if any(token in evidence_blob for token in ("frontend", "ui", "react",  "angular",  "mendix-fe", "vite", "browser")):
        execution_areas.append("frontend")
    if not execution_areas and any(token in evidence_blob for token in ("web_application", "web application", "fullstack", "full-stack")):
        execution_areas.extend(["backend", "frontend"])

    required_candidate_outputs = [
        f"runs/kit/{req_id}/src/",
        f"runs/kit/{req_id}/test/",
        f"runs/kit/{req_id}/ci/LTC.json",
        f"runs/kit/{req_id}/ci/HOWTO.md",
    ]

    recommended_outputs = _build_recommended_outputs(req_id, req, payload)

    runtime_manifest_policy = {
        "required": True,
        "scope": "KIT_EVAL_ONLY",
        "policy": (
            "If the KIT emits runnable source or tests, emit the runtime-native "
            "dependency manifest needed by the KIT evaluation harness under "
            f"runs/kit/{req_id}/ci/. This manifest is not the canonical application "
            "runtime manifest unless promotion later reconciles it explicitly."
        ),
        "examples": [
            f"runs/kit/{req_id}/ci/package.json for Node/npm ecosystems",
            f"runs/kit/{req_id}/ci/requirements.txt or ci/pyproject.toml for Python ecosystems",
            f"runs/kit/{req_id}/ci/pom.xml for Maven ecosystems",
            f"runs/kit/{req_id}/ci/go.mod for Go ecosystems",
            f"runs/kit/{req_id}/ci/RUNTIME_MANIFEST.md when the ecosystem has no standard manifest",
        ],
        "must_not": [
            f"Do not create runtime manifests under runs/kit/{req_id}/src/**.",
            "Do not emit Python requirements for non-Python implementations.",
            "Do not emit npm manifests for non-Node implementations.",
            "Do not add unrelated speculative dependencies.",
        ],
    }

    solution_launcher_policy = {
        "required_when_executable_area_exists": True,
        "scope": "SOLUTION_COMPOSITION_ROOT",
        "execution_areas_detected": execution_areas,
        "policy": (
            "When emitted code exposes an executable application area, generate or "
            "regenerate one coherent composition root per execution area. A launcher "
            "belongs to the solution area, not to the individual REQ. Do not create "
            "REQ-local app mains. Reuse existing repository launcher conventions when "
            "present; otherwise infer the minimal runtime-native launcher shape from "
            "SPEC, PLAN and TECH_CONSTRAINTS."
        ),
        "must_cover": [
            "backend application composition when backend/API/server modules exist",
            "frontend application composition when frontend/UI/browser modules exist",
            "stable exports/imports that wire generated feature modules into the executable area",
            "local runnable entry points documented in HOWTO and referenced by LTC where relevant",
        ],
        "must_not": [
            "Do not create one launcher per REQ.",
            "Do not hide runnable composition inside feature-only modules.",
            "Do not confuse KIT/EVAL manifests under ci/ with promotion-ready runtime manifests under candidate execution area roots.",
            "Do not put eval-only scripts, temp overlay paths, or REQ-specific eval paths in promotion-ready runtime manifests.",
            "Do not bypass existing canonical launcher files when repository evidence already provides them.",
        ],
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
            "role": "execution_area_runtime_manifest",
            "path_hint": f"runs/kit/{req_id}/src/<execution-area>/<ecosystem-native-runtime-manifest>",
            "kind": "source",
            "required": bool(execution_areas),
            "purpose": (
                "Promotion-ready runtime manifest for a runnable execution area. "
                "This is distinct from the ci/ eval manifest and must be inferred "
                "from SPEC, PLAN, TECH_CONSTRAINTS, FILE_REQUIREMENTS, and repository evidence."
            ),
            "must_cover": [
                "runtime dependencies required by the promoted execution area",
                "runtime scripts or launch metadata relative to the execution area root",
                "ecosystem-native manifest or module descriptor when the ecosystem uses one",
            ],
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
            "purpose": "One coherent launcher/composition root per executable area, solution-scoped rather than REQ-scoped.",
            "must_cover": solution_launcher_policy["must_cover"],
            "must_not_contain": solution_launcher_policy["must_not"],
        },
    ]

    provider_obligations: List[str] = []
    if provider_realism_required:
        provider_obligations.extend(
            [
                "Generic in-memory provider-shaped wrappers are not sufficient for this REQ.",
                "Concrete provider factory boundaries or SDK-backed adapters are mandatory when technical_scope explicitly names providers or SDKs.",
                "Local deterministic tests may use fakes, but runtime-facing code must expose real provider construction or provider-ready factory wiring.",
                "If concrete provider wiring is intentionally deferred, the KIT must explicitly mark the REQ as not promotable and describe the blocking gap.",
            ]
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
        "missing_selected_capabilities_blocking": bool(
            capability_integrity.get("missing_any_selected_capability")
        ),
        "forbidden": [
            "Do not write outside runs/kit/<REQ-ID>/.",
            "Do not modify canonical src/, test/, tests/, docs/harper, or dependency KIT roots.",
            "Do not infer implementation language from lane alone.",
            "Do not create one application launcher per REQ.",
            "Do not put eval-only manifests or eval-only scripts under runs/kit/<REQ-ID>/src/**.",
            "Do not omit promotion-ready runtime manifests for runnable execution areas merely because a ci/ eval manifest exists.",
            "Do not satisfy provider-heavy REQs with decorative or purely in-memory wrappers when concrete provider/runtime wiring is explicitly required.",
        ],
    }

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

    req = _extract_req_from_plan(payload, req_id)
    workspace_inspection_policy = _build_workspace_inspection_policy(req_id, req)
    capability_manifest = _extract_capability_manifest(payload)
    capability_integrity = _build_capability_integrity(req, capability_manifest)
    target_contract = _build_target_contract(req_id, req)
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
    allowed_write_roots = [
        f"runs/kit/{req_id}/src",
        f"runs/kit/{req_id}/test",
        f"runs/kit/{req_id}/ci",
        f"runs/kit/{req_id}/docs",
    ]

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
        "local_runtime": local_runtime,
        "req": req,
        "capability_context": {
            "lane": req.get("lane"),
            "domain": req.get("domain"),
            "runtime_profile": req.get("runtime_profile"),
            "packs": req.get("packs") or [],
            "skills": req.get("skills") or [],
            "design_profiles": req.get("design_profiles") or [],
            "gate_expectations": req.get("gate_expectations") or [],
            "main_module_boundary": req.get("main_module_boundary"),
            "future_compatibility_notes": req.get("future_compatibility_notes") or [],
            "manifest": capability_manifest,
            "integrity": capability_integrity,
        },
        "target_contract": target_contract,
        "file_requirements": file_requirements,
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
                
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
        },
        "hard_rules": [
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
            "Do not commit, branch, push, tag, or open pull requests.",
            "Respect capability_context from AGENT_EXECUTION_CONTEXT.json: lane, domain, runtime_profile, packs, skills, design_profiles, gate_expectations, main_module_boundary, future_compatibility_notes, and manifest content when available.",
            "Patch operations are allowed only under allowed_write_roots.",
            "Do not create or modify files outside runs/kit/<REQ-ID>/ for this phase.",
            "Never modify dependency KIT roots; they are read-only context for this target REQ.",
            "Do not install packages globally or into the system runtime.",
            "Do not infer the application implementation language from local_runtime.tool_hints.",
            "Infer the implementation runtime from SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, and repository evidence.",
            "Use local_runtime.tool_hints only as optional command hints after the implementation runtime is known.",
            "If package.json and npm scripts are present, prefer repository-native npm scripts for checks.",
            "If dependency installation is unavailable, report checks as environment-blocked and run repository-native smoke checks.",
            "Never install undeclared packages; only use dependencies declared by the project or the generated REQ-local validation contract.",
            "Before generating code, read docs/harper/PLAN.md and docs/harper/plan.json to identify the target REQ dependencies.",
            "Before generating code, inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when they exist.",
            "Before generating code, inspect canonical promoted source roots under src/ when they exist.",
            "Before generating tests, inspect canonical promoted test roots under test/ and tests/ when they exist.",
            "Generated code must be immediately promotable into canonical src/ and test roots without changing public contracts unexpectedly.",
            "If the KIT emits runnable source or tests, emit the runtime-native KIT eval manifest under runs/kit/<REQ-ID>/ci/, such as ci/package.json for Node/npm, ci/requirements.txt or ci/pyproject.toml for Python, pom.xml for Maven, go.mod for Go, or the ecosystem-native equivalent.",
            "If the KIT emits backend/frontend/service executable modules, provide one coherent solution-scoped launcher/composition entry per execution area when needed: one backend launcher, one frontend launcher, and one per separate service. Do not create one launcher per REQ.",
            "Launcher/composition files must live under the canonical execution area inside the candidate src tree, not under a REQ-local feature-only namespace unless the repository already uses that convention.",
            "Keep KIT/EVAL manifests under runs/kit/<REQ-ID>/ci/.",
            "If the KIT creates or updates a runnable execution area, also emit the ecosystem-native promotion-ready runtime manifest under runs/kit/<REQ-ID>/src/<execution-area>/.",
            "Do not hardcode runs/kit, ci/, temporary overlay paths, or REQ-specific eval paths in promotion-ready runtime manifests.",
            "It is allowed to regenerate files already emitted by previous KITs when they are functionally required for the current KIT; CLike promotion/merge handles reconciliation later.",
            "Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical src/test roots. If needed you can extend the module/file with all necessary code in the current req, but we need to be sure that the generated code is consistent with the dependency KITs and canonical roots for applying unified diffs later.",
            "Reuse dependency KIT contracts and canonical source contracts whenever they exist.",
            "If a dependency KIT or canonical source root is missing, explicitly report it as an implementation assumption or gap.",
            "Produce repository-aware, dependency-aware, promotable candidate code and tests.",
            "Prefer the clearest, readable, and well-structured implementation that fully satisfies the REQ acceptance criteria, stays aligned with repository patterns, and remains directly promotable without decorative architecture.",
        ],
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            f"# Local Agent KIT Execution Package — {req_id}",
            "",
            "You are executing a local-agent candidate generation task owned by the orchestrator.",
            "The extension is only a local actuator. The orchestrator owns workflow state, policy, and promotion.",
            "",
            "Read these files first:",
            f"- runs/kit/{req_id}/docs/AGENT_EXECUTION_CONTEXT.json",
            f"- runs/kit/{req_id}/docs/TARGET_CONTRACT.json",
            f"- runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json",
            f"- runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md when present",
            "",
            f"Target REQ: {req_id}",
            "",
            "Strict rules:",
            "- Follow AGENT_EXECUTION_CONTEXT.json as the primary execution contract.",
            "- Read workspace_inspection_policy before designing the implementation.",
            "- Inspect promoted src/test roots and dependency KIT roots listed in workspace_inspection_policy before writing.",
            "- Treat canonical src/test roots as promoted truth and dependency KIT roots as E2E contract evidence.",
            "- Read and respect capability_context before designing the implementation.",
            "- Prefer CLIKE_SELECTED_CAPABILITY_CONTEXT.md over the generic full manifest when selected capability guidance exists.",
            "- Use main_module_boundary to keep the implementation focused and avoid scattered files.",
            "- Treat selected skills, packs, and design profiles as mandatory REQ constraints only when they affect this REQ.",
            "- Prefer CLIKE_SELECTED_CAPABILITY_CONTEXT.md over the generic full manifest when selected capability guidance exists.",
            "- Do not add decorative architecture just to show that a capability was used.",
            "- Follow this agentic protocol before writing files: inspect contracts, identify the clearest promotable provider-realistic implementation shape that fully covers the REQ, organize source/tests/docs/LTC as one coherent and readable slice, and then run or document executable checks.",
            """- Before writing any code, read docs/harper/PLAN.md and docs/harper/plan.json.
            - Identify the target REQ dependencies from the plan.
            - Inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when present.
            - Inspect canonical promoted source roots under src/ when present.
            - Inspect canonical promoted test roots under test/ and tests/ when present.
            - Reuse existing dependency KIT contracts and canonical source/test contracts.
            - Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical roots.
            - Generate candidate code that is directly promotable into canonical src/test roots.
            - If a dependency KIT, canonical source root, or canonical test root is missing, explicitly report the gap before generating the implementation.
            - Treat selected skills, packs, and design profiles as mandatory REQ constraints.
            - If a selected capability is missing from the capability manifest/index, report a blocking capability-context gap and do not silently relax the obligation.
            """,
            "- Write only under the allowed candidate roots.",
            "- Do not modify canonical src/, test/, tests/ roots.",
            "- Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "- Do not perform git operations.",
            "- Do not promote candidate files into canonical workspace roots.",
            "",
            "Required candidate outputs:",
            f"- runs/kit/{req_id}/src/...",
            f"- runs/kit/{req_id}/test/...",
            f"- runs/kit/{req_id}/ci/LTC.json",
            f"- runs/kit/{req_id}/ci/HOWTO.md",
            "",
            "Recommended candidate outputs:",
            f"- runs/kit/{req_id}/docs/README_{req_id}.md",
            f"- runs/kit/{req_id}/docs/KIT_{req_id}.md",
            f"- runs/kit/{req_id}/ci/runtime-dependency manifest **MADATORY**, e.g. ci/package.json for Node/npm or ci/requirements.txt for Python",
            f"- runs/kit/{req_id}/ci/package.json for Node/npm KITs when source/tests need npm scripts or dependencies",
            f"- runs/kit/{req_id}/ci/requirements.txt only for Python KITs",
            "",
            "At the end, print a concise summary with:",
            "- target REQ and detected dependencies;",
            "- dependency KITs inspected;",
            "- canonical src/test roots inspected;",
            "- files created/updated;",
            "- existing contracts reused;",
            "- commands run;",
            "- tests/lint/type checks executed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
            "",
            """- Use the project/runtime evidence declared in SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, AGENT_EXECUTION_CONTEXT.json, and repository files.
            - Do not infer the application implementation language from local_runtime.tool_hints.
            - local_runtime.tool_hints are optional command hints only after the implementation runtime is known.
            - If package.json and npm scripts are present, prefer repository-native npm scripts such as `npm run test`, `npm run lint`, and `npm run build`.
            - Keep KIT/EVAL manifests under `runs/kit/<REQ-ID>/ci/`.
            - If you create or update a runnable execution area, also emit the ecosystem-native promotion-ready runtime manifest under that execution area's candidate source root.
            - Runtime manifests must use paths relative to their own execution area root and must not contain runs/kit, ci/, temporary overlay paths, or REQ-specific eval paths.
            - Use Python only when the SPEC, PLAN, TECH_CONSTRAINTS, TARGET_CONTRACT, FILE_REQUIREMENTS, or repository evidence explicitly identifies Python as the implementation stack.
            
            - A backend lane does not mean Python.
            - If SPEC.md or TECH_CONSTRAINTS.yaml declares Node.js, Express, React, Vite, npm, JavaScript, or TypeScript, emit JavaScript/TypeScript ecosystem files and a KIT-local ci/package.json.
            - Use Python only when the SPEC, PLAN, TECH_CONSTRAINTS, TARGET_CONTRACT, FILE_REQUIREMENTS, or repository evidence explicitly identifies Python as the implementation stack.
            - Do not create Python files and virtualenv for non-Python projects merely because Python is available locally.
            - Do not install packages globally or into the system runtime.
            - If dependencies cannot be installed because the environment is offline, externally managed, or blocked by policy, report the check as environment-blocked and run repository-native compile/smoke checks instead.
            - Environment-blocked fallback never relaxes provider obligations declared in TARGET_CONTRACT.json and FILE_REQUIREMENTS.json.
            - For provider-heavy REQs, generic in-memory provider-shaped wrappers are not sufficient when concrete provider/runtime wiring is explicitly required by technical_scope.
            - Patch operations are allowed only under the allowed_write_roots declared in AGENT_EXECUTION_CONTEXT.json.
            """,
        ]
    )

    context_path = f"runs/kit/{req_id}/docs/AGENT_EXECUTION_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_PROMPT.md"

    return {
        "ok": True,
        "phase": "kit",
        "echo": f"Local agent execution package prepared for {req_id}",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
        ],
        "errors": [],
        "runId": run_id,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "phase_supported": execution_policy.get("phase_supported"),
        },
        "local_agent": {
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:kit",
            "phase": "kit",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": {
                "schema_version": "clike.local_agent_invocation.v1",
                "executor": local_executor,
                "command_ref": local_executor,
                "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
                "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
                "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
                "cwd": ".",
            },
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "expected_outputs": context["expected_outputs"],
            "package_files": [
                {
                    "path": context_path,
                    "content": context_json,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": prompt_path,
                    "content": prompt,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/TARGET_CONTRACT.json",
                    "content": json.dumps(target_contract, indent=2, ensure_ascii=False),
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json",
                    "content": json.dumps(file_requirements, indent=2, ensure_ascii=False),
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                (
                    [
                        {
                            "path": f"runs/kit/{req_id}/docs/AGENT_INPUT_AUDIT.json",
                            "content": agent_input_audit_json,
                            "mime": "application/json",
                            "encoding": "utf-8",
                        },
                        {
                            "path": f"runs/kit/{req_id}/docs/AGENT_INPUT_AUDIT.md",
                            "content": agent_input_audit_md,
                            "mime": "text/markdown",
                            "encoding": "utf-8",
                        },
                    ]
                    if include_agent_input_audit
                    else []
                ),
                {
                    "path": f"runs/kit/{req_id}/docs/AGENT_INPUT_AUDIT.md",
                    "content": agent_input_audit_md,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_MANIFEST.md",
                    "content": standalone_capability_manifest,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json",
                    "content": standalone_capability_index,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
                    "content": standalone_selected_capability_context,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
                {
                    "path": f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
                    "content": standalone_selected_capability_context_json,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
            ],
        },
    }


def build_eval_local_agent_package(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for /eval pre-pass.

    The local agent is not the judge.
    It may harden candidate code/tests only under runs/kit/<REQ-ID>/.
    Canonical CLike eval still runs after this pre-pass.
    """
    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"eval-local-{req_id}"
    local_executor = _resolve_local_executor(payload)

    req = _extract_req_from_plan(payload, req_id)
    workspace_inspection_policy = _build_workspace_inspection_policy(req_id, req)
    capability_manifest = _extract_capability_manifest(payload)
    capability_integrity = _build_capability_integrity(req, capability_manifest)

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
        "local_runtime": local_runtime,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_canonical_eval_only_when_not_local_agent_only",
        },
        "req": req,
        "capability_context": {
            "lane": req.get("lane"),
            "domain": req.get("domain"),
            "runtime_profile": req.get("runtime_profile"),
            "packs": req.get("packs") or [],
            "skills": req.get("skills") or [],
            "design_profiles": req.get("design_profiles") or [],
            "gate_expectations": req.get("gate_expectations") or [],
            "main_module_boundary": req.get("main_module_boundary"),
            "future_compatibility_notes": req.get("future_compatibility_notes") or [],
            "manifest": capability_manifest,
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
            "ltc_json_path": f"runs/kit/{req_id}/ci/LTC.json",
            "howto_md_path": f"runs/kit/{req_id}/ci/HOWTO.md",
            "kit_notes_path": f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            "readme_path": f"runs/kit/{req_id}/docs/README_{req_id}.md",
        },
        "workspace_inspection_policy": workspace_inspection_policy,
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
                f"runs/kit/{req_id}/ci/requirements.txt",
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
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
            "This is an eval pre-pass, not the canonical eval judge.",
            "After this pre-pass, CLike canonical /eval must still run and decide pass/fail.",
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
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

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            f"# Local Agent EVAL Pre-Pass Package — {req_id}",
            "",
            "You are a local software-generation agent executing a CLike Harper /eval pre-pass package.",
            "The orchestrator is the workflow owner. The VS Code extension is only the actuator.",
            "The canonical CLike eval remains the final judge and will run after your pre-pass.",
            "",
            "Read this file before acting:",
            f"- runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json",
            "",
            f"Target REQ: {req_id}",
            "",
            "Strict rules:",
            "- Follow AGENT_EVAL_CONTEXT.json as the primary execution contract.",
            "- Read capability_context, including capability_context.manifest.content when available.",
            "- Use selected skills, packs, runtime profile, design profile, and gate expectations as repair constraints.",
            "- Apply capability guidance only when relevant to this REQ; do not create decorative fixes.",
            "- Use main_module_boundary to avoid scattering repairs across unrelated files.",
            "- This is an eval pre-pass: you may execute checks, diagnose failures, harden candidate code/tests, and repair LTC/HOWTO when they are wrong.",
            "- You must not declare the final eval result. Canonical CLike EvalRunner remains the judge.",
            "- Before writing anything, read docs/harper/PLAN.md and docs/harper/plan.json.",
            "- Identify the target REQ dependencies from the plan.",
            "- Inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when present.",
            "- Inspect candidate source roots under runs/kit/<REQ-ID>/src.",
            "- Inspect candidate test roots under runs/kit/<REQ-ID>/test.",
            "- Inspect candidate CI/eval contracts under runs/kit/<REQ-ID>/ci, especially LTC.json and HOWTO.md.",
            "- Inspect canonical promoted source roots under src/ when present.",
            "- Inspect canonical promoted test roots under test/ and tests/ when present.",
            "- Reuse existing dependency KIT contracts and canonical source/test contracts.",
            "- Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical roots.",
            "- You may extend candidate tests if they are not exhaustive enough for the REQ acceptance criteria.",
            "- You may use mocks/stubs only inside candidate tests and only for external infrastructure boundaries.",
            "- Do not mock the business logic under test.",
            "- Write only under allowed_write_roots from AGENT_EVAL_CONTEXT.json.",
            "- Do not modify canonical src/, test/, tests/ roots.",
            "- Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "- Do not perform git operations.",
            "- Do not promote candidate files into canonical workspace roots.",
            "- Generate files needed to make the KIT runnable and evaluable; promotion/merge reconciliation is owned by CLike, not by the agent.",
            "- **IMPRTANT** If the KIT needs runtime-dependecy-manifesta as package.json, requirements.txt, pyproject.toml, or another runtime manifest to run tests, emit it under the target KIT root.",
            "- If launch/composition wiring is needed, emit one coherent backend launcher, one frontend launcher, or one per separate service as applicable. Do not create one launcher per REQ.",
            "- Use LTC/HOWTO and repository-native tooling to choose the eval runtime.",
            "- Do not infer the application implementation language from local_runtime.tool_hints.",
            "- local_runtime.tool_hints are optional command hints only after the eval runtime is known.",
            "- Do not install packages globally or into the system runtime.",
            "- Do not create a Python virtualenv for non-Python projects.",
            "- If package.json and npm scripts are present, prefer repository-native npm scripts for eval checks.",
            "- If dependencies cannot be installed because the environment is offline, externally managed, or blocked by policy, report the check as environment-blocked and run dependency-free compile/smoke checks instead.",
            "- Patch operations are allowed only under allowed_write_roots.",
            "",
            "Required eval actions:",
            f"- Read runs/kit/{req_id}/ci/LTC.json.",
            f"- Read runs/kit/{req_id}/ci/HOWTO.md when present.",
            f"- Inspect runs/kit/{req_id}/src and runs/kit/{req_id}/test.",
            "- Inspect promoted src/test roots and dependency KIT roots listed in workspace_inspection_policy when present.",
            "- Execute the LTC/HOWTO commands when possible.",
            "- If LTC.json is malformed, incomplete, or not executable, repair LTC.json under runs/kit/<REQ-ID>/ci before changing source code.",
            "- Ensure LTC.json contains a non-empty cases[] execution contract.",
            "- Each LTC cases[] entry must include `run` as the canonical executable command field; `command` may be duplicated as a backward-compatible alias.",
            "- commands[] may exist only as human-readable aliases and must not be the only executable contract.",
            "- Repair candidate code/tests under allowed_write_roots when checks fail for code reasons.",
            "- If checks are blocked by missing infrastructure, mark or document the blockage instead of faking success.",
            "- Create reports under runs/kit/<REQ-ID>/reports when useful.",
            "",
            "At the end, print a concise summary with:",
            "- target REQ and detected dependencies;",
            "- dependency KITs inspected, including exact paths or missing-root notes;",
            "- canonical promoted src/test roots inspected, including exact paths or missing-root notes;",
            "- candidate files created/updated;",
            "- tests extended or added;",
            "- existing contracts reused;",
            "- commands run;",
            "- tests/lint/type checks executed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
        ]
    )

    context_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_PROMPT.md"

    return {
        "ok": True,
        "phase": "eval",
        "echo": f"Local agent eval pre-pass package prepared for {req_id}",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-eval-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
            "canonical_eval_still_required",
        ],
        "errors": [],
        "runId": run_id,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "phase_supported": execution_policy.get("phase_supported"),
        },
        "local_agent": {
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:eval",
            "phase": "eval",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": {
                "schema_version": "clike.local_agent_invocation.v1",
                "executor": local_executor,
                "command_ref": local_executor,
                "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
                "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
                "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
                "cwd": ".",
            },
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
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
            },
            "package_files": [
                {
                    "path": context_path,
                    "content": context_json,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": prompt_path,
                    "content": prompt,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
            ],
        },
       }


def normalize_local_agent_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize the extension actuator result back into a Harper-compatible envelope.
    """
    phase = _safe_text(payload.get("phase")) or "kit"
    req_id = _safe_text(payload.get("req_id")).upper()
    run_id = _safe_text(payload.get("runId")) or _safe_text(payload.get("run_id"))

    files = payload.get("files") or []
    stdout = _safe_text(payload.get("stdout"))
    stderr = _safe_text(payload.get("stderr"))
    exit_code = payload.get("exit_code")

    expected_prefix = f"runs/kit/{req_id}/"
    bad_paths: List[str] = []
    normalized_files: List[Dict[str, Any]] = []

    for item in files:
        if not isinstance(item, dict):
            continue
        file_path = _safe_text(item.get("path"))
        content = item.get("content")
        if not file_path:
            continue
        if not file_path.startswith(expected_prefix):
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

    if not normalized_files:
        ok = False
        errors.append(f"no_candidate_files_returned_for:{req_id}")
        if exit_code_non_zero:
            errors.append(f"local_agent_exit_code:{exit_code}")
    elif exit_code_non_zero:
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