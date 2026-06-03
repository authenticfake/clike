import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = REPO_ROOT / "gateway"
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.resolver import resolve_methodology_context


def _load_gateway_module(name: str, relative_path: str):
    path = GATEWAY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract_module = _load_gateway_module("gateway_active_output_contract", "utils/active_output_contract.py")
methodology_prompt_module = _load_gateway_module("gateway_methodology_prompt_contract", "utils/methodology_prompt.py")

build_active_output_contract = contract_module.build_active_output_contract
validate_files_against_active_output_contract = contract_module.validate_files_against_active_output_contract
render_methodology_context_for_cloud_prompt = methodology_prompt_module.render_methodology_context_for_cloud_prompt


def _bmad_contract(phase: str, agent: str, req_id: str | None = None):
    context = resolve_methodology_context(
        phase=phase,
        methodology="bmad",
        agent=agent,
    )
    return build_active_output_contract(
        phase=phase,
        runner="cloud",
        methodology_context=context,
        req_id=req_id,
    )


def test_native_idea_cloud_contract_requires_only_idea():
    contract = build_active_output_contract(phase="idea", runner="cloud")

    assert contract["methodology"] == "native_clike"
    assert contract["required_outputs"] == ["docs/harper/IDEA.md"]
    assert "docs/harper/bmad/idea/BRIEF.md" not in contract["required_outputs"]


def test_bmad_idea_analyst_cloud_contract_requires_canonical_and_companions():
    contract = _bmad_contract("idea", "analyst")

    assert contract["methodology"] == "bmad"
    assert contract["agent"] == "analyst"
    assert "docs/harper/IDEA.md" in contract["required_outputs"]
    assert "docs/harper/bmad/idea/BRIEF.md" in contract["required_outputs"]
    assert "docs/harper/bmad/idea/PRFAQ_NOTES.md" in contract["required_outputs"]
    assert "docs/harper/bmad/idea/ASSUMPTIONS.md" in contract["required_outputs"]
    assert "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md" in contract["required_outputs"]
    assert contract["strict_missing_required_outputs"] is True


def test_bmad_spec_pm_cloud_contract_can_emit_spec_and_product_companions():
    contract = _bmad_contract("spec", "pm")

    assert "docs/harper/SPEC.md" in contract["required_outputs"]
    assert "docs/harper/bmad/spec/PRD.md" in contract["required_outputs"]
    assert "docs/harper/bmad/spec/EPICS.md" in contract["required_outputs"]
    assert "docs/harper/bmad/spec/ACCEPTANCE_MODEL.md" in contract["required_outputs"]
    assert "docs/harper/bmad/spec/SCOPE_DECISIONS.md" in contract["required_outputs"]
    assert "docs/harper/bmad/spec/**" in contract["allowed_optional_output_globs"]


def test_bmad_spec_ux_cloud_contract_is_companion_only_and_forbids_spec():
    contract = _bmad_contract("spec", "ux")

    assert "docs/harper/SPEC.md" not in contract["required_outputs"]
    assert "docs/harper/ux/DESIGN.md" in contract["required_outputs"]
    assert "docs/harper/ux/EXPERIENCE.md" in contract["required_outputs"]
    assert contract["allowed_optional_output_globs"] == ["docs/harper/ux/**"]
    assert "docs/harper/SPEC.md" in contract["forbidden_output_globs"]


def test_bmad_plan_architect_cloud_contract_includes_plan_json_lane_guides_and_architecture():
    contract = _bmad_contract("plan", "architect")

    assert "docs/harper/PLAN.md" in contract["required_outputs"]
    assert "docs/harper/plan.json" in contract["required_outputs"]
    assert "docs/harper/lane-guides/**" in contract["required_outputs"]
    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" in contract["required_outputs"]
    assert "docs/harper/bmad/architecture/DECISIONS.md" in contract["required_outputs"]
    assert "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md" in contract["required_outputs"]
    assert "docs/harper/bmad/architecture/RISKS.md" in contract["required_outputs"]


def test_bmad_plan_pm_cloud_contract_includes_story_companions():
    contract = _bmad_contract("plan", "pm")

    assert "docs/harper/PLAN.md" in contract["required_outputs"]
    assert "docs/harper/plan.json" in contract["required_outputs"]
    assert "docs/harper/lane-guides/**" in contract["required_outputs"]
    assert "docs/harper/bmad/plan/STORIES.md" in contract["required_outputs"]
    assert "docs/harper/bmad/plan/STORY_MAP.md" in contract["required_outputs"]
    assert "docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md" in contract["required_outputs"]


def test_native_plan_contract_rejects_bmad_architecture_companion():
    contract = build_active_output_contract(phase="plan", runner="cloud")
    result = validate_files_against_active_output_contract(
        [
            {"path": "docs/harper/PLAN.md", "content": "# Plan"},
            {"path": "docs/harper/plan.json", "content": "{}"},
            {"path": "docs/harper/lane-guides/python.md", "content": "# Python"},
            {"path": "docs/harper/bmad/architecture/ARCHITECTURE.md", "content": "# Architecture"},
        ],
        contract,
    )

    assert result["ok"] is False
    assert result["disallowed_outputs"] == ["docs/harper/bmad/architecture/ARCHITECTURE.md"]


def test_bmad_plan_architect_contract_allows_architecture_companions():
    contract = _bmad_contract("plan", "architect")
    result = validate_files_against_active_output_contract(
        [
            {"path": "docs/harper/PLAN.md", "content": "# Plan"},
            {"path": "docs/harper/plan.json", "content": "{}"},
            {"path": "docs/harper/lane-guides/python.md", "content": "# Python"},
            {"path": "docs/harper/bmad/architecture/ARCHITECTURE.md", "content": "# Architecture"},
            {"path": "docs/harper/bmad/architecture/DECISIONS.md", "content": "# Decisions"},
            {"path": "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md", "content": "# Boundaries"},
            {"path": "docs/harper/bmad/architecture/RISKS.md", "content": "# Risks"},
        ],
        contract,
    )

    assert result["ok"] is True
    assert result["disallowed_outputs"] == []


def test_bmad_plan_pm_contract_allows_plan_companions():
    contract = _bmad_contract("plan", "pm")
    result = validate_files_against_active_output_contract(
        [
            {"path": "docs/harper/PLAN.md", "content": "# Plan"},
            {"path": "docs/harper/plan.json", "content": "{}"},
            {"path": "docs/harper/lane-guides/python.md", "content": "# Python"},
            {"path": "docs/harper/bmad/plan/STORIES.md", "content": "# Stories"},
            {"path": "docs/harper/bmad/plan/STORY_MAP.md", "content": "# Story Map"},
            {"path": "docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md", "content": "# Readiness"},
        ],
        contract,
    )

    assert result["ok"] is True
    assert result["disallowed_outputs"] == []


def test_bmad_kit_developer_cloud_contract_replaces_req_id():
    contract = _bmad_contract("kit", "developer", req_id="REQ-001")

    assert "runs/kit/REQ-001/src/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/test/**" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md" in contract["required_outputs"]
    assert "runs/kit/REQ-001/docs/RUNBOOK.md" in contract["required_outputs"]


def test_bmad_eval_qa_cloud_contract_is_advisory_docs_only():
    contract = _bmad_contract("eval", "qa", req_id="REQ-001")

    assert contract["required_outputs"] == [
        "runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md",
        "runs/kit/REQ-001/docs/FIX_GUIDANCE.md",
        "runs/kit/REQ-001/docs/MISSING_TESTS.md",
        "runs/kit/REQ-001/docs/RISK_REVIEW.md",
    ]
    assert "runs/eval/REQ-001/**" in contract["forbidden_output_globs"]
    assert contract["strict_missing_required_outputs"] is False


def test_bmad_finalize_cloud_contract_extends_native_finalize_outputs():
    contract = _bmad_contract("finalize", "tech-writer")

    assert "README.md" in contract["required_outputs"]
    assert "docs/harper/HOWTO_RUN.md" in contract["required_outputs"]
    assert "docs/harper/PR_BODY.md" in contract["required_outputs"]
    assert "docs/harper/bmad/finalize/DOC_REVIEW.md" in contract["required_outputs"]
    assert "docs/harper/bmad/finalize/RELEASE_NARRATIVE.md" in contract["required_outputs"]
    assert "docs/harper/bmad/finalize/STAKEHOLDER_SUMMARY.md" in contract["required_outputs"]


def test_validation_reports_missing_required_bmad_outputs():
    contract = _bmad_contract("idea", "analyst")

    result = validate_files_against_active_output_contract(
        [{"path": "docs/harper/IDEA.md", "content": "# Idea"}],
        contract,
    )

    assert result["ok"] is False
    assert "docs/harper/bmad/idea/BRIEF.md" in result["missing_required_outputs"]
    assert "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md" in result["missing_required_outputs"]


def test_validation_rejects_forbidden_spec_ux_output():
    contract = _bmad_contract("spec", "ux")

    result = validate_files_against_active_output_contract(
        [
            {"path": "docs/harper/SPEC.md", "content": "# Forbidden"},
            {"path": "docs/harper/ux/DESIGN.md", "content": "# Design"},
        ],
        contract,
    )

    assert result["ok"] is False
    assert result["forbidden_outputs"] == ["docs/harper/SPEC.md"]


def test_validation_allows_extra_bmad_file_only_under_optional_glob():
    contract = _bmad_contract("idea", "analyst")
    files = [
        {"path": path, "content": ""}
        for path in contract["required_outputs"]
    ]
    files.append({"path": "docs/harper/bmad/idea/DEEP_DIVE_X.md", "content": "# Deep Dive"})

    ok_result = validate_files_against_active_output_contract(files, contract)
    assert ok_result["ok"] is True

    bad_result = validate_files_against_active_output_contract(
        [*files, {"path": "docs/harper/bmad/spec/WRONG.md", "content": "# Wrong"}],
        contract,
    )
    assert bad_result["ok"] is False
    assert bad_result["disallowed_outputs"] == ["docs/harper/bmad/spec/WRONG.md"]


def test_rendered_bmad_idea_prompt_contract_contains_required_outputs_and_no_conflict_text():
    context = resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    contract = build_active_output_contract(
        phase="idea",
        runner="cloud",
        methodology_context=context,
    )

    rendered = render_methodology_context_for_cloud_prompt(context, active_output_contract=contract)

    assert "### Active Output Contract" in rendered
    assert "Emit each output as a BEGIN_FILE / END_FILE block" in rendered
    assert "BEGIN_FILE relative/path" in rendered
    assert "END_FILE" in rendered
    assert "Markdown file contents may contain fenced code blocks" in rendered
    assert "Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks" in rendered
    assert "Emit one or more `file:/path` blocks with complete file contents" not in rendered
    assert "### BMAD Companion Artifact Contract" in rendered
    for path in [
        "docs/harper/bmad/idea/BRIEF.md",
        "docs/harper/bmad/idea/PRFAQ_NOTES.md",
        "docs/harper/bmad/idea/ASSUMPTIONS.md",
        "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md",
    ]:
        assert path in rendered
    assert "Print EXCLUSIVELY one file block" not in rendered
    assert "Produce only the single" not in rendered
    assert "No additional files" not in rendered


def test_rendered_native_idea_prompt_contract_has_no_bmad_block():
    contract = build_active_output_contract(phase="idea", runner="cloud")
    rendered = render_methodology_context_for_cloud_prompt(None, active_output_contract=contract)

    assert "### Active Output Contract" in rendered
    assert "Emit each output as a BEGIN_FILE / END_FILE block" in rendered
    assert "Markdown file contents may contain fenced code blocks" in rendered
    assert "Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks" in rendered
    assert "Emit one or more `file:/path` blocks with complete file contents" not in rendered
    assert "docs/harper/IDEA.md" in rendered
    assert "BMAD Companion Artifact Contract" not in rendered
    assert "docs/harper/bmad/idea/BRIEF.md" not in rendered


def test_static_prompt_files_do_not_contain_unconditional_native_single_file_restrictions():
    forbidden = [
        "Print EXCLUSIVELY one file block",
        "Produce **only** the single",
        "Produce only the single",
        "No additional files",
    ]
    for path in (GATEWAY_ROOT / "prompts").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{phrase!r} found in {path.relative_to(REPO_ROOT)}"
