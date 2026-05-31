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

    def test_bmad_explicit_agent_resolution(self):
        context = resolve_methodology_context(
            phase="plan",
            methodology="bmad",
            agent="pm",
        )

        self.assertEqual(context["agent"], "pm")
        self.assertEqual(context["requested_agent"], "pm")
        self.assertEqual(context["allowed_agents"], ["architect", "pm"])

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
