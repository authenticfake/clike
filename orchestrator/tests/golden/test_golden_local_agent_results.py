"""Golden snapshots of local-agent result normalization (WP8.0 characterization).

``POST /v1/harper/local-agent/complete`` → ``normalize_local_agent_result`` decides which files a
local agent produced are kept, which errors and warnings are raised, and how plan.json is
enriched. The request is built exactly like the extension does (extension.js, completeBody): the
policy fields come from the phase package in the phase golden snapshots, the files from the agent.

Regenerate after an *intended* change with ``CLIKE_GOLDEN_UPDATE=1`` and review the diff.
"""

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.local_agent_package import normalize_local_agent_result  # noqa: E402

TESTS_ROOT = ORCHESTRATOR_ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))
# documents that meet the quality bar, shared with the unit tests
import test_extend_local_agent_package as extend_fx  # noqa: E402
import test_normalize_local_agent_result_document_phase as doc_fx  # noqa: E402

GOLDEN = Path(__file__).resolve().parent
PHASE_SNAPSHOTS = GOLDEN / "snapshots"
SNAPSHOT_DIR = GOLDEN / "snapshots_local_results"
UPDATE = os.getenv("CLIKE_GOLDEN_UPDATE") == "1"
COFFEEBUDDY = REPO_ROOT / "CoffeeBuddy"
REQ = "REQ-001"

PLAN_MD = """# PLAN — CoffeeBuddy

## Plan Snapshot
Two REQs on the python lane.

| REQ | Title | Lane |
|---|---|---|
| REQ-001 | Coffee order intake | python |
| REQ-002 | Order status notifications | python |
"""

PLAN_JSON = {
    "snapshot": {"project": "CoffeeBuddy"},
    "lanes": [{"id": "python"}],
    "reqs": [
        {"id": "REQ-001", "title": "Coffee order intake", "acceptance": ["Orders can be created"], "lane": "python",
         "dependsOn": [], "skills": ["api-hardening"], "packs": ["python-service"], "design_profiles": ["not_applicable"]},
        {"id": "REQ-002", "title": "Order status notifications", "acceptance": ["Status changes notify"], "lane": "python",
         "dependsOn": ["REQ-001"]},
    ],
}


def _package(snapshot_name: str) -> dict:
    data = json.loads((PHASE_SNAPSHOTS / f"{snapshot_name}.json").read_text(encoding="utf-8"))
    return ((data.get("output") or {}).get("local_agent")) or {}


def _request(phase: str, package_snapshot: str, files: list, *, exit_code: int = 0, stdout: str = "", stderr: str = "", req_id=None) -> dict:
    pkg = _package(package_snapshot)
    return {
        "phase": phase,
        "req_id": req_id,
        "runId": f"golden-{phase}",
        "executionPreference": "local_agent_only",
        "localAgentExecutor": "claude_code",
        "allowed_write_roots": pkg.get("allowed_write_roots") or [],
        "forbidden_paths": pkg.get("forbidden_paths") or [],
        "infra_profile": pkg.get("infra_profile"),
        "runtime_service_profile": pkg.get("runtime_service_profile"),
        "cloud_provisioning_profile": pkg.get("cloud_provisioning_profile"),
        "available_capabilities": pkg.get("available_capabilities"),
        "capability_metadata": pkg.get("capability_metadata"),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "files": files,
    }


def _f(path: str, content: str) -> dict:
    return {"path": path, "content": content}


def _scenarios():
    idea = (COFFEEBUDDY / "IDEA.md").read_text(encoding="utf-8")
    spec = (COFFEEBUDDY / "SPEC.md").read_text(encoding="utf-8")
    plan_json = json.dumps(PLAN_JSON, indent=2)
    kit_files = [
        _f(f"runs/kit/{REQ}/src/coffee/orders.py", "def create_order(item):\n    return {'item': item}\n"),
        _f(f"runs/kit/{REQ}/test/test_orders.py", "from coffee.orders import create_order\n\ndef test_create():\n    assert create_order('x')\n"),
        _f(f"runs/kit/{REQ}/ci/LTC.json", json.dumps({"req_id": REQ, "checks": [{"id": "unit", "command": "pytest -q", "blocking": True}]})),
        _f(f"runs/kit/{REQ}/ci/HOWTO.md", "# HOWTO\n\nRun `pytest -q` from the KIT root.\n"),
        _f(f"runs/kit/{REQ}/ci/requirements.txt", "pytest\n"),
    ]
    extend_doc = "docs/harper/EXTEND_2026-10-04_REQ-003_REQ-003.md"
    return [
        ("idea__valid", _request("idea", "idea__local__native", [_f("docs/harper/IDEA.md", doc_fx.VALID_IDEA)])),
        ("spec__valid", _request("spec", "spec__local__native", [_f("docs/harper/SPEC.md", doc_fx.VALID_SPEC)])),
        ("plan__valid", _request("plan", "plan__local__native", [
            _f("docs/harper/PLAN.md", doc_fx.VALID_PLAN_MD), _f("docs/harper/plan.json", doc_fx.VALID_PLAN_JSON),
            _f("docs/harper/lane-guides/backend.md", doc_fx.VALID_LANE)])),
        ("extend__valid", _request("extend", "extend__local__native", [
            _f("docs/harper/PLAN.md", extend_fx.VALID_PLAN_MD), _f("docs/harper/plan.json", extend_fx.VALID_PLAN_JSON),
            _f("docs/harper/EXTEND_2026-10-04_REQ-2_REQ-2.md", extend_fx.AUDIT)])),
        ("idea__coffeebuddy", _request("idea", "idea__local__native", [_f("docs/harper/IDEA.md", idea)])),
        ("idea__no_output", _request("idea", "idea__local__native", [])),
        ("idea__forbidden_write", _request("idea", "idea__local__native", [_f("docs/harper/IDEA.md", idea), _f("src/app.py", "print('x')\n")])),
        ("spec__coffeebuddy", _request("spec", "spec__local__native", [_f("docs/harper/SPEC.md", spec)])),
        ("spec__too_thin", _request("spec", "spec__local__native", [_f("docs/harper/SPEC.md", "# SPEC\n\nTBD\n")])),
        ("plan__no_checkpoints", _request("plan", "plan__local__native", [
            _f("docs/harper/PLAN.md", PLAN_MD), _f("docs/harper/plan.json", plan_json),
            _f("docs/harper/lane-guides/python.md", "# Lane guide — python\n\nUse pytest.\n")])),
        ("plan__capabilities", _request("plan", "plan__local__native__repo", [
            _f("docs/harper/PLAN.md", PLAN_MD), _f("docs/harper/plan.json", plan_json)])),
        ("plan__missing_plan_json", _request("plan", "plan__local__native", [_f("docs/harper/PLAN.md", PLAN_MD)])),
        ("kit__valid", _request("kit", "kit__local__native", kit_files, req_id=REQ)),
        ("kit__agent_failed", _request("kit", "kit__local__native", kit_files[:1], exit_code=1, stderr="Error: tool call failed", req_id=REQ)),
        ("kit__outside_roots", _request("kit", "kit__local__native", kit_files + [_f("docs/harper/SPEC.md", spec)], req_id=REQ)),
        ("eval__valid", _request("eval", "eval__local__native", kit_files[2:4] + [
            _f(f"runs/kit/{REQ}/reports/eval_notes.md", "# Eval notes\n\nAll checks pass locally.\n")], req_id=REQ)),
        ("finalize__minimal", _request("finalize", "finalize__local__native", [
            _f("README.md", "# CoffeeBuddy\n\nRun `make dev`.\n"), _f("scripts/dev.sh", "#!/bin/sh\nuvicorn app:app\n")])),
        ("finalize__cloud_profiles", _request("finalize", "finalize__local__native__cloudinfra", [
            _f("README.md", "# CoffeeBuddy\n\nDeploy with terraform.\n"), _f("infra/main.tf", "provider \"aws\" {}\n")])),
        ("extend__incomplete_audit", _request("extend", "extend__local__native", [
            _f("docs/harper/PLAN.md", PLAN_MD), _f("docs/harper/plan.json", plan_json),
            _f(extend_doc, "# EXTEND — REQ-003\n\n## Change Summary\nLoyalty points.\n")])),
        ("extend__forbidden_write", _request("extend", "extend__local__native", [
            _f("docs/harper/PLAN.md", PLAN_MD), _f(f"runs/kit/{REQ}/src/x.py", "x = 1\n")])),
    ]


class GoldenLocalAgentResultTests(unittest.TestCase):
    maxDiff = None

    def test_local_agent_result_snapshots(self):
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        for name, request in _scenarios():
            with self.subTest(name):
                try:
                    actual = {"output": normalize_local_agent_result(json.loads(json.dumps(request)))}
                except Exception as exc:  # failure modes are part of the contract
                    actual = {"exception": {"type": type(exc).__name__, "message": str(exc)}}
                rendered = json.dumps({"request": request, **actual}, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
                snap = SNAPSHOT_DIR / f"{name}.json"
                if UPDATE:
                    snap.write_text(rendered, encoding="utf-8")
                    continue
                self.assertTrue(snap.exists(), f"missing snapshot {snap.name}; run with CLIKE_GOLDEN_UPDATE=1")
                self.assertEqual(snap.read_text(encoding="utf-8"), rendered, f"golden drift: {name}")


if __name__ == "__main__":
    unittest.main()
