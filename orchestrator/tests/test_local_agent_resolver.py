from services.execution_policy import resolve_execution_policy
from services.local_agent_package import resolve_local_executor


def _capabilities(claude_available: bool, codex_available: bool) -> dict:
    return {
        "claude_code": {
            "enabled": True,
            "configured_command": "claude",
            "command_found": claude_available,
            "available": claude_available,
        },
        "gpt_codex": {
            "enabled": True,
            "configured_command": "codex",
            "command_found": codex_available,
            "available": codex_available,
        },
    }


def test_resolves_claude_when_only_claude_available():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=True, codex_available=False),
    }
    assert resolve_local_executor(payload) == "claude_code"


def test_resolves_codex_when_only_codex_available():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=False, codex_available=True),
    }
    assert resolve_local_executor(payload) == "gpt_codex"


def test_returns_none_when_no_executor_available():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=False, codex_available=False),
    }
    assert resolve_local_executor(payload) is None


def test_explicit_unavailable_executor_is_not_forced_when_another_is_available():
    payload = {
        "localAgentExecutor": "gpt_codex",
        "localAgentCapabilities": _capabilities(claude_available=True, codex_available=False),
    }
    assert resolve_local_executor(payload) == "claude_code"


def test_legacy_client_without_capabilities_keeps_default():
    # Older clients do not report capabilities; keep backward-compatible default.
    assert resolve_local_executor({"localAgentExecutor": "auto"}) == "gpt_codex"
    assert resolve_local_executor({"localAgentExecutor": "claude_code"}) == "claude_code"


# --- Gate contract -----------------------------------------------------------
# The availability-aware gate in services.harper composes resolve_execution_policy
# with resolve_local_executor. These tests pin that decision table so a no-runnable
# executor never yields a gpt_codex package and agent-only never falls back to cloud.

def _gate_decision(*, phase: str, preference: str, payload: dict) -> str:
    policy = resolve_execution_policy(phase=phase, execution_preference=preference)
    if policy.get("selected") != "local_agent":
        return policy["selected"]
    if resolve_local_executor(payload):
        return "local_agent"
    return "error" if preference == "local_agent_only" else "cloud_fallback"


def test_gate_prefer_agent_uses_claude_not_codex_when_only_claude_available():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=True, codex_available=False),
    }
    assert resolve_local_executor(payload) == "claude_code"
    assert _gate_decision(phase="spec", preference="prefer_local_agent", payload=payload) == "local_agent"


def test_gate_prefer_agent_falls_back_to_cloud_when_no_executor_available():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=False, codex_available=False),
    }
    assert _gate_decision(phase="spec", preference="prefer_local_agent", payload=payload) == "cloud_fallback"


def test_gate_agent_only_errors_and_never_falls_back_to_cloud():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=False, codex_available=False),
    }
    assert _gate_decision(phase="spec", preference="local_agent_only", payload=payload) == "error"


def test_gate_cloud_only_never_selects_local_agent():
    payload = {
        "localAgentExecutor": "auto",
        "localAgentCapabilities": _capabilities(claude_available=True, codex_available=True),
    }
    assert _gate_decision(phase="kit", preference="cloud_only", payload=payload) == "cloud"
