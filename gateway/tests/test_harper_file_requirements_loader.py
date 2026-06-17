import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = REPO_ROOT / "gateway"
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(1, str(ORCHESTRATOR_ROOT))


def _load_harper_route():
    # Reuse the same isolated loader used by the kit fixture test so the heavy
    # route module is imported via importlib without side effects.
    helper_path = GATEWAY_ROOT / "tests/test_harper_file_blocks.py"
    spec = importlib.util.spec_from_file_location(
        "harper_file_block_parser_helper_for_file_requirements_test", helper_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.harper


harper = _load_harper_route()


def test_load_file_requirements_helper_is_defined():
    # DEFECT 3: the helper was referenced by the KIT path but never defined,
    # which raised NameError (HTTP 500). Importing the route and resolving the
    # symbol proves it now exists and is the canonical loader.
    assert hasattr(harper, "_load_file_requirements_from_core_blobs")
    assert callable(harper._load_file_requirements_from_core_blobs)


def test_load_file_requirements_parses_canonical_blob():
    core_blobs = {
        "docs/harper/FILE_REQUIREMENTS.json": json.dumps(
            {"req_id": "REQ-001", "required_outputs": ["src/app.py"]}
        ),
        "docs/harper/TARGET_CONTRACT.json": json.dumps({"req_id": "REQ-001"}),
    }
    file_requirements = harper._load_file_requirements_from_core_blobs(core_blobs)
    assert isinstance(file_requirements, dict)
    assert file_requirements["req_id"] == "REQ-001"
    assert file_requirements["required_outputs"] == ["src/app.py"]


def test_missing_file_requirements_returns_none_for_controlled_422_guard():
    # The KIT branch raises a controlled 422 when this loader returns None; it
    # must never raise NameError / 500. Empty and unrelated-only core_blobs
    # must both yield None so the existing validation guard fires.
    assert harper._load_file_requirements_from_core_blobs({}) is None
    assert harper._load_file_requirements_from_core_blobs(None) is None
    assert (
        harper._load_file_requirements_from_core_blobs(
            {"docs/harper/TARGET_CONTRACT.json": json.dumps({"req_id": "REQ-001"})}
        )
        is None
    )
