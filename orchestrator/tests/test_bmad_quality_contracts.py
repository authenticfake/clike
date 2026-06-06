import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
GATEWAY_ROOT = REPO_ROOT / "gateway"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.quality_contracts import (
    evaluate_lane_guide_structure,
    evaluate_plan_json_structure,
    evaluate_spec_quality,
    load_bmad_quality_contracts,
)
from services.methodologies.resolver import resolve_methodology_context


def _load_gateway_methodology_prompt_module():
    path = GATEWAY_ROOT / "utils" / "methodology_prompt.py"
    spec = importlib.util.spec_from_file_location("gateway_methodology_prompt", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BmadQualityContractTests(unittest.TestCase):
    def test_manifest_quality_contracts_are_machine_readable(self):
        contracts = load_bmad_quality_contracts()

        self.assertIn("spec", contracts)
        self.assertIn("plan", contracts)
        self.assertIn("plan_json_req", contracts)
        self.assertIn("lane_guide", contracts)
        self.assertIn("TECH_CONSTRAINTS.yaml remains authoritative", " ".join(contracts["principles"]))
        self.assertIn("kit_readiness", contracts["plan_json_req"]["required_fields"])
        self.assertIn("main_module_boundary", contracts["plan_json_req"]["required_fields"])
        self.assertIn("security_requirements", contracts["plan_json_req"]["required_fields"])
        self.assertIn("operational_requirements", contracts["plan_json_req"]["required_fields"])

    def test_resolver_includes_quality_contracts_for_spec_and_plan(self):
        spec_context = resolve_methodology_context(phase="spec", methodology="bmad", agent="pm")
        plan_context = resolve_methodology_context(phase="plan", methodology="bmad", agent="architect")
        kit_context = resolve_methodology_context(phase="kit", methodology="bmad", agent="developer")

        self.assertIn("quality_contracts", spec_context)
        self.assertIn("spec", spec_context["quality_contracts"])
        self.assertIn("quality_contracts", plan_context)
        self.assertIn("plan_json_req", plan_context["quality_contracts"])
        self.assertIn("lane_guide", plan_context["quality_contracts"])
        self.assertNotIn("quality_contracts", kit_context)

    def test_cloud_prompt_renders_bmad_quality_contracts_only_when_present(self):
        module = _load_gateway_methodology_prompt_module()
        plan_context = resolve_methodology_context(phase="plan", methodology="bmad", agent="architect")

        rendered = module.render_methodology_context_for_cloud_prompt(plan_context)

        self.assertIn("### BMAD Quality Contract", rendered)
        self.assertIn("TECH_CONSTRAINTS.yaml remains authoritative", rendered)
        self.assertIn("kit_readiness", rendered)
        self.assertIn("main_module_boundary", rendered)
        self.assertIn("forbidden shortcuts", rendered)
        self.assertIn("eval/gate expectations", rendered)
        self.assertEqual(module.render_methodology_context_for_cloud_prompt(None), "")

    def test_shallow_plan_json_fails_structural_score(self):
        shallow = {
            "reqs": [
                {
                    "id": "REQ-001",
                    "title": "Build feature",
                    "acceptance": ["works"],
                }
            ]
        }

        result = evaluate_plan_json_structure(shallow)

        self.assertFalse(result["passed"])
        self.assertLess(result["score"], 0.5)
        self.assertIn("REQ-001", result["missing_by_req"])
        self.assertIn("kit_readiness", result["missing_by_req"]["REQ-001"])
        self.assertIn("main_module_boundary", result["missing_by_req"]["REQ-001"])

    def test_rich_plan_json_passes_structural_score(self):
        rich = {
            "reqs": [
                {
                    "id": "REQ-001",
                    "title": "Build bounded capability",
                    "status": "planned",
                    "dependsOn": [],
                    "lane": "app",
                    "domain": "workflow",
                    "runtime_profile": {"source": "TECH_CONSTRAINTS.yaml", "notes": "runtime selected by project evidence"},
                    "functional_scope": ["create the bounded behavior"],
                    "technical_scope": ["implement inside the declared module boundary"],
                    "non_functional_requirements": ["bounded latency target from SPEC"],
                    "security_requirements": ["preserve authorization boundary"],
                    "operational_requirements": ["emit structured logs and health evidence"],
                    "integration_contracts": [{"name": "input API", "owner": "REQ-001"}],
                    "data_contracts": [{"name": "request payload", "schema": "documented"}],
                    "acceptance": ["Given valid input, when processed, then output matches the contract."],
                    "test_strategy": ["unit test", "contract test", "negative path test"],
                    "risk_notes": ["integration drift; mitigate with contract tests"],
                    "main_module_boundary": "src/workflow",
                    "gate_expectations": ["EvalRunner passes and gate evidence is complete."],
                    "kit_readiness": {
                        "ready": True,
                        "evidence": ["SPEC, TECH_CONSTRAINTS, and lane guide are sufficient for /kit."],
                    },
                }
            ]
        }

        result = evaluate_plan_json_structure(json.dumps(rich))

        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["missing_by_req"], {})

    def test_lane_guide_missing_commands_fails(self):
        lane_guide = """
        # App Lane

        ## Lane Purpose
        Implement bounded app behavior.

        ## Runtime Constraints
        Follow TECH_CONSTRAINTS.

        ## Expected Files
        Candidate source and test files.

        ## Contract Boundaries
        Stay inside declared module boundaries.

        ## Integration Points
        Use declared contracts only.

        ## Forbidden Shortcuts
        Do not bypass eval.

        ## Eval/Gate Expectations
        Canonical EvalRunner and gate remain authoritative.
        """

        result = evaluate_lane_guide_structure(lane_guide)

        self.assertFalse(result["passed"])
        self.assertIn("test_commands", result["missing_topics"])
        self.assertIn("lint_type_build_security_commands", result["missing_topics"])

    def test_spec_missing_security_observability_and_testability_gets_warnings(self):
        spec = """
        # SPEC

        This describes the functional scope and user journey.
        It includes acceptance criteria and scope/non-goals traced to IDEA.
        """

        result = evaluate_spec_quality(spec)

        self.assertFalse(result["passed"])
        self.assertIn("testability", result["missing_topics"])
        self.assertIn("security_privacy_compliance", result["missing_topics"])
        self.assertIn("observability_operations", result["missing_topics"])
        self.assertTrue(any("testability" in warning for warning in result["warnings"]))
        self.assertTrue(any("security_privacy_compliance" in warning for warning in result["warnings"]))
        self.assertTrue(any("observability_operations" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
