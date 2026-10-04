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
