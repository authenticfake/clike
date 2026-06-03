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

    if agent_id and agent_id not in SUPPORTED_BMAD_AGENTS:
        raise UnsupportedMethodologyAgentError(
            "Unsupported BMAD agent: "
            f"{agent_id}. Supported agents: {', '.join(sorted(SUPPORTED_BMAD_AGENTS))}."
        )

    manifest = _load_manifest("bmad")
    phase_rules = dict((manifest.get("phase_mapping") or {}).get(phase_name) or BMAD_PHASE_ROLES.get(phase_name) or {})
    workflow_context = _compact_workflow_context(manifest, phase_name)

    if phase_rules.get("clike_only"):
        if agent_id:
            raise MethodologyPhaseAgentError(
                f"BMAD agent '{agent_id}' is not allowed for phase '{phase_name}'. "
                "Gate remains CLike-only."
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

    return {
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
        "version": manifest.get("version"),
        **workflow_context,
    }
