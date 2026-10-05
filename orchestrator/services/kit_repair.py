"""Auto-eval KIT repair (roadmap §3): the rules the model follows, shared by the cloud prompt and
the local-agent package so both paths repair under the same governance (enforced by
services.gate_integrity.amend_acceptance_surface)."""

from __future__ import annotations

from typing import Any, Dict, List

_OUTPUT_TAIL = 4000


def repair_rules(req_id: str) -> List[str]:
    return [
        f"Tests under runs/kit/{req_id}/test/ are locked acceptance criteria: make the code pass them; never edit, skip or weaken them. Exceptions: (a) you may remove an unused import from a test file when lint fails on it; (b) when a failed check shows the TEST itself is wrong (an error raised in the test file such as TypeError/AttributeError/NameError/ImportError from a wrong API call, import or fixture, not a failed assertion), fix the test, not the code: keep every test function, every assert and every pytest.raises/approx identical and add no skip/xfail.",
        f"runs/kit/{req_id}/ci/LTC.json: you may only fix the command of a check that cannot run (wrong path, module or flag). Never remove a check or make it non-blocking.",
        f"Vulnerable dependencies: upgrade the affected packages in runs/kit/{req_id}/ci/requirements.txt (or the ecosystem manifest) to current versions without known vulnerabilities.",
        f"A failure caused by the environment (network, missing system tool) is not fixed by changing code: explain it in runs/kit/{req_id}/docs/KIT_{req_id}.md.",
        "Fix the root cause in the source; do not special-case the tests.",
    ]


def repair_failures(repair: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The failed checks of a repair request, normalized (output tail bounded)."""
    out = []
    for item in repair.get("failures") or []:
        if isinstance(item, dict):
            out.append({
                "name": str(item.get("name") or "check"),
                "code": item.get("code"),
                "command": str(item.get("command") or ""),
                "output": str(item.get("output") or "")[-_OUTPUT_TAIL:],
            })
    return out
