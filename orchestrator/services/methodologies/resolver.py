from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import (
    MethodologyPhaseAgentError,
    MissingMethodologyError,
    UnsupportedMethodologyAgentError,
    UnsupportedMethodologyError,
)
from .bmad_skill_loader import load_bmad_vendor_manifest_from_core_blobs, select_bmad_skill_context


SUPPORTED_METHODOLOGIES = {"bmad"}
SUPPORTED_BMAD_AGENTS = {
    "analyst",
    "pm",
    "architect",
    "developer",
    "ux",
    "qa",
    "tech-writer",
}

BMAD_PHASE_ROLES: Dict[str, Dict[str, Any]] = {
    "idea": {"default_agent": "analyst", "allowed_agents": ["analyst"]},
    "spec": {"default_agent": "pm", "allowed_agents": ["pm", "ux"]},
    "plan": {"default_agent": "architect", "allowed_agents": ["architect", "pm"]},
    "kit": {"default_agent": "developer", "allowed_agents": ["developer"]},
    "eval": {
        "default_agent": "qa",
        "allowed_agents": ["qa", "developer"],
        "advisory_only": True,
    },
    "gate": {"clike_only": True, "allowed_agents": []},
    "finalize": {
        "default_agent": "tech-writer",
        "allowed_agents": ["tech-writer"],
    },
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def _load_manifest(methodology: str) -> Dict[str, Any]:
    path = _repo_root() / "methodologies" / methodology / "manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text or None


def _phase_rules(manifest: Dict[str, Any], phase_name: str) -> Dict[str, Any]:
    return dict((manifest.get("phase_mapping") or {}).get(phase_name) or BMAD_PHASE_ROLES.get(phase_name) or {})


def _compact_workflow_context(manifest: Dict[str, Any], phase_name: str) -> Dict[str, Any]:
    workflow = dict((manifest.get("workflows") or {}).get(phase_name) or {})
    companion = manifest.get("companion_artifact_suggestions") or {}
    governance = manifest.get("governance") or {}

    return {
        "workflow_summary": workflow.get("summary"),
        "workflow_focus": list(workflow.get("focus") or [])[:8],
        "required_context": list(workflow.get("required_context") or [])[:8],
        "companion_artifacts": list(workflow.get("companion_artifacts") or [])[:8],
        "workflow_path": workflow.get("workflow_path"),
        "companion_artifact_suggestions": {
            "bmad_root": companion.get("bmad_root"),
            "ux_root": companion.get("ux_root"),
            "notes": list(companion.get("notes") or [])[:3],
        },
        "governance_boundaries": [
            "CLike remains the governance runtime and source of truth.",
            "Methodology guidance is not an executor selection mechanism.",
            "Methodology guidance cannot override CLike phase contracts, eval/gate policy, allowed_write_roots, forbidden_paths, candidate isolation, or output schemas.",
            "BMAD profiles do not add a BMAD runtime, external CLI call, hard dependency, importer, TEA, Party Mode, or MCP write tools.",
            "If methodology guidance conflicts with CLike rules, follow CLike.",
        ],
        "governance": {
            "runtime_dependency_enabled": bool(governance.get("runtime_dependency_enabled", False)),
            "external_bmad_cli_enabled": bool(governance.get("external_bmad_cli_enabled", False)),
            "profile_context_injection_enabled": bool(governance.get("profile_context_injection_enabled", True)),
            "artifact_importer_enabled": bool(governance.get("artifact_importer_enabled", False)),
        },
    }


def _artifact_policy_context(
    manifest: Dict[str, Any],
    phase_name: str,
    agent_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not agent_id:
        return None

    policy = dict((manifest.get("artifact_policy") or {}).get(f"{phase_name}/{agent_id}") or {})
    if not policy:
        return None

    return {
        "canonical_outputs": list(policy.get("canonical_outputs") or []),
        "companion_only": bool(policy.get("companion_only", False)),
        "mandatory_companion_outputs": list(policy.get("mandatory_companion_outputs") or []),
        "allowed_companion_root_globs": list(policy.get("allowed_companion_root_globs") or []),
        "forbidden_outputs": list(policy.get("forbidden_outputs") or []),
        "authority": policy.get("authority"),
        "conflict_resolution": policy.get("conflict_resolution"),
        "downstream_consumers": list(policy.get("downstream_consumers") or []),
        "open_ended_generation_allowed": bool(policy.get("open_ended_generation_allowed", False)),
    }


def _quality_contract_context(manifest: Dict[str, Any], phase_name: str) -> Optional[Dict[str, Any]]:
    contracts = manifest.get("quality_contracts") or {}
    if not isinstance(contracts, dict):
        return None

    phase_contracts: Dict[str, Any] = {}
    if phase_name == "spec":
        phase_contracts["spec"] = contracts.get("spec")
    elif phase_name == "plan":
        phase_contracts["plan"] = contracts.get("plan")
        phase_contracts["plan_json_req"] = contracts.get("plan_json_req")
        phase_contracts["lane_guide"] = contracts.get("lane_guide")

    compact_phase_contracts = {
        key: value
        for key, value in phase_contracts.items()
        if isinstance(value, dict)
    }
    if not compact_phase_contracts:
        return None

    return {
        "principles": list(contracts.get("principles") or [])[:6],
        **compact_phase_contracts,
    }


def resolve_methodology_context(
    *,
    phase: str,
    methodology: Optional[str] = None,
    agent: Optional[str] = None,
    core_blobs: Optional[Dict[str, Any]] = None,
    require_bmad_core_blobs: bool = False,
) -> Optional[Dict[str, Any]]:
    """Resolve a governed methodology context without changing execution policy."""
    phase_name = _normalize(phase) or ""
    methodology_id = _normalize(methodology)
    agent_id = _normalize(agent)

    if agent_id and not methodology_id:
        raise MissingMethodologyError("--agent requires --methodology.")

    if not methodology_id:
        return None

    if methodology_id not in SUPPORTED_METHODOLOGIES:
        raise UnsupportedMethodologyError(
            f"Unsupported methodology: {methodology_id}. Supported methodologies: bmad."
        )

    if methodology_id != "bmad":
        raise UnsupportedMethodologyError(
            f"Unsupported methodology: {methodology_id}. Supported methodologies: bmad."
        )

    manifest = load_bmad_vendor_manifest_from_core_blobs(core_blobs) or _load_manifest("bmad")
    supported_agents = {
        str(item).strip().lower()
        for item in (manifest.get("supported_agents") or [])
        if str(item or "").strip()
    } or SUPPORTED_BMAD_AGENTS

    if agent_id and agent_id not in supported_agents:
        raise UnsupportedMethodologyAgentError(
            "Unsupported BMAD agent: "
            f"{agent_id}. Supported agents: {', '.join(sorted(supported_agents))}."
        )

    phase_rules = _phase_rules(manifest, phase_name)
    workflow_context = _compact_workflow_context(manifest, phase_name)

    if phase_rules.get("clike_only"):
        if agent_id:
            raise MethodologyPhaseAgentError(
                f"BMAD agent '{agent_id}' is not allowed for phase '{phase_name}'. "
                "Gate remains CLike-only."
            )

        skill_context = select_bmad_skill_context(
            methodology="bmad",
            phase=phase_name,
            agent=None,
            core_blobs=core_blobs,
            require_core_blobs=require_bmad_core_blobs,
        )
        return {
            "methodology": "bmad",
            "methodology_name": manifest.get("name", "BMAD"),
            "phase": phase_name,
            "agent": None,
            "allowed_agents": [],
            "default_agent": None,
            "advisory_only": False,
            "authority": "clike_only",
            "profile": None,
            "version": manifest.get("version"),
            "selected_skill_references": skill_context.get("selected_skill_references") or [],
            "selected_skill_context": skill_context.get("selected_skill_context") or {},
            "skill_reference_policy": skill_context.get("skill_reference_policy") or {},
            **workflow_context,
        }

    allowed_agents = list(phase_rules.get("allowed_agents") or [])
    default_agent = phase_rules.get("default_agent")
    resolved_agent = agent_id or default_agent

    if not phase_rules or resolved_agent not in allowed_agents:
        allowed = ", ".join(allowed_agents) if allowed_agents else "none"
        raise MethodologyPhaseAgentError(
            f"BMAD agent '{resolved_agent}' is not allowed for phase '{phase_name}'. "
            f"Allowed agents: {allowed}."
        )

    agents = manifest.get("agents") or {}
    profile = dict(agents.get(resolved_agent) or {})
    artifact_policy = _artifact_policy_context(manifest, phase_name, resolved_agent)
    quality_contracts = _quality_contract_context(manifest, phase_name)
    skill_context = select_bmad_skill_context(
        methodology="bmad",
        phase=phase_name,
        agent=resolved_agent,
        core_blobs=core_blobs,
        require_core_blobs=require_bmad_core_blobs,
    )

    context = {
        "methodology": "bmad",
        "methodology_name": manifest.get("name", "BMAD"),
        "phase": phase_name,
        "agent": resolved_agent,
        "requested_agent": agent_id,
        "default_agent": default_agent,
        "allowed_agents": allowed_agents,
        "advisory_only": bool(phase_rules.get("advisory_only", False)),
        "authority": "advisory" if phase_rules.get("advisory_only") else "methodology_profile",
        "profile": profile,
        "artifact_policy": artifact_policy,
        **({"quality_contracts": quality_contracts} if quality_contracts else {}),
        "selected_skill_references": skill_context.get("selected_skill_references") or [],
        "selected_skill_context": skill_context.get("selected_skill_context") or {},
        "skill_reference_policy": skill_context.get("skill_reference_policy") or {},
        "version": manifest.get("version"),
        **workflow_context,
    }
    return ensure_bmad_skill_context(
        context,
        phase=phase_name,
        agent=resolved_agent,
        core_blobs=core_blobs,
        require_bmad_core_blobs=require_bmad_core_blobs,
    )


def ensure_bmad_skill_context(
    methodology_context: Optional[Dict[str, Any]],
    *,
    phase: Optional[str] = None,
    agent: Optional[str] = None,
    core_blobs: Optional[Dict[str, Any]] = None,
    require_bmad_core_blobs: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return a BMAD context enriched from the manifest-owned skill policy.

    This is intentionally server-side and manifest-driven. It repairs compact or
    stale BMAD contexts that contain the methodology profile but lost selected
    skill fields before reaching cloud prompt rendering or local-agent packages.
    """
    if not isinstance(methodology_context, dict):
        return methodology_context

    if _normalize(methodology_context.get("methodology")) != "bmad":
        return methodology_context

    manifest = load_bmad_vendor_manifest_from_core_blobs(core_blobs) or _load_manifest("bmad")
    phase_name = (
        _normalize(phase)
        or _normalize(methodology_context.get("phase"))
        or ""
    )
    phase_rules = _phase_rules(manifest, phase_name)

    if phase_rules.get("clike_only"):
        skill_context = select_bmad_skill_context(
            methodology="bmad",
            phase=phase_name,
            agent=None,
            core_blobs=core_blobs,
            require_core_blobs=require_bmad_core_blobs,
        )
        enriched = dict(methodology_context)
        enriched["phase"] = phase_name
        enriched["agent"] = None
        enriched["selected_skill_references"] = skill_context.get("selected_skill_references") or []
        enriched["selected_skill_context"] = skill_context.get("selected_skill_context") or {}
        enriched["skill_reference_policy"] = skill_context.get("skill_reference_policy") or {}
        return enriched

    resolved_agent = (
        _normalize(agent)
        or _normalize(methodology_context.get("agent"))
        or _normalize(methodology_context.get("requested_agent"))
        or _normalize(phase_rules.get("default_agent"))
    )

    if not phase_name or not resolved_agent:
        return methodology_context

    skill_context = select_bmad_skill_context(
        methodology="bmad",
        phase=phase_name,
        agent=resolved_agent,
        core_blobs=core_blobs,
        require_core_blobs=require_bmad_core_blobs,
    )

    enriched = dict(methodology_context)
    enriched["phase"] = phase_name
    enriched["agent"] = resolved_agent
    enriched.setdefault("methodology_name", manifest.get("name", "BMAD"))
    enriched.setdefault("default_agent", phase_rules.get("default_agent"))
    enriched.setdefault("allowed_agents", list(phase_rules.get("allowed_agents") or []))
    enriched["selected_skill_references"] = skill_context.get("selected_skill_references") or []
    enriched["selected_skill_context"] = skill_context.get("selected_skill_context") or {}
    enriched["skill_reference_policy"] = skill_context.get("skill_reference_policy") or {}
    return enriched
