import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class PlanPromptContentTests(unittest.TestCase):
    def assert_contains_all(self, text: str, phrases: list[str]) -> None:
        lowered = text.lower()
        for phrase in phrases:
            self.assertIn(phrase.lower(), lowered)

    def test_plan_system_mentions_core_req_obligations(self) -> None:
        content = _read("gateway/prompts/harper/plan_system.md")

        self.assert_contains_all(
            content,
            [
                "Functional Scope",
                "Non-Functional Requirements",
                "Security Requirements",
                "TECH_CONSTRAINTS obligations",
                "/kit implementation-legible",
                "main_module_boundary",
                "integration_contracts",
                "data_contracts",
                "runtime_profile",
                "gate_expectations",
                "what this REQ builds now",
                "what this REQ intentionally defers",
                "what downstream REQs may assume",
            ],
        )

    def test_bmad_plan_workflow_mentions_core_req_obligations(self) -> None:
        content = _read("orchestrator/methodologies/bmad/workflows/plan.md")

        self.assert_contains_all(
            content,
            [
                "Functional Scope",
                "Non-Functional Requirements",
                "Security Requirements",
                "TECH_CONSTRAINTS obligations",
                "/kit",
                "implementation-legible",
                "main module boundary",
                "integration_contracts",
                "data_contracts",
                "runtime_profile",
                "gate_expectations",
                "what this REQ builds now",
                "what this REQ intentionally defers",
                "what downstream REQs may assume",
            ],
        )


if __name__ == "__main__":
    unittest.main()
