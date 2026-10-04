"""Active output contract as rendered in cloud prompts.

Moved from gateway/tests/test_active_output_contract.py with the cloud prompt composition (WP8.7).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.cloud_prompt import active_output_contract as contracts  # noqa: E402
from services.cloud_prompt import messages as harper  # noqa: E402
from services.cloud_prompt import methodology_prompt  # noqa: E402
from services.methodologies.resolver import resolve_methodology_context  # noqa: E402

PHASES_DIR = ORCHESTRATOR_ROOT / "phases"
GATEWAY_FIXTURES = REPO_ROOT / "gateway/tests/fixtures"
MANIFEST_PATH = REPO_ROOT / "orchestrator/methodologies/bmad/manifest.json"
build_active_output_contract = contracts.build_active_output_contract
validate_files_against_active_output_contract = contracts.validate_files_against_active_output_contract
render_methodology_context_for_cloud_prompt = methodology_prompt.render_methodology_context_for_cloud_prompt
render_current_canonical_validation_for_cloud_prompt = methodology_prompt.render_current_canonical_validation_for_cloud_prompt


def compose_cloud_selected_phase_skill_context(core_blobs, methodology_context):
    return harper._compose_cloud_selected_skill_context(
        core_blobs=core_blobs, methodology_context=methodology_context, active_output_contract=None
    )


def _load_gateway_module(name: str, relative_path: str):
    path = GATEWAY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _kit_file_requirements(req_id: str = "REQ-001"):
    return {
        "required_outputs": [
            {
                "path_hint": f"runs/kit/{req_id}/src/coffeebuddy.runtime/contracts.py",
                "kind": "source",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/test/coffeebuddy.runtime/test_req_behavior.py",
                "kind": "test",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/ci/requirements.txt",
                "kind": "ci",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/docs/README_{req_id}.md",
                "kind": "doc",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
                "kind": "doc",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/ci/LTC.json",
                "kind": "ci",
                "required": True,
            },
            {
                "path_hint": f"runs/kit/{req_id}/ci/HOWTO.md",
                "kind": "ci_doc",
                "required": True,
            },
        ]
    }


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


def test_rendered_bmad_kit_developer_prompt_lists_p0_required_outputs():
    context = resolve_methodology_context(phase="kit", methodology="bmad", agent="developer")
    contract = build_active_output_contract(
        phase="kit",
        runner="cloud",
        methodology_context=context,
        req_id="REQ-001",
        file_requirements=_kit_file_requirements(),
    )

    rendered = render_methodology_context_for_cloud_prompt(context, active_output_contract=contract)

    assert "### BMAD Skill Reference Context" in rendered
    assert "dev-story-execution" in rendered
    assert "story-readiness" in rendered
    assert "### ACTIVE KIT REQUIRED OUTPUTS" in rendered
    assert "If any is missing, Gateway will reject the entire KIT response." in rendered
    assert "These files are P0 mandatory outputs." in rendered
    for path in [
        "runs/kit/REQ-001/docs/TARGET_CONTRACT.json",
        "runs/kit/REQ-001/docs/FILE_REQUIREMENTS.json",
        "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
        "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md",
        "runs/kit/REQ-001/docs/SELF_REVIEW.md",
        "runs/kit/REQ-001/docs/RUNBOOK.md",
    ]:
        assert path in rendered


def test_rendered_native_kit_prompt_lists_native_outputs_without_bmad_docs():
    contract = build_active_output_contract(
        phase="kit",
        runner="cloud",
        req_id="REQ-001",
        file_requirements=_kit_file_requirements(),
    )

    rendered = render_methodology_context_for_cloud_prompt(None, active_output_contract=contract)

    assert "### ACTIVE KIT REQUIRED OUTPUTS" in rendered
    assert "runs/kit/REQ-001/docs/TARGET_CONTRACT.json" in rendered
    assert "runs/kit/REQ-001/docs/FILE_REQUIREMENTS.json" in rendered
    assert "BMAD Skill Reference Context" not in rendered
    assert "dev-story-execution" not in rendered
    assert "story-readiness" not in rendered
    assert "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md" not in rendered
    assert "BMAD developer companion docs are required" not in rendered


def test_static_prompt_files_do_not_contain_unconditional_native_single_file_restrictions():
    forbidden = [
        "Print EXCLUSIVELY one file block",
        "Produce **only** the single",
        "Produce only the single",
        "No additional files",
    ]
    for path in PHASES_DIR.glob("*/cloud_*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{phrase!r} found in {path.relative_to(REPO_ROOT)}"
