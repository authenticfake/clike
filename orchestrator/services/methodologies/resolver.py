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
    phase_rules = dict(BMAD_PHASE_ROLES.get(phase_name) or {})

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
        "version": manifest.get("version"),
    }
