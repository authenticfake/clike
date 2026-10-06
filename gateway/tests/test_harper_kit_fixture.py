import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = REPO_ROOT / "gateway"
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from methodology_contexts import resolve_methodology_context


PROMPT_FIXTURE = GATEWAY_ROOT / "tests/fixtures/coffebuddy_bmad__f975f4413d3f5819e8f915194__kit.json"
RAW_FIXTURE = GATEWAY_ROOT / "tests/fixtures/openai_gpt-5.5__kit__a4316f4afefd.json"

EXPECTED_OLD_PATHS = {
    "runs/kit/REQ-001/src/coffeebuddy.runtime/contracts.py",
    "runs/kit/REQ-001/src/coffeebuddy.runtime/config.py",
    "runs/kit/REQ-001/src/coffeebuddy.runtime/adapters.py",
    "runs/kit/REQ-001/src/coffeebuddy.runtime/factory.py",
    "runs/kit/REQ-001/test/coffeebuddy.runtime/test_req_behavior.py",
    "runs/kit/REQ-001/test/coffeebuddy.runtime/test_provider_realism.py",
    "runs/kit/REQ-001/ci/requirements.txt",
    "runs/kit/REQ-001/ci/LTC.json",
    "runs/kit/REQ-001/ci/HOWTO.md",
    "runs/kit/REQ-001/docs/README_REQ-001.md",
    "runs/kit/REQ-001/docs/KIT_REQ-001.md",
}

# TARGET_CONTRACT.json / FILE_REQUIREMENTS.json are no longer expected from the model (written by CLike).
EXPECTED_MISSING = [
    "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
    "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md",
    "runs/kit/REQ-001/docs/SELF_REVIEW.md",
    "runs/kit/REQ-001/docs/RUNBOOK.md",
]


def _load_gateway_module(name: str, relative_path: str):
    path = GATEWAY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_harper_route():
    helper = _load_gateway_module("harper_file_block_parser_helper_for_kit_fixture", "tests/test_harper_file_blocks.py")
    return helper.harper


harper = _load_harper_route()
contracts = _load_gateway_module("harper_kit_fixture_contracts", "utils/active_output_contract.py")


def _kit_file_requirements():
    return {
        "namespace_materialization": {
            "ecosystem": "python",
            "applies": True,
            "import_namespace": "coffeebuddy.runtime",
            "package_path": "coffeebuddy/runtime",
            "source_root": "runs/kit/REQ-001/src/coffeebuddy/runtime",
            "test_root": "runs/kit/REQ-001/test/coffeebuddy/runtime",
            "rules": [
                "For Python, dotted namespaces are import namespaces, not literal directory names.",
                "Materialize `coffeebuddy.runtime` as `coffeebuddy/runtime`.",
                "Do not create `src/coffeebuddy.runtime`.",
                "Do not insert `src/coffeebuddy.runtime` into sys.path as a package workaround.",
                "Include `__init__.py` files unless the project explicitly uses namespace packages.",
                "Tests must import through the Python namespace, for example `coffeebuddy.runtime`.",
            ],
        },
        "required_outputs": [
            {"path_hint": "runs/kit/REQ-001/src/coffeebuddy.runtime/contracts.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/src/coffeebuddy.runtime/config.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/src/coffeebuddy.runtime/adapters.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/src/coffeebuddy.runtime/factory.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/test/coffeebuddy.runtime/test_req_behavior.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/test/coffeebuddy.runtime/test_provider_realism.py", "required": True},
            {"path_hint": "runs/kit/REQ-001/ci/requirements.txt", "required": True},
            {"path_hint": "runs/kit/REQ-001/ci/LTC.json", "required": True},
            {"path_hint": "runs/kit/REQ-001/ci/HOWTO.md", "required": True},
            {"path_hint": "runs/kit/REQ-001/docs/README_REQ-001.md", "required": True},
            {"path_hint": "runs/kit/REQ-001/docs/KIT_REQ-001.md", "required": True},
        ]
    }


def _target_contract():
    return {
        "req_id": "REQ-001",
        "lane": "python",
        "title": "CoffeeBuddy runtime contracts",
        "acceptance": ["Runtime contracts are importable", "Provider realism is covered"],
    }


def _kit_core_blobs():
    selected_capabilities = {
        "schema_version": "clike.selected_capability_context.v1",
        "req_id": "REQ-001",
        "packs": {"selected": ["enterprise-onprem"], "resolved": [], "missing": []},
        "skills": {
            "selected": [
                "secure-config-secrets",
                "local-cloud-parity",
                "backend-contract-boundary",
                "eval-contract-writer",
            ],
            "resolved": [],
            "missing": [],
        },
        "design_profiles": {"selected": [], "resolved": [], "missing": []},
    }
    return {
        "SPEC.md": "# SPEC\nCoffeeBuddy runtime requirements.",
        "PLAN.md": "# PLAN\nREQ-001 builds CoffeeBuddy runtime contracts.",
        "plan.json": json.dumps({"reqs": [{"id": "REQ-001", "title": "CoffeeBuddy runtime contracts"}]}),
        "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n",
        "TARGET_CONTRACT.json": json.dumps(_target_contract()),
        "FILE_REQUIREMENTS.json": json.dumps(_kit_file_requirements()),
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": json.dumps(selected_capabilities),
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": (
            "# CLike Selected Capability Context\n\n"
            "## Selected Packs\n- enterprise-onprem\n\n"
            "## Selected Skills\n- secure-config-secrets\n- local-cloud-parity\n"
            "- backend-contract-boundary\n- eval-contract-writer\n"
        ),
    }


def _bmad_developer_context():
    return resolve_methodology_context(phase="kit", methodology="bmad", agent="developer")


def _bmad_developer_contract():
    return contracts.build_active_output_contract(
        phase="kit",
        runner="cloud",
        methodology_context=_bmad_developer_context(),
        req_id="REQ-001",
        file_requirements=_kit_file_requirements(),
    )


def _raw_fixture_text() -> str:
    payload = json.loads(RAW_FIXTURE.read_text(encoding="utf-8"))
    return payload["llm_result"]["text"]


def test_raw_fixture_extracts_old_kit_files_offline_without_llm():
    files, remainder = harper._extract_file_blocks(_raw_fixture_text(), phase="kit")
    files = harper._dedupe_by_path(files)
    paths = {item["path"] for item in files}

    assert remainder == ""
    assert paths == EXPECTED_OLD_PATHS


def test_raw_fixture_reproduces_missing_required_outputs_offline():
    files, _ = harper._extract_file_blocks(_raw_fixture_text(), phase="kit")
    files = harper._dedupe_by_path(files)
    result = contracts.validate_files_against_active_output_contract(files, _bmad_developer_contract())

    assert result["ok"] is False
    assert result["missing_required_outputs"] == EXPECTED_MISSING


