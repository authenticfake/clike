import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.active_output_contract import build_active_output_contract
from services.methodologies.resolver import resolve_methodology_context


def test_native_local_kit_contract_is_candidate_scoped():
    contract = build_active_output_contract(
        phase="kit",
        runner="local_agent",
        req_id="REQ-001",
    )

    assert contract["methodology"] == "native_clike"
    assert "runs/kit/REQ-001/src/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/test/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/ci/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md" not in contract["required_outputs"]
    assert contract["strict_missing_required_outputs"] is False


def test_bmad_local_kit_contract_extends_candidate_outputs_with_developer_docs():
    context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
    )

    contract = build_active_output_contract(
        phase="kit",
        runner="local_agent",
        methodology_context=context,
        req_id="REQ-001",
    )

    assert contract["methodology"] == "bmad"
    assert contract["agent"] == "developer"
    assert "runs/kit/REQ-001/src/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/test/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/ci/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/SELF_REVIEW.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/RUNBOOK.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/**" in contract["allowed_optional_output_globs"]
    assert "src/**" in contract["forbidden_output_globs"]


def test_bmad_local_eval_contract_includes_advisory_outputs_without_authority():
    context = resolve_methodology_context(
        phase="eval",
        methodology="bmad",
        agent="qa",
    )

    contract = build_active_output_contract(
        phase="eval",
        runner="local_agent",
        methodology_context=context,
        req_id="REQ-001",
    )

    assert contract["methodology"] == "bmad"
    assert contract["agent"] == "qa"
    assert "runs/kit/REQ-001/reports/BMAD_EVAL_REPAIR_NOTES.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/FIX_GUIDANCE.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/MISSING_TESTS.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/RISK_REVIEW.md" in contract["required_outputs"]
    assert "runs/eval/REQ-001/**" in contract["forbidden_output_globs"]
    assert contract["strict_missing_required_outputs"] is False


def test_gate_has_no_bmad_active_output_contract_authority():
    context = resolve_methodology_context(phase="gate", methodology="bmad")

    assert context["authority"] == "clike_only"
    assert "artifact_policy" not in context

    contract = build_active_output_contract(
        phase="gate",
        runner="local_agent",
        methodology_context=context,
    )

    assert contract["methodology"] == "native_clike"
    assert contract["required_outputs"] == []
