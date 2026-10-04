"""Methodology artifact policy applied to model outputs (gateway, post-LLM)."""
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = REPO_ROOT / "gateway"

from methodology_contexts import resolve_methodology_context


def _load_gateway_module(name: str, relative_path: str):
    path = GATEWAY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


artifact_policy_module = _load_gateway_module("gateway_artifact_policy", "utils/artifact_policy.py")
active_output_contract_module = _load_gateway_module("gateway_active_output_contract_for_prompt_tests", "utils/active_output_contract.py")
filter_files_by_methodology_artifact_policy = artifact_policy_module.filter_files_by_methodology_artifact_policy
build_active_output_contract = active_output_contract_module.build_active_output_contract
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


