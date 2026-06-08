import importlib.util
import json
import sys
import tempfile
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
from services.local_agent_package import build_eval_local_agent_package, build_kit_local_agent_package
from services.methodologies.resolver import resolve_methodology_context


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_VENDOR_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad"


def _bmad_vendor_core_blobs():
    blobs = {
        ".clike/skills/vendor/bmad/manifest.json": (TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")
    }
    for path in sorted(TEMPLATE_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _load_gateway_methodology_prompt_module():
    path = REPO_ROOT / "gateway" / "utils" / "methodology_prompt.py"
    spec = importlib.util.spec_from_file_location("gateway_methodology_prompt", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gateway_artifact_policy_module():
    path = REPO_ROOT / "gateway" / "utils" / "artifact_policy.py"
    spec = importlib.util.spec_from_file_location("gateway_artifact_policy", path)
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
            ),
            **_bmad_vendor_core_blobs(),
        },
    }


def _rich_kit_payload():
    payload = _base_payload()
    payload["kit"] = {"targets": ["REQ-001"], "repair": True}
    payload["core_blobs"] = {
        "IDEA.md": "# Idea\nBuild governed delivery.",
        "SPEC.md": "# Spec\nThe app must support the thing.",
        "PLAN.md": "# Plan\nREQ-000 then REQ-001.",
        "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: node\n  ui: react\n",
        "docs/harper/lane-guides/app.md": "# App Lane\nUse the app lane policy.",
        "plan.json": json.dumps(
            {
                "reqs": [
                    {
                        "id": "REQ-000",
                        "title": "Foundation",
                        "acceptance": ["Foundation works"],
                        "lane": "App",
                        "dependsOn": [],
                    },
                    {
                        "id": "REQ-001",
                        "title": "Build the thing",
                        "acceptance": ["Thing works", "Thing is tested"],
                        "lane": "App",
                        "dependsOn": ["REQ-000"],
                    },
                    {
                        "id": "REQ-002",
                        "title": "Use the thing",
                        "acceptance": ["Usage works"],
                        "lane": "App",
                        "dependsOn": ["REQ-001"],
                    },
                ]
            }
        ),
        "companion::docs/harper/bmad/spec/PRD_DRAFT.md": "# PRD Draft\nBMAD product notes.",
        "companion::docs/harper/ux/wireframes/FLOW.md": "# UX Flow\nUser journey notes.",
        "TARGET_CONTRACT.json": json.dumps(
            {
                "req_id": "REQ-001",
                "acceptance": ["Thing works", "Thing is tested"],
            }
        ),
        "FILE_REQUIREMENTS.json": json.dumps(
            {
                "required_outputs": [
                    {"path": "runs/kit/REQ-001/src/example.js", "required": True}
                ]
            }
        ),
        **_bmad_vendor_core_blobs(),
    }
    return payload


def _write_workspace_file(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def _eval_package(payload):
    return build_eval_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy={
            "requested": "prefer_local_agent",
            "selected": "local_agent",
            "reason": "test",
            "phase_supported": True,
        },
    )


class HarperCapabilityExtractionTests(unittest.TestCase):
    def _contract_for_req(self, req):
        return harper._extract_target_contract(
            {"plan.json": json.dumps({"reqs": [req]})},
            "REQ-001",
        )

    def test_target_contract_extracts_top_level_capabilities(self):
        contract = self._contract_for_req(
            {
                "id": "REQ-001",
                "title": "Build",
                "acceptance": [],
                "packs": ["enterprise-python"],
                "skills": ["provider-realism"],
                "design_profiles": ["ops-console"],
            }
        )

        self.assertEqual(contract["packs"], ["enterprise-python"])
        self.assertEqual(contract["skills"], ["provider-realism"])
        self.assertEqual(contract["design_profiles"], ["ops-console"])

    def test_target_contract_extracts_nested_capabilities(self):
        contract = self._contract_for_req(
            {
                "id": "REQ-001",
                "title": "Build",
                "acceptance": [],
                "capabilities": {
                    "packs": ["enterprise-onprem"],
                    "skills": ["secure-config-secrets"],
                    "design_profiles": ["enterprise-console"],
                },
            }
        )

        self.assertEqual(contract["packs"], ["enterprise-onprem"])
        self.assertEqual(contract["skills"], ["secure-config-secrets"])
        self.assertEqual(contract["design_profiles"], ["enterprise-console"])

    def test_target_contract_top_level_non_empty_capabilities_win(self):
        contract = self._contract_for_req(
            {
                "id": "REQ-001",
                "title": "Build",
                "acceptance": [],
                "packs": ["top-pack"],
                "skills": ["top-skill"],
                "design_profiles": ["top-design"],
                "capabilities": {
                    "packs": ["nested-pack"],
                    "skills": ["nested-skill"],
                    "design_profiles": ["nested-design"],
                },
            }
        )

        self.assertEqual(contract["packs"], ["top-pack"])
        self.assertEqual(contract["skills"], ["top-skill"])
        self.assertEqual(contract["design_profiles"], ["top-design"])

    def test_target_contract_empty_top_level_capabilities_fall_back_to_nested(self):
        contract = self._contract_for_req(
            {
                "id": "REQ-001",
                "title": "Build",
                "acceptance": [],
                "packs": [],
                "skills": [],
                "design_profiles": [],
                "capabilities": {
                    "packs": ["nested-pack"],
                    "skills": ["nested-skill"],
                    "designProfiles": ["nested-design"],
                },
            }
        )

        self.assertEqual(contract["packs"], ["nested-pack"])
        self.assertEqual(contract["skills"], ["nested-skill"])
        self.assertEqual(contract["design_profiles"], ["nested-design"])


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
        self.assertIn("### BMAD Companion Artifact Contract", rendered)
        self.assertIn("### BMAD Companion Artifact Inventory", rendered)
        self.assertIn("### BMAD Governance Boundaries", rendered)
        self.assertIn("### BMAD Downstream Handoff", rendered)
        self.assertIn("### BMAD Skill Reference Context", rendered)
        self.assertIn("dev-story-execution", rendered)
        self.assertIn("story-readiness", rendered)
        self.assertIn("- methodology: bmad", rendered)
        self.assertIn("- role: developer", rendered)
        self.assertIn("- workflow_summary:", rendered)
        self.assertIn("- workflow_focus:", rendered)
        self.assertIn("- required_context:", rendered)
        self.assertIn("- companion_artifacts:", rendered)
        self.assertIn("CLike remains the governance runtime", rendered)

    def test_cloud_prompt_renderer_omits_bmad_block_without_context(self):
        module = _load_gateway_methodology_prompt_module()

        self.assertEqual(module.render_methodology_context_for_cloud_prompt(None), "")
        self.assertEqual(module.render_methodology_context_for_cloud_prompt({}), "")

    def test_cloud_prompt_renderer_includes_companion_inventory(self):
        module = _load_gateway_methodology_prompt_module()
        rendered = module.render_methodology_context_for_cloud_prompt(
            {
                "methodology": "bmad",
                "phase": "kit",
                "agent": "developer",
                "discovered_companion_artifacts": [
                    {
                        "path": "docs/harper/bmad/idea/DEEP_DIVE_X.md",
                        "source_group": "bmad_project",
                        "size_bytes": 100,
                        "sha256": "abcdef1234567890",
                        "truncated": True,
                    }
                ],
            }
        )

        self.assertIn("BMAD Companion Artifact Inventory", rendered)
        self.assertIn("docs/harper/bmad/idea/DEEP_DIVE_X.md", rendered)
        self.assertIn("truncated: True", rendered)

    def test_cloud_prompt_renderer_includes_spec_ux_companion_only_policy(self):
        module = _load_gateway_methodology_prompt_module()
        context = resolve_methodology_context(
            phase="spec",
            methodology="bmad",
            agent="ux",
        )

        rendered = module.render_methodology_context_for_cloud_prompt(context)

        self.assertIn("SPEC UX artifact policy:", rendered)
        self.assertIn("- companion-only: true", rendered)
        self.assertIn("PM-owned canonical SPEC remains authoritative", rendered)
        self.assertIn("UX must produce companion artifacts only", rendered)
        self.assertIn("UX artifacts are consumed by /plan", rendered)
        self.assertIn("docs/harper/SPEC.md", rendered)

    def test_gateway_artifact_policy_filters_spec_ux_outputs(self):
        module = _load_gateway_artifact_policy_module()
        context = resolve_methodology_context(
            phase="spec",
            methodology="bmad",
            agent="ux",
        )
        warnings = []

        filtered = module.filter_files_by_methodology_artifact_policy(
            [
                {"path": "docs/harper/SPEC.md", "content": "# Wrong"},
                {"path": "docs/harper/ux/DESIGN.md", "content": "# Design"},
                {"path": "docs/harper/bmad/spec/PRD.md", "content": "# PRD"},
            ],
            phase="spec",
            methodology_context=context,
            warnings=warnings,
        )

        self.assertEqual([item["path"] for item in filtered], ["docs/harper/ux/DESIGN.md"])
        self.assertTrue(any("bmad_spec_ux_companion_only" in item for item in warnings))
        self.assertTrue(any("docs/harper/SPEC.md" in item for item in warnings))

    def test_gateway_artifact_policy_allows_spec_pm_outputs(self):
        module = _load_gateway_artifact_policy_module()
        context = resolve_methodology_context(
            phase="spec",
            methodology="bmad",
            agent="pm",
        )
        warnings = []

        filtered = module.filter_files_by_methodology_artifact_policy(
            [
                {"path": "docs/harper/SPEC.md", "content": "# Spec"},
                {"path": "docs/harper/bmad/spec/PRD.md", "content": "# PRD"},
                {"path": "docs/harper/ux/DESIGN.md", "content": "# Design"},
            ],
            phase="spec",
            methodology_context=context,
            warnings=warnings,
        )

        self.assertEqual(
            [item["path"] for item in filtered],
            ["docs/harper/SPEC.md", "docs/harper/bmad/spec/PRD.md"],
        )
        self.assertTrue(any("docs/harper/ux/DESIGN.md" in item for item in warnings))

    def test_gateway_harper_run_passes_resolved_methodology_context_to_cloud_composer(self):
        source = (REPO_ROOT / "gateway" / "routes" / "harper.py").read_text(encoding="utf-8")

        self.assertIn("render_methodology_context_for_cloud_prompt(", source)
        self.assertIn("build_active_output_contract(", source)
        self.assertIn("validate_files_against_active_output_contract(", source)
        self.assertIn("req.methodology_context", source)
        self.assertIn("filter_files_by_methodology_artifact_policy(", source)

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
        self.assertEqual(context["active_output_contract"]["methodology"], "bmad")
        self.assertIn("runs/kit/REQ-001/docs/BMAD_DEV_STORY.md", context["active_output_contract"]["required_outputs"])
        self.assertIn("workflow_summary", context["methodology_context"])
        self.assertIn("workflow_focus", context["methodology_context"])
        self.assertIn("required_context", context["methodology_context"])
        self.assertIn("companion_artifacts", context["methodology_context"])
        self.assertIn("governance_boundaries", context["methodology_context"])
        self.assertIn("Methodology profile:", package["local_agent"]["prompt_content"])
        self.assertIn("workflow_focus:", package["local_agent"]["prompt_content"])
        self.assertIn("required_context:", package["local_agent"]["prompt_content"])
        self.assertIn("companion_artifacts:", package["local_agent"]["prompt_content"])
        self.assertIn("governance_boundary:", package["local_agent"]["prompt_content"])
        self.assertIn("allowed_write_roots", package["local_agent"]["prompt_content"])
        self.assertIn("Active output contract:", package["local_agent"]["prompt_content"])
        self.assertIn("selected_skill_references", context)
        self.assertIn("selected_skill_context", context)
        self.assertIn("skill_reference_policy", context)
        self.assertEqual(
            [item["id"] for item in context["selected_skill_references"]],
            ["dev-story-execution", "story-readiness"],
        )
        self.assertIn("### BMAD Skill Reference Context", package["local_agent"]["prompt_content"])
        self.assertIn("dev-story-execution", package["local_agent"]["prompt_content"])
        self.assertIn("story-readiness", package["local_agent"]["prompt_content"])
        self.assertIn("never execute BMAD runtime", package["local_agent"]["prompt_content"])
        self.assertIn("Never expand write roots", package["local_agent"]["prompt_content"])

    def test_methodology_context_is_absent_when_omitted(self):
        package = _kit_package(_base_payload())
        context = _context_file(package)

        self.assertNotIn("methodology_context", context)
        self.assertNotIn("Methodology profile:", package["local_agent"]["prompt_content"])
        self.assertNotIn("selected_skill_references", context)
        self.assertNotIn("BMAD Skill Reference Context", package["local_agent"]["prompt_content"])
        self.assertEqual(context["active_output_contract"]["methodology"], "native_clike")

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

        eval_baseline_payload = _rich_kit_payload()
        eval_baseline_payload["eval"] = {"targets": ["REQ-001"]}
        eval_baseline = _eval_package(eval_baseline_payload)

        eval_bmad_payload = _rich_kit_payload()
        eval_bmad_payload["eval"] = {"targets": ["REQ-001"]}
        eval_bmad_payload["methodology_context"] = resolve_methodology_context(
            phase="eval",
            methodology="bmad",
            agent="qa",
        )
        eval_with_bmad = _eval_package(eval_bmad_payload)

        self.assertEqual(
            eval_baseline["local_agent"]["allowed_write_roots"],
            eval_with_bmad["local_agent"]["allowed_write_roots"],
        )
        self.assertEqual(
            eval_baseline["local_agent"]["forbidden_paths"],
            eval_with_bmad["local_agent"]["forbidden_paths"],
        )

    def test_kit_agent_execution_context_includes_bounded_project_and_companion_context(self):
        payload = _rich_kit_payload()
        payload["methodology_context"] = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
        )

        package = _kit_package(payload)
        context = _context_file(package)
        local_agent = package["local_agent"]

        self.assertEqual(context["methodology_context"]["methodology"], "bmad")
        self.assertEqual(context["active_output_contract"]["methodology"], "bmad")
        self.assertEqual(
            [item["id"] for item in context["selected_skill_references"]],
            ["dev-story-execution", "story-readiness"],
        )
        self.assertIn("### BMAD Skill Reference Context", local_agent["prompt_content"])
        self.assertIn("dev-story-execution", local_agent["prompt_content"])
        self.assertIn("story-readiness", local_agent["prompt_content"])
        self.assertIn(
            "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
            context["active_output_contract"]["required_outputs"],
        )
        self.assertEqual(context["current_req"]["req_id"], "REQ-001")
        self.assertEqual(context["current_req"]["acceptance_criteria"], ["Thing works", "Thing is tested"])
        self.assertEqual(context["current_req"]["dependencies"], ["REQ-000"])
        self.assertTrue(context["source_documents"]["tech_constraints"]["present"])
        self.assertEqual(context["source_documents"]["tech_constraints"]["path"], "docs/harper/TECH_CONSTRAINTS.yaml")
        self.assertTrue(context["source_documents"]["idea"]["present"])
        self.assertTrue(context["source_documents"]["spec"]["present"])
        self.assertTrue(context["source_documents"]["plan"]["present"])
        self.assertTrue(context["source_documents"]["plan_json"]["present"])
        self.assertEqual(context["source_documents"]["plan_json"]["path"], "docs/harper/plan.json")
        self.assertTrue(context["source_documents"]["lane_guides"]["present"])
        self.assertEqual(
            context["source_documents"]["lane_guides"]["documents"][0]["path"],
            "docs/harper/lane-guides/app.md",
        )
        self.assertEqual(
            context["companion_documents"]["bmad"]["documents"][0]["path"],
            "docs/harper/bmad/spec/PRD_DRAFT.md",
        )
        self.assertEqual(
            context["companion_documents"]["ux"]["documents"][0]["path"],
            "docs/harper/ux/wireframes/FLOW.md",
        )
        self.assertEqual(context["repair_context"]["repair"], True)
        self.assertIn("runs/eval/REQ-001", context["repair_context"]["previous_eval_context_paths"])
        self.assertEqual(
            context["repository_analysis_required"]["promoted_source_roots_read_only"],
            ["src"],
        )
        self.assertEqual(
            context["repository_analysis_required"]["promoted_test_roots_read_only"],
            ["test", "tests"],
        )
        self.assertEqual(
            context["workspace_inspection_policy"]["dependency_kit_roots"],
            ["runs/kit/REQ-000"],
        )
        self.assertEqual(
            context["candidate_output_roots"]["src"],
            "runs/kit/REQ-001/src",
        )
        self.assertEqual(
            context["candidate_contract_paths"]["target_contract"],
            "runs/kit/REQ-001/docs/TARGET_CONTRACT.json",
        )
        self.assertEqual(
            context["expected_outputs"]["bmad"]["mandatory_companion_outputs"],
            [
                "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
                "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md",
                "runs/kit/REQ-001/docs/SELF_REVIEW.md",
                "runs/kit/REQ-001/docs/RUNBOOK.md",
            ],
        )
        self.assertEqual(
            local_agent["expected_outputs"]["bmad"]["mandatory_companion_outputs"],
            context["expected_outputs"]["bmad"]["mandatory_companion_outputs"],
        )
        self.assertEqual(
            local_agent["allowed_write_roots"],
            [
                "runs/kit/REQ-001/src",
                "runs/kit/REQ-001/test",
                "runs/kit/REQ-001/ci",
                "runs/kit/REQ-001/docs",
            ],
        )
        self.assertIn("src", local_agent["forbidden_paths"])
        self.assertIn("test", local_agent["forbidden_paths"])
        self.assertIn("tests", local_agent["forbidden_paths"])
        self.assertIn("docs/harper/PLAN.md", local_agent["forbidden_paths"])
        self.assertIn("docs/harper/plan.json", local_agent["forbidden_paths"])
        self.assertIn("AGENT_EXECUTION_CONTEXT.json", local_agent["prompt_content"])
        self.assertIn("TECH_CONSTRAINTS.yaml is authoritative", local_agent["prompt_content"])
        self.assertIn("Parse BMAD companion artifacts", local_agent["prompt_content"])
        self.assertIn("Active output contract:", local_agent["prompt_content"])
        self.assertIn("active_output_contract", local_agent)
        self.assertIn("Read BMAD/UX companion docs before code generation", local_agent["prompt_content"])
        self.assertIn("Do not treat companion docs as canonical", local_agent["prompt_content"])
        self.assertIn("never run Git operations", local_agent["prompt_content"])

    def test_eval_agent_context_includes_bmad_repair_inputs_without_expanding_write_roots(self):
        payload = _rich_kit_payload()
        payload["eval"] = {"targets": ["REQ-001"]}
        payload["methodology_context"] = resolve_methodology_context(
            phase="eval",
            methodology="bmad",
            agent="qa",
        )

        package = _eval_package(payload)
        context = _package_context_file(package, "AGENT_EVAL_CONTEXT.json")
        local_agent = package["local_agent"]

        self.assertEqual(context["methodology_context"]["methodology"], "bmad")
        self.assertEqual(context["methodology_context"]["agent"], "qa")
        self.assertEqual(context["active_output_contract"]["methodology"], "bmad")
        self.assertIn(
            "runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md",
            context["active_output_contract"]["required_outputs"],
        )
        self.assertEqual(context["current_req"]["req_id"], "REQ-001")
        self.assertEqual(context["current_req"]["acceptance_criteria"], ["Thing works", "Thing is tested"])
        self.assertEqual(context["current_req"]["dependencies"], ["REQ-000"])
        self.assertTrue(context["source_documents"]["tech_constraints"]["present"])
        self.assertEqual(context["source_documents"]["tech_constraints"]["path"], "docs/harper/TECH_CONSTRAINTS.yaml")
        self.assertEqual(context["source_documents"]["idea"]["path"], "docs/harper/IDEA.md")
        self.assertEqual(context["source_documents"]["spec"]["path"], "docs/harper/SPEC.md")
        self.assertEqual(context["source_documents"]["plan"]["path"], "docs/harper/PLAN.md")
        self.assertEqual(context["source_documents"]["plan_json"]["path"], "docs/harper/plan.json")
        self.assertTrue(context["source_documents"]["lane_guides"]["present"])
        self.assertEqual(
            context["companion_documents"]["bmad"]["documents"][0]["path"],
            "docs/harper/bmad/spec/PRD_DRAFT.md",
        )
        self.assertEqual(
            context["companion_documents"]["ux"]["documents"][0]["path"],
            "docs/harper/ux/wireframes/FLOW.md",
        )
        self.assertEqual(context["candidate_roots"]["src"], "runs/kit/REQ-001/src")
        self.assertEqual(context["candidate_roots"]["test"], "runs/kit/REQ-001/test")
        self.assertEqual(context["candidate_roots"]["ci"], "runs/kit/REQ-001/ci")
        self.assertEqual(context["candidate_roots"]["docs"], "runs/kit/REQ-001/docs")
        self.assertEqual(context["candidate_eval_inputs"]["ltc_path"], "runs/kit/REQ-001/ci/LTC.json")
        self.assertEqual(context["candidate_eval_inputs"]["howto_path"], "runs/kit/REQ-001/ci/HOWTO.md")
        self.assertEqual(
            context["candidate_eval_inputs"]["target_contract_paths"],
            [
                "runs/kit/REQ-001/ci/TARGET_CONTRACT.json",
                "runs/kit/REQ-001/docs/TARGET_CONTRACT.json",
            ],
        )
        self.assertEqual(
            context["candidate_eval_inputs"]["file_requirements_paths"],
            [
                "runs/kit/REQ-001/ci/FILE_REQUIREMENTS.json",
                "runs/kit/REQ-001/docs/FILE_REQUIREMENTS.json",
            ],
        )
        self.assertEqual(context["candidate_eval_inputs"]["target_contract"]["req_id"], "REQ-001")
        self.assertIn("required_outputs", context["candidate_eval_inputs"]["file_requirements"])
        self.assertEqual(context["previous_eval_reports"]["root"], "runs/eval/REQ-001")
        self.assertIs(context["previous_eval_reports"]["read_only"], True)
        self.assertIs(context["repair_intent"]["requested"], True)
        self.assertEqual(
            context["bmad_developer_docs"]["expected_paths"],
            [
                "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
                "runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md",
                "runs/kit/REQ-001/docs/SELF_REVIEW.md",
                "runs/kit/REQ-001/docs/RUNBOOK.md",
            ],
        )
        self.assertEqual(
            context["bmad_qa_advisory_output_targets"]["mandatory_companion_outputs"],
            [
                "runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md",
                "runs/kit/REQ-001/docs/FIX_GUIDANCE.md",
                "runs/kit/REQ-001/docs/MISSING_TESTS.md",
                "runs/kit/REQ-001/docs/RISK_REVIEW.md",
            ],
        )
        self.assertEqual(
            context["expected_eval_inputs"]["bmad"]["mandatory_companion_outputs"],
            context["bmad_qa_advisory_output_targets"]["mandatory_companion_outputs"],
        )
        self.assertEqual(
            local_agent["expected_outputs"]["bmad"]["mandatory_companion_outputs"],
            context["bmad_qa_advisory_output_targets"]["mandatory_companion_outputs"],
        )
        self.assertEqual(
            context["repository_analysis_required"]["promoted_source_roots_read_only"],
            ["src"],
        )
        self.assertEqual(
            context["repository_analysis_required"]["promoted_test_roots_read_only"],
            ["test", "tests"],
        )
        self.assertEqual(
            context["repository_analysis_required"]["dependency_kit_roots_read_only"],
            ["runs/kit/REQ-000"],
        )
        self.assertEqual(
            local_agent["allowed_write_roots"],
            [
                "runs/kit/REQ-001/src",
                "runs/kit/REQ-001/test",
                "runs/kit/REQ-001/ci",
                "runs/kit/REQ-001/docs",
                "runs/kit/REQ-001/reports",
            ],
        )
        for forbidden in ["src", "test", "tests", "docs/harper/PLAN.md", "docs/harper/plan.json"]:
            self.assertIn(forbidden, local_agent["forbidden_paths"])
        self.assertIn("runs/kit/REQ-001/reports/BMAD_EVAL_REPAIR_NOTES.md", context["local_repair_policy"]["notes_output_path"])
        self.assertIn("BMAD_EVAL_REPAIR_NOTES.md", local_agent["prompt_content"])
        self.assertIn("Active output contract:", local_agent["prompt_content"])
        self.assertIn("active_output_contract", local_agent)
        self.assertIn("canonical EvalRunner remains authoritative", local_agent["prompt_content"])
        self.assertIn("Use BMAD QA docs for repair guidance", local_agent["prompt_content"])
        self.assertIn("Never mutate canonical eval verdict fields", local_agent["prompt_content"])
        self.assertIn("never run Git operations", local_agent["prompt_content"])

    def test_eval_local_agent_package_has_no_bmad_block_without_context(self):
        payload = _rich_kit_payload()
        payload["eval"] = {"targets": ["REQ-001"]}

        package = _eval_package(payload)
        context = _package_context_file(package, "AGENT_EVAL_CONTEXT.json")

        self.assertNotIn("methodology_context", context)
        self.assertNotIn("Methodology profile:", package["local_agent"]["prompt_content"])


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

        resolve_mock.assert_called_once()
        _, resolve_kwargs = resolve_mock.call_args
        self.assertEqual(resolve_kwargs.get("phase"), "spec")
        self.assertEqual(resolve_kwargs.get("methodology"), "bmad")
        self.assertEqual(resolve_kwargs.get("agent"), "pm")
        self.assertTrue(resolve_kwargs.get("require_bmad_core_blobs"))
        self.assertIn(".clike/skills/vendor/bmad/manifest.json", resolve_kwargs.get("core_blobs") or {})
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

    async def test_gateway_invalid_canonical_artifact_result_is_returned_not_raised(self):
        async def fake_post_json(path, payload):
            return {
                "ok": False,
                "phase": payload.get("phase"),
                "error_code": "invalid_canonical_artifact",
                "text": "IDEA.md failed canonical validation and was not written.",
                "files": [],
                "partial_files": [
                    {
                        "path": "docs/harper/bmad/idea/BRIEF.md",
                        "content": "# Brief",
                    }
                ],
                "diagnostic_files": [
                    {
                        "path": "docs/harper/bmad/idea/BRIEF.md",
                        "content": "# Brief",
                    }
                ],
                "diffs": [],
                "tests": {"passed": 0, "failed": 1, "summary": "invalid_canonical_artifact"},
                "warnings": [],
                "errors": [
                    {
                        "path": "docs/harper/IDEA.md",
                        "failed_checks": ["missing_idea_h1"],
                        "diagnostic": "IDEA.md failed canonical Harper structure validation.",
                        "error_code": "invalid_canonical_artifact",
                    }
                ],
                "rejected": [
                    {
                        "path": "docs/harper/IDEA.md",
                        "failed_checks": ["missing_idea_h1"],
                    }
                ],
                "runId": payload.get("runId"),
            }

        async def fake_resolve_llm_selection(**kwargs):
            return {}

        payload = _base_payload()
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper,
            "resolve_llm_selection",
            side_effect=fake_resolve_llm_selection,
        ):
            out = await harper.run_phase("idea", payload)

        self.assertIs(out["ok"], False)
        self.assertEqual(out["error_code"], "invalid_canonical_artifact")
        self.assertEqual(out["files"], [])
        self.assertEqual(out["partial_files"][0]["path"], "docs/harper/bmad/idea/BRIEF.md")
        self.assertEqual(out["errors"][0]["failed_checks"], ["missing_idea_h1"])

    async def test_server_discovered_companion_docs_are_injected_into_cloud_payload(self):
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

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_file(root, "docs/harper/bmad/idea/BRIEF.md", "# Brief\nServer brief.")
            _write_workspace_file(root, "docs/harper/bmad/idea/DEEP_DIVE_X.md", "# Deep Dive\nServer wins.")
            _write_workspace_file(root, "docs/harper/ux/DESIGN.md", "# Design\nServer UX.")

            payload = _base_payload()
            payload.update(
                {
                    "repository_context": {"repo_root": str(root), "workspace_folder": str(root)},
                    "methodology": "bmad",
                    "agent": "pm",
                }
            )
            payload["core_blobs"]["companion::docs/harper/bmad/idea/DEEP_DIVE_X.md"] = "client stale"

            with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
                harper,
                "resolve_llm_selection",
                side_effect=fake_resolve_llm_selection,
            ):
                await harper.run_phase("spec", payload)

        self.assertEqual(captured[0]["path"], "/v1/harper/run")
        sent = captured[0]["payload"]
        artifact_paths = {
            item["path"]
            for item in sent["methodology_context"]["discovered_companion_artifacts"]
        }
        self.assertIn("docs/harper/bmad/idea/BRIEF.md", artifact_paths)
        self.assertIn("docs/harper/bmad/idea/DEEP_DIVE_X.md", artifact_paths)
        self.assertIn("docs/harper/ux/DESIGN.md", artifact_paths)
        self.assertIn(
            "Server wins.",
            sent["core_blobs"]["companion::docs/harper/bmad/idea/DEEP_DIVE_X.md"],
        )
        self.assertNotIn(
            "client stale",
            sent["core_blobs"]["companion::docs/harper/bmad/idea/DEEP_DIVE_X.md"],
        )

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

    async def test_gateway_is_not_called_for_kit_local_agent_package_generation(self):
        payload = _rich_kit_payload()
        payload.update(
            {
                "executionPreference": "local_agent_only",
                "methodology": "bmad",
                "agent": "developer",
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
        ), patch.object(
            harper,
            "_write_stage_artifact",
            return_value=None,
        ), patch.object(harper, "_post_json", side_effect=AssertionError("Gateway must not be called")):
            package = await harper.run_phase("kit", payload)

        self.assertEqual(package["local_agent"]["action"], "local_agent_required")
        context = _context_file(package)
        self.assertEqual(context["methodology_context"]["methodology"], "bmad")
        self.assertEqual(context["methodology_context"]["phase"], "kit")
        self.assertEqual(context["methodology_context"]["agent"], "developer")
        self.assertEqual(
            [item["id"] for item in context["selected_skill_references"]],
            ["dev-story-execution", "story-readiness"],
        )
        self.assertIn("selected_skill_context", context)
        self.assertIn("skill_reference_policy", context)
        self.assertIn("### BMAD Skill Reference Context", package["local_agent"]["prompt_content"])
        self.assertIn("dev-story-execution", package["local_agent"]["prompt_content"])
        self.assertIn("story-readiness", package["local_agent"]["prompt_content"])
        self.assertEqual(context["companion_documents"]["bmad"]["documents"][0]["path"], "docs/harper/bmad/spec/PRD_DRAFT.md")

    async def test_kit_cloud_gateway_payload_receives_selected_bmad_skill_context(self):
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

        payload = _rich_kit_payload()
        payload.update(
            {
                "executionPreference": "cloud_only",
                "methodology": "bmad",
                "agent": "developer",
            }
        )

        with patch.object(
            harper,
            "_write_stage_artifact",
            return_value=None,
        ), patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper,
            "resolve_llm_selection",
            side_effect=fake_resolve_llm_selection,
        ):
            await harper.run_phase("kit", payload)

        self.assertEqual(captured[0]["path"], "/v1/harper/run")
        sent = captured[0]["payload"]
        methodology_context = sent["methodology_context"]
        self.assertEqual(sent["methodology"], "bmad")
        self.assertEqual(sent["agent"], "developer")
        self.assertEqual(methodology_context["methodology"], "bmad")
        self.assertEqual(methodology_context["phase"], "kit")
        self.assertEqual(methodology_context["agent"], "developer")
        self.assertEqual(
            [item["id"] for item in methodology_context["selected_skill_references"]],
            ["dev-story-execution", "story-readiness"],
        )
        self.assertIn("selected_skill_context", methodology_context)
        self.assertIn("skill_reference_policy", methodology_context)
        self.assertIn("context_envelope", sent)
        self.assertEqual(sent["context_envelope"]["phase"], "kit")
        self.assertEqual(sent["context_envelope"]["methodology"], "bmad")
        self.assertEqual(sent["context_envelope"]["agent"], "developer")
        self.assertEqual(
            [
                item["id"]
                for item in sent["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]
            ],
            ["dev-story-execution", "story-readiness"],
        )

    async def test_gateway_is_not_called_for_eval_local_agent_package_generation(self):
        payload = _rich_kit_payload()
        payload.update(
            {
                "eval": {"targets": ["REQ-001"]},
                "executionPreference": "local_agent_only",
                "methodology": "bmad",
                "agent": "qa",
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

        self.assertEqual(package["local_agent"]["action"], "local_agent_required")
        context = _package_context_file(package, "AGENT_EVAL_CONTEXT.json")
        self.assertEqual(context["methodology_context"]["methodology"], "bmad")
        self.assertEqual(context["methodology_context"]["agent"], "qa")

    async def test_server_discovered_companion_docs_reach_local_kit_and_eval_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_file(root, "docs/harper/bmad/idea/BRIEF.md", "# Brief\nServer brief.")
            _write_workspace_file(root, "docs/harper/bmad/idea/DEEP_DIVE_X.md", "# Deep Dive\nServer wins.")
            _write_workspace_file(root, "docs/harper/ux/DESIGN.md", "# Design\nServer UX.")
            _write_workspace_file(root, "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md", "# Dev Story\nServer REQ docs.")

            kit_payload = _rich_kit_payload()
            kit_payload.update(
                {
                    "repository_context": {"repo_root": str(root), "workspace_folder": str(root)},
                    "executionPreference": "local_agent_only",
                    "methodology": "bmad",
                    "agent": "developer",
                }
            )
            kit_payload["core_blobs"]["companion::docs/harper/bmad/idea/DEEP_DIVE_X.md"] = "client stale"

            with patch.object(
                harper,
                "resolve_execution_policy",
                return_value={
                    "requested": "local_agent_only",
                    "selected": "local_agent",
                    "reason": "test",
                    "phase_supported": True,
                },
            ), patch.object(
                harper,
                "_write_stage_artifact",
                return_value=None,
            ), patch.object(harper, "_post_json", side_effect=AssertionError("Gateway must not be called")):
                kit_package = await harper.run_phase("kit", kit_payload)

            kit_context = _context_file(kit_package)
            bmad_paths = {
                item["path"]: item["snippet"]
                for item in kit_context["companion_documents"]["bmad"]["documents"]
            }
            ux_paths = {
                item["path"]
                for item in kit_context["companion_documents"]["ux"]["documents"]
            }
            req_doc_paths = {
                item["path"]
                for item in kit_context["companion_documents"]["req_docs"]["documents"]
            }

            self.assertIn("docs/harper/bmad/idea/BRIEF.md", bmad_paths)
            self.assertIn("docs/harper/bmad/idea/DEEP_DIVE_X.md", bmad_paths)
            self.assertIn("Server wins.", bmad_paths["docs/harper/bmad/idea/DEEP_DIVE_X.md"])
            self.assertIn("docs/harper/ux/DESIGN.md", ux_paths)
            self.assertIn("runs/kit/REQ-001/docs/BMAD_DEV_STORY.md", req_doc_paths)
            self.assertIn(
                "docs/harper/bmad/idea/DEEP_DIVE_X.md",
                {
                    item["path"]
                    for item in kit_context["methodology_context"]["discovered_companion_artifacts"]
                },
            )
            self.assertIn(
                "docs/harper/bmad/idea/DEEP_DIVE_X.md",
                {
                    item["path"]
                    for item in kit_context["discovered_companion_artifact_inventory"]
                },
            )
            self.assertIn(
                "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
                kit_context["expected_outputs"]["bmad"]["mandatory_companion_outputs"],
            )

            eval_payload = _rich_kit_payload()
            eval_payload.update(
                {
                    "repository_context": {"repo_root": str(root), "workspace_folder": str(root)},
                    "eval": {"targets": ["REQ-001"]},
                    "executionPreference": "local_agent_only",
                    "methodology": "bmad",
                    "agent": "qa",
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
                eval_package = await harper.run_phase("eval", eval_payload)

            eval_context = _package_context_file(eval_package, "AGENT_EVAL_CONTEXT.json")
            self.assertIn(
                "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md",
                {
                    item["path"]
                    for item in eval_context["companion_documents"]["req_docs"]["documents"]
                },
            )
            self.assertIn(
                "docs/harper/ux/DESIGN.md",
                {
                    item["path"]
                    for item in eval_context["companion_documents"]["ux"]["documents"]
                },
            )
            self.assertIn(
                "docs/harper/bmad/idea/DEEP_DIVE_X.md",
                {
                    item["path"]
                    for item in eval_context["discovered_companion_artifact_inventory"]
                },
            )
            self.assertIn(
                "runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md",
                eval_context["bmad_qa_advisory_output_targets"]["mandatory_companion_outputs"],
            )

    async def test_document_phase_returns_local_agent_package_without_cloud_call(self):
        for phase, expected_output in (
            ("idea", "docs/harper/IDEA.md"),
            ("spec", "docs/harper/SPEC.md"),
            ("plan", "docs/harper/PLAN.md"),
        ):
            cloud_calls = []

            async def fake_post_json(path, payload):
                cloud_calls.append(path)
                return {"ok": True, "phase": payload.get("phase")}

            async def fake_resolve_llm_selection(**kwargs):
                return {}

            payload = _base_payload()
            payload["executionPreference"] = "prefer_local_agent"
            # /idea requires at least one current-run attachment as source of truth.
            if phase == "idea":
                payload["attachments"] = [
                    {"name": "IDEA.md", "path": ".clike/uploads/IDEA.md", "mime": "text/markdown"}
                ]

            with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
                harper,
                "resolve_llm_selection",
                side_effect=fake_resolve_llm_selection,
            ):
                out = await harper.run_phase(phase, payload)

            self.assertEqual(cloud_calls, [], f"cloud was called for {phase}")
            self.assertEqual(out["phase"], phase)
            self.assertEqual(out["local_agent"]["action"], "local_agent_required")
            self.assertEqual(out["execution"]["selected"], "local_agent")
            self.assertIn(
                expected_output,
                out["local_agent"]["expected_outputs"]["always"],
            )

    async def test_document_phase_local_agent_only_failure_does_not_fall_back_to_cloud(self):
        cloud_calls = []

        async def fake_post_json(path, payload):
            cloud_calls.append(path)
            return {"ok": True, "phase": payload.get("phase")}

        async def fake_resolve_llm_selection(**kwargs):
            return {}

        def boom(**kwargs):
            raise RuntimeError("document package build failed")

        payload = _base_payload()
        payload["executionPreference"] = "local_agent_only"

        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper,
            "resolve_llm_selection",
            side_effect=fake_resolve_llm_selection,
        ), patch.object(
            harper,
            "build_document_phase_local_agent_package",
            side_effect=boom,
        ):
            out = await harper.run_phase("spec", payload)

        self.assertEqual(cloud_calls, [], "local_agent_only must not call cloud on failure")
        self.assertIs(out["ok"], False)
        self.assertEqual(out["execution"]["selected"], "local_agent")
        self.assertEqual(out["execution"]["reason"], "local_agent_spec_package_failed")


if __name__ == "__main__":
    unittest.main()
