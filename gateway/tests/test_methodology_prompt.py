import importlib.util
import json
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
active_output_contract_module = _load_gateway_module("gateway_active_output_contract_for_prompt_tests", "utils/active_output_contract.py")
selected_skill_context_prompt_module = _load_gateway_module(
    "gateway_selected_skill_context_prompt",
    "utils/selected_skill_context_prompt.py",
)
filter_files_by_methodology_artifact_policy = artifact_policy_module.filter_files_by_methodology_artifact_policy
render_methodology_context_for_cloud_prompt = methodology_prompt_module.render_methodology_context_for_cloud_prompt
render_current_canonical_validation_for_cloud_prompt = (
    methodology_prompt_module.render_current_canonical_validation_for_cloud_prompt
)
build_active_output_contract = active_output_contract_module.build_active_output_contract
compose_cloud_selected_phase_skill_context = (
    selected_skill_context_prompt_module.compose_cloud_selected_phase_skill_context
)
MANIFEST_PATH = REPO_ROOT / "orchestrator/methodologies/bmad/manifest.json"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _kit_file_requirements(req_id: str = "REQ-001"):
    return {
        "required_outputs": [
            {"path_hint": f"runs/kit/{req_id}/src/coffeebuddy.runtime/contracts.py", "required": True},
            {"path_hint": f"runs/kit/{req_id}/test/coffeebuddy.runtime/test_req_behavior.py", "required": True},
            {"path_hint": f"runs/kit/{req_id}/ci/LTC.json", "required": True},
            {"path_hint": f"runs/kit/{req_id}/ci/HOWTO.md", "required": True},
            {"path_hint": f"runs/kit/{req_id}/docs/README_{req_id}.md", "required": True},
            {"path_hint": f"runs/kit/{req_id}/docs/KIT_{req_id}.md", "required": True},
        ]
    }


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
    assert "### BMAD Skill Reference Context" in rendered
    assert "prd-shaping" in rendered


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
    assert "### BMAD Skill Reference Context" in rendered
    assert "architecture-readiness" in rendered
    assert "story-readiness" in rendered


def test_bmad_spec_pm_renderer_includes_selected_methodology_skills():
    context = resolve_methodology_context(
        phase="spec",
        methodology="bmad",
        agent="pm",
    )

    rendered = render_methodology_context_for_cloud_prompt(context)

    assert "### BMAD Skill Reference Context" in rendered
    assert "prd-shaping" in rendered
    assert "epic-framing" in rendered
    assert "acceptance-modeling" in rendered


def test_bmad_kit_developer_renderer_lists_active_p0_required_outputs():
    context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
    )
    contract = build_active_output_contract(
        phase="kit",
        runner="cloud",
        methodology_context=context,
        req_id="REQ-001",
        file_requirements=_kit_file_requirements(),
    )

    rendered = render_methodology_context_for_cloud_prompt(
        context,
        active_output_contract=contract,
    )

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


def test_bmad_cloud_prompt_renders_manifest_selected_skills_for_every_declared_pair():
    for key, expected in _manifest()["skill_selection"].items():
        phase, agent = key.split("/", 1)
        context = resolve_methodology_context(
            phase=phase,
            methodology="bmad",
            agent=agent,
        )

        rendered = render_methodology_context_for_cloud_prompt(context)

        assert "### BMAD Skill Reference Context" in rendered
        assert [item["id"] for item in context["selected_skill_references"]] == expected
        for skill_id in expected:
            assert skill_id in rendered


def test_native_kit_renderer_lists_active_outputs_without_bmad_developer_docs():
    contract = build_active_output_contract(
        phase="kit",
        runner="cloud",
        req_id="REQ-001",
        file_requirements=_kit_file_requirements(),
    )

    rendered = render_methodology_context_for_cloud_prompt(
        None,
        active_output_contract=contract,
    )

    assert "### ACTIVE KIT REQUIRED OUTPUTS" in rendered
    assert "BMAD Skill Reference Context" not in rendered
    assert "dev-story-execution" not in rendered
    assert "story-readiness" not in rendered
    assert "runs/kit/REQ-001/docs/TARGET_CONTRACT.json" in rendered
    assert "runs/kit/REQ-001/docs/FILE_REQUIREMENTS.json" in rendered
    assert "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md" not in rendered
    assert "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md" not in rendered
    assert "runs/kit/REQ-001/docs/SELF_REVIEW.md" not in rendered
    assert "runs/kit/REQ-001/docs/RUNBOOK.md" not in rendered


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

def test_cloud_selected_phase_skill_context_renders_clike_and_bmad_selected_context():
    core_blobs = {
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": (
            "# CLike Selected Capability Context\n\n"
            "Target REQ: `REQ-004`\n\n"
            "## Selected Skills\n\n"
            "### Skill: backend-contract-boundary\n"
            "- Path: `.clike/skills/backend-contract-boundary/SKILL.md`\n\n"
            "### Skill: mvp-e2e-promotability\n"
            "- Path: `.clike/skills/mvp-e2e-promotability/SKILL.md`\n\n"
            "### Skill: eval-contract-writer\n"
            "- Path: `.clike/skills/eval-contract-writer/SKILL.md`\n\n"
            "### Skill: gate-risk-reviewer\n"
            "- Path: `.clike/skills/gate-risk-reviewer/SKILL.md`\n"
        ),
        "TARGET_CONTRACT.json": '{"req_id":"REQ-004","acceptance":[]}',
        "FILE_REQUIREMENTS.json": '{"required_files":[]}',
    }
    methodology_context = {
        "methodology": "bmad",
        "phase": "kit",
        "agent": "developer",
        "authority": "methodology_profile",
        "advisory_only": True,
        "profile": {"summary": "Developer agent"},
        "selected_skill_references": [
            {
                "id": "dev-story-execution",
                "path": ".clike/skills/vendor/bmad/dev-story-execution/SKILL.md",
                "source_transport": "core_blobs",
                "source_root": ".clike/skills/vendor/bmad",
            },
            {
                "id": "story-readiness",
                "path": ".clike/skills/vendor/bmad/story-readiness/SKILL.md",
                "source_transport": "core_blobs",
                "source_root": ".clike/skills/vendor/bmad",
            },
        ],
        "selected_skill_context": {
            "snippets": [
                {
                    "id": "dev-story-execution",
                    "text": "Developer must implement the story with tests and run evidence.",
                },
                {
                    "id": "story-readiness",
                    "text": "Developer must verify story readiness before implementation.",
                },
            ],
            "required_outputs": [],
            "companion_outputs": [],
            "quality_checks": [],
            "forbidden_behavior": [],
            "governance_boundaries": [],
        },
        "skill_reference_policy": {
            "workspace_vendor_reference_root": ".clike/skills/vendor/bmad",
            "cloud_context_enabled": True,
            "local_agent_context_enabled": True,
        },
    }

    rendered = compose_cloud_selected_phase_skill_context(
        core_blobs,
        methodology_context,
    )

    assert "## Cloud Selected Phase Skill Context" in rendered
    assert "### CLike Selected Capability Context" in rendered
    assert "backend-contract-boundary" in rendered
    assert "mvp-e2e-promotability" in rendered
    assert "eval-contract-writer" in rendered
    assert "gate-risk-reviewer" in rendered

    assert "### BMAD Skill Reference Context" in rendered
    assert "dev-story-execution" in rendered
    assert "story-readiness" in rendered
    assert ".clike/skills/vendor/bmad/dev-story-execution/SKILL.md" in rendered


def test_cloud_selected_phase_skill_context_renders_clike_only_for_native_harper_run():

    core_blobs = {
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": (
            "# CLike Selected Capability Context\n\n"
            "Target REQ: `REQ-004`\n\n"
            "## Selected Skills\n\n"
            "### Skill: backend-contract-boundary\n"
            "- Path: `.clike/skills/backend-contract-boundary/SKILL.md`\n"
        ),
        "TARGET_CONTRACT.json": '{"req_id":"REQ-004","acceptance":[]}',
        "FILE_REQUIREMENTS.json": '{"required_files":[]}',
    }

    rendered = compose_cloud_selected_phase_skill_context(core_blobs, None)

    assert "### CLike Selected Capability Context" in rendered
    assert "backend-contract-boundary" in rendered
    assert "### BMAD Skill Reference Context" not in rendered
    assert "dev-story-execution" not in rendered
    assert "story-readiness" not in rendered


def test_cloud_selected_phase_skill_context_returns_empty_without_selected_context():
    assert compose_cloud_selected_phase_skill_context({}, None) == ""
