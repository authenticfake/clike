import json
import sys
import types


try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")

    class HTTPStatusError(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

    httpx_stub.HTTPStatusError = HTTPStatusError
    httpx_stub.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx_stub

try:
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    pydantic_stub = types.ModuleType("pydantic")
    pydantic_stub.HttpUrl = str
    sys.modules["pydantic"] = pydantic_stub

try:
    import pydantic_settings  # noqa: F401
except ModuleNotFoundError:
    pydantic_settings_stub = types.ModuleType("pydantic_settings")

    class BaseSettings:
        pass

    pydantic_settings_stub.SettingsConfigDict = dict
    pydantic_settings_stub.BaseSettings = BaseSettings
    sys.modules["pydantic_settings"] = pydantic_settings_stub

try:
    import yaml  # noqa: F401
except ModuleNotFoundError:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda value: {}
    sys.modules["yaml"] = yaml_stub

from services import harper
from utils.namespace_paths import materialize_repo_path, python_module_boundary_to_package_path


def _python_core_blobs():
    return {
        "SPEC.md": "# SPEC\nPython service using pytest.",
        "PLAN.md": "# PLAN\nREQ-001 owns coffeebuddy.runtime.",
        "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n  test: pytest\n",
        "plan.json": json.dumps(
            {
                "reqs": [
                    {
                        "id": "REQ-001",
                        "title": "Runtime contracts",
                        "lane": "python",
                        "runtime_profile": "python",
                        "technical_scope": "Create Python runtime contracts.",
                        "acceptance": ["Imports use coffeebuddy.runtime"],
                        "main_module_boundary": "coffeebuddy.runtime",
                    }
                ]
            }
        ),
    }


def test_python_namespace_materializer_maps_dotted_import_to_package_path():
    assert python_module_boundary_to_package_path("coffeebuddy.runtime") == "coffeebuddy/runtime"
    assert python_module_boundary_to_package_path("app.services.auth") == "app/services/auth"
    assert materialize_repo_path("src/coffeebuddy.runtime", ecosystem="python") == "src/coffeebuddy/runtime"
    assert materialize_repo_path("src/coffeebuddy.runtime", ecosystem="node") == "src/coffeebuddy.runtime"


def test_target_contract_materializes_python_main_module_boundary_paths():
    contract = harper._extract_target_contract(_python_core_blobs(), "REQ-001")

    assert contract["main_module_boundary"] == "coffeebuddy.runtime"
    assert contract["paths"]["canonical_module_family"] == "src/coffeebuddy/runtime"
    assert contract["paths"]["expected_source_roots"] == ["src/coffeebuddy/runtime"]
    assert contract["paths"]["expected_test_roots"] == ["test/coffeebuddy/runtime"]
    assert contract["paths"]["namespace_materialization"]["package_path"] == "coffeebuddy/runtime"


def test_file_requirements_use_python_package_directories_for_dotted_namespace():
    core_blobs = _python_core_blobs()
    contract = harper._extract_target_contract(core_blobs, "REQ-001")
    requirements = harper._build_file_requirements(contract, core_blobs)
    paths = [item["path_hint"] for item in requirements["required_outputs"]]

    assert requirements["namespace_materialization"]["package_path"] == "coffeebuddy/runtime"
    assert any("runs/kit/REQ-001/src/coffeebuddy/runtime/" in path for path in paths)
    assert any("runs/kit/REQ-001/test/coffeebuddy/runtime/" in path for path in paths)
    assert not any("coffeebuddy.runtime" in path for path in paths)
