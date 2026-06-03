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


artifact_policy_module = _load_gateway_module("gateway_artifact_policy", "utils/artifact_policy.py")
methodology_prompt_module = _load_gateway_module("gateway_methodology_prompt", "utils/methodology_prompt.py")
filter_files_by_methodology_artifact_policy = artifact_policy_module.filter_files_by_methodology_artifact_policy
render_methodology_context_for_cloud_prompt = methodology_prompt_module.render_methodology_context_for_cloud_prompt
render_current_canonical_validation_for_cloud_prompt = (
    methodology_prompt_module.render_current_canonical_validation_for_cloud_prompt
)


def test_renderer_returns_empty_without_methodology_context():
    assert render_methodology_context_for_cloud_prompt(None) == ""
    assert render_methodology_context_for_cloud_prompt({}) == ""


def test_bmad_idea_renderer_includes_companion_contract_outputs():
    context = resolve_methodology_context(
        phase="idea",
        methodology="bmad",
        agent="analyst",
    )

    rendered = render_methodology_context_for_cloud_prompt(context)

    assert "### Governed Methodology Profile" in rendered
    assert "### BMAD Companion Artifact Contract" in rendered
    assert "docs/harper/IDEA.md" in rendered
    assert "docs/harper/bmad/idea/BRIEF.md" in rendered
    assert "docs/harper/bmad/idea/PRFAQ_NOTES.md" in rendered
    assert "canonical artifacts win" in rendered


def test_idea_system_prompt_keeps_canonical_schema_and_bmad_companions_separate():
    prompt = (GATEWAY_ROOT / "prompts" / "harper" / "idea_system.md").read_text(encoding="utf-8")

    for text in [
        "# IDEA — <Project Name>",
        "## Vision",
        "## Problem Statement",
        "## Target Users & Context",
        "## Value & Outcomes",
        "## Out of Scope",
        "## Technology Constraints",
        "## Risks & Assumptions",
        "## Success Metrics",
        "docs/harper/bmad/idea/BRIEF.md",
        "docs/harper/bmad/idea/PRFAQ_NOTES.md",
        "docs/harper/bmad/idea/ASSUMPTIONS.md",
        "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md",
        "BMAD must not change, replace, reorder, or extend the primary IDEA.md schema",
        "The `docs/harper/IDEA.md` file must be valid even if every BMAD companion file is ignored.",
        "For `docs/harper/IDEA.md`, `BEGIN_FILE` / `END_FILE` is preferred because Technology Constraints contains a YAML fence.",
        "Do not wrap Markdown files containing internal triple-backtick code fences inside an outer triple-backtick file block.",
    ]:
        assert text in prompt

    assert "Do not satisfy BMAD by generating companion files only" in prompt
    assert "BMAD-specific details must be placed in companion artifacts" in render_methodology_context_for_cloud_prompt(
        resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    )


def test_idea_system_prompt_does_not_require_bmad_sections_inside_canonical_idea():
    prompt = (GATEWAY_ROOT / "prompts" / "harper" / "idea_system.md").read_text(encoding="utf-8")

    forbidden_required_phrases = [
        "## Deployment Portability Rule",
        "## Technology Constraints Profile Rule",
        "## Strategic Fit",
        "## /spec Handoff Readiness",
        "## Non-Goals",
        "## Constraints",
        "distinct profiles for `app-core` and `ai-rag`",
        "list supported RAG formats explicitly",
    ]

    for phrase in forbidden_required_phrases:
        assert phrase not in prompt


def test_plan_system_prompt_lane_guide_schema_matches_validator_contract():
    prompt = (GATEWAY_ROOT / "prompts" / "harper" / "plan_system.md").read_text(encoding="utf-8")

    for phrase in [
        "### Purpose and Scope",
        "### Expected Files and Boundaries",
        "Expected files:",
        "Boundaries:",
        "### Test and Validation Commands",
        "Local test command:",
        "Containerized validation command:",
        "### Eval/Gate Expectations",
        "Eval expectations:",
        "Gate expectations:",
        "Commands:",
        "### TECH_CONSTRAINTS Integration",
        "### Forbidden Shortcuts",
    ]:
        assert phrase in prompt


def test_bmad_plan_architect_renderer_includes_architecture_contract_outputs():
    context = resolve_methodology_context(
        phase="plan",
        methodology="bmad",
        agent="architect",
    )

    rendered = render_methodology_context_for_cloud_prompt(context)

    assert "docs/harper/PLAN.md" in rendered
    assert "docs/harper/plan.json" in rendered
    assert "docs/harper/lane-guides/**" in rendered
    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" in rendered
    assert "docs/harper/bmad/architecture/DECISIONS.md" in rendered
    assert "### BMAD Downstream Handoff" in rendered


def test_discovered_custom_companion_artifact_appears_in_inventory_with_snippet():
    context = resolve_methodology_context(
        phase="idea",
        methodology="bmad",
        agent="analyst",
    )
    context["discovered_companion_artifacts"] = [
        {
            "path": "docs/harper/bmad/idea/DEEP_DIVE_X.md",
            "source_group": "bmad_project",
            "size_bytes": 128,
            "sha256": "abcdef1234567890",
            "truncated": True,
            "snippet": "# Deep Dive\nUseful downstream evidence.",
        }
    ]

    rendered = render_methodology_context_for_cloud_prompt(context)

    assert "### BMAD Companion Artifact Inventory" in rendered
    assert "source_group: bmad_project" in rendered
    assert "DEEP_DIVE_X.md" in rendered
    assert "sha256: abcdef123456" in rendered
    assert "size_bytes: 128" in rendered
    assert "truncated: True" in rendered
    assert "Useful downstream evidence." in rendered


def test_native_harper_prompt_files_do_not_contain_bmad_blocks():
    for path in (GATEWAY_ROOT / "prompts" / "harper").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "BMAD Companion Artifact Contract" not in text
        assert "BMAD Companion Artifact Inventory" not in text


def test_spec_ux_forbidden_spec_output_is_enforced():
    context = resolve_methodology_context(
        phase="spec",
        methodology="bmad",
        agent="ux",
    )
    warnings = []

    filtered = filter_files_by_methodology_artifact_policy(
        [
            {"path": "docs/harper/SPEC.md", "content": "# Forbidden"},
            {"path": "docs/harper/ux/SPEC_UX_APPENDIX.md", "content": "# UX"},
        ],
        phase="spec",
        methodology_context=context,
        warnings=warnings,
    )

    assert [item["path"] for item in filtered] == ["docs/harper/ux/SPEC_UX_APPENDIX.md"]
    assert any("bmad_spec_ux_companion_only" in item for item in warnings)


def test_plan_architect_output_policy_allows_lane_guides_and_architecture_companions():
    context = resolve_methodology_context(
        phase="plan",
        methodology="bmad",
        agent="architect",
    )
    warnings = []

    filtered = filter_files_by_methodology_artifact_policy(
        [
            {"path": "docs/harper/PLAN.md", "content": "# Plan"},
            {"path": "docs/harper/plan.json", "content": "{}"},
            {"path": "docs/harper/lane-guides/app.md", "content": "# App Lane"},
            {"path": "docs/harper/bmad/architecture/ARCHITECTURE.md", "content": "# Architecture"},
            {"path": "docs/harper/bmad/plan/STORIES.md", "content": "# Wrong role"},
        ],
        phase="plan",
        methodology_context=context,
        warnings=warnings,
    )

    assert [item["path"] for item in filtered] == [
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        "docs/harper/lane-guides/app.md",
        "docs/harper/bmad/architecture/ARCHITECTURE.md",
    ]
    assert any("docs/harper/bmad/plan/STORIES.md" in item for item in warnings)


def test_non_bmad_output_validation_is_unchanged():
    files = [{"path": "docs/harper/SPEC.md", "content": "# Spec"}]

    assert filter_files_by_methodology_artifact_policy(
        files,
        phase="spec",
        methodology_context=None,
        warnings=[],
    ) == files


def test_current_invalid_canonical_context_renders_repair_guidance():
    rendered = render_current_canonical_validation_for_cloud_prompt(
        [
            {
                "path": "docs/harper/IDEA.md",
                "failed_checks": ["missing_idea_h1", "missing_heading:## Vision"],
                "diagnostic": "IDEA.md failed canonical Harper structure validation.",
                "untrusted_repair_material_snippet": "tech_constraints:\n  runtime: unknown",
            }
        ]
    )

    assert "### Current Canonical Artifact Validation" in rendered
    assert "current_canonical_invalid: true" in rendered
    assert "invalid_path: docs/harper/IDEA.md" in rendered
    assert "missing_idea_h1" in rendered
    assert "must not be imitated structurally" in rendered
    assert "Generate a valid replacement" in rendered
    assert "untrusted_repair_material_snippet" in rendered
