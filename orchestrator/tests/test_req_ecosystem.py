"""KIT ecosystem detection (B19): declared technology constraints decide, keywords are whole words."""

import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.harper import _detect_req_ecosystem  # noqa: E402

PY_TC = {"TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n  framework: fastapi\n"}
MULTI_TC = {"TECH_CONSTRAINTS.yaml": (
    "tech_constraints:\n  backend:\n    runtime: python\n    framework: fastapi\n"
    "  frontend:\n    language: javascript\n    framework: none\n")}
PROSE = "The status expression is reactive; failures are expressed on the page; nodes are listed."


def test_declared_python_wins_over_misleading_prose():
    # baseline run: "expression"/"reactive"/"nodes" made a FastAPI project produce .js paths
    assert _detect_req_ecosystem(PY_TC, "", PROSE) == (True, False)


def test_several_execution_areas_follow_the_req_lane():
    assert _detect_req_ecosystem(MULTI_TC, "python", "") == (True, False)
    assert _detect_req_ecosystem(MULTI_TC, "frontend", "") == (False, True)


def test_without_constraints_keywords_are_whole_words():
    assert _detect_req_ecosystem({}, "", PROSE) == (False, False)
    assert _detect_req_ecosystem({}, "", "Use FastAPI and pytest") == (True, False)
    assert _detect_req_ecosystem({}, "", "An Express API with React") == (False, True)
    assert _detect_req_ecosystem({}, "python", "") == (True, False)
