"""Recorded methodology contexts (contract fixtures) for gateway tests.

The Orchestrator owns methodology resolution. Gateway tests must not import
Orchestrator code, so they consume contexts recorded from the Orchestrator
resolver under ``fixtures/methodology_contexts/``. The Orchestrator test
``test_gateway_methodology_context_fixtures.py`` fails when these drift and
regenerates them with ``CLIKE_GOLDEN_UPDATE=1``.
"""

import copy
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "methodology_contexts"


def fixture_path(*, phase: str, methodology: str, agent: str) -> Path:
    return FIXTURE_DIR / f"{methodology}__{phase}__{agent}.json"


def resolve_methodology_context(*, phase: str, methodology: str, agent: str) -> dict:
    path = fixture_path(phase=phase, methodology=methodology, agent=agent)
    if not path.exists():
        raise FileNotFoundError(
            f"No recorded methodology context for {methodology}/{phase}/{agent}: add the combination to "
            "orchestrator/tests/test_gateway_methodology_context_fixtures.py and run it with CLIKE_GOLDEN_UPDATE=1"
        )
    return copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
