import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.quality_scorecard import (
    parse_markdown_sections,
    score_idea_markdown,
)


NATIVE_SOURCE = REPO_ROOT / "CoffeeBuddy" / "IDEA_cb_clike.md"
BMAD_SOURCE_CANDIDATES = [
    REPO_ROOT / "CoffeeBuddy" / "IDEA_withBMAD.md",
    REPO_ROOT / "CoffeeBuddy" / "IDEA_withBMAD.md.md",
]
NATIVE_FIXTURE = REPO_ROOT / "orchestrator" / "tests" / "fixtures" / "native" / "IDEA.md"
BMAD_FIXTURE = REPO_ROOT / "orchestrator" / "tests" / "fixtures" / "bmad_experimental" / "IDEA.md"


def _bmad_source() -> Path:
    for path in BMAD_SOURCE_CANDIDATES:
        if path.exists():
            return path
    raise AssertionError(
        "BMAD fixture source is missing. Expected CoffeeBuddy/IDEA_withBMAD.md "
        "or repository-provided CoffeeBuddy/IDEA_withBMAD.md.md."
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class BmadQualityScorecardFixtureTests(unittest.TestCase):
    def test_fixture_sources_and_copied_fixtures_exist_and_match(self):
        self.assertTrue(
            NATIVE_SOURCE.exists(),
            "Native fixture source is missing: CoffeeBuddy/IDEA_cb_clike.md",
        )
        bmad_source = _bmad_source()
        self.assertTrue(NATIVE_FIXTURE.exists(), "Native copied fixture is missing.")
        self.assertTrue(BMAD_FIXTURE.exists(), "BMAD copied fixture is missing.")
        self.assertEqual(_read(NATIVE_FIXTURE), _read(NATIVE_SOURCE))
        self.assertEqual(_read(BMAD_FIXTURE), _read(bmad_source))

    def test_both_fixtures_parse_as_markdown_sections(self):
        native_sections = parse_markdown_sections(_read(NATIVE_FIXTURE))
        bmad_sections = parse_markdown_sections(_read(BMAD_FIXTURE))

        self.assertGreaterEqual(len(native_sections), 6)
        self.assertGreater(len(bmad_sections), len(native_sections))
        self.assertEqual(native_sections[0]["title"], "IDEA — CoffeeBuddy")
        self.assertEqual(bmad_sections[0]["title"], "IDEA — CoffeeBuddy")

    def test_bmad_experimental_fixture_scores_higher_than_native(self):
        native_score = score_idea_markdown(_read(NATIVE_FIXTURE))
        bmad_score = score_idea_markdown(_read(BMAD_FIXTURE))

        self.assertIsInstance(native_score["score"], float)
        self.assertIsInstance(bmad_score["score"], float)
        self.assertGreater(bmad_score["score"], native_score["score"])
        self.assertGreater(bmad_score["normalized_score"], native_score["normalized_score"])
        self.assertIn("missing", native_score)
        self.assertIn("improvement_notes", native_score)
        self.assertIsInstance(native_score["improvement_notes"], list)
        self.assertIsInstance(bmad_score["improvement_notes"], list)

    def test_bmad_fixture_contains_handoff_readiness_section(self):
        bmad_text = _read(BMAD_FIXTURE)

        self.assertIn("/spec Handoff Readiness", bmad_text)

    def test_native_fixture_lacks_some_high_fidelity_sections(self):
        native_text = _read(NATIVE_FIXTURE)

        missing_sections = [
            "/spec Handoff Readiness",
            "Deployment Portability Rule",
            "Technology Constraints (SPEC-ready)",
        ]
        self.assertGreaterEqual(
            sum(1 for marker in missing_sections if marker not in native_text),
            2,
        )

    def test_scorecard_returns_dimension_notes_for_shallow_native_fixture(self):
        native_score = score_idea_markdown(_read(NATIVE_FIXTURE))
        dimension_names = {item["name"] for item in native_score["dimensions"]}

        self.assertIn("deployment_portability", dimension_names)
        self.assertIn("downstream_handoff_readiness", dimension_names)
        self.assertIn("traceability_source_references", dimension_names)
        self.assertIn("downstream_handoff_readiness", native_score["missing"])
        self.assertIn("technology_constraints_richness", native_score["missing"])
        self.assertTrue(
            any("handoff" in note.lower() for note in native_score["improvement_notes"])
        )
        self.assertIn("does not prove live model quality", native_score["notes"])


if __name__ == "__main__":
    unittest.main()
