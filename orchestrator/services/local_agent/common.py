"""Shared helpers of the local-agent packages: plumbing, capabilities, methodology, prompt blocks, plan helpers, executor resolution, attachments.

Split out of services/local_agent_package.py (WP8.5); behaviour unchanged.
"""


from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from services.capabilities import (
    build_capability_context,
    build_selected_capability_context,
)
from services.methodologies.errors import ClikeSelectedCapabilitiesMissingError
from services.methodologies.resolver import ensure_bmad_skill_context, resolve_methodology_context
from utils.namespace_paths import (
    is_python_runtime_context,
)
from services.kit_repair import repair_failures, repair_rules
from services.phase_definitions import phase_text


def _text(key: str) -> list:
    """Static text of this module, kept in phases/_shared_text.yaml (WP8.5)."""
    return list(phase_text("_shared")[key])


def _local_agent_invocation(local_executor: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    """How the extension runs the agent CLI (clike.local_agent_invocation.v1)."""
    return {
        "schema_version": "clike.local_agent_invocation.v1",
        "executor": local_executor,
        "command_ref": local_executor,
        "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
        "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
        "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
        "cwd": ".",
    }


def _execution_summary(execution_policy: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requested": execution_policy.get("requested"),
        "selected": execution_policy.get("selected"),
        "reason": execution_policy.get("reason"),
        "phase_supported": execution_policy.get("phase_supported"),
    }


def _package_file(path: str, content: Any, mime: str) -> Dict[str, Any]:
    """A text file the extension writes into the workspace before running the agent."""
    return {"path": path, "content": content, "mime": mime, "encoding": "utf-8"}


def _package_envelope(
    *,
    phase: str,
    echo: str,
    summary: str,
    extra_warnings: List[str],
    run_id: Any,
    execution_policy: Dict[str, Any],
    local_agent: Dict[str, Any],
) -> Dict[str, Any]:
    """Response returned to the extension when the phase must run on a local agent."""
    return {
        "ok": True,
        "phase": phase,
        "echo": echo,
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": summary},
        "warnings": ["execution_package:local_agent_required", "extension_role:local_actuator_only", *extra_warnings],
        "errors": [],
        "runId": run_id,
        "execution": _execution_summary(execution_policy),
        "local_agent": local_agent,
    }


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


def _req_capability_list(req: Dict[str, Any], *keys: str, nested_key: str) -> List[str]:
    nested = req.get("capabilities") if isinstance(req.get("capabilities"), dict) else {}
    for key in keys:
        values = req.get(key)
        if isinstance(values, list) and values:
            return [str(item) for item in values if str(item or "").strip()]
    nested_keys = [nested_key]
    if nested_key == "design_profiles":
        nested_keys.append("designProfiles")
    for key in nested_keys:
        values = nested.get(key)
        if isinstance(values, list):
            return [str(item) for item in values if str(item or "").strip()]
    return []


def _selected_capability_summary(req: Dict[str, Any], capability_manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "selected_packs": _req_capability_list(req, "packs", nested_key="packs"),
        "selected_skills": _req_capability_list(req, "skills", nested_key="skills"),
        "selected_design_profiles": _req_capability_list(
            req,
            "design_profiles",
            "designProfiles",
            nested_key="design_profiles",
        ),
        "context_available": bool(capability_manifest.get("selected_context_available")),
        "context_markdown_path": "CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
        "context_json_path": "CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
        "capability_context_paths": {
            "selected_markdown": "CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
            "selected_json": "CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
            "manifest": "CLIKE_CAPABILITY_MANIFEST.md",
            "index": "CLIKE_CAPABILITY_INDEX.json",
        },
        "source": "CLIKE_SELECTED_CAPABILITY_CONTEXT",
    }


def _ensure_selected_capability_context(
    payload: Dict[str, Any],
    *,
    req_id: str,
    target_contract: Dict[str, Any],
) -> Dict[str, Any]:
    core_blobs = dict(payload.get("core_blobs") or {})
    declared = bool(
        target_contract.get("packs")
        or target_contract.get("skills")
        or target_contract.get("design_profiles")
    )
    if not declared:
        return payload

    if _selected_capability_context_has_selection(core_blobs.get("CLIKE_SELECTED_CAPABILITY_CONTEXT.json")):
        return payload

    if not core_blobs.get("CLIKE_CAPABILITY_INDEX.json"):
        capability_blobs = build_capability_context(None, core_blobs=core_blobs)
        if capability_blobs:
            core_blobs.update(capability_blobs)

    selected_blobs = build_selected_capability_context(
        core_blobs=core_blobs,
        target_req_id=req_id,
        target_contract=target_contract,
    )
    if selected_blobs:
        updated = dict(payload)
        updated["core_blobs"] = {**core_blobs, **selected_blobs}
        return updated
    return payload


def _selected_capability_context_has_selection(raw_context: Any) -> bool:
    try:
        data = json.loads(str(raw_context or ""))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("selected_packs") or data.get("selected_skills") or data.get("selected_design_profiles"):
        return True
    for key in ("packs", "skills", "design_profiles"):
        group = data.get(key) if isinstance(data.get(key), dict) else {}
        if group.get("selected") or group.get("resolved"):
            return True
    return False


def _raise_if_selected_capabilities_missing_for_agent(
    *,
    phase: str,
    req_id: str,
    methodology_context: Optional[Dict[str, Any]],
    selected_capabilities: Dict[str, Any],
    capability_manifest: Dict[str, Any],
    capability_integrity: Dict[str, Any],
    context_envelope: Dict[str, Any],
) -> None:
    declared_packs = list(selected_capabilities.get("selected_packs") or [])
    declared_skills = list(selected_capabilities.get("selected_skills") or [])
    declared_design = list(selected_capabilities.get("selected_design_profiles") or [])
    if not (declared_packs or declared_skills or declared_design):
        return

    clike = context_envelope.get("clike_capabilities") or {}
    if clike.get("selected_packs") or clike.get("selected_skills") or clike.get("selected_design_profiles"):
        return

    raise ClikeSelectedCapabilitiesMissingError(
        "CLIKE_SELECTED_CAPABILITIES_MISSING: "
        f"req_id={req_id} phase={phase} "
        f"methodology={(methodology_context or {}).get('methodology') or 'native'} "
        f"selected_packs_declared={declared_packs} "
        f"selected_skills_declared={declared_skills} "
        f"selected_design_profiles_declared={declared_design} "
        "source_transport=core_blobs "
        f"capability_index_present={bool(capability_manifest.get('index_available'))} "
        f"selected_capability_context_present={bool(capability_manifest.get('selected_context_available'))} "
        f"missing_capability_ids={(capability_integrity.get('missing_selected_packs') or []) + (capability_integrity.get('missing_selected_skills') or []) + (capability_integrity.get('missing_selected_design_profiles') or [])} "
        f"available_packs={_manifest_capability_names(capability_manifest, 'packs')} "
        f"available_skills={_manifest_capability_names(capability_manifest, 'skills')} "
        f"available_design_profiles={_manifest_capability_names(capability_manifest, 'design_profiles')}"
    )


def _runtime_ecosystem_for_req(req: Dict[str, Any], payload: Dict[str, Any]) -> str:
    text = "\n".join(
        [
            _safe_text(req.get("title")),
            _safe_text(req.get("functional_scope")),
            _safe_text(req.get("technical_scope")),
            _safe_text(req.get("test_profile")),
            _safe_text(req.get("main_module_boundary")),
            _safe_text(_extract_core_blob(payload, "SPEC.md")),
            _safe_text(_extract_core_blob(payload, "PLAN.md")),
            _safe_text(_extract_core_blob(payload, "TECH_CONSTRAINTS.yaml")),
            _safe_text(_extract_core_blob(payload, "TECH_CONSTRAINTS.yml")),
            _safe_text(_extract_core_blob(payload, "FILE_REQUIREMENTS.json")),
        ]
    )
    if is_python_runtime_context(
        lane=req.get("lane"),
        runtime_profile=req.get("runtime_profile"),
        text=text,
    ):
        return "python"
    return "unknown"


def _render_selected_capability_prompt_block(selected_capabilities: Dict[str, Any]) -> str:
    if not isinstance(selected_capabilities, dict) or not selected_capabilities.get("context_available"):
        return ""
    return "\n".join(
        [
            "",
            "### CLike Selected Capability Context",
            f"- selected_packs: {'; '.join(str(x) for x in selected_capabilities.get('selected_packs') or []) or 'none'}",
            f"- selected_skills: {'; '.join(str(x) for x in selected_capabilities.get('selected_skills') or []) or 'none'}",
            f"- selected_design_profiles: {'; '.join(str(x) for x in selected_capabilities.get('selected_design_profiles') or []) or 'none'}",
            *_text("render_selected_capability_prompt_block.lines"),
        ]
    )


def _render_namespace_materialization_prompt_block(namespace_context: Dict[str, Any]) -> str:
    if not isinstance(namespace_context, dict) or not namespace_context.get("rules"):
        return ""
    return "\n".join(
        [
            "",
            "### Namespace Materialization",
            f"- ecosystem: {namespace_context.get('ecosystem') or 'unknown'}",
            f"- import_namespace: {namespace_context.get('import_namespace') or 'none'}",
            f"- package_path: {namespace_context.get('package_path') or 'none'}",
            f"- source_root: {namespace_context.get('source_root') or 'none'}",
            *[f"- {rule}" for rule in (namespace_context.get("rules") or [])],
        ]
    )


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


def _methodology_context_for_local_agent(
    payload: Dict[str, Any],
    *,
    phase_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return compact CLike-resolved methodology context for local-agent packages."""
    raw = payload.get("methodology_context")
    if not isinstance(raw, dict) or not raw.get("methodology"):
        methodology = _safe_text(payload.get("methodology")).lower()
        if methodology != "bmad":
            return None
        phase = _safe_text(phase_hint or payload.get("phase") or payload.get("cmd") or "")
        agent = _safe_text(payload.get("agent") or "")
        raw = resolve_methodology_context(
            phase=phase,
            methodology=methodology,
            agent=agent or None,
            core_blobs=payload.get("core_blobs") or {},
            require_bmad_core_blobs=True,
        )
        if not isinstance(raw, dict) or not raw.get("methodology"):
            return None
    raw = ensure_bmad_skill_context(
        raw,
        phase=raw.get("phase") or phase_hint or payload.get("phase") or payload.get("cmd"),
        agent=raw.get("agent") or payload.get("agent"),
        core_blobs=payload.get("core_blobs") or {},
        require_bmad_core_blobs=True,
    ) or raw

    profile = raw.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    allowed_agents = raw.get("allowed_agents") or []
    if not isinstance(allowed_agents, list):
        allowed_agents = []
    workflow_focus = raw.get("workflow_focus") or []
    if not isinstance(workflow_focus, list):
        workflow_focus = []
    required_context = raw.get("required_context") or []
    if not isinstance(required_context, list):
        required_context = []
    companion_artifacts = raw.get("companion_artifacts") or []
    if not isinstance(companion_artifacts, list):
        companion_artifacts = []
    discovered_companion_artifacts = raw.get("discovered_companion_artifacts") or []
    if not isinstance(discovered_companion_artifacts, list):
        discovered_companion_artifacts = []
    governance_boundaries = raw.get("governance_boundaries") or []
    if not isinstance(governance_boundaries, list):
        governance_boundaries = []
    artifact_policy = raw.get("artifact_policy") or {}
    if not isinstance(artifact_policy, dict):
        artifact_policy = {}
    selected_skill_references = raw.get("selected_skill_references") or []
    if not isinstance(selected_skill_references, list):
        selected_skill_references = []
    selected_skill_context = raw.get("selected_skill_context") or {}
    if not isinstance(selected_skill_context, dict):
        selected_skill_context = {}
    skill_reference_policy = raw.get("skill_reference_policy") or {}
    if not isinstance(skill_reference_policy, dict):
        skill_reference_policy = {}

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
        "workflow_summary": raw.get("workflow_summary"),
        "workflow_focus": workflow_focus[:8],
        "required_context": required_context[:8],
        "companion_artifacts": companion_artifacts[:8],
        "discovered_companion_artifacts": discovered_companion_artifacts[:40],
        "artifact_policy": {
            "canonical_outputs": list(artifact_policy.get("canonical_outputs") or []),
            "companion_only": bool(artifact_policy.get("companion_only", False)),
            "mandatory_companion_outputs": list(artifact_policy.get("mandatory_companion_outputs") or []),
            "allowed_companion_root_globs": list(artifact_policy.get("allowed_companion_root_globs") or []),
            "forbidden_outputs": list(artifact_policy.get("forbidden_outputs") or []),
            "conflict_resolution": artifact_policy.get("conflict_resolution"),
            "downstream_consumers": list(artifact_policy.get("downstream_consumers") or []),
        },
        "workflow_path": raw.get("workflow_path"),
        "governance_boundaries": governance_boundaries[:6] or _text("methodology_context_for_local_agent.lines"),
        "selected_skill_references": selected_skill_references[:12],
        "selected_skill_context": {
            "snippets": list(selected_skill_context.get("snippets") or [])[:8],
            "required_outputs": list(selected_skill_context.get("required_outputs") or [])[:24],
            "companion_outputs": list(selected_skill_context.get("companion_outputs") or [])[:24],
            "quality_checks": list(selected_skill_context.get("quality_checks") or [])[:24],
            "forbidden_behavior": list(selected_skill_context.get("forbidden_behavior") or [])[:24],
            "governance_boundaries": list(selected_skill_context.get("governance_boundaries") or [])[:12],
            **({"vendor_inventory_summary": selected_skill_context.get("vendor_inventory_summary")} if selected_skill_context.get("vendor_inventory_summary") else {}),
        },
        "skill_reference_policy": {
            "enabled": bool(skill_reference_policy.get("enabled", False)),
            "workspace_vendor_reference_root": skill_reference_policy.get("workspace_vendor_reference_root"),
            "template_vendor_reference_root": skill_reference_policy.get("template_vendor_reference_root"),
            "vendor_skill_root": skill_reference_policy.get("vendor_skill_root") or skill_reference_policy.get("workspace_vendor_reference_root"),
            "activation": skill_reference_policy.get("activation"),
            "runtime_import_enabled": bool(skill_reference_policy.get("runtime_import_enabled", False)),
            "external_skill_execution_enabled": bool(skill_reference_policy.get("external_skill_execution_enabled", False)),
            "external_bmad_cli_enabled": bool(skill_reference_policy.get("external_bmad_cli_enabled", False)),
            "network_fetch_enabled": bool(skill_reference_policy.get("network_fetch_enabled", False)),
            "cloud_context_enabled": bool(skill_reference_policy.get("cloud_context_enabled", False)),
            "local_agent_context_enabled": bool(skill_reference_policy.get("local_agent_context_enabled", False)),
        },
    }


def _render_methodology_prompt_block(methodology_context: Optional[Dict[str, Any]]) -> str:
    if not methodology_context:
        return ""

    profile = methodology_context.get("profile") or {}
    workflow_focus = methodology_context.get("workflow_focus") or []
    required_context = methodology_context.get("required_context") or []
    companion_artifacts = methodology_context.get("companion_artifacts") or []
    governance_boundaries = methodology_context.get("governance_boundaries") or []
    selected_skill_references = methodology_context.get("selected_skill_references") or []
    selected_skill_context = methodology_context.get("selected_skill_context") or {}
    if not isinstance(selected_skill_context, dict):
        selected_skill_context = {}
    skill_ids = [
        str(item.get("id") or "")
        for item in selected_skill_references
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    return "\n".join(
        [
            "",
            "Methodology profile:",
            f"- methodology: {methodology_context.get('methodology')}",
            f"- role: {methodology_context.get('agent') or 'none'}",
            f"- authority: {methodology_context.get('authority')}",
            f"- advisory_only: {bool(methodology_context.get('advisory_only'))}",
            f"- role_summary: {profile.get('summary') or ''}",
            f"- workflow_summary: {methodology_context.get('workflow_summary') or ''}",
            f"- workflow_focus: {'; '.join(str(x) for x in workflow_focus[:8]) if workflow_focus else 'none'}",
            f"- required_context: {'; '.join(str(x) for x in required_context[:8]) if required_context else 'none'}",
            f"- companion_artifacts: {'; '.join(str(x) for x in companion_artifacts[:8]) if companion_artifacts else 'none'}",
            *(
                [
                    "### BMAD Skill Reference Context",
                    "BMAD skill context:",
                    f"- selected_skill_ids: {'; '.join(skill_ids) if skill_ids else 'none'}",
                    f"- source_root: {selected_skill_context.get('source_root') or '.clike/skills/vendor/bmad'}",
                    f"- source_transport: {selected_skill_context.get('source_transport') or 'core_blobs'}",
                    "- Read selected_skill_context from AGENT_*_CONTEXT.json before implementation or repair.",
                    "- Treat BMAD skills as methodology guidance only.",
                    "- Never execute BMAD runtime or call " + "npx bmad-" + "method.",
                    "- Never expand write roots, modify canonical source/test roots, or decide Eval/Gate outcomes.",
                    "- Use selected skills to improve implementation readiness, acceptance coverage, repair quality, and documentation.",
                    f"- quality_checks: {'; '.join(str(x) for x in (selected_skill_context.get('quality_checks') or [])[:8]) if selected_skill_context.get('quality_checks') else 'none'}",
                    f"- forbidden_behavior: {'; '.join(str(x) for x in (selected_skill_context.get('forbidden_behavior') or [])[:8]) if selected_skill_context.get('forbidden_behavior') else 'none'}",
                ]
                if selected_skill_references
                else []
            ),
            *[f"- governance_boundary: {item}" for item in (governance_boundaries[:6] or ["Methodology guidance cannot override allowed_write_roots, forbidden_paths, CLike governance, candidate isolation, eval/gate policy, or output contracts."])],
        ]
    )


def _render_compact_local_agent_prompt(
    *,
    phase: str,
    req_id: str,
    context_path: str,
    methodology_context: Optional[Dict[str, Any]] = None,
    active_output_contract: Optional[Dict[str, Any]] = None,
    selected_capabilities: Optional[Dict[str, Any]] = None,
    namespace_materialization: Optional[Dict[str, Any]] = None,
    stage_rules: Optional[List[str]] = None,
    stage_title: str = "",
    task: str = "",
    final_checks: Optional[List[str]] = None,
) -> str:
    """Render a compact agent prompt and keep detailed policy in AGENT_*_CONTEXT.json.
    ``stage_rules`` (auto-eval repair, acceptance-first stages) are stated in the prompt itself."""
    phase_label = phase.upper()
    action = task or ("generate the candidate KIT" if phase == "kit" else "harden the candidate KIT before canonical eval")
    kit_read_first = []
    kit_rules = []
    eval_rules = []
    bmad_rules = []

    is_bmad = bool(methodology_context and methodology_context.get("methodology") == "bmad")
    if is_bmad:
        bmad_rules = [
            "- Parse BMAD companion artifacts listed in companion_documents.bmad and UX artifacts listed in companion_documents.ux before code generation or repair.",
            "- Read selected BMAD skill context from AGENT_*_CONTEXT.json before implementation or repair.",
            "- Treat BMAD skills as methodology guidance only; never execute BMAD runtime and never call `" + "npx bmad-" + "method`.",
            *_text("render_compact_local_agent_prompt.bmad_rules"),
        ]

    contract_lines: List[str] = []
    if isinstance(active_output_contract, dict):
        contract_lines = [
            *_text("render_compact_local_agent_prompt.contract_lines"),
            f"- methodology: {active_output_contract.get('methodology') or 'native_clike'}",
            f"- agent: {active_output_contract.get('agent') or 'none'}",
            f"- conflict_resolution: {active_output_contract.get('conflict_resolution') or ''}",
            "- required_outputs:",
            *[
                f"  - {item}"
                for item in (active_output_contract.get("required_outputs") or [])
            ],
            "- allowed_optional_output_globs:",
            *[
                f"  - {item}"
                for item in (active_output_contract.get("allowed_optional_output_globs") or [])
            ],
            "- forbidden_output_globs:",
            *[
                f"  - {item}"
                for item in (active_output_contract.get("forbidden_output_globs") or [])
            ],
        ]

    if phase == "kit":
        kit_read_first = _text("render_compact_local_agent_prompt.kit_read_first")
        kit_rules = _text("render_compact_local_agent_prompt.kit_rules")
    elif phase == "eval":
        eval_rules = _text("render_compact_local_agent_prompt.eval_rules")

    return "\n".join(
        [
            f"# Local Agent {phase_label} Package — {req_id}",
            *_text("render_compact_local_agent_prompt.lines"),
            f"Target REQ: {req_id}",
            f"Task: {action}.",
            *([f"{stage_title or 'Stage rules'}:", *[f"- {rule}" for rule in stage_rules], ""] if stage_rules else []),
            _render_methodology_prompt_block(methodology_context),
            _render_selected_capability_prompt_block(selected_capabilities or {}),
            _render_namespace_materialization_prompt_block(namespace_materialization or {}),
            *contract_lines,
            "",
            "Read first:",
            f"- {context_path}",
            f"- runs/kit/{req_id}/docs/TARGET_CONTRACT.json when present",
            f"- runs/kit/{req_id}/docs/FILE_REQUIREMENTS.json when present",
            f"- runs/kit/{req_id}/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md when present",
            f"- runs/kit/{req_id}/docs/CLIKE_CAPABILITY_INDEX.json when present",
            *kit_read_first,
            *_text("render_compact_local_agent_prompt.lines.2"),
            *bmad_rules,
            *kit_rules,
            *eval_rules,
            *_text("render_compact_local_agent_prompt.lines.3"),
            *(["", "Before you finish — eval-readiness self-check:", *[f"- {rule}" for rule in final_checks]] if final_checks else []),
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


def _extract_plan_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    plan_json_text = _extract_core_blob(payload, "plan.json")
    if not plan_json_text:
        return {}

    try:
        data = json.loads(plan_json_text)
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _extract_plan_reqs(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    reqs = plan.get("reqs") or plan.get("req") or plan.get("requirements") or []
    return [item for item in reqs if isinstance(item, dict)] if isinstance(reqs, list) else []


def _build_related_reqs(req_id: str, req: Dict[str, Any], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    req_id_norm = _safe_text(req_id).upper()
    dependencies = set(_extract_req_dependencies(req))
    related: List[Dict[str, Any]] = []

    for item in _extract_plan_reqs(plan):
        item_id = _safe_text(item.get("id")).upper()
        if not item_id or item_id == req_id_norm:
            continue

        item_dependencies = set(_extract_req_dependencies(item))
        if item_id in dependencies or req_id_norm in item_dependencies:
            related.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "lane": item.get("lane"),
                    "dependsOn": item.get("dependsOn") or item.get("depends_on") or item.get("dependencies") or [],
                    "relationship": "dependency" if item_id in dependencies else "dependent",
                }
            )

    return related


def _compact_snippet(text: str, max_chars: int = 4000) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n\n...[truncated]"


def _core_doc_reference(payload: Dict[str, Any], path: str, suffix: str, max_chars: int = 4000) -> Dict[str, Any]:
    content = _extract_core_blob(payload, suffix)
    return {
        "path": path,
        "present": bool(content),
        "snippet": _compact_snippet(content, max_chars) if content else "",
    }


def _parse_json_core_blob(payload: Dict[str, Any], suffix: str) -> Optional[Dict[str, Any]]:
    text = _extract_core_blob(payload, suffix)
    if not text:
        return None

    try:
        data = json.loads(text)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _companion_documents_from_core_blobs(payload: Dict[str, Any], root_prefix: str) -> List[Dict[str, Any]]:
    core_blobs = payload.get("core_blobs") or {}
    prefix = f"companion::{root_prefix}".lower()
    docs: List[Dict[str, Any]] = []

    for key in sorted(core_blobs.keys()):
        key_text = str(key or "").strip()
        if not key_text.lower().startswith(prefix):
            continue

        path = key_text[len("companion::") :]
        content = str(core_blobs.get(key) or "")
        docs.append(
            {
                "key": key_text,
                "path": path,
                "bytes": len(content.encode("utf-8")),
                "snippet": _compact_snippet(content, 2500),
            }
        )

    return docs


def _documents_from_core_blobs_prefix(payload: Dict[str, Any], root_prefix: str, max_chars: int = 2500) -> List[Dict[str, Any]]:
    core_blobs = payload.get("core_blobs") or {}
    prefix = str(root_prefix or "").lower().rstrip("/") + "/"
    docs: List[Dict[str, Any]] = []

    for key in sorted(core_blobs.keys()):
        key_text = str(key or "").strip()
        if not key_text.lower().startswith(prefix):
            continue

        content = str(core_blobs.get(key) or "")
        docs.append(
            {
                "path": key_text,
                "bytes": len(content.encode("utf-8")),
                "snippet": _compact_snippet(content, max_chars),
                "read_only": True,
            }
        )

    return docs


def _bmad_expected_outputs(
    *,
    req_id: str,
    methodology_context: Optional[Dict[str, Any]],
    phase: str,
) -> Dict[str, Any]:
    if not methodology_context or methodology_context.get("methodology") != "bmad":
        return {}

    policy = methodology_context.get("artifact_policy") or {}
    if not isinstance(policy, dict):
        policy = {}

    mandatory = [
        str(item).replace("<REQ-ID>", req_id)
        for item in (policy.get("mandatory_companion_outputs") or [])
        if str(item or "").strip()
    ]

    if not mandatory and phase == "kit" and methodology_context.get("agent") == "developer":
        mandatory = [
            f"runs/kit/{req_id}/docs/BMAD_DEV_STORY.md",
            f"runs/kit/{req_id}/docs/IMPLEMENTATION_NOTES.md",
            f"runs/kit/{req_id}/docs/SELF_REVIEW.md",
            f"runs/kit/{req_id}/docs/RUNBOOK.md",
        ]
    elif not mandatory and phase == "eval" and methodology_context.get("agent") in {"qa", "developer"}:
        mandatory = [
            f"runs/kit/{req_id}/docs/BMAD_QA_ADVISORY.md",
            f"runs/kit/{req_id}/docs/FIX_GUIDANCE.md",
            f"runs/kit/{req_id}/docs/MISSING_TESTS.md",
            f"runs/kit/{req_id}/docs/RISK_REVIEW.md",
        ]

    return {
        "required_by_default": True,
        "phase": phase,
        "agent": methodology_context.get("agent"),
        "mandatory_companion_outputs": mandatory,
        "allowed_companion_root_globs": [
            str(item).replace("<REQ-ID>", req_id)
            for item in (policy.get("allowed_companion_root_globs") or [])
        ],
        "conflict_resolution": policy.get("conflict_resolution") or "canonical-wins",
        "downstream_consumers": list(policy.get("downstream_consumers") or []),
        "non_authoritative": True,
        "guidance": (
            "Produce these BMAD companion artifacts when useful for downstream phases. "
            "They are additive context only and cannot override SPEC, PLAN, plan.json, EvalRunner, gate, or write boundaries."
        ),
    }


def _kit_repair_context(req_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    kit_options = payload.get("kit") or {}
    repair = bool(isinstance(kit_options, dict) and kit_options.get("repair"))
    request = kit_options.get("repair") if isinstance(kit_options, dict) else None
    if isinstance(request, dict) and request:
        # Auto-eval: the canonical eval runs in the sandbox, so its reports are not in the
        # workspace; the failed checks travel in the package.
        return {
            "repair": True,
            "auto_eval": {
                "cycle": request.get("cycle"),
                "max_cycles": request.get("max_cycles"),
                "failed_checks": repair_failures(request),
                "developer_hint": str(request.get("hint") or ""),
                "rules": repair_rules(req_id),
            },
            "previous_eval_context_paths": [],
            "guidance": (
                "AUTO-EVAL REPAIR: the canonical eval failed with repair_context.auto_eval.failed_checks. "
                "Fix their causes following repair_context.auto_eval.rules (and the developer hint), "
                "change only what is needed, and run the failing commands yourself when possible "
                "before finishing. Changes to test/ and ci/ outside the rules are rejected and restored."
            ),
        }
    paths = [
        f"runs/eval/{req_id}",
        f"runs/eval/{req_id}/reports",
        f"runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json",
        f"runs/kit/{req_id}/docs/AGENT_EVAL_PROMPT.md",
        f"runs/kit/{req_id}/reports",
    ]
    return {
        "repair": repair,
        "previous_eval_context_paths": paths if repair else [],
        "guidance": (
            "When repair is true, inspect previous eval reports and focus on failed checks. "
            "Do not perform broad unrelated rewrites."
        )
        if repair
        else "",
    }


def _previous_eval_report_references(req_id: str) -> Dict[str, Any]:
    return {
        "root": f"runs/eval/{req_id}",
        "reports_root": f"runs/eval/{req_id}/reports",
        "glob": f"runs/eval/{req_id}/**/*.json",
        "read_only": True,
        "usage": "Read previous eval reports when present. Do not write under runs/eval from local-agent packages.",
    }


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


def _resolve_local_executor(payload: Dict[str, Any]) -> Optional[str]:
    """
    Resolve a concrete local executor from the request payload.

    The extension is the actuator, so the orchestrator must only return an
    executor that the extension can actually run. Selection is driven by the
    real availability reported in ``localAgentCapabilities`` (not merely by the
    configured command name). When capabilities are present and no executor is
    available, this returns ``None`` so the caller can fall back to cloud
    (prefer_local_agent) or fail deterministically (local_agent_only) instead
    of producing a package the actuator will certainly reject.
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
        if available(raw):
            return raw
        # Older clients do not send capabilities: trust the explicit request.
        if not capabilities:
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

    # No available executor. Keep backward compatibility for older clients that
    # do not report capabilities (assume the legacy default), but never hand the
    # actuator an executor the client has explicitly reported as unavailable.
    if not capabilities:
        return "gpt_codex"
    return None


def resolve_local_executor(payload: Dict[str, Any]) -> Optional[str]:
    """Public availability-aware resolver.

    Returns a concrete runnable executor id, or ``None`` when the client
    reported capabilities and none of the supported executors are available.
    """
    return _resolve_local_executor(payload)


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


def _safe_attachment_filename(name: str, fallback_index: int) -> str:
    """Sanitize an attachment name into a safe workspace-local file name."""
    base = _safe_text(name).replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not base:
        base = f"attachment_{fallback_index}"
    return base[:180]


def _materialize_attachments(
    payload: Dict[str, Any], phase_norm: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Materialize current-run attachments into workspace-local run-package files so
    the local agent can read them from its cwd without any external-path Read
    approval.

    Returns (manifest, package_files):
    - manifest: compact, content-free; each item exposes name, original_path
      (metadata only), workspace_path (the run-local copy), mime, size, and
      whether the content was materialized.
    - package_files: file entries the extension writes into the workspace before
      invoking the agent (same mechanism as the AGENT_* context/prompt files).
    """
    raw_attachments = payload.get("attachments")
    if not isinstance(raw_attachments, list):
        raw_attachments = []

    attach_root = f"runs/{phase_norm}/attachments"
    items: List[Dict[str, Any]] = []
    package_files: List[Dict[str, Any]] = []
    used_names: set = set()

    for index, attachment in enumerate(raw_attachments):
        if not isinstance(attachment, dict):
            continue

        name = _safe_text(attachment.get("name"))
        original_path = _safe_text(attachment.get("path"))

        item: Dict[str, Any] = {}
        if name:
            item["name"] = name
        if original_path:
            # Metadata only. The agent must never read this directly.
            item["original_path"] = original_path

        mime = _safe_text(attachment.get("mime") or attachment.get("type"))
        if mime:
            item["mime"] = mime
        size = attachment.get("size")
        if isinstance(size, (int, float)) and not isinstance(size, bool):
            item["size"] = int(size)

        # Resolve the inline content the extension forwarded for this attachment.
        content = attachment.get("content")
        content_base64 = attachment.get("bytes_b64") or attachment.get("content_base64")

        if isinstance(content, str) or isinstance(content_base64, str):
            safe_name = _safe_attachment_filename(name or original_path, index)
            # Avoid collisions when two attachments share a base name.
            candidate = safe_name
            dup = 1
            while candidate in used_names:
                stem, dot, ext = safe_name.partition(".")
                candidate = f"{stem}_{dup}{dot}{ext}" if dot else f"{safe_name}_{dup}"
                dup += 1
            used_names.add(candidate)

            workspace_path = f"{attach_root}/{candidate}"
            item["workspace_path"] = workspace_path
            item["materialized"] = True

            if isinstance(content, str):
                package_files.append(
                    {
                        "path": workspace_path,
                        "content": content,
                        "mime": mime or "text/plain",
                        "encoding": "utf-8",
                    }
                )
            else:
                package_files.append(
                    {
                        "path": workspace_path,
                        "content_base64": content_base64,
                        "mime": mime or "application/octet-stream",
                        "encoding": "base64",
                    }
                )
        else:
            # No inline content available to copy into the workspace.
            item["materialized"] = False

        if item:
            items.append(item)

    manifest = {
        "present": bool(items),
        "count": len(items),
        "items": items,
    }
    return manifest, package_files


def _capability_index_names(core_blobs: Dict[str, Any], kind: str) -> List[str]:
    """Available capability names of a kind from CLIKE_CAPABILITY_INDEX.json."""
    raw = str((core_blobs or {}).get("CLIKE_CAPABILITY_INDEX.json") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    items = data.get(kind) if isinstance(data, dict) else []
    names: List[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = _safe_text(item.get("name"))
            if name and name not in names:
                names.append(name)
    return names


def _manifest_capability_names(capability_manifest: Dict[str, Any], kind: str) -> List[str]:
    """Discovered capability names (lower-case) from a capability manifest dict (B2).

    Callers used to pass the manifest to _capability_index_names, which expects core blobs, so
    every capability counted as undiscovered.
    """
    index = {"CLIKE_CAPABILITY_INDEX.json": (capability_manifest or {}).get("index_content")}
    return [name.lower() for name in _capability_index_names(index, kind)]
