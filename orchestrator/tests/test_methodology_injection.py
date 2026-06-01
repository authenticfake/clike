import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")

    class HTTPStatusError(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

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

    pydantic_settings_stub.BaseSettings = BaseSettings
    sys.modules["pydantic_settings"] = pydantic_settings_stub

try:
    import yaml  # noqa: F401
except ModuleNotFoundError:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda value: {}
    sys.modules["yaml"] = yaml_stub

from services import harper
from services.local_agent_package import build_kit_local_agent_package
from services.methodologies.resolver import resolve_methodology_context


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_gateway_methodology_prompt_module():
    path = REPO_ROOT / "gateway" / "utils" / "methodology_prompt.py"
    spec = importlib.util.spec_from_file_location("gateway_methodology_prompt", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_payload():
    return {
        "runId": "test-run",
        "project_id": "project",
        "project_name": "Project",
        "localAgentExecutor": "gpt_codex",
        "localAgentCapabilities": {},
        "core_blobs": {
            "plan.json": json.dumps(
                {
                    "reqs": [
                        {
                            "id": "REQ-001",
                            "title": "Build the thing",
                            "acceptance": ["Thing works"],
                            "lane": "App",
                            "dependsOn": [],
                        }
                    ]
                }
            )
        },
    }


def _kit_package(payload):
    return build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy={
            "requested": "prefer_local_agent",
            "selected": "local_agent",
            "reason": "test",
            "phase_supported": True,
        },
    )


def _package_context_file(package, suffix):
    files = package["local_agent"]["package_files"]
    match = [
        item
        for item in files
        if isinstance(item, dict) and item["path"].endswith(suffix)
    ]
    assert match
    return json.loads(match[0]["content"])


def _context_file(package):
    return _package_context_file(package, "AGENT_EXECUTION_CONTEXT.json")


class MethodologyInjectionTests(unittest.TestCase):
    def test_bmad_context_is_injected_for_cloud_runs_through_gateway_prompt_renderer(self):
        module = _load_gateway_methodology_prompt_module()
        context = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
        )

        rendered = module.render_methodology_context_for_cloud_prompt(context)

        self.assertIn("### Governed Methodology Profile", rendered)
        self.assertIn("- methodology: bmad", rendered)
        self.assertIn("- role: developer", rendered)
        self.assertIn("CLike remains the governance runtime", rendered)

    def test_gateway_harper_run_passes_resolved_methodology_context_to_cloud_composer(self):
        source = (REPO_ROOT / "gateway" / "routes" / "harper.py").read_text(encoding="utf-8")

        self.assertIn("render_methodology_context_for_cloud_prompt(methodology_context)", source)
        self.assertIn("req.methodology_context", source)

    def test_bmad_context_is_injected_for_local_agent_package(self):
        payload = _base_payload()
        payload["methodology_context"] = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
        )

        package = _kit_package(payload)
        context = _context_file(package)

        self.assertEqual(context["methodology_context"]["methodology"], "bmad")
        self.assertEqual(context["methodology_context"]["agent"], "developer")
        self.assertIn("Methodology profile:", package["local_agent"]["prompt_content"])
        self.assertIn("allowed_write_roots", package["local_agent"]["prompt_content"])

    def test_methodology_context_is_absent_when_omitted(self):
        package = _kit_package(_base_payload())
        context = _context_file(package)

        self.assertNotIn("methodology_context", context)
        self.assertNotIn("Methodology profile:", package["local_agent"]["prompt_content"])

    def test_allowed_and_forbidden_paths_are_unchanged_when_bmad_is_enabled(self):
        baseline = _kit_package(_base_payload())

        payload = _base_payload()
        payload["methodology_context"] = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
        )
        with_bmad = _kit_package(payload)

        self.assertEqual(
            baseline["local_agent"]["allowed_write_roots"],
            with_bmad["local_agent"]["allowed_write_roots"],
        )
        self.assertEqual(
            baseline["local_agent"]["forbidden_paths"],
            with_bmad["local_agent"]["forbidden_paths"],
        )


class OrchestratorMethodologyOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_supplied_methodology_context_is_ignored_for_cloud_gateway_payload(self):
        captured = []

        async def fake_post_json(path, payload):
            captured.append({"path": path, "payload": dict(payload)})
            return {
                "ok": True,
                "phase": payload.get("phase"),
                "echo": "",
                "text": "",
                "files": [],
                "diffs": [],
                "tests": {"passed": 0, "failed": 0, "summary": "test"},
                "warnings": [],
                "errors": [],
                "runId": payload.get("runId"),
            }

        async def fake_resolve_llm_selection(**kwargs):
            return {}

        payload = _base_payload()
        payload.update(
            {
                "methodology": "bmad",
                "agent": "pm",
                "methodology_context": {
                    "methodology": "bmad",
                    "agent": "developer",
                    "phase": "kit",
                    "profile": {"summary": "client-owned malicious context"},
                },
            }
        )

        with patch.object(
            harper,
            "resolve_methodology_context",
            wraps=harper.resolve_methodology_context,
        ) as resolve_mock, patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper,
            "resolve_llm_selection",
            side_effect=fake_resolve_llm_selection,
        ):
            await harper.run_phase("spec", payload)

        resolve_mock.assert_called_once_with(phase="spec", methodology="bmad", agent="pm")
        self.assertEqual(captured[0]["path"], "/v1/harper/run")
        sent = captured[0]["payload"]
        self.assertEqual(sent["methodology"], "bmad")
        self.assertEqual(sent["agent"], "pm")
        self.assertEqual(sent["methodology_context"]["methodology"], "bmad")
        self.assertEqual(sent["methodology_context"]["phase"], "spec")
        self.assertEqual(sent["methodology_context"]["agent"], "pm")
        self.assertNotEqual(sent["methodology_context"]["profile"].get("summary"), "client-owned malicious context")

    async def test_no_methodology_removes_client_supplied_methodology_context(self):
        captured = []

        async def fake_post_json(path, payload):
            captured.append(dict(payload))
            return {
                "ok": True,
                "phase": payload.get("phase"),
                "echo": "",
                "text": "",
                "files": [],
                "diffs": [],
                "tests": {"passed": 0, "failed": 0, "summary": "test"},
                "warnings": [],
                "errors": [],
                "runId": payload.get("runId"),
            }

        async def fake_resolve_llm_selection(**kwargs):
            return {}

        payload = _base_payload()
        payload["methodology_context"] = {
            "methodology": "bmad",
            "agent": "developer",
            "phase": "kit",
        }

        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper,
            "resolve_llm_selection",
            side_effect=fake_resolve_llm_selection,
        ):
            await harper.run_phase("spec", payload)

        self.assertNotIn("methodology", captured[0])
        self.assertNotIn("agent", captured[0])
        self.assertNotIn("methodology_context", captured[0])

    async def test_local_agent_package_receives_only_resolved_methodology_context(self):
        payload = _base_payload()
        payload.update(
            {
                "eval": {"targets": ["REQ-001"]},
                "executionPreference": "local_agent_only",
                "methodology": "bmad",
                "agent": "qa",
                "methodology_context": {
                    "methodology": "bmad",
                    "agent": "developer",
                    "phase": "kit",
                    "profile": {"summary": "client-owned malicious context"},
                },
            }
        )

        with patch.object(
            harper,
            "resolve_execution_policy",
            return_value={
                "requested": "local_agent_only",
                "selected": "local_agent",
                "reason": "test",
                "phase_supported": True,
            },
        ), patch.object(harper, "_post_json", side_effect=AssertionError("Gateway must not be called")):
            package = await harper.run_phase("eval", payload)

        context = _package_context_file(package, "AGENT_EVAL_CONTEXT.json")
        methodology_context = context["methodology_context"]

        self.assertEqual(methodology_context["methodology"], "bmad")
        self.assertEqual(methodology_context["phase"], "eval")
        self.assertEqual(methodology_context["agent"], "qa")
        self.assertIs(methodology_context["advisory_only"], True)
        self.assertNotEqual(methodology_context["profile"].get("summary"), "client-owned malicious context")
        self.assertIn("Methodology profile:", package["local_agent"]["prompt_content"])

    async def test_local_agent_package_has_no_methodology_context_when_methodology_is_omitted(self):
        payload = _base_payload()
        payload.update(
            {
                "eval": {"targets": ["REQ-001"]},
                "executionPreference": "local_agent_only",
                "methodology_context": {
                    "methodology": "bmad",
                    "agent": "qa",
                    "phase": "eval",
                },
            }
        )

        with patch.object(
            harper,
            "resolve_execution_policy",
            return_value={
                "requested": "local_agent_only",
                "selected": "local_agent",
                "reason": "test",
                "phase_supported": True,
            },
        ), patch.object(harper, "_post_json", side_effect=AssertionError("Gateway must not be called")):
            package = await harper.run_phase("eval", payload)

        context = _package_context_file(package, "AGENT_EVAL_CONTEXT.json")

        self.assertNotIn("methodology_context", context)
        self.assertNotIn("Methodology profile:", package["local_agent"]["prompt_content"])


if __name__ == "__main__":
    unittest.main()
