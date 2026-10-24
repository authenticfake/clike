"""SPEC decides ordinary choices, PLAN marks only owner questions as blockers, KIT never stops on an open
detail: the same rule for the cloud model and the local agents (ShortLink: 8 open decisions, a KIT
without code)."""

from pathlib import Path

from services.phase_definitions import phase_definition, phase_text

PHASES = Path(__file__).resolve().parents[1] / "phases"


def _cloud(phase: str) -> str:
    return (PHASES / phase / "cloud_system.md").read_text(encoding="utf-8")


def _one(lines, marker):
    [line] = [line for line in lines if marker in line]
    return line


def test_spec_decides_ordinary_choices_for_cloud_and_agent():
    rule = _one(phase_definition("spec")["local_agent"]["hard_rules"], "Decide, do not defer")
    assert rule in _cloud("spec")
    assert "OPEN-01" in rule and "Assumptions" in rule


def test_plan_marks_only_owner_questions_as_blockers_for_cloud_and_agent():
    line = _one(phase_definition("plan")["local_agent"]["prompt_lines"], "kit_ready")
    rule = line.split("reqs[].blockers. ", 1)[1]
    assert rule in _cloud("plan")
    assert '"kit_ready": true' in _cloud("plan") and '"blockers": []' in _cloud("plan")


def test_kit_never_stops_on_an_open_detail_for_cloud_and_agent():
    line = _one(phase_text("_shared")["render_compact_local_agent_prompt.kit_rules"], "not a reason to stop")
    assert line.removeprefix("- ") in _cloud("kit")


def test_kit_checks_never_wait_for_a_person_nor_reach_reserved_hosts_for_cloud_and_agent():
    line = _one(phase_text("_shared")["render_compact_local_agent_prompt.kit_rules"], "waits for a person")
    assert line.removeprefix("- ") in _cloud("kit")
    assert "reserved hosts" in line
