import unittest

from services.methodologies.errors import (
    MethodologyPhaseAgentError,
    MissingMethodologyError,
    UnsupportedMethodologyAgentError,
    UnsupportedMethodologyError,
)
from services.methodologies.resolver import resolve_methodology_context


class MethodologyResolverTests(unittest.TestCase):
    def test_bmad_default_agent_resolution_per_phase(self):
        cases = [
            ("idea", "analyst"),
            ("spec", "pm"),
            ("plan", "architect"),
            ("kit", "developer"),
            ("eval", "qa"),
            ("finalize", "tech-writer"),
        ]

        for phase, expected_agent in cases:
            with self.subTest(phase=phase):
                context = resolve_methodology_context(phase=phase, methodology="bmad")

                self.assertEqual(context["methodology"], "bmad")
                self.assertEqual(context["phase"], phase)
                self.assertEqual(context["agent"], expected_agent)
                self.assertEqual(context["default_agent"], expected_agent)
                self.assertIn("workflow_summary", context)
                self.assertIsInstance(context["workflow_focus"], list)
                self.assertIsInstance(context["required_context"], list)
                self.assertIsInstance(context["companion_artifacts"], list)
                self.assertIsInstance(context["governance_boundaries"], list)

    def test_bmad_explicit_agent_resolution(self):
        context = resolve_methodology_context(
            phase="plan",
            methodology="bmad",
            agent="pm",
        )

        self.assertEqual(context["agent"], "pm")
        self.assertEqual(context["requested_agent"], "pm")
        self.assertEqual(context["allowed_agents"], ["architect", "pm"])

    def test_allowed_explicit_roles_per_phase(self):
        cases = [
            ("idea", "analyst"),
            ("spec", "pm"),
            ("spec", "ux"),
            ("plan", "architect"),
            ("plan", "pm"),
            ("kit", "developer"),
            ("eval", "qa"),
            ("eval", "developer"),
            ("finalize", "tech-writer"),
        ]

        for phase, agent in cases:
            with self.subTest(phase=phase, agent=agent):
                context = resolve_methodology_context(
                    phase=phase,
                    methodology="bmad",
                    agent=agent,
                )

                self.assertEqual(context["agent"], agent)
                self.assertIn(agent, context["allowed_agents"])

    def test_phase_agent_allowances_match_bmad_profile(self):
        self.assertEqual(
            resolve_methodology_context(phase="idea", methodology="bmad")["agent"],
            "analyst",
        )
        self.assertEqual(
            resolve_methodology_context(phase="spec", methodology="bmad", agent="ux")["agent"],
            "ux",
        )
        self.assertEqual(
            resolve_methodology_context(phase="plan", methodology="bmad", agent="pm")["agent"],
            "pm",
        )
        self.assertEqual(
            resolve_methodology_context(phase="kit", methodology="bmad")["agent"],
            "developer",
        )
        self.assertEqual(
            resolve_methodology_context(phase="finalize", methodology="bmad")["agent"],
            "tech-writer",
        )

    def test_plan_workflow_metadata_is_implementation_legible(self):
        context = resolve_methodology_context(phase="plan", methodology="bmad")
        focus_text = " ".join(context["workflow_focus"]).lower()

        self.assertIn("functional", focus_text)
        self.assertIn("security", focus_text)
        self.assertIn("integration", focus_text)
        self.assertIn("data contracts", focus_text)
        self.assertIn("what later reqs may assume", focus_text)
        self.assertIn("TECH_CONSTRAINTS.yaml", context["required_context"])

    def test_workflow_metadata_and_governance_boundaries_exist(self):
        context = resolve_methodology_context(phase="kit", methodology="bmad")

        self.assertIn("workflow_summary", context)
        self.assertTrue(context["workflow_summary"])
        self.assertGreaterEqual(len(context["workflow_focus"]), 1)
        self.assertGreaterEqual(len(context["required_context"]), 1)
        self.assertGreaterEqual(len(context["companion_artifacts"]), 1)
        self.assertGreaterEqual(len(context["governance_boundaries"]), 1)
        boundaries = " ".join(context["governance_boundaries"]).lower()
        self.assertIn("allowed_write_roots", boundaries)
        self.assertIn("forbidden_paths", boundaries)
        self.assertIn("eval/gate", boundaries)

    def test_agent_without_methodology_is_rejected(self):
        with self.assertRaisesRegex(MissingMethodologyError, "--agent requires --methodology"):
            resolve_methodology_context(phase="kit", agent="developer")

    def test_invalid_methodology_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedMethodologyError, "Unsupported methodology: scrum"):
            resolve_methodology_context(phase="spec", methodology="scrum")

    def test_invalid_bmad_agent_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedMethodologyAgentError, "Unsupported BMAD agent: coach"):
            resolve_methodology_context(phase="spec", methodology="bmad", agent="coach")

    def test_invalid_phase_agent_mapping_is_rejected(self):
        with self.assertRaisesRegex(MethodologyPhaseAgentError, "not allowed for phase 'kit'"):
            resolve_methodology_context(phase="kit", methodology="bmad", agent="architect")

    def test_eval_is_advisory_only(self):
        context = resolve_methodology_context(phase="eval", methodology="bmad")

        self.assertEqual(context["agent"], "qa")
        self.assertIs(context["advisory_only"], True)
        self.assertEqual(context["authority"], "advisory")

    def test_gate_has_no_bmad_authority_context(self):
        context = resolve_methodology_context(phase="gate", methodology="bmad")

        self.assertIsNone(context["agent"])
        self.assertEqual(context["allowed_agents"], [])
        self.assertIsNone(context["default_agent"])
        self.assertIs(context["advisory_only"], False)
        self.assertEqual(context["authority"], "clike_only")

    def test_gate_rejects_explicit_bmad_agent(self):
        with self.assertRaisesRegex(MethodologyPhaseAgentError, "Gate remains CLike-only"):
            resolve_methodology_context(phase="gate", methodology="bmad", agent="qa")


if __name__ == "__main__":
    unittest.main()
