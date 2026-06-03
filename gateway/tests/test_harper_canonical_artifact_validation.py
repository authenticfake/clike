import importlib.util
import sys
import tempfile
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


validation = _load_gateway_module("harper_canonical_validation", "utils/harper_canonical_validation.py")
contracts = _load_gateway_module("gateway_active_output_contract_validation", "utils/active_output_contract.py")


NATIVE_IDEA = (REPO_ROOT / "orchestrator/tests/fixtures/native/IDEA.md").read_text(encoding="utf-8")
BMAD_IDEA = (REPO_ROOT / "orchestrator/tests/fixtures/bmad_experimental/IDEA.md").read_text(encoding="utf-8")
BAD_RAW_YAML_IDEA = (GATEWAY_ROOT / "tests/fixtures/harper/bad_idea_raw_yaml_first.md").read_text(encoding="utf-8")
BAD_TEMPLATE_LEAK_IDEA = (GATEWAY_ROOT / "tests/fixtures/harper/bad_idea_prompt_template_leak.md").read_text(encoding="utf-8")
BAD_PLACEHOLDER_IDEA = (GATEWAY_ROOT / "tests/fixtures/harper/bad_idea_placeholders.md").read_text(encoding="utf-8")


VALID_BMAD_STABLE_IDEA = """# IDEA — CoffeeBuddy

## Vision
CoffeeBuddy coordinates office coffee runs with a focused slice that reduces chat noise and ordering mistakes. The first demo proves a fast shared order flow for one office team.

## Problem Statement
Office coffee orders are scattered across chat, memory, and ad hoc spreadsheets. Teammates lose time collecting preferences, confirming totals, and fixing mistakes. Slice 1 solves the problem when a teammate can open one shared flow, submit an order, and see a confirmed group summary.

## Target Users & Context
- Primary user: office teammate coordinating a coffee run.
- Secondary stakeholder: office manager tracking repeated coordination friction.
- Operating context: small office teams with mixed mobile and desktop use.

## Value & Outcomes
- Reduce order coordination time from several chat exchanges to one shared flow.
- Improve order accuracy through explicit item and preference confirmation.
- Make the first slice demonstrable without payments or loyalty integrations.

## Out of Scope
- Payments, loyalty programs, vendor marketplace features, and full expense workflows.
- Multi-office rollout before the first office slice is validated.

## Technology Constraints
```yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "office coordination"
  classification:
    solution_type: "web"
    deployment_context: "unknown"
    data_sensitivity: "internal"
  assumptions:
    - "Runtime and hosting are not evidenced yet."
  evaluation:
    required_checks:
      - "tests"
```

## Risks & Assumptions
- Business assumption: teams are willing to use a shared order link instead of chat.
- Technical assumption: runtime and deployment target will be selected during SPEC and PLAN.
- UX risk: the flow must stay faster than sending a chat message.

## Success Metrics
- Time-to-first-order submitted under 90 seconds for the first slice.
- At least 80 percent of pilot users complete the order without assistance.
- Critical order detail error rate below 5 percent during pilot use.
"""

VALID_LANE_GUIDE = """## Lane Guide — python

### Purpose and Scope
Lane purpose and scope: Python owns backend API and worker implementation.

### Expected Files and Boundaries
- Expected files: runs/kit/<REQ-ID>/src/python/** and service package modules.
- Expected tests: runs/kit/<REQ-ID>/test/python/** unit and integration tests.
- Boundaries: do not write SQL migrations, Kafka schemas, infra manifests, or BMAD companion artifacts from this lane.

### Tools
- tests: pytest
- lint: ruff
- types: mypy
- security: bandit
- build: python -m compileall

### Test and Validation Commands
- Local test command: pytest -q runs/kit/<REQ-ID>/test/python
- Containerized validation command: docker compose run --rm app pytest -q
- Commands: tests, lint, types, security, and build commands must be executable or explicitly marked not applicable.

### Eval/Gate Expectations
- Eval expectations: EvalRunner sees passing tests, coverage evidence, and integration contract proof.
- Gate expectations: Gate enforces tests/lint/types/security/build results with zero critical vulnerabilities.

### Default Gate Policy
- min coverage: 80
- max criticals: 0

### Enterprise Runner Notes
- Jenkins: run tests, lint, types, security, and build as separate stages.

### TECH_CONSTRAINTS Integration
TECH_CONSTRAINTS integration covers runtime, secrets, observability, and registry constraints.

### Forbidden Shortcuts
- No fake production adapters, hidden runtime assumptions, or writes outside expected files and boundaries.
"""


INVALID_BMAD_ONLY_IDEA = """# CoffeeBuddy Strategy

## Strategic Fit
CoffeeBuddy aligns to office operations goals.

## /spec Handoff Readiness
Functional anchors and acceptance hooks are listed here.

## Deployment Portability Rule
The implementation should support multiple deployment profiles.

## Technology Constraints Profile Rule
Profile-based constraints are discussed here.
"""


def test_good_native_idea_fixture_passes():
    result = validation.validateIdeaMarkdown(NATIVE_IDEA, evidence_text=NATIVE_IDEA)

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_good_bmad_enriched_idea_fixture_passes():
    result = validation.validateIdeaMarkdown(BMAD_IDEA, evidence_text=BMAD_IDEA)

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_valid_bmad_idea_with_stable_harper_headings_passes():
    result = validation.validateIdeaMarkdown(
        VALID_BMAD_STABLE_IDEA,
        evidence_text=VALID_BMAD_STABLE_IDEA,
    )

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_four_backtick_file_block_with_internal_yaml_parses_and_validates():
    helper_path = GATEWAY_ROOT / "tests/test_harper_file_blocks.py"
    spec = importlib.util.spec_from_file_location("harper_file_block_parser_helper", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    block = f"{helper.BT4}file:/docs/harper/IDEA.md\n{VALID_BMAD_STABLE_IDEA}{helper.BT4}\n"
    files, remainder = helper.harper._extract_file_blocks(block, phase="idea")

    assert remainder == ""
    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    result = validation.validateIdeaMarkdown(files[0]["content"], evidence_text=files[0]["content"])

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_begin_file_with_internal_yaml_parses_and_validates():
    helper_path = GATEWAY_ROOT / "tests/test_harper_file_blocks.py"
    spec = importlib.util.spec_from_file_location("harper_file_block_parser_helper_begin", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    block = f"BEGIN_FILE docs/harper/IDEA.md\n{VALID_BMAD_STABLE_IDEA}END_FILE\n"
    files, remainder = helper.harper._extract_file_blocks(block, phase="idea")

    assert remainder == ""
    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    assert files[0]["content"].startswith("# IDEA")
    assert not files[0]["content"].lstrip().startswith("yaml")
    result = validation.validateIdeaMarkdown(files[0]["content"], evidence_text=files[0]["content"])

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_bmad_idea_begin_file_response_accepts_canonical_and_companions():
    helper_path = GATEWAY_ROOT / "tests/test_harper_file_blocks.py"
    spec = importlib.util.spec_from_file_location("harper_file_block_parser_helper_bmad", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    response = "\n".join(
        [
            f"BEGIN_FILE docs/harper/IDEA.md\n{VALID_BMAD_STABLE_IDEA}END_FILE",
            "BEGIN_FILE docs/harper/bmad/idea/BRIEF.md\n# Brief\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/idea/PRFAQ_NOTES.md\n# PRFAQ\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/idea/ASSUMPTIONS.md\n# Assumptions\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/idea/RESEARCH_QUESTIONS.md\n# Research\nEND_FILE",
        ]
    )
    files, remainder = helper.harper._extract_file_blocks(response, phase="idea")
    files = helper.harper._dedupe_by_path(files)

    context = resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    contract = contracts.build_active_output_contract(
        phase="idea",
        runner="cloud",
        methodology_context=context,
    )
    canonical = validation.validate_canonical_harper_files(files, evidence_text=VALID_BMAD_STABLE_IDEA)
    active = contracts.validate_files_against_active_output_contract(canonical["accepted_files"], contract)

    assert remainder == ""
    assert canonical["rejected"] == []
    assert active["ok"] is True
    assert "docs/harper/IDEA.md" in {item["path"] for item in canonical["accepted_files"]}
    assert "docs/harper/bmad/idea/BRIEF.md" in {item["path"] for item in canonical["accepted_files"]}


def test_bmad_only_idea_shape_without_canonical_headings_fails():
    result = validation.validateIdeaMarkdown(INVALID_BMAD_ONLY_IDEA)

    assert result["ok"] is False
    assert "missing_idea_h1" in result["failed_checks"]
    assert "missing_heading:## Vision" in result["failed_checks"]
    assert "missing_heading:## Problem Statement" in result["failed_checks"]
    assert "missing_fenced_yaml_after_technology_constraints" in result["failed_checks"]


def test_bad_raw_yaml_first_idea_fails():
    result = validation.validateIdeaMarkdown(BAD_RAW_YAML_IDEA)

    assert result["ok"] is False
    assert "missing_idea_h1" in result["failed_checks"]
    assert "starts_with_raw_yaml_or_fence" in result["failed_checks"]


def test_bad_prompt_template_leak_idea_fails():
    result = validation.validateIdeaMarkdown(BAD_TEMPLATE_LEAK_IDEA)

    assert result["ok"] is False
    assert "contains_BEGIN_FILE" in result["failed_checks"]
    assert "contains_END_FILE" in result["failed_checks"]
    assert any("contains_prompt_template_phrase" in item for item in result["failed_checks"])


def test_bad_placeholder_idea_fails():
    result = validation.validateIdeaMarkdown(BAD_PLACEHOLDER_IDEA)

    assert result["ok"] is False
    assert "contains_unresolved_placeholder:<Project Name>" in result["failed_checks"]
    assert "contains_unresolved_placeholder:My Solution Name" in result["failed_checks"]


def test_spec_ux_cannot_overwrite_spec_md_via_validator():
    ux_companion = """# SPEC UX Appendix

## User Journeys
This is companion-only UX content.
"""

    result = validation.validateSpecMarkdown(ux_companion)

    assert result["ok"] is False
    assert "looks_like_companion_only_ux_content" in result["failed_checks"]


def test_plan_validator_catches_missing_req_ids():
    bad = """# PLAN — CoffeeBuddy

## Dependencies
Ordering is clear.

## KIT Readiness
/kit can run.
"""

    result = validation.validatePlanMarkdown(bad)

    assert result["ok"] is False
    assert "missing_req_ids" in result["failed_checks"]


def test_plan_json_validator_catches_invalid_json_and_markdown():
    result = validation.validatePlanJson("# PLAN\nnot json")

    assert result["ok"] is False
    assert "invalid_json" in result["failed_checks"]
    assert "looks_like_markdown" in result["failed_checks"]


def test_lane_guide_validator_catches_missing_commands_and_eval_expectations():
    bad = """# Backend Lane

## Purpose
Backend lane.

## Expected Files
Source files.
"""

    result = validation.validateLaneGuideMarkdown(bad)

    assert result["ok"] is False
    assert "missing_test_or_validation_commands" in result["failed_checks"]
    assert "missing_eval_gate_expectations" in result["failed_checks"]


def test_valid_lane_guide_with_expected_boundaries_and_eval_gate_passes():
    result = validation.validateLaneGuideMarkdown(VALID_LANE_GUIDE)

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_lane_guide_missing_purpose_and_scope_fails():
    bad = """## Lane Guide — python

### Expected Files and Boundaries
- Expected files: runs/kit/<REQ-ID>/src/python/**
- Boundaries: do not write infra files.

### Test and Validation Commands
- Local test command: pytest -q tests

### Eval/Gate Expectations
- Eval expectations and Gate expectations are defined.
"""

    result = validation.validateLaneGuideMarkdown(bad)

    assert result["ok"] is False
    assert "missing_lane_purpose_or_scope" in result["failed_checks"]


def test_lane_guide_missing_expected_files_and_boundaries_fails():
    bad = """## Lane Guide — python

### Purpose and Scope
Lane purpose and scope: Python owns backend code.

### Tools
- tests: pytest

### Test and Validation Commands
- Local test command: pytest -q tests

### Eval/Gate Expectations
- Eval expectations and Gate expectations are defined.
"""

    result = validation.validateLaneGuideMarkdown(bad)

    assert result["ok"] is False
    assert "missing_expected_files_or_boundaries" in result["failed_checks"]


def test_lane_guide_missing_eval_gate_expectations_fails():
    bad = """## Lane Guide — python

### Purpose and Scope
Lane purpose and scope: Python owns backend code.

### Expected Files and Boundaries
- Expected files: runs/kit/<REQ-ID>/src/python/**
- Boundaries: do not write infra files.

### Tools
- tests: pytest

### Test and Validation Commands
- Local test command: pytest -q tests
"""

    result = validation.validateLaneGuideMarkdown(bad)

    assert result["ok"] is False
    assert "missing_eval_gate_expectations" in result["failed_checks"]


def test_lane_guide_missing_test_and_validation_commands_fails():
    bad = """## Lane Guide — python

### Purpose and Scope
Lane purpose and scope: Python owns backend code.

### Expected Files and Boundaries
- Expected files: runs/kit/<REQ-ID>/src/python/**
- Boundaries: do not write infra files.

### Eval/Gate Expectations
- Eval expectations and Gate expectations are defined.
"""

    result = validation.validateLaneGuideMarkdown(bad)

    assert result["ok"] is False
    assert "missing_test_or_validation_commands" in result["failed_checks"]


def test_bmad_plan_architect_begin_file_response_accepts_lane_guide_and_companions():
    helper_path = GATEWAY_ROOT / "tests/test_harper_file_blocks.py"
    spec = importlib.util.spec_from_file_location("harper_file_block_parser_helper_plan_bmad", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    plan_md = """# PLAN — CoffeeBuddy

## Dependencies
- REQ-001 has no dependencies.

## KIT Readiness
/kit can implement REQ-001.
"""
    plan_json = """{"reqs":[{"id":"REQ-001","title":"Backend slice","status":"open","acceptance":["Works"],"dependsOn":[]}]}"""
    response = "\n".join(
        [
            f"BEGIN_FILE docs/harper/PLAN.md\n{plan_md}END_FILE",
            f"BEGIN_FILE docs/harper/plan.json\n{plan_json}\nEND_FILE",
            f"BEGIN_FILE docs/harper/lane-guides/python.md\n{VALID_LANE_GUIDE}END_FILE",
            "BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md\n# Architecture\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/architecture/DECISIONS.md\n# Decisions\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md\n# Integration Boundaries\nEND_FILE",
            "BEGIN_FILE docs/harper/bmad/architecture/RISKS.md\n# Risks\nEND_FILE",
        ]
    )
    context = resolve_methodology_context(phase="plan", methodology="bmad", agent="architect")
    files, remainder = helper.harper._extract_file_blocks(
        response,
        phase="plan",
        extra_allowed_patterns=helper.harper._methodology_file_header_allow_patterns(context),
    )
    files = helper.harper._dedupe_by_path(files)
    contract = contracts.build_active_output_contract(
        phase="plan",
        runner="cloud",
        methodology_context=context,
    )
    canonical = validation.validate_canonical_harper_files(files)
    active = contracts.validate_files_against_active_output_contract(canonical["accepted_files"], contract)

    paths = {item["path"] for item in files}
    assert remainder == ""
    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" in paths
    assert "docs/harper/bmad/architecture/DECISIONS.md" in paths
    assert "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md" in paths
    assert "docs/harper/bmad/architecture/RISKS.md" in paths
    assert canonical["rejected"] == []
    assert active["ok"] is True


def test_response_with_valid_idea_and_bmad_companions_is_accepted():
    context = resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    contract = contracts.build_active_output_contract(
        phase="idea",
        runner="cloud",
        methodology_context=context,
    )
    files = [
        {"path": "docs/harper/IDEA.md", "content": NATIVE_IDEA},
        {"path": "docs/harper/bmad/idea/BRIEF.md", "content": "# Brief"},
        {"path": "docs/harper/bmad/idea/PRFAQ_NOTES.md", "content": "# PRFAQ"},
        {"path": "docs/harper/bmad/idea/ASSUMPTIONS.md", "content": "# Assumptions"},
        {"path": "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md", "content": "# Research"},
    ]

    canonical = validation.validate_canonical_harper_files(files, evidence_text=NATIVE_IDEA)
    active = contracts.validate_files_against_active_output_contract(canonical["accepted_files"], contract)

    assert canonical["rejected"] == []
    assert active["ok"] is True


def test_response_with_malformed_idea_rejects_canonical_but_not_companions():
    context = resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    contract = contracts.build_active_output_contract(
        phase="idea",
        runner="cloud",
        methodology_context=context,
    )
    files = [
        {"path": "docs/harper/IDEA.md", "content": "```yaml\ntech_constraints: {}\n```"},
        {"path": "docs/harper/bmad/idea/BRIEF.md", "content": "# Brief"},
        {"path": "docs/harper/bmad/idea/PRFAQ_NOTES.md", "content": "# PRFAQ"},
        {"path": "docs/harper/bmad/idea/ASSUMPTIONS.md", "content": "# Assumptions"},
        {"path": "docs/harper/bmad/idea/RESEARCH_QUESTIONS.md", "content": "# Research"},
    ]

    canonical = validation.validate_canonical_harper_files(files)
    active = contracts.validate_files_against_active_output_contract(canonical["accepted_files"], contract)

    assert canonical["rejected"][0]["error_code"] == "invalid_canonical_artifact"
    assert canonical["rejected"][0]["path"] == "docs/harper/IDEA.md"
    assert all(item["path"].startswith("docs/harper/bmad/idea/") for item in canonical["accepted_files"])
    assert "docs/harper/IDEA.md" in active["missing_required_outputs"]


def test_rejected_canonical_artifact_gets_controlled_debug_path():
    files = [
        {"path": "docs/harper/IDEA.md", "content": BAD_RAW_YAML_IDEA},
        {"path": "docs/harper/bmad/idea/BRIEF.md", "content": "# Brief"},
    ]
    canonical = validation.validate_canonical_harper_files(files)

    with tempfile.TemporaryDirectory() as tmp:
        rejected = validation.attach_rejected_artifact_debug_refs(
            canonical["rejected"],
            telemetry_root=tmp,
            project_id="../project",
            run_id="run/../bad",
            phase="idea",
            files=canonical["rejected_source_files"],
        )

        assert rejected[0]["error_code"] == "invalid_canonical_artifact"
        debug_path = Path(rejected[0]["debug_path"])
        assert debug_path.exists()
        assert Path(tmp).resolve() in debug_path.resolve().parents
        assert ".." not in debug_path.name
        assert debug_path.read_text(encoding="utf-8") == BAD_RAW_YAML_IDEA


def test_gateway_structured_failure_payload_shape_is_not_http_502_style():
    files = [
        {"path": "docs/harper/IDEA.md", "content": BAD_RAW_YAML_IDEA},
        {"path": "docs/harper/bmad/idea/BRIEF.md", "content": "# Brief"},
    ]
    canonical = validation.validate_canonical_harper_files(files)

    payload = {
        "ok": False,
        "phase": "idea",
        "error_code": "invalid_canonical_artifact",
        "errors": [
            {
                "path": item["path"],
                "failed_checks": item["failed_checks"],
                "diagnostic": item["diagnostic"],
                "error_code": "invalid_canonical_artifact",
            }
            for item in canonical["rejected"]
        ],
        "warnings": [],
        "rejected": canonical["rejected"],
        "files": [],
        "partial_files": canonical["accepted_files"],
        "diagnostic_files": canonical["accepted_files"],
        "text": "IDEA.md failed canonical validation and was not written.",
        "runId": "test-run",
        "telemetry": {"validation_failed": True},
    }

    assert payload["ok"] is False
    assert payload["error_code"] == "invalid_canonical_artifact"
    assert payload["errors"][0]["path"] == "docs/harper/IDEA.md"
    assert payload["files"] == []
    assert all(item["path"] != "docs/harper/IDEA.md" for item in payload["partial_files"])
    assert any(item["path"].startswith("docs/harper/bmad/idea/") for item in payload["partial_files"])


def test_response_missing_required_bmad_companions_reports_missing_required_outputs():
    context = resolve_methodology_context(phase="idea", methodology="bmad", agent="analyst")
    contract = contracts.build_active_output_contract(
        phase="idea",
        runner="cloud",
        methodology_context=context,
    )
    files = [{"path": "docs/harper/IDEA.md", "content": NATIVE_IDEA}]

    canonical = validation.validate_canonical_harper_files(files, evidence_text=NATIVE_IDEA)
    active = contracts.validate_files_against_active_output_contract(canonical["accepted_files"], contract)

    assert canonical["rejected"] == []
    assert active["ok"] is False
    assert "docs/harper/bmad/idea/BRIEF.md" in active["missing_required_outputs"]
