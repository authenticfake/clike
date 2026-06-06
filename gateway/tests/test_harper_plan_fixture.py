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


FIXTURE_PATH = GATEWAY_ROOT / "tests/fixtures/provider-openai__openai_gpt-5.5__plan__f381f2f0a1fb.json"
EXPECTED_FIXTURE_PATHS = {
    "docs/harper/PLAN.md",
    "docs/harper/plan.json",
    "docs/harper/lane-guides/python.md",
    "docs/harper/lane-guides/sql.md",
    "docs/harper/lane-guides/kafka.md",
    "docs/harper/lane-guides/ci.md",
    "docs/harper/lane-guides/infra.md",
    "docs/harper/bmad/architecture/ARCHITECTURE.md",
    "docs/harper/bmad/architecture/DECISIONS.md",
    "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md",
    "docs/harper/bmad/architecture/RISKS.md",
}
LANE_FAILURE_CODES = {
    "missing_lane_purpose_or_scope",
    "missing_expected_files_or_boundaries",
    "missing_test_or_validation_commands",
    "missing_eval_gate_expectations",
}


def _load_gateway_module(name: str, relative_path: str):
    path = GATEWAY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_harper_route():
    helper = _load_gateway_module("harper_file_block_parser_helper_for_plan_fixture", "tests/test_harper_file_blocks.py")
    return helper.harper


harper = _load_harper_route()
validation = _load_gateway_module("harper_plan_fixture_validation", "utils/harper_canonical_validation.py")
contracts = _load_gateway_module("harper_plan_fixture_contracts", "utils/active_output_contract.py")
artifact_policy = _load_gateway_module("harper_plan_fixture_artifact_policy", "utils/artifact_policy.py")


def _fixture_output_text() -> str:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw = payload["raw"]
    chunks = []
    for item in raw.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                chunks.append(content.get("text") or "")
    assert chunks, "fixture must contain provider raw output_text content"
    return "\n".join(chunks)


def _bmad_architect_context():
    return resolve_methodology_context(phase="plan", methodology="bmad", agent="architect")


def _extract_fixture_files():
    context = _bmad_architect_context()
    files, remainder = harper._extract_file_blocks(
        _fixture_output_text(),
        phase="plan",
        extra_allowed_patterns=harper._methodology_file_header_allow_patterns(context),
    )
    files = harper._dedupe_by_path(files)
    warnings = []
    files = artifact_policy.filter_files_by_methodology_artifact_policy(
        files,
        phase="plan",
        methodology_context=context,
        warnings=warnings,
    )
    return files, remainder, context, warnings


def _valid_lane_guide() -> str:
    return """## Lane Guide — python

### Purpose and Scope
Lane purpose and scope: Python owns backend API and worker code for REQ-001, and does not own migrations, Kafka schemas, or infrastructure manifests.

### Expected Files and Boundaries
- Expected files: runs/kit/<REQ-ID>/src/python/** and package modules under the planned backend boundary.
- Expected tests: runs/kit/<REQ-ID>/test/python/**.
- Boundaries: do not write SQL migrations, Kafka schemas, BMAD companion artifacts, or deployment manifests from this lane.

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
- Eval expectations: EvalRunner verifies passing tests, runtime profile adherence, skill adherence, and evidence files.
- Gate expectations: Gate enforces tests, security, runtime constraints, forbidden shortcuts, and zero critical issues.

### Default Gate Policy
- min coverage: 80
- max criticals: 0

### Enterprise Runner Notes
- Jenkins: run tests, lint, types, security, and build as distinct stages.

### TECH_CONSTRAINTS Integration
- Runtime, registry, secrets, observability, and air-gap constraints must be honored.

### Forbidden Shortcuts
- No fake production adapters, hidden runtime assumptions, skipped tests, or writes outside expected files and boundaries.
"""


def test_provider_raw_fixture_extracts_expected_plan_and_bmad_files_offline():
    files, remainder, context, warnings = _extract_fixture_files()
    paths = {item["path"] for item in files}
    contract = contracts.build_active_output_contract(
        phase="plan",
        runner="cloud",
        methodology_context=context,
    )
    active = contracts.validate_files_against_active_output_contract(files, contract)

    assert remainder == ""
    assert warnings == []
    assert paths == EXPECTED_FIXTURE_PATHS
    assert active["ok"] is True


def test_provider_raw_fixture_lane_guides_reproduce_canonical_failure_offline():
    files, _, _, _ = _extract_fixture_files()
    lane_results = {
        item["path"]: validation.validateLaneGuideMarkdown(item["content"], path=item["path"])
        for item in files
        if item["path"].startswith("docs/harper/lane-guides/")
    }
    observed_failure_codes = {
        code
        for result in lane_results.values()
        for code in result["failed_checks"]
    }

    assert set(lane_results) == {
        "docs/harper/lane-guides/python.md",
        "docs/harper/lane-guides/sql.md",
        "docs/harper/lane-guides/kafka.md",
        "docs/harper/lane-guides/ci.md",
        "docs/harper/lane-guides/infra.md",
    }
    assert all(result["ok"] is False for result in lane_results.values())
    assert LANE_FAILURE_CODES.issubset(observed_failure_codes)


def test_provider_raw_fixture_canonical_validation_keeps_atomic_rejection_shape():
    files, _, _, _ = _extract_fixture_files()
    canonical = validation.validate_canonical_harper_files(files)
    rejected_paths = {item["path"] for item in canonical["rejected"]}
    partial_paths = {item["path"] for item in canonical["accepted_files"]}

    assert rejected_paths == {
        "docs/harper/lane-guides/python.md",
        "docs/harper/lane-guides/sql.md",
        "docs/harper/lane-guides/kafka.md",
        "docs/harper/lane-guides/ci.md",
        "docs/harper/lane-guides/infra.md",
    }
    assert "docs/harper/PLAN.md" in partial_paths
    assert "docs/harper/plan.json" in partial_paths


def test_valid_updated_lane_guide_shape_passes_validator():
    result = validation.validateLaneGuideMarkdown(_valid_lane_guide())

    assert result["ok"] is True
    assert result["failed_checks"] == []


def test_fixture_bmad_architecture_headers_are_architect_only():
    raw = _fixture_output_text()
    native_files, native_remainder = harper._extract_file_blocks(raw, phase="plan")
    bmad_files, bmad_remainder, _, _ = _extract_fixture_files()

    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" not in {item["path"] for item in native_files}
    assert "BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md" in native_remainder
    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" in {item["path"] for item in bmad_files}
    assert bmad_remainder == ""
