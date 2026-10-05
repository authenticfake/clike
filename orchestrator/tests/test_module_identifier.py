"""Module family from plan fields (B18): identifiers or paths only, never free text."""

import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.harper import _module_identifier  # noqa: E402


def test_prose_yields_the_module_identifier_not_a_directory_name():
    # benchmark baseline: this sentence became runs/kit/REQ-001/src/pingboard.health owns .../implementation.js
    text = ("pingboard.health owns configuration, canonical data, checking, snapshot publication, and status reads; "
            "pingboard.app is the shared composition root")
    assert _module_identifier(text) == "pingboard.health"


def test_identifiers_and_paths_are_kept():
    assert _module_identifier("coffeebuddy.runtime") == "coffeebuddy.runtime"
    assert _module_identifier("src/coffeebuddy/runtime") == "src/coffeebuddy/runtime"
    assert _module_identifier("`orders`") == "orders"


def test_prose_without_an_identifier_yields_nothing():
    assert _module_identifier("the order intake area of the backend") == ""
    assert _module_identifier(None) == ""
