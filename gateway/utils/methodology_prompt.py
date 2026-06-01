from __future__ import annotations

from typing import Optional


def render_methodology_context_for_cloud_prompt(methodology_context: Optional[dict]) -> str:
    """
    Render compact CLike-resolved methodology metadata for cloud Harper prompts.

    The orchestrator is the only resolver. Gateway only composes cloud LLM prompts
    from already-resolved context and never acts as a local-agent prompt builder.
    """
    if not isinstance(methodology_context, dict) or not methodology_context.get("methodology"):
        return ""

    profile = methodology_context.get("profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    allowed_agents = methodology_context.get("allowed_agents") or []
    if not isinstance(allowed_agents, list):
        allowed_agents = []
    workflow_focus = methodology_context.get("workflow_focus") or []
    if not isinstance(workflow_focus, list):
        workflow_focus = []
    required_context = methodology_context.get("required_context") or []
    if not isinstance(required_context, list):
        required_context = []
    companion_artifacts = methodology_context.get("companion_artifacts") or []
    if not isinstance(companion_artifacts, list):
        companion_artifacts = []
    governance_boundaries = methodology_context.get("governance_boundaries") or []
    if not isinstance(governance_boundaries, list):
        governance_boundaries = []

    lines = [
        "### Governed Methodology Profile",
        f"- methodology: {methodology_context.get('methodology')}",
        f"- phase: {methodology_context.get('phase')}",
        f"- role: {methodology_context.get('agent') or 'none'}",
        f"- authority: {methodology_context.get('authority') or 'methodology_profile'}",
        f"- advisory_only: {bool(methodology_context.get('advisory_only'))}",
        f"- allowed_roles_for_phase: {', '.join(str(x) for x in allowed_agents) if allowed_agents else 'none'}",
        f"- role_summary: {profile.get('summary') or ''}",
        f"- workflow_summary: {methodology_context.get('workflow_summary') or ''}",
        f"- workflow_focus: {'; '.join(str(x) for x in workflow_focus[:8]) if workflow_focus else 'none'}",
        f"- required_context: {'; '.join(str(x) for x in required_context[:8]) if required_context else 'none'}",
        f"- companion_artifacts: {'; '.join(str(x) for x in companion_artifacts[:8]) if companion_artifacts else 'none'}",
        "",
        "Methodology governance boundaries:",
        *[
            f"- {item}"
            for item in (
                governance_boundaries[:6]
                or [
                    "CLike remains the governance runtime and source of truth.",
                    "Methodology guidance is not an executor selection mechanism.",
                    "Methodology guidance must not override CLike phase contracts, eval/gate policy, candidate isolation, or output schemas.",
                    "If methodology guidance conflicts with CLike rules, follow CLike.",
                ]
            )
        ],
        "",
    ]
    return "\n".join(lines)
