"""Cloud vs local-agent equivalence per phase (WP8.9).

For each phase, the cloud path (active output contract used to compose the prompt and validate the
model output) and the local-agent path (contract + package handed to Claude Code / Codex) must ask
for the same outputs. Where they already agree the test requires equality; where they diverge
today the divergence is recorded below and pinned, so any new drift fails and reconciling a phase
means deleting its entry (post-WP improvement round, see the private WP8 report §8).
"""

import json
import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.cloud_prompt.active_output_contract import build_active_output_contract as cloud_contract  # noqa: E402
from services.local_agent_package import _DOCUMENT_PHASE_SPECS, _path_accepted  # noqa: E402
from services.methodologies.active_output_contract import build_active_output_contract as local_contract  # noqa: E402

SNAPSHOTS = ORCHESTRATOR_ROOT / "tests/golden/snapshots"
REQ = "REQ-001"

# phase -> (cloud required outputs, local-agent required outputs). Only the eval differs on purpose:
# the local eval is an advisory pre-pass that writes repair notes; the canonical eval is deterministic.
KNOWN_DIVERGENCES = {
    "eval": ([], [f"runs/kit/{REQ}/reports/BMAD_EVAL_REPAIR_NOTES.md"]),
}


def _required(phase):
    cloud = cloud_contract(phase=phase, runner="cloud", methodology_context=None, req_id=REQ, file_requirements=None)
    local = local_contract(phase=phase, runner="local_agent", methodology_context=None, req_id=REQ)
    return list(cloud.get("required_outputs") or []), list(local.get("required_outputs") or [])


def _local_package(phase):
    data = json.loads((SNAPSHOTS / f"{phase}__local__native.json").read_text(encoding="utf-8"))
    return data["output"]["local_agent"]


def test_document_phases_ask_for_the_same_outputs_on_both_paths():
    for phase in ("idea", "spec", "plan"):
        cloud, local = _required(phase)
        assert cloud == local, phase
        package = _local_package(phase)
        always = package["expected_outputs"]["always"]
        assert always == _DOCUMENT_PHASE_SPECS[phase]["output_contract"]["always"]
        # every concrete required output is writable by the agent and accepted back by the orchestrator
        for path in always:
            assert any(path == root or path.startswith(root.rstrip("/") + "/") for root in package["allowed_write_roots"]), path
            assert _path_accepted(phase, path), path


def test_known_divergences_are_pinned():
    for phase, expected in KNOWN_DIVERGENCES.items():
        assert _required(phase) == expected, f"{phase}: cloud/agent outputs changed; update or reconcile"


def test_kit_asks_the_agent_for_every_cloud_deliverable():
    cloud, local = _required("kit")
    assert cloud and set(cloud) <= set(local), set(cloud) - set(local)
    # the agent also gets its candidate roots (it writes them directly)
    assert {f"runs/kit/{REQ}/src/**", f"runs/kit/{REQ}/test/**", f"runs/kit/{REQ}/ci/**"} <= set(local)


def test_phases_without_a_divergence_entry_are_equivalent():
    for phase in ("idea", "spec", "plan", "extend", "finalize"):
        assert phase not in KNOWN_DIVERGENCES
        cloud, local = _required(phase)
        assert cloud == local, phase
