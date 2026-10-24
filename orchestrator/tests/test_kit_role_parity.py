"""The KIT's role for the target lane is the same for the cloud model and the local agents."""

from pathlib import Path

from services.phase_definitions import phase_text

PHASES = Path(__file__).resolve().parents[1] / "phases"


def test_cloud_and_agent_kit_prompts_state_the_same_lane_role():
    [role] = phase_text("_shared")["render_compact_local_agent_prompt.kit_role"]
    assert role in (PHASES / "kit" / "cloud_system.md").read_text(encoding="utf-8")
    for stack in ("Go", "Ruby", "Swift/iOS", "Flutter", "IEC 61131-3", "Mendix"):
        assert stack in role
