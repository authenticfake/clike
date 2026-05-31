from __future__ import annotations

import json
import re

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

def _capability_manifest_for_agent_context(
    req_id: str,
    capability_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Keep AGENT_*_CONTEXT.json compact.

    The full capability files are already written as standalone package files.
    Re-embedding them inside AGENT_*_CONTEXT.json creates huge duplicated prompts
    and weakens agent focus. The context should expose availability and paths;
    the agent prompt tells the agent which files to read.
    """
    return {
        "available": bool(capability_manifest.get("available")),
        "manifest_name": capability_manifest.get("manifest_name") or "CLIKE_CAPABILITY_MANIFEST.md",
        "manifest_path": f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_MANIFEST.md",
        "index_name": capability_manifest.get("index_name") or "CLIKE_CAPABILITY_INDEX.json",
        "index_available": bool(capability_manifest.get("index_available")),
        "index_path": f"runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json",
        "selected_context_name": capability_manifest.get("selected_context_name") or "CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
        "selected_context_available": bool(capability_manifest.get("selected_context_available")),
        "selected_context_path": f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
        "selected_context_json_name": capability_manifest.get("selected_context_json_name") or "CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
        "selected_context_json_path": f"runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
        "usage": (
            "Read the selected capability context file first when available. "
            "Do not rely on duplicated embedded capability content in AGENT_*_CONTEXT.json."
        ),
    }


def _dedupe_rules(rules: Any) -> List[str]:
    """Deduplicate prompt/context rules while preserving first occurrence order."""
    if not isinstance(rules, list):
        return []

    seen: set[str] = set()
    out: List[str] = []

    for item in rules:
        text = _safe_text(item)
        if not text:
            continue

        normalized = re.sub(r"\s+", " ", text).strip().lower()
        normalized = normalized.removeprefix("- ").strip()

        if normalized in seen:
            continue

        seen.add(normalized)
        out.append(text)

    return out


def _methodology_context_for_local_agent(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return compact CLike-resolved methodology context for local-agent packages."""
    raw = payload.get("methodology_context")
    if not isinstance(raw, dict) or not raw.get("methodology"):
        return None

    profile = raw.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    allowed_agents = raw.get("allowed_agents") or []
    if not isinstance(allowed_agents, list):
        allowed_agents = []

    return {
        "methodology": raw.get("methodology"),
        "methodology_name": raw.get("methodology_name"),
        "phase": raw.get("phase"),
        "agent": raw.get("agent"),
        "requested_agent": raw.get("requested_agent"),
        "default_agent": raw.get("default_agent"),
        "allowed_agents": allowed_agents,
        "advisory_only": bool(raw.get("advisory_only", False)),
        "authority": raw.get("authority") or "methodology_profile",
        "profile": {
            "id": profile.get("id"),
            "title": profile.get("title"),
            "summary": profile.get("summary"),
        },
        "governance_boundaries": [
            "CLike remains the governance runtime and source of truth.",
            "Methodology guidance is not an executor selection mechanism.",
            "Methodology guidance cannot override CLike phase contracts, eval/gate policy, allowed_write_roots, forbidden_paths, candidate isolation, or output schemas.",
            "BMAD developer guidance must not expand write permissions.",
            "If methodology guidance conflicts with CLike rules, follow CLike.",
        ],
    }


def _render_methodology_prompt_block(methodology_context: Optional[Dict[str, Any]]) -> str:
    if not methodology_context:
        return ""

    profile = methodology_context.get("profile") or {}
    return "\n".join(
        [
            "",
            "Methodology profile:",
            f"- methodology: {methodology_context.get('methodology')}",
            f"- role: {methodology_context.get('agent') or 'none'}",
            f"- authority: {methodology_context.get('authority')}",
            f"- advisory_only: {bool(methodology_context.get('advisory_only'))}",
            f"- role_summary: {profile.get('summary') or ''}",
            "- Methodology guidance cannot override allowed_write_roots, forbidden_paths, CLike governance, candidate isolation, eval/gate policy, or output contracts.",
        ]
    )


def _render_compact_local_agent_prompt(
    *,
    phase: str,
    req_id: str,
    context_path: str,
    methodology_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a compact agent prompt and keep detailed policy in AGENT_*_CONTEXT.json."""
    phase_label = phase.upper()
    action = "generate the candidate KIT" if phase == "kit" else "harden the candidate KIT before canonical eval"

    return "\n".join(
        [
            f"# Local Agent {phase_label} Package — {req_id}",
            "",
            "You are executing a CLike Harper local-agent package.",
            "The orchestrator owns workflow state, policy, and promotion.",
            "The VS Code extension is only the local actuator.",
            "",
            f"Target REQ: {req_id}",
            f"Task: {action}.",
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read first:",
            f"- {context_path}",
            f"- runs/kit/{req_id}/docs/TARGET_CONTRACT.json when present",
            f"- runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json when present",
            f"- runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md when present",
            f"- runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json when present",
            "",
            "Execution rules:",
            "Execution rules:",
            "- Follow AGENT_*_CONTEXT.json as the source of truth.",
            "- For EVAL hardening, if a REQ-local ci/package.json exists, run `npm install --prefix runs/kit/<REQ-ID>/ci --no-audit --no-fund` before declaring npm, TypeScript, lint, test, or security checks environment-blocked. This is a local declared dependency install, not a global install.",
            "- For EVAL hardening, do not report TypeScript/tsc as environment-blocked until the REQ-local install command has been attempted and failed with concrete network, registry, filesystem, or policy evidence.",
            "- Write only under allowed_write_roots.",
            "- Do not run git commands.",
            "- Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.",
            "- Do not modify canonical src/, test/, tests/, docs/harper, dependency KIT roots, or git metadata.",
            "- Inspect dependency KITs and canonical roots before writing or repairing candidate files.",
            "- Reuse existing contracts before creating new modules, helpers, adapters, or test utilities.",
            "- Run the smallest relevant checks and report exact commands and outcomes.",
            "- For EVAL hardening, repair from the actual failing diagnostics, not from generic policy. Read the failing command stdout/stderr, identify exact file:line diagnostics, patch only those candidate-owned files, then rerun the same failing command.",
            "- Do not return the hardening pass as complete while the same blocking command still reports candidate-owned diagnostics of the same class, such as TS2339, TS18046, lint errors, syntax errors, or raw-secret findings in candidate-owned files.",
            "- Continue focused repair/rerun cycles up to max_repair_cycles_inside_agent when the same check keeps failing with remaining candidate-owned diagnostics.",
            "- For typecheck failures, repair candidate-owned source/tests/CI instead of reporting success or environment-blocked when the declared local dependencies can be installed.",
            "- For union response shape failures, decide whether the missing field is part of the stable public contract. If yes, repair the service/producer response shape. If no, repair the test with explicit narrowing before field access.",
            "- For caught errors typed as unknown, use a typed helper/adapter before asserting classification, retryable, status/statusCode, or domain failure categories.",
            "- For Node/JavaScript checkJs tests, assert.throws() and assert.rejects() callbacks receive unknown errors. After `error instanceof SomeError`, add `const typedError = /** @type {SomeError} */ (error);` and read custom fields only from typedError.",
            "- Do not weaken tests, type checks, security checks, gate policy, or public contracts to hide failures.",
            "",
            "Return a concise summary with files changed, commands run, checks passed/failed, and unresolved gaps.",
        ]
    )


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
            "belongs to the execution area, not to the individual REQ and not to a "
            "feature/domain namespace. One launcher per execution area is allowed "
            "and expected when required. Do not create REQ-local app mains. Reuse existing "
            "repository launcher conventions when present; otherwise infer the minimal "
            "runtime-native launcher shape from SPEC, PLAN and TECH_CONSTRAINTS."
        ),
        "must_cover": [
            "backend application composition when backend/API/server modules exist",
            "frontend application composition when frontend/UI/browser modules exist",
            "stable exports/imports that wire generated feature modules into the executable area",
            "local runnable entry points documented in HOWTO and referenced by LTC where relevant",
        ],
         "must_not": [
            "Do not create one launcher per REQ.",
            "Do not create one launcher per feature/domain namespace; one launcher per execution area such as backend, frontend, worker, or CLI is allowed and expected when required.",
            "Do not hide runnable composition inside feature-only modules.",
            "Do not place new launchers under domain namespaces such as src/<domain>/api/app.* unless the repository already uses that convention.",
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
            "must_cover": [
                "adapter or factory modules for every named obligation that is relevant to this REQ",
                "lazy import or runtime-native optional dependency handling when the library is heavy or environment-specific",
                "fail-fast errors with clear setup guidance when required runtime libraries are unavailable",
                "deterministic local tests using fixtures/fakes only around external engine execution, not around business orchestration",
                "runtime-native dependency declaration in ci manifest, source manifest, optional extras, or equivalent ecosystem descriptor when applicable",
                "heavy AI/model/runtime libraries must be declared as source runtime optional extras or optional smoke dependencies, not as blocking ci/eval dependencies, when deterministic fake-client tests cover the local eval path",
                "narrow ecosystem-native static-analysis handling at the external adapter/import boundary when a mature external library lacks typing, stubs, metadata, or analyzer support",
            ],
            "must_not_contain": [
                "Protocol-only or interface-only implementation when named libraries are explicitly required",
                "external model downloads or network service startup in blocking local eval",
                "heavy AI/model/runtime packages in blocking ci/eval manifests when deterministic fake-client tests are sufficient",
                "sensitive extracted text, prompt content, or document payloads in logs",
                "business logic coupled directly to provider SDKs or engine-specific APIs",
                "global static-analysis disables for external library typing/analyzer gaps; suppress or wrap only at the adapter/import boundary with the narrowest ecosystem-native mechanism",
            ],
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
            [
                "Generic in-memory provider-shaped wrappers are not sufficient for this REQ.",
                "Official or widely adopted ecosystem SDKs are preferred inside adapter/infrastructure boundaries when concrete providers are named.",
                "Do not reimplement provider protocols, auth/signing, wire formats, or client behavior when a mature SDK exists.",
                "Concrete provider factories or SDK-backed adapters are mandatory when technical_scope explicitly names providers, runtime services, or SDK-backed infrastructure.",
                "Provider SDK imports are allowed inside adapter, provider factory, infrastructure, or integration boundary modules.",
                "Business-facing contracts must remain provider-independent and must not expose provider SDK types unless SPEC explicitly requires it.",
                "Local deterministic tests may use fakes, SDK stubs, or official mock helpers, but runtime-facing code must expose real provider construction or SDK-backed factory wiring.",
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
            "boundary_rules": [
                "Do not reimplement mature external tools when an official or widely adopted library exists.",
                "Keep business orchestration independent from engine-specific APIs.",
                "Use adapters/factories to isolate heavy OCR, parser, classifier, vector, model, storage, queue, or provider runtimes.",
                "Use deterministic fixtures/fakes only for external execution boundaries in tests.",
                "Handle untyped or analyzer-unsupported external libraries with the narrowest ecosystem-native suppression or wrapper at the adapter/import boundary only.",
                "Never disable lint, type, or security checks globally to hide external library typing/analyzer gaps.",
                "If a named library is intentionally deferred, mark the KIT non-promotable and list the missing obligation.",
            ],
        },
        "provider_sdk_policy": {
            "official_or_consolidated_sdks_preferred": True,
            "policy": (
                "When a REQ names concrete providers or runtime services, official or widely adopted ecosystem SDKs "
                "must be used inside adapter/infrastructure boundaries unless SPEC explicitly forbids them."
            ),
            "boundary_rules": [
                "Do not reimplement provider protocols, auth/signing, wire formats, or client behavior when a mature SDK exists.",
                "Provider SDK imports are allowed inside adapter, provider factory, infrastructure, or integration boundary modules.",
                "Business-facing contracts must remain provider-independent.",
                "Business modules must not instantiate provider SDK clients directly.",
                "Tests may use SDK stubs, official mock helpers, or deterministic fake clients, but runtime-facing code must expose real SDK-backed wiring when provider realism is required.",
            ],
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
    methodology_context = _methodology_context_for_local_agent(payload)

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
        **({"methodology_context": methodology_context} if methodology_context else {}),
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
            "manifest": context_capability_manifest,
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
                f"runs/kit/{req_id}/ci/pom.xml only for Java KITs",
                f"runs/kit/{req_id}/ci/package.json only for Node KITs",
                
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
        },
        "hard_rules": [
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
            "Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.", 
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
            "For Node/TypeScript frontend KITs with a runnable package under src/frontend, LTC.json must set top-level package_json to runs/kit/<REQ-ID>/src/frontend/package.json so CLike installs the actual frontend dependencies before typecheck, test, lint, or build.",
            "For Node/TypeScript frontend KITs, Vitest/Jest/ESLint/TypeScript config files imported by npm scripts must live inside the same package root as package.json, for example runs/kit/<REQ-ID>/src/frontend/vitest.config.ts. Tests may live in runs/kit/<REQ-ID>/test, but configs must not live outside the package root when they import package dependencies such as vitest/config.",
            "For Node/TypeScript frontend KITs, every package imported by test setup files, Vitest/Jest config files, component tests, accessibility tests, or test utilities must be declared in the runnable package devDependencies. For example, if test/setup.ts imports @testing-library/jest-dom/vitest, src/frontend/package.json must include @testing-library/jest-dom in devDependencies.",
            "For Node/TypeScript frontend KITs, avoid brittle UI test selectors such as getAllByLabelText(...)[1] or getAllByRole(...)[n] when route composition can change. Prefer scoped queries with within(container), unique accessible names, test-specific render roots, or explicit route/page components.",
            "Generated commands may execute from CLIKE_EVAL_WORKSPACE/src/frontend, but dependency installation must target the same execution-area manifest resolved by CLike.",
            "For Node/TypeScript frontend KITs where tests live outside the runnable package root, for example runs/kit/<REQ-ID>/test while package_json points to runs/kit/<REQ-ID>/src/frontend/package.json, the test runner config must make external test dependencies resolvable from the runnable package. Prefer one of these safe patterns: place tests under the runnable package root, or add explicit Vitest/Jest aliases for every external test import such as @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jest-axe, and any generated test utility packages.",
            "Do not assume that installing dependencies under src/frontend/node_modules makes imports from runs/kit/<REQ-ID>/test automatically resolvable. CLike EvalRunner may execute tests from an overlay workspace where dependency installation and test source roots are intentionally separated.",
            "If dependency installation is unavailable, report checks as environment-blocked and run repository-native smoke checks.",
            "Never install undeclared packages; only use dependencies declared by the project or the generated REQ-local validation contract.",
            "Before generating code, read docs/harper/PLAN.md and docs/harper/plan.json to identify the target REQ dependencies and whether the REQ owns or merely contributes to an execution area.",
            "Before generating code, inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when they exist.",
            "Before generating code, inspect canonical promoted source roots under src/ when they exist.",
            "If a dependency REQ appears both in canonical promoted src/ and in runs/kit/<DEPENDENCY_REQ_ID>/src, treat canonical src/ as the promoted source of truth. Use dependency KIT roots only as read-only historical/evidence context unless the dependency is not promoted yet or the execution context explicitly marks it as required.",
            "Before generating tests, inspect canonical promoted test roots under test/ and tests/ when they exist.",
            "When the target REQ intentionally changes or extends behavior already covered by promoted tests, reconcile those regression tests inside the current candidate test root. Do not modify canonical test/ or tests/ roots. Instead, create an updated same-relative-path candidate test file when the CLike overlay must shadow stale promoted expectations.",
            "For additive frontend/backoffice REQs, do not leave promoted UI tests stale when the REQ adds routes, navigation entries, RBAC-visible sections, form fields, or capability pages. Update candidate tests to prove backward compatibility plus the intentional new behavior.",
            "Reuse before create: extend or integrate existing dependency KIT and promoted contracts/modules before creating new shared concepts, duplicate adapters, duplicate enums, duplicate launchers, or duplicate composition roots.",
            "Generated CI scripts must consume the official CLike eval workspace when checking runtime source/test behavior.",
            "Generated raw-secret scanners must scan only candidate-owned evidence: runs/kit/<REQ-ID>/src, runs/kit/<REQ-ID>/test, runs/kit/<REQ-ID>/tests, runs/kit/<REQ-ID>/docs, and candidate-owned ci scripts/contracts.",
            "Generated raw-secret scanners must never scan installed dependency, vendor, generated, cache, report, or temporary workspace directories such as node_modules, .git, .cache, .tmp, coverage, dist, build, local-eval-workspaces, __pycache__, .venv, .next, package-manager caches, or generated overlay workspaces.",
            "Do not weaken secret patterns to hide findings. If a raw-secret finding is under candidate-owned source/test/docs/ci files, keep it blocking. If findings are only under dependency/vendor/generated directories, repair the scanner scope instead.",
            "Dependency vulnerability, license, or supply-chain checks belong to separate SCA/audit gates such as npm audit, not to raw-secret scanning of node_modules README files.",
            "Generated Node CI scripts, but for all CI scripts indipendent from language-specific tools (i.e.:python, java, ts, js, go, rust,  c, cpp, c#,...), that use mkdtemp, temporary overlays, local-eval-workspaces, or report directories must prefer CLIKE_EVAL_TEMP_ROOT when present, then create the parent directory first with mkdir(..., { recursive: true }) before writing or calling mkdtemp.",
            "For typed or statically checked runtimes, generated source, tests, and CI scripts must access custom exception/error metadata only after using the language-native narrowing, casting, matching, or typed-exception mechanism.",
            "For Node/JavaScript tests checked by TypeScript checkJs, callbacks passed to assert.throws() or assert.rejects() receive an unknown error value. After asserting `error instanceof SomeError`, always introduce a JSDoc cast such as `const typedError = /** @type {SomeError} */ (error);` and read custom fields such as `issues`, `code`, `classification`, `retryable`, `statusCode`, or `metadata` only from the typed variable.",
            "Generated candidate tests must preserve assertions on error semantics, but must assert through a narrowed or adapted error value instead of directly reading fields from a generic exception/error/object.",
            "Generated CI utility scripts must use small safe helper/adaptor functions for platform-specific error metadata such as code, errno, syscall, path, status/statusCode, cause, provider codes, classification, retryable, or domain failure categories.",
            "Do not disable type checking, relax compiler/linter settings, remove meaningful assertions, or widen all failures to untyped catch-all values merely to pass EVAL. Repair candidate-owned code/tests/CI with language-idiomatic typed error handling.",
            "Generated static file-contract checks that validate KIT-local ci/docs artifacts must resolve the KIT root relative to the script location, not from CLIKE_EVAL_WORKSPACE, because the overlay workspace may intentionally omit ci/docs files.",
            "Generated CI scripts must not create a second temporary overlay when an official CLike eval workspace is available.",
            "Generated helpers such as createOverlayWorkspace, prepareWorkspace, buildWorkspace, composeWorkspace, or runtime-specific equivalents must first check the CLike eval workspace env contract and return it directly when available.",
            "Generated CI scripts must not recopy src/test/tests or reconstruct dependency KIT composition when CLike EvalRunner has already provided CLIKE_EVAL_WORKSPACE or CLIKE_EVAL_OVERLAY_WORKSPACE.",
            "Fallback overlay creation is allowed only for manual execution outside canonical CLike EvalRunner.",
            "This eval workspace rule is runtime-agnostic and applies to Node/JS/TS, Python, Java, Go, Rust, .NET, IaC, Mendix, PLC/SCADA, and custom enterprise runners.",
            "Package-manager script names must remain literal: commands such as npm run test, npm run lint, and npm run build must never be rewritten into npm run <absolute-path>.",
            "Generated code must be immediately promotable into canonical src/ and test roots without changing public contracts unexpectedly.",
            "For typed or statically checked runtimes, generated source, tests, and CI scripts must access custom exception/error metadata only after using the language-native narrowing, casting, matching, typed-exception, or adapter mechanism.",
            "Generated candidate tests must preserve assertions on error semantics, but must assert through a narrowed or adapted error value instead of directly reading fields from a generic exception/error/object.",
            "Generated CI utility scripts must use small safe helper/adaptor functions for platform-specific error metadata such as code, errno, syscall, path, status/statusCode, cause, provider codes, classification, retryable, or domain failure categories.",
            "Do not disable type checking, relax compiler/linter settings, remove meaningful assertions, or widen all failures to untyped catch-all values merely to pass EVAL. Repair candidate-owned code/tests/CI with language-idiomatic typed error handling.",
            "If the KIT emits runnable source or tests, emit the runtime-native KIT eval manifest needed to run them, such as ci/package.json for Node/npm or ci/requirements.txt for Python.",            
            "If the KIT creates or updates a runnable execution area, also emit the ecosystem-native promotion-ready runtime manifest under runs/kit/<REQ-ID>/src/<execution-area>/.",
            "Composition root ownership is explicit: only create or replace a backend/frontend/service launcher when the REQ owns that execution area composition or when repository evidence shows no existing composition root. Otherwise contribute feature modules and update integration seams without stealing the launcher.",
            "If FILE_REQUIREMENTS.json marks execution_area_runtime_manifest or solution_composition_root as required=true, omitting that artifact is a blocking KIT defect: either emit the artifact or explicitly mark the KIT non-promotable with the missing role and reason.",
            "If the KIT emits backend/frontend/service executable modules, provide one coherent launcher or composition entry per executable area only when the REQ owns composition or no existing launcher exists. Do not create one launcher per REQ.",
            "Launcher/composition files must live under the canonical execution area inside the candidate src tree, not under a REQ-local feature-only namespace or domain namespace unless the repository already uses that convention.",
            "For backend execution areas, prefer src/backend/<runtime-native-entrypoint> when no existing launcher convention is present; use src/<entrypoint> only for flat source-root conventions.",
            "Do not create launchers under domain namespaces such as src/<domain>/api/app.* unless that is the existing repository convention.",
            "Do not hardcode public bind addresses such as 0.0.0.0 in local launcher defaults; use loopback defaults or explicit runtime configuration.",
            "Keep KIT/EVAL manifests under runs/kit/<REQ-ID>/ci/.",
            "Do not hardcode runs/kit, ci/, temporary overlay paths, or REQ-specific eval paths in promotion-ready runtime manifests.",
            "It is allowed to regenerate files already emitted by previous KITs when they are functionally required for the current KIT; CLike promotion/merge handles reconciliation later.",
            "Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical src/test roots. If needed you can extend the module/file with all necessary code in the current req, but we need to be sure that the generated code is consistent with the dependency KITs and canonical roots for applying unified diffs later.",
            "Reuse dependency KIT contracts and canonical source contracts whenever they exist.",
            "If a dependency KIT or canonical source root is missing, explicitly report it as an implementation assumption or gap.",
            "Produce repository-aware, dependency-aware, promotable candidate code and tests.",
            "Prefer the clearest, readable, and well-structured implementation that fully satisfies the REQ acceptance criteria, stays aligned with repository patterns, and remains directly promotable without decorative architecture.",
        ],
    }

    context["hard_rules"] = _dedupe_rules(context.get("hard_rules") or [])
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
            "- Inspect promoted tests that CLike EvalRunner will include in the dependency-aware overlay. If the current REQ intentionally extends behavior covered by those tests, emit updated candidate tests under runs/kit/<REQ-ID>/test with the same relative path when needed so the overlay shadows stale expectations without modifying canonical tests.",
            "- Treat canonical src/test roots as promoted truth. Dependency KIT roots are read-only E2E contract evidence/fallback and must not override canonical src/test when the same dependency is already promoted.",
            "- Prefer CLIKE_SELECTED_CAPABILITY_CONTEXT.md over the generic full manifest when selected capability guidance exists.",
            "- Use main_module_boundary to keep feature implementation focused and avoid scattered files.",
            "- If FILE_REQUIREMENTS.json requires execution_area_runtime_manifest, solution_composition_root, or module_launcher, those execution-area artifacts may be created outside main_module_boundary but must stay under the allowed candidate src root and must remain execution-area-scoped, not REQ-scoped or domain-namespace-scoped.",
            "- For backend execution areas, prefer a stable execution-area root such as src/backend/app.* and src/backend/main.* when no repository convention already exists; do not create new launchers under src/<domain>/api/ just because the feature exposes an API router.",
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
            "- If promoted tests become stale because the REQ intentionally changes additive behavior, emit an updated same-relative-path candidate test under runs/kit/<REQ-ID>/test/ so the official overlay evaluates the new contract without editing canonical test roots.",
            f"- runs/kit/{req_id}/ci/LTC.json",
            f"- runs/kit/{req_id}/ci/HOWTO.md",
            "- Every FILE_REQUIREMENTS.json required_outputs item with required=true is mandatory.",
            "- If execution_area_runtime_manifest is required=true, emit the ecosystem-native promotion-ready runtime manifest under the candidate src execution area/root, not only under ci/.",
            "- If solution_composition_root or module_launcher is required=true, emit one coherent runnable composition root/launcher for the execution area, even when that file lives outside main_module_boundary.",
            "- If external_library_obligation is required=true, emit production-facing adapters/factories and dependency declarations for the named libraries; deterministic tests may fake external execution, but source code must not stop at Protocol/interface-only boundaries.",
            "- Keep blocking ci/eval manifests lightweight: hosted SDKs and quality tools may be installed for smoke tests, but heavy AI/model/runtime packages must be source optional extras or optional smoke dependencies unless the REQ explicitly requires a real integration eval environment.",
            "- When external libraries lack typing, stubs, metadata, or analyzer support, use the narrowest ecosystem-native suppression or wrapper only at the adapter/import boundary; never disable lint/type/security globally.",
            "- If a Node/TypeScript KIT has a separate runnable package under src/frontend or another execution-area root, set LTC.json top-level package_json to that package.json; ci/package.json may remain a lightweight CI script runner but must not be the only installed dependency manifest when frontend scripts need next, tsc, vitest, eslint, or similar tools.",
            "- If Node/TypeScript tests are outside the runnable package root, ensure the test runner config resolves all external imports used by those tests. For Vitest, add explicit aliases through createRequire/import.meta.url or move tests under the package root. At minimum, any imported @testing-library/*, jest-axe, axe, user-event, or generated test utility package must resolve from the package_json installation root.",
            "- If a static check validates KIT-local ci/docs files, resolve the KIT root from the static-check script directory. Use CLIKE_EVAL_WORKSPACE only for source/test runtime checks.",
            "- If any required output cannot be emitted safely, mark the KIT non-promotable and list the missing role in unresolved gaps.",
            "",
            "Recommended candidate outputs:",
            f"- runs/kit/{req_id}/docs/README_{req_id}.md",
            f"- runs/kit/{req_id}/docs/KIT_{req_id}.md",
            f"- runs/kit/{req_id}/ci/runtime-dependency manifest **MANDATORY**, e.g. ci/package.json for Node/npm or ci/requirements.txt for Python",
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
            "- stale promoted tests reconciled, including exact same-relative-path candidate overrides or explicit note that none were needed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
            "",
            """- Use the project/runtime evidence declared in SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, AGENT_EXECUTION_CONTEXT.json, and repository files.
            - Do not infer the application implementation language from local_runtime.tool_hints.
            - local_runtime.tool_hints are optional command hints only after the implementation runtime is known.
            - If package.json and npm scripts are present, prefer repository-native npm scripts such as `npm run test`, `npm run lint`, and `npm run build`.
            - Keep KIT/EVAL manifests under `runs/kit/<REQ-ID>/ci/`.
            - Generated CI scripts must consume the official CLike eval workspace when present: CLIKE_EVAL_WORKSPACE, CLIKE_EVAL_WORKSPACE_ROOT, CLIKE_EVAL_OVERLAY_WORKSPACE, or CLIKE_OVERLAY_WORKSPACE.
            - Generated raw-secret scanners must scan only candidate-owned source, tests, docs, and CI scripts/contracts. They must exclude installed dependencies, vendor folders, generated overlays, caches, reports, and temporary workspaces, including node_modules, local-eval-workspaces, dist, build, coverage, .cache, .tmp, .git, __pycache__, .venv, and package-manager caches.
            - Do not weaken secret regexes or remove meaningful security checks. If findings are inside candidate-owned files, keep the check blocking. If findings are only inside node_modules or generated/vendor/temp folders, repair the scanner scope.
            - Node CI scripts that call mkdtemp or create local overlay/report/temp workspaces must call mkdir(parent, { recursive: true }) before mkdtemp or before writing files under that parent.
            - Secret scanning is not dependency auditing. Do not scan node_modules README files for raw secrets; use a separate dependency/SCA gate for npm audit or equivalent checks.
            - Generated helpers such as createOverlayWorkspace, prepareWorkspace, buildWorkspace, composeWorkspace, or runtime-specific equivalents must first check the CLike eval workspace env contract and return it directly when available.
            - Do not create a second temporary overlay, recopy src/test/tests, or reconstruct dependency KIT composition when CLike EvalRunner has already provided an eval workspace.
            - Fallback overlay creation is allowed only for manual execution outside canonical CLike EvalRunner.
            - This rule is runtime-agnostic and applies to Node/JS/TS, Python, Java, Go, Rust, .NET, IaC, Mendix, PLC/SCADA, and custom enterprise runners.
            - For typed or statically checked runtimes, do not read custom exception/error metadata from a generic error value. Narrow, cast, pattern-match, downcast, or adapt the error through the language-native mechanism before asserting fields such as code, classification, retryable, status/statusCode, errno, syscall, path, cause, provider error codes, or domain failure categories.
            - Preserve meaningful failure-path assertions. Do not remove assertions, disable type checks, relax compiler/linter configuration, or hide failures by converting everything to untyped catch-all values.
            - Use idiomatic mechanisms for the detected runtime: type guards/JSDoc narrowing for JavaScript or TypeScript, isinstance/custom exceptions for Python, errors.As/errors.Is for Go, checked/custom exception classes for Java, pattern matching or typed error variants for Rust, and typed exception filters/custom exception types for .NET.
            - If generated CI utility code needs platform-specific error metadata, create a small local safe accessor/helper instead of reading implementation-specific fields directly from a generic error object.
            - If you create or update a runnable execution area, also emit the ecosystem-native promotion-ready runtime manifest under that execution area's candidate source root.
            - Runtime manifests must use paths relative to their own execution area root and must not contain runs/kit, ci/, temporary overlay paths, or REQ-specific eval paths.
            - Use Python only when the SPEC, PLAN, TECH_CONSTRAINTS, TARGET_CONTRACT, FILE_REQUIREMENTS, or repository evidence explicitly identifies Python as the implementation stack
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
    prompt = _render_compact_local_agent_prompt(
        phase="kit",
        req_id=req_id,
        context_path=context_path,
        methodology_context=methodology_context,
    )

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
    Build the orchestrator-owned local agent execution package for /eval hardening.

    The local agent is not the judge.
    It must execute the REQ-local LTC/HOWTO checks when possible, repair
    deterministic candidate failures under runs/kit/<REQ-ID>/, rerun the
    repaired checks, and leave canonical CLike EvalRunner as the final judge.
    """
    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"eval-local-{req_id}"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload)

    req = _extract_req_from_plan(payload, req_id)
    workspace_inspection_policy = _build_workspace_inspection_policy(req_id, req)
    capability_manifest = _extract_capability_manifest(payload)
    capability_integrity = _build_capability_integrity(req, capability_manifest)

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
        **({"methodology_context": methodology_context} if methodology_context else {}),
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
            "recommended": _build_recommended_outputs(req_id, req, payload),
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

    prompt = "\n".join(
        [
            f"# Local Agent EVAL Hardening Package — {req_id}",
            "",
            "You are a local software-generation agent executing a CLike Harper /eval hardening package.",
            "The orchestrator is the workflow owner. The VS Code extension is only the actuator.",
            "Your job is to make the candidate KIT evaluable before canonical CLike EvalRunner runs.",
            "The canonical CLike eval remains the final judge and will run after your hardening pass.",
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
            "- This is an eval hardening pass: you must execute the REQ-local LTC/HOWTO checks when possible.",
            "- Top priority for typecheck repair: if tests access fields missing from one branch of a union response, do not hide the issue with broad casts. Determine whether the field belongs to the stable public contract. If yes, repair the service/producer response shape. If no, repair the test with explicit narrowing before field access.",
            "- For workflow orchestration responses, workflowRun, job, idempotency, artifacts, and trace are contract-sensitive fields. Preserve idempotency and trace assertions; do not remove them to pass typecheck.",
            "- For unknown caught errors, use a narrow typed helper/adapter before asserting classification, retryable, status/statusCode, or domain failure categories.",
            "- For Node/JavaScript checkJs tests, assert.throws() and assert.rejects() callbacks receive unknown errors. Repair them by asserting `error instanceof ExpectedError`, then introducing a JSDoc cast such as `const typedError = /** @type {ExpectedError} */ (error);` and reading custom fields only from the typed variable.",
            "- Read AGENT_EVAL_CONTEXT.json and follow allowed_write_roots/forbidden_paths strictly.",
            "- If checks fail for deterministic candidate source, test, or CI reasons, you must repair the smallest related files under allowed_write_roots.",
            "- After repairing, you must rerun the failed or modified checks once before returning.",
            "- You must not weaken LTC.json, gate_policy, tsconfig, tests, or assertions to hide real failures.",
            "- You must not declare the final eval result. Canonical CLike EvalRunner remains the judge.",
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
            "- **IMPORTANT** If the KIT needs runtime-dependency manifests such as package.json, requirements.txt, pyproject.toml, or another runtime manifest to run tests, emit them under the target KIT root.",
            "- If launch/composition wiring is needed, emit one coherent backend launcher, one frontend launcher, or one per separate service as applicable. Do not create one launcher per REQ.",
            "- Use LTC/HOWTO and repository-native tooling to choose the eval runtime.",
            "- Do not infer the application implementation language from local_runtime.tool_hints.",
            "- local_runtime.tool_hints are optional command hints only after the eval runtime is known.",
            "- Do not install packages globally or into the system runtime.",
            "- Do not create a Python virtualenv for non-Python projects.",
            "- Prefer repository-native or REQ-local eval commands declared by LTC/HOWTO and the runtime-native eval manifest.",
            "- Before declaring tool, dependency, typecheck, lint, test, syntax, build, or security checks environment-blocked, inspect the REQ-local ci/ directory for a runtime-native eval manifest and attempt the ecosystem-native local setup command for that manifest.",
            "- A REQ-local setup command is allowed only inside the candidate KIT or eval workspace. Do not install packages globally or into the system runtime.",
            "- If dependency setup fails, report the concrete blocker: network, registry, filesystem, sandbox, policy, unsupported runtime, missing toolchain, or invalid manifest.",
            "- For dependency-resolution failures, repair the candidate eval contract by adding the missing declared dependency, resolver configuration, or test-runner configuration in the runtime-native way. Do not fake success and do not remove meaningful tests just to pass eval.",
            "- For typed-language or statically checked runtime failures involving exception/error metadata, repair candidate tests and CI scripts by narrowing, casting, pattern-matching, or adapting error values through language-native safe helpers before accessing custom fields.",
            "- Do not access implementation-specific error fields directly unless the error value has been explicitly narrowed to a compatible type.",
            "- Examples of custom or platform-specific error metadata include code, classification, retryable, status/statusCode, errno, syscall, path, cause, provider error codes, and domain-specific failure categories.",
            "- Preserve meaningful assertions on error semantics. Do not remove assertions, do not disable type checks, do not relax compiler/linter configuration, and do not hide failures by widening everything to untyped/any/object unless the language has no safer local mechanism.",
            "- Use the idiomatic mechanism for the active language and tooling: type guards or JSDoc narrowing for JavaScript/TypeScript, isinstance or typed exception classes for Python, errors.As/errors.Is for Go, checked/custom exception classes for Java, pattern matching or Result error variants for Rust, and typed exception filters or custom exception types for .NET.",
            "- If the failure is inside generated CI utility code, repair the CI utility with a small local adapter/helper that extracts error metadata safely without weakening product source or tests.",
            "- When a candidate test fails because `catch (error)` is `unknown`, add a local JSDoc typedef/helper near the test, for example `asWorkflowTestError(error)`, and assert on the narrowed variable instead of `error` directly.",
            "- When a generated CI utility script fails because `Error` lacks Node/system fields such as `code`, `errno`, `syscall`, or `path`, add a small helper such as `getErrorCode(error)` or `asNodeSystemError(error)` and use that helper instead of direct `error.code` access.",
            "- If TS2339/TS18046 appears in candidate-owned test files or CI scripts, treat it as a deterministic repairable candidate defect, not as an environment-blocked check.",
            "- After repairing TS2339/TS18046, rerun the smallest failed command, usually `npm run typecheck`, before returning.",
            "- For generated CI utility scripts only, `// @ts-nocheck` is allowed as a last resort when the failure is inside the validator script itself, the script is already covered by a syntax check, and product source/tests remain typechecked.",
            "- If dependencies cannot be installed because the environment is offline, externally managed, or blocked by policy, report the check as environment-blocked and run dependency-free compile/smoke checks instead.",
            "- If a type/lint/static-analysis check fails because candidate tests or CI scripts access custom exception/error metadata from a generic error value, repair the candidate-owned file using the language-native narrowing/casting/matching/typed-exception/adaptor mechanism and rerun the smallest failed command.",
            "- Preserve all meaningful assertions on error semantics, including retryability, classification, status/statusCode, provider codes, system error codes, cause, and domain failure categories.",
            "- Do not remove the failure-path test, do not suppress the type checker globally, do not relax compiler/linter configuration, and do not convert the entire file to untyped/unsafe code merely to pass EVAL.",
            "- This repair rule is runtime-agnostic. Apply the idiomatic mechanism for the detected language and tooling rather than hardcoding a JavaScript-only pattern.",
            "- When repairing CI scripts, preserve the CLike eval workspace contract: scripts must consume CLIKE_EVAL_WORKSPACE, CLIKE_EVAL_WORKSPACE_ROOT, CLIKE_EVAL_OVERLAY_WORKSPACE, or CLIKE_OVERLAY_WORKSPACE when present.",
            "- If check-no-secrets reports findings only under node_modules, package manager caches, local-eval-workspaces, dist, build, coverage, .cache, .tmp, .git, __pycache__, .venv, or generated overlay workspaces, repair the secret-scan script to exclude those dependency/vendor/generated/temp directories and rerun the check. Do not weaken secret patterns for candidate-owned files.",
            "- If check-no-secrets reports findings under candidate-owned source, tests, docs, or CI scripts/contracts, keep the check blocking and repair the candidate-owned file instead of suppressing the finding.",
            "- If a Node CI script fails with ENOENT from mkdtemp or from writing under local-eval-workspaces, repair the script by creating the parent directory recursively before mkdtemp/write operations, then rerun the failed command.",
            "- Do not classify mkdtemp ENOENT under a generated candidate CI script as a missing external tool. It is a deterministic repairable candidate CI defect.",
            "- For default targeted /eval, CI scripts must evaluate the current REQ candidate tests under runs/kit/<REQ-ID>/test, while using promoted/dependency source roots only as imports. Do not typecheck or secret-scan promoted/dependency tests unless the user explicitly requested a full regression/all-REQ eval.",
            "- For Node test runners, do not pass unexpanded glob strings such as `test/**/*.test.mjs` directly to node --test. Expand test files in the script first, then invoke node --test with concrete file paths.",
            "- Do not repair eval failures by creating an unconditional second overlay workspace.",
            "- Helpers such as createOverlayWorkspace, prepareWorkspace, buildWorkspace, composeWorkspace, "
            "or runtime-specific equivalents should prefer the CLike-provided eval workspace only when it contains "
            "the expected runnable source/test roots.",
            "- If the provided eval workspace is missing expected tests or source roots, fallback workspace creation is allowed "
            "and should be treated as a repair of an incomplete eval contract, not as a second unconditional overlay.",            "- Patch operations are allowed only under allowed_write_roots.",
            "",
            "Required eval actions:",
            f"- Read runs/kit/{req_id}/ci/LTC.json.",
            f"- Read runs/kit/{req_id}/ci/HOWTO.md when present.",
            f"- Inspect runs/kit/{req_id}/src and runs/kit/{req_id}/test.",
            "- Inspect promoted src/test roots and dependency KIT roots listed in workspace_inspection_policy when present.",
            "- Execute the LTC/HOWTO commands when possible before making changes.",
            "- Before reporting that checks are blocked, inspect the REQ-local ci/ folder for a runtime-native eval manifest and run the ecosystem-native local dependency/setup command in that specific candidate/eval workspace.",
            "- The setup command must be inferred from the manifest and repository evidence, not from hardcoded language preference in CLike.",
            "- After local dependency/setup succeeds, rerun generated security, syntax, tests, typecheck, lint, or build commands against the same execution area that canonical CLike EvalRunner will use.",
            "- If a security scanner fails only because it scanned installed dependencies or generated temporary workspaces, repair the scanner scope and rerun it.",
            "- If typecheck/test/syntax scripts create temporary workspaces, verify they create their parent directories recursively before mkdtemp or writes.",
            "- If any LTC/HOWTO command fails for deterministic candidate code/test/ci reasons, repair the smallest directly related files under allowed_write_roots.",
            "- After every repair, rerun the failed command or the smallest equivalent command once before returning.",
            "- If the command still fails, write the exact remaining failure and why it is not safely repairable.",
            "- For any test runner, verify that every imported or referenced test dependency is declared and resolvable from the runtime-native eval manifest or executable package root. Repair dependency declarations or resolver configuration in the ecosystem-native way.",            "- If LTC.json is malformed, incomplete, or not executable, repair LTC.json under runs/kit/<REQ-ID>/ci before changing source code.",
            "- Ensure LTC.json contains a non-empty cases[] execution contract.",
            "- Each LTC cases[] entry must include `run` as the canonical executable command field; `command` may be duplicated as a backward-compatible alias.",
            "- commands[] may exist only as human-readable aliases and must not be the only executable contract.",
            "- This rule is runtime-agnostic and applies to Node/JS/TS, Python, Java, Go, Rust, .NET, IaC, Mendix, PLC/SCADA, and custom enterprise runners.",
            "- For typed or statically checked runtimes, do not let normalized DTOs, schema outputs, parsed payloads, frozen objects, validation results, or adapter responses collapse to generic object shapes when their fields are used later.",
            "- If generated code reads fields from a normalized object, validation helper output, parsed JSON payload, adapter response, or immutable/frozen object, preserve an explicit shape using the runtime-native mechanism.",
            "- Examples of fields that require preserved shapes include source, contentType, bytes, metadata, id, status, traceId, classification, retryable, statusCode, provider codes, and domain failure categories.",
            "- In JavaScript/TypeScript with checkJs, Object.freeze({...}) and validation helpers must have JSDoc typedef/interface-compatible return shapes when downstream code accesses their fields. Avoid returning or inferring Readonly<{}> for objects with real fields.",
            "- In other runtimes, use the equivalent idiom: dataclass/TypedDict/protocol for Python, struct for Go/Rust, record/class/interface for Java/.NET, or typed maps only when the value shape is explicit.",
            "- If you create or update a runnable execution area, also emit the ecosystem-native promotion-ready runtime manifest under that execution area's candidate source root.",
            "- If a frontend test fails because it relies on brittle positional selectors such as getAllByLabelText(...)[1] or getAllByRole(...)[n], repair the candidate test to use scoped queries, unique accessible names, or a narrower rendered component/root. Do not remove meaningful assertions just to pass eval.",
            "- If checks are blocked by missing infrastructure, mark or document the blockage instead of faking success.",            "- Create reports under runs/kit/<REQ-ID>/reports when useful.",
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
            "- stale promoted tests reconciled, including exact same-relative-path candidate overrides or explicit note that none were needed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
        ]
    )

    context_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_PROMPT.md"
    prompt = _render_compact_local_agent_prompt(
        phase="eval",
        req_id=req_id,
        context_path=context_path,
        methodology_context=methodology_context,
    )

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

def _normalize_relative_path(value: Any) -> str:
    """Normalize a workspace-relative path without allowing absolute traversal."""
    path = _safe_text(value).replace("\\", "/").strip().strip("'\"")
    path = re.sub(r"/+", "/", path).lstrip("/")
    parts = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            return ""
        parts.append(part)
    return "/".join(parts)


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
    methodology_context = _methodology_context_for_local_agent(payload)

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

    return {
        "ok": True,
        "phase": "finalize",
        "echo": "Local agent finalize package prepared for SOLUTION",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-finalize-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
            "solution_finalize_requires_workspace_mutation",
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
            "package_id": f"{run_id}:SOLUTION:finalize",
            "phase": "finalize",
            "req_id": "SOLUTION",
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
            "expected_outputs": final_outputs,
            "infra_profile": infra_profile,
            "runtime_service_profile": runtime_service_profile,
            "cloud_provisioning_profile": cloud_provisioning_profile,
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
    run_id = _safe_text(payload.get("runId")) or "extend-local"
    local_executor = _resolve_local_executor(payload)
    methodology_context = _methodology_context_for_local_agent(payload)

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

    allowed_write_roots = [
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        "docs/harper/SPEC.md",
        "docs/harper/TECH_CONSTRAINTS.yaml",
        "docs/harper/lane-guides",
        "docs/harper",
    ]

    forbidden_paths = [
        ".git",
        "src",
        "test",
        "tests",
        "runs/kit",
        "runs/eval",
        "runs/gate",
        "node_modules",
        ".venv",
        "__pycache__",
        "__MACOSX",
    ]

    context = {
        "schema_version": "clike.agent.extend_context.v1",
        "phase": "extend",
        "run_id": run_id,
        "anchor_req": anchor_req,
        "explicit_req": explicit_req,
        "raw_input": raw_input,
        "input_sources": {
            "inline_text_present": bool(raw_input),
            "attachments_present": bool(payload.get("attachments")),
            "attachment_count": len(payload.get("attachments") or []),
        },
        **({"methodology_context": methodology_context} if methodology_context else {}),
        "mission": {
            "purpose": "Append new requirements to existing Harper planning artifacts without regenerating the plan.",
            "append_only_by_default": True,
            "preserve_existing_requirements": True,
            "update_plan_md": True,
            "update_plan_json": True,
            "update_spec_if_needed": True,
            "update_lane_guides_if_needed": True,
            "emit_extend_audit": True,
        },
        "required_reads": [
            "docs/harper/PLAN.md",
            "docs/harper/plan.json",
            "docs/harper/SPEC.md when present",
            "docs/harper/TECH_CONSTRAINTS.yaml when present",
            "docs/harper/lane-guides/*.md when present",
            ".clike/project.json when present",
            ".clike/capabilities.yaml when present",
            ".clike/capabilities.yml when present",
            ".clike/skills/** when relevant",
            ".clike/packs/** when relevant",
            ".clike/design-profiles/** when relevant",
        ],
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "output_contract": {
            "always": [
                "docs/harper/PLAN.md",
                "docs/harper/plan.json",
                "docs/harper/EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md",
            ],
            "conditional": [
                "docs/harper/SPEC.md only when new capability scope is introduced",
                "docs/harper/lane-guides/<concern>.md only when lane guidance is introduced or extended",
            ],
        },
        "hard_rules": [
            "Do not run git commands.",
            "Before final output, normalize every created or modified text file by stripping trailing whitespace and ensuring a final newline.",
            "Do not modify src/, test/, tests/, runs/kit/, runs/eval/, or runs/gate/.",
            "Do not regenerate PLAN.md from scratch.",
            "Do not rewrite, renumber, delete, or semantically modify existing consolidated REQs.",
            "Append new REQs after the requested anchor when provided.",
            "If no anchor is provided, detect the last REQ in plan.json/PLAN.md and append after it.",
            "Keep REQ IDs unique and contiguous unless the user explicitly supplied IDs.",
            "Mirror the existing plan.json requirement object shape instead of inventing a new schema.",
            "Update dependency graph and milestone/backlog sections only by appending the new REQs.",
            "Update SPEC.md only when the extension introduces new product/system capability scope, terms, constraints, integration boundaries, or user-visible behavior.",
            "Update lane-guides only when the extension introduces a new concern lane or materially extends existing lane guidance.",
            "Lane is a capability concern, not an implementation language.",
            "Do not infer implementation language from lane.",
            "Emit a Harper Extend audit file under docs/harper/EXTEND_<date>_<first_req>_<last_req>.md.",
            "The audit must list input sources, anchor, added REQs, updated files, preserved REQs, dependency decisions, validation results, and unresolved risks.",
        ],
        "validation_expectations": [
            "PLAN.md exists after the change.",
            "plan.json parses after the change.",
            "All new REQ IDs appear in both PLAN.md and plan.json.",
            "All new REQs have acceptance criteria.",
            "All dependencies resolve to existing or newly added REQs.",
            "Existing REQs are preserved.",
            "No source/test/KIT/eval files are changed.",
            "An EXTEND audit report is written.",
        ],
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)
    context_path = "docs/harper/AGENT_EXTEND_CONTEXT.json"
    prompt_path = "docs/harper/AGENT_EXTEND_PROMPT.md"

    prompt = "\n".join(
        [
            "# Local Agent EXTEND Execution Package — Harper Plan Extension",
            "",
            "You are executing a CLike Harper /extend package.",
            "The orchestrator owns workflow state and policy. The local agent is only the workspace documentation actuator.",
            _render_methodology_prompt_block(methodology_context),
            "",
            "Read before acting:",
            "- docs/harper/AGENT_EXTEND_CONTEXT.json",
            "",
            "Mission:",
            "- Extend the current Harper plan by appending new requirements.",
            "- Preserve existing consolidated REQs exactly unless the user explicitly requested a separate revise operation.",
            "- Update PLAN.md and plan.json so they remain aligned.",
            "- Update SPEC.md only if the new REQs introduce new capability scope, domain terms, constraints, integrations, or user-visible behavior.",
            "- Update or create lane-guides only if new concern guidance is needed.",
            "- Emit docs/harper/EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md.",
            "",
            "Allowed writes:",
            "- docs/harper/PLAN.md",
            "- docs/harper/plan.json",
            "- docs/harper/SPEC.md",
            "- docs/harper/lane-guides/*.md",
            "- docs/harper/EXTEND_*.md",
            "",
            "Forbidden writes:",
            "- src/",
            "- test/",
            "- tests/",
            "- runs/kit/",
            "- runs/eval/",
            "- runs/gate/",
            "- .git/",
            "",
            "Append-only rules:",
            "- Do not regenerate the plan from scratch.",
            "- Do not modify existing REQ acceptance criteria.",
            "- Do not renumber existing REQs.",
            "- Do not change status/gate/promotion metadata of existing REQs.",
            "- Add new dependencies only for new REQs.",
            "- If shared sections need updates, append minimal new entries only.",
            "",
            "Input:",
            f"- anchor_req: {anchor_req or '<auto-detect-last-req>'}",
            f"- explicit_req: {explicit_req or '<none>'}",
            f"- raw_input: {raw_input or '<see chat/attachments/core context>'}",
            "",
            "At the end, print:",
            "- files changed;",
            "- added REQ IDs;",
            "- preserved REQ range;",
            "- SPEC updated yes/no and why;",
            "- lane-guides updated yes/no and why;",
            "- validation performed;",
            "- unresolved gaps.",
        ]
    )

    return {
        "ok": True,
        "phase": "extend",
        "echo": "Local agent extend package prepared for Harper plan extension",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-extend-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
            "extend_requires_harper_docs_mutation",
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
            "package_id": f"{run_id}:SOLUTION:extend",
            "phase": "extend",
            "req_id": "SOLUTION",
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
            "expected_outputs": context["output_contract"],
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
    phase = (_safe_text(payload.get("phase")) or "kit").lower()
    req_id = (_safe_text(payload.get("req_id")) or ("SOLUTION" if phase in {"finalize", "extend"} else "")).upper()
    run_id = _safe_text(payload.get("runId")) or _safe_text(payload.get("run_id"))

    files = payload.get("files") or []
    stdout = _safe_text(payload.get("stdout"))
    stderr = _safe_text(payload.get("stderr"))
    exit_code = payload.get("exit_code")

    def _extend_allowed_path(file_path: str) -> bool:
        p = _normalize_relative_path(file_path)
        if not p:
            return False

        if p in {
            "docs/harper/PLAN.md",
            "docs/harper/plan.json",
            "docs/harper/SPEC.md",
        }:
            return True

        if p.startswith("docs/harper/lane-guides/") and p.endswith(".md"):
            return True

        if p.startswith("docs/harper/EXTEND_") and p.endswith(".md"):
            return True

        if p in {
            "docs/harper/AGENT_EXTEND_CONTEXT.json",
            "docs/harper/AGENT_EXTEND_PROMPT.md",
        }:
            return True

        return False

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

            source_auth_evidence = any(
                path.startswith("src/")
                and any(
                    marker in content.lower()
                    for marker in (
                        "auth_provider",
                        "auth_mode",
                        "auth_issuer",
                        "auth_issuer_url",
                        "auth_client_id",
                        "auth_audience",
                        "auth_jwks_uri",
                        "auth_jwks_url",
                        "oidc",
                        "oidc_issuer",
                        "oidc_audience",
                        "oidc_client",
                        "oidc_jwks_uri",
                        "jwks",
                        "saml_metadata",
                        "required_groups",
                        "identity",
                        "rbac",
                        "disabled-local",
                        "local-disabled",
                    )
                )
                for path, content in content_by_path.items()
            )
            if not source_auth_evidence:
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

    if not normalized_files:
        ok = False
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
