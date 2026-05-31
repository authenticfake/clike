import importlib.util
import json
import unittest
from pathlib import Path

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


def _context_file(package):
    files = package["local_agent"]["package_files"]
    match = [
        item
        for item in files
        if isinstance(item, dict) and item["path"].endswith("AGENT_EXECUTION_CONTEXT.json")
    ]
    assert match
    return json.loads(match[0]["content"])


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


if __name__ == "__main__":
    unittest.main()
