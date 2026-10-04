"""Phase → cloud system prompt mapping (WP7.7, moved with the composition in WP8.7)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from fastapi import HTTPException  # noqa: E402

from services.cloud_prompt import messages  # noqa: E402

PHASES = ORCHESTRATOR_ROOT / "phases"


def _compose(phase):
    return messages._compose_system_messages(phase, "# idea", {}, None, None, "run-1", None, None)


@pytest.mark.parametrize("phase", ["eval", "gate"])
def test_eval_and_gate_use_their_own_prompts(phase):
    expected = (PHASES / phase / "cloud_system.md").read_text(encoding="utf-8").strip()[:200]
    assert expected in _compose(phase)[0]["content"]


def test_every_phase_prompt_file_exists():
    for name in ("idea", "spec", "plan", "kit", "eval", "gate", "finalize", "extend"):
        assert (PHASES / name / "cloud_system.md").is_file(), name
    for stage in ("integrity_eval", "promotion_hardener", "promotion_eval"):
        assert (PHASES / "kit" / f"cloud_{stage}.md").is_file(), stage


def test_unknown_phase_is_rejected():
    with pytest.raises(HTTPException) as ctx:
        _compose("deploy")
    assert ctx.value.status_code == 400


def test_missing_prompt_is_an_error_not_a_placeholder():
    with patch.object(messages, "PROMPT_SPEC_SYSTEM_PATH", "/nonexistent/spec_system.md"):
        with pytest.raises(HTTPException) as ctx:
            _compose("spec")
    assert ctx.value.status_code == 503


def test_idea_output_checklist_prefers_begin_file_blocks():
    checklist = messages._output_checklist_for_phase("idea")

    assert "BEGIN_FILE / END_FILE" in checklist
    assert "Markdown file contents may contain fenced code blocks" in checklist
    assert "Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks" in checklist
    assert "Emit one or more `file:/path` blocks with complete file contents" not in checklist


def test_shared_output_contract_and_canonical_validation_are_identical_in_both_services():
    # The orchestrator composes prompts with these rules; the gateway validates model output with
    # them. Until both services share a package, the copies must stay byte-identical.
    repo = ORCHESTRATOR_ROOT.parent
    pairs = [
        ("services/cloud_prompt/active_output_contract.py", "gateway/utils/active_output_contract.py"),
        ("services/cloud_prompt/canonical_validation.py", "gateway/utils/harper_canonical_validation.py"),
    ]
    for orch, gw in pairs:
        assert (ORCHESTRATOR_ROOT / orch).read_bytes() == (repo / gw).read_bytes(), orch


def _golden_user(name):
    import json

    data = json.loads((ORCHESTRATOR_ROOT / f"tests/golden/snapshots/{name}.json").read_text(encoding="utf-8"))
    payload = data["gateway_calls"][0]["payload"]
    return payload, payload["composed_messages"][1]["content"]


def test_plan_receives_idea_and_spec_content_not_just_their_names():
    # B6: with SPEC "reference only" the model produced an empty plan.json (live run, gpt-6.1-sol).
    payload, user = _golden_user("plan__cloud__native")
    assert "### SPEC.md (verbatim)" in user and "### SPEC.md (reference only)" not in user
    assert "### IDEA.md (verbatim)" in user
    spec_line = next(line for line in payload["core_blobs"]["SPEC.md"].splitlines() if len(line) > 40)
    assert spec_line in user


def test_kit_receives_technology_constraints_spec_and_target_req():
    # B5: without TECH_CONSTRAINTS/SPEC the model picked Flask for a FastAPI project (live run).
    payload, user = _golden_user("kit__cloud__native")
    context = user.split("## PROJECT CONTEXT", 1)[1].split("## HARD RULES", 1)[0]
    assert "framework: fastapi" in context
    assert "### SPEC.md (verbatim)" in context and "### IDEA.md (verbatim)" in context
    assert '"id": "REQ-001"' in context
    assert '"id": "REQ-002"' not in context  # only the target REQ and its dependencies
