"""KIT core-blob filter keeps lane guides (B3) and the selected capability context (B4)."""

import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.harper import _filter_core_blobs_for_target_req  # noqa: E402


def test_lane_guides_and_selected_capability_context_survive_the_filter():
    blobs = {
        "SPEC.md": "s", "plan.json": "{}",
        "docs/harper/lane-guides/python.md": "# Lane guide",
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": "# selected", "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": "{}",
        "docs/harper/random-notes.md": "not normative",
    }
    kept = _filter_core_blobs_for_target_req(blobs, "REQ-001")
    assert "docs/harper/lane-guides/python.md" in kept
    assert "CLIKE_SELECTED_CAPABILITY_CONTEXT.md" in kept and "CLIKE_SELECTED_CAPABILITY_CONTEXT.json" in kept
    assert "docs/harper/random-notes.md" not in kept
