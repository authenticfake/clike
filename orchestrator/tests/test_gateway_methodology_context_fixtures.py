"""Keep the Gateway's recorded methodology contexts in sync with the resolver.

Gateway tests consume contexts recorded under
``gateway/tests/fixtures/methodology_contexts/`` instead of importing
Orchestrator code. This test owns that contract: it fails when the resolver
output drifts from the recorded fixtures.

Regenerate after an intended resolver change with::

    CLIKE_GOLDEN_UPDATE=1 pytest orchestrator/tests/test_gateway_methodology_context_fixtures.py -q
"""

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.resolver import resolve_methodology_context  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "gateway/tests/fixtures/methodology_contexts"
UPDATE = os.getenv("CLIKE_GOLDEN_UPDATE") == "1"

# (phase, agent) combinations used by gateway tests.
BMAD_COMBINATIONS = [
    ("idea", "analyst"),
    ("spec", "pm"),
    ("spec", "ux"),
    ("plan", "architect"),
    ("plan", "pm"),
    ("kit", "developer"),
    ("eval", "qa"),
    ("finalize", "tech-writer"),
]


def _render(context: dict) -> str:
    return json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class GatewayMethodologyContextFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_recorded_contexts_match_resolver(self):
        for phase, agent in BMAD_COMBINATIONS:
            path = FIXTURE_DIR / f"bmad__{phase}__{agent}.json"
            with self.subTest(path.name):
                rendered = _render(resolve_methodology_context(phase=phase, methodology="bmad", agent=agent))
                if UPDATE:
                    path.write_text(rendered, encoding="utf-8")
                    continue
                self.assertTrue(path.exists(), f"missing fixture {path.name}; run with CLIKE_GOLDEN_UPDATE=1")
                self.assertEqual(path.read_text(encoding="utf-8"), rendered, f"methodology context drift: {path.name}")

    def test_no_orphan_fixtures(self):
        expected = {f"bmad__{phase}__{agent}.json" for phase, agent in BMAD_COMBINATIONS}
        actual = {p.name for p in FIXTURE_DIR.glob("*.json")}
        self.assertEqual(actual - expected, set(), "fixtures without a resolver combination")


if __name__ == "__main__":
    unittest.main()
