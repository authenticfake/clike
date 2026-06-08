from services.execution_policy import resolve_execution_policy


DOCUMENT_PHASES = ["idea", "spec", "plan"]
ACTUATOR_PHASES = ["kit", "eval", "finalize", "extend"]


def test_document_phases_supported_for_prefer_local_agent():
    for phase in DOCUMENT_PHASES:
        policy = resolve_execution_policy(
            phase=phase,
            execution_preference="prefer_local_agent",
        )
        assert policy["phase_supported"] is True
        assert policy["selected"] == "local_agent"
        assert policy["eligible"] is True
        assert policy["fallback_applied"] is False


def test_document_phases_supported_for_local_agent_only():
    for phase in DOCUMENT_PHASES:
        policy = resolve_execution_policy(
            phase=phase,
            execution_preference="local_agent_only",
        )
        assert policy["phase_supported"] is True
        assert policy["selected"] == "local_agent"


def test_document_phases_auto_prefers_cloud_path():
    for phase in DOCUMENT_PHASES:
        policy = resolve_execution_policy(phase=phase, execution_preference="auto")
        assert policy["selected"] == "cloud"
        assert policy["phase_supported"] is True


def test_document_phases_cloud_only_forces_cloud():
    for phase in DOCUMENT_PHASES:
        policy = resolve_execution_policy(phase=phase, execution_preference="cloud_only")
        assert policy["selected"] == "cloud"
        assert policy["eligible"] is False


def test_existing_actuator_phases_unchanged_for_prefer_local_agent():
    for phase in ACTUATOR_PHASES:
        policy = resolve_execution_policy(
            phase=phase,
            execution_preference="prefer_local_agent",
        )
        assert policy["selected"] == "local_agent"
        assert policy["phase_supported"] is True


def test_unknown_phase_not_supported_for_local_agent():
    policy = resolve_execution_policy(phase="gate", execution_preference="prefer_local_agent")
    assert policy["phase_supported"] is False
    assert policy["selected"] == "cloud"
    assert policy["fallback_applied"] is True
