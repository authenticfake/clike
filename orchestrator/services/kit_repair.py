"""KIT rules shared by the cloud prompt and the local-agent package, so both paths work under the
same governance (enforced by services.gate_integrity.amend_acceptance_surface): the auto-eval
repair (roadmap §3) and the acceptance-first KIT (tests written and locked before the code)."""

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


def acceptance_stage_rules(req_id: str) -> List[str]:
    return [
        f"This call writes ONLY the acceptance surface of {req_id}. The implementation is written later by a separate KIT call that cannot change these files.",
        f"Output only: acceptance tests under runs/kit/{req_id}/test/, runs/kit/{req_id}/ci/LTC.json, runs/kit/{req_id}/ci/HOWTO.md, the test-runtime manifest and CI runner scripts under runs/kit/{req_id}/ci/, and runs/kit/{req_id}/docs/ACCEPTANCE_{req_id}.md. Do NOT write src/: it is dropped.",
        "Derive the tests from the REQ's acceptance criteria, test strategy and contracts (plan.json, PLAN.md) and from SPEC.md, not from an imagined implementation.",
        "Test the public boundary the plan and FILE_REQUIREMENTS declare (module paths, function/endpoint names, data contracts) and import from exactly those paths, so an implementation can satisfy the tests. Do not test private helpers.",
        f"Map every acceptance criterion to at least one test; docs/ACCEPTANCE_{req_id}.md is a table: criterion | test id(s) | LTC check.",
        "Tests must be deterministic, offline (local servers, fakes), bounded in time (timeouts on network calls and servers, every started process stopped) and use only real APIs of the declared libraries and versions.",
        "The LTC runs in the eval sandbox against the composed workspace, as the KIT rules describe; its blocking checks are the promotion criteria.",
    ]


def acceptance_stage_section(req_id: str) -> str:
    lines = ["## ACCEPTANCE STAGE — tests first", ""]
    lines += [f"- {rule}" for rule in acceptance_stage_rules(req_id)]
    return "\n".join(lines)


def acceptance_first_code_rules(req_id: str) -> List[str]:
    return [
        f"The acceptance tests and eval profile of {req_id} were written first and are LOCKED (they are listed below and provided as candidate:: files).",
        f"Write the implementation under runs/kit/{req_id}/src/, the docs (README_{req_id}.md, KIT_{req_id}.md) and the runtime dependencies needed to pass them; you may add runtime packages to runs/kit/{req_id}/ci/requirements.txt (or the ecosystem manifest).",
        f"Do not output files under runs/kit/{req_id}/test/, nor ci/LTC.json or ci/HOWTO.md: they are locked and such outputs are rejected.",
        "Match exactly the module paths, names, signatures and behaviour the tests import and assert.",
        f"If a locked test cannot be satisfied (it contradicts SPEC or another test), implement the rest and explain why in docs/KIT_{req_id}.md.",
    ]


def acceptance_first_code_section(req_id: str, locked_files: List[str]) -> str:
    lines = ["## ACCEPTANCE-FIRST — implement against the locked tests", ""]
    lines += [f"- {rule}" for rule in acceptance_first_code_rules(req_id)]
    if locked_files:
        lines += ["", "Locked files:"] + [f"- {path}" for path in locked_files]
    return "\n".join(lines)


def kit_self_check_rules(req_id: str) -> List[str]:
    """Final checks before answering, one per failure class measured with the Harper benchmark
    (any language: they refer to the checks the KIT's own LTC runs)."""
    return [
        "Every file you write, tests included, passes the lint, format, type and security checks your LTC runs, with their configured rules (import order and grouping, unused imports and variables, line length, types).",
        "When a test asserts something about a file you also write (forbidden words, required keys or sections, its location), re-read that whole file against the assertion, comments included.",
        "Tests assert observable behaviour required by SPEC and the acceptance criteria (results, status codes, persisted state, emitted events, logs), not incidental internals (how many objects are created or closed, private attributes, call order) unless the SPEC requires them.",
        "Use only APIs that exist in the library versions you pin; when unsure, prefer the documented generic form (e.g. a test client's request(method, url, ...) rather than a convenience method with an unusual argument).",
        "Every test is bounded in time: timeouts on network calls and waits, servers, processes and tasks stopped in teardown, no fixed sleeps.",
        f"Checks run in a sandbox where the project root is read-only: write reports, coverage, caches and temporary files only under CLIKE_EVAL_REPORT_DIR / CLIKE_EVAL_TEMP_ROOT, and make the LTC commands work from their declared cwd.",
    ]


def kit_self_check_section(req_id: str) -> str:
    lines = ["## Before you answer — eval-readiness self-check", ""]
    lines += [f"- {rule}" for rule in kit_self_check_rules(req_id)]
    return "\n".join(lines)
