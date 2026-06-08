from __future__ import annotations

from typing import Any, Dict

# Local agent execution is intentionally restricted.
#
# Recovery rule:
# - /idea, /spec, /plan are early Harper document phases. They may use a
#   local-agent document package that writes only their canonical Harper outputs.
# - /kit base phase can use a local agent execution package.
# - /eval may use a local-agent pre-pass, but canonical CLike EvalRunner remains the final judge.
# - /finalize may use a local-agent solution integration package because it needs
# - /estend may use a local-agent solution integration package because it needs
#   real workspace inspection, composition wiring, local scripts, and runnability evidence.
# - kit follow-up phases are orchestrator/cloud-owned until the local contract is stable.
_ALLOWED_LOCAL_AGENT_PHASES = {
    "idea",
    "spec",
    "plan",
    "kit",
    "eval",
    "finalize",
    "extend",
}


def normalize_execution_preference(value: Any) -> str:
    raw = str(value or "").strip().lower()

    # Backward compatibility with the old Claude-specific UI values.
    if raw == "prefer_claude_code":
        return "prefer_local_agent"
    if raw == "claude_code_only":
        return "local_agent_only"

    allowed = {
        "auto",
        "cloud_only",
        "prefer_local_agent",
        "local_agent_only",
        "hybrid",
    }
    return raw if raw in allowed else "auto"


def resolve_execution_policy(
    *,
    phase: str,
    execution_preference: Any,
) -> Dict[str, Any]:
    pref = normalize_execution_preference(execution_preference)
    phase_norm = str(phase or "").strip().lower()

    phase_supported = phase_norm in _ALLOWED_LOCAL_AGENT_PHASES

    selected = "cloud"
    requested = pref
    eligible = False
    reason = "default_cloud"
    fallback_applied = False

    if pref == "cloud_only":
        selected = "cloud"
        eligible = False
        reason = "forced_cloud"

    elif pref == "auto":
        selected = "cloud"
        eligible = phase_supported
        reason = "auto_prefers_current_cloud_path"

    elif pref == "prefer_local_agent":
        if phase_supported:
            selected = "local_agent"
            eligible = True
            reason = "local_agent_preferred_for_phase"
        else:
            selected = "cloud"
            eligible = False
            fallback_applied = True
            reason = "phase_not_supported_for_local_agent"

    elif pref == "local_agent_only":
        if phase_supported:
            selected = "local_agent"
            eligible = True
            reason = "local_agent_only_for_phase"
        else:
            selected = "cloud"
            eligible = False
            fallback_applied = True
            reason = "phase_not_supported_for_local_agent"

    elif pref == "hybrid":
        # Hybrid is not a separate execution path yet.
        # For the recovery tranche, it means: prefer the orchestrator-owned
        # local package where safe, otherwise fall back to cloud.
        if phase_supported:
            selected = "local_agent"
            eligible = True
            reason = "hybrid_uses_local_agent_package_for_supported_phase"
        else:
            selected = "cloud"
            eligible = False
            fallback_applied = True
            reason = "phase_not_supported_for_hybrid"

    return {
        "requested": requested,
        "selected": selected,
        "eligible": eligible,
        "phase_supported": phase_supported,
        "fallback_applied": fallback_applied,
        "reason": reason,
    }