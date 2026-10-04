"""Golden snapshots of the Orchestrator phase boundary (WP0.4).

For every Harper phase and executor mode this freezes what ``run_phase``
emits across its outbound boundary:

* cloud: every payload posted to the Gateway (``_post_json``), in order;
* local agent: the execution package returned to the extension.

Exceptions are part of the contract too and are snapshotted as such.

Regenerate after an *intended* change with::

    CLIKE_GOLDEN_UPDATE=1 pytest orchestrator/tests/golden -q

and review the snapshot diff before committing.
"""

import asyncio
import copy
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services import harper  # noqa: E402

SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"
UPDATE = os.getenv("CLIKE_GOLDEN_UPDATE") == "1"
COFFEEBUDDY = REPO_ROOT / "CoffeeBuddy"
BMAD_VENDOR_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad"
# Synthetic, tracked `.clike` capabilities (never the template dir: it may hold untracked user skills).
CLIKE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "clike_workspace" / ".clike"

PHASES_CLOUD = ["idea", "spec", "plan", "kit", "eval", "finalize", "extend"]
PHASES_LOCAL = ["idea", "spec", "plan", "kit", "eval", "finalize", "extend"]


def _bmad_vendor_core_blobs():
    blobs = {".clike/skills/vendor/bmad/manifest.json": (BMAD_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")}
    for path in sorted(BMAD_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _plan_json(select_capabilities: bool = False):
    plan = {
        "reqs": [
            {
                "id": "REQ-001",
                "title": "Coffee order intake",
                "acceptance": ["Orders can be created", "Invalid orders are rejected"],
                "lane": "python",
                "dependsOn": [],
            },
            {
                "id": "REQ-002",
                "title": "Order status notifications",
                "acceptance": ["Status changes notify the requester"],
                "lane": "python",
                "dependsOn": ["REQ-001"],
            },
        ]
    }
    if select_capabilities:
        plan["reqs"][0].update({"packs": ["python-service"], "skills": ["api-hardening"], "design_profiles": ["minimal"]})
    return plan


def _base_payload(phase: str, workspace: Path, methodology: str | None, variant: str = "") -> dict:
    idea = (COFFEEBUDDY / "IDEA.md").read_text(encoding="utf-8")
    spec = (COFFEEBUDDY / "SPEC.md").read_text(encoding="utf-8")
    core_blobs = {
        "IDEA.md": idea,
        "SPEC.md": spec,
        "PLAN.md": "# PLAN — CoffeeBuddy\n\n| REQ | Title |\n|---|---|\n| REQ-001 | Coffee order intake |\n| REQ-002 | Order status notifications |\n",
        "plan.json": json.dumps(_plan_json(select_capabilities=variant == "repo")),
        "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n  framework: fastapi\n",
    }
    if methodology == "bmad":
        core_blobs.update(_bmad_vendor_core_blobs())
    payload = {
        "runId": "golden-run",
        "project_id": "coffeebuddy_golden",
        "project_name": "CoffeeBuddy",
        "cmd": phase,
        "phase": phase,
        "mode": "harper",
        "model": "openai:gpt-5.4-mini",
        "docRoot": "docs/harper",
        "messages": [{"role": "user", "content": f"/{phase} golden scenario"}],
        "core": ["IDEA.md", "SPEC.md", "PLAN.md", "plan.json"],
        "core_blobs": core_blobs,
        "attachments": [],
        "flags": {},
        "workspace": {"root": str(workspace)},
        "localAgentExecutor": "claude_code",
        "localAgentCapabilities": {},
    }
    if phase == "idea" and variant != "noattach":
        payload["attachments"] = [
            {"name": "IDEA.md", "path": "CoffeeBuddy/IDEA.md", "origin": "workspace", "mime": "text/markdown", "content": idea}
        ]
    if phase in {"kit", "eval", "finalize"}:
        payload["kit"] = {"targets": ["REQ-001"]}
        payload["todo_ids"] = ["REQ-001"]
    if phase == "kit" and variant in ("fullchain", "fullchain_files"):
        payload["kit"]["phases"] = ["kit", "integrity_eval", "promotion_hardener", "promotion_eval"]
    if phase == "eval":
        payload["eval"] = {"targets": ["REQ-001"]}
    if phase == "extend":
        payload["messages"] = [{"role": "user", "content": "/extend add loyalty points for frequent buyers"}]
    # --- WP8.0 characterization variants ---
    if variant == "repo":
        import shutil

        shutil.copytree(CLIKE_FIXTURE, workspace / ".clike")
        payload["repository_context"] = {"repo_root": str(workspace), "workspace_folder": str(workspace), "branch": "main", "git_detected": True}
    if variant == "codex":
        payload["localAgentExecutor"] = "gpt_codex"
    if variant == "repair":
        payload["kit"]["repair"] = True
    if variant == "audit":
        payload["includeAgentInputAudit"] = True
    if variant == "attach":
        payload["attachments"] = [
            {"name": "loyalty.md", "path": "notes/loyalty.md", "origin": "workspace", "mime": "text/markdown",
             "content": "# Loyalty\n\nFrequent buyers earn one free coffee every ten orders.\n"}
        ]
        payload["extend"] = {"fromAttachment": True}
    if variant == "contractblobs":
        core_blobs["TARGET_CONTRACT.json"] = json.dumps({"req_id": "REQ-001", "lane": "python", "acceptance": ["Orders can be created"]})
        core_blobs["FILE_REQUIREMENTS.json"] = json.dumps({"req_id": "REQ-001", "required_outputs": [{"role": "source", "path": "runs/kit/REQ-001/src/app.py"}]})
    if variant == "cloudinfra":
        core_blobs["TECH_CONSTRAINTS.yaml"] = (
            "tech_constraints:\n  runtime: python\n  framework: fastapi\n"
            "  deployment:\n    target: aws\n    services: [aws ecs, aws rds, aws secrets manager]\n    iac: terraform\n"
        )
    if methodology:
        payload["methodology"] = methodology
        payload["agent"] = {"idea": "analyst", "spec": "pm", "plan": "architect", "finalize": "tech-writer"}.get(phase, "developer")
    return payload


async def _fake_resolve_llm_selection(**kwargs):
    return {}


def _fake_gateway_response(payload, variant: str = ""):
    files = []
    if variant == "fullchain_files":
        # make the KIT chain run its later stages on real candidates (candidate:: blobs)
        phase = payload.get("phase")
        if phase == "kit":
            files = [
                {"path": "runs/kit/REQ-001/src/coffee/orders.py", "content": "def create_order(item):\n    return {'item': item}\n"},
                {"path": "runs/kit/REQ-001/test/test_orders.py", "content": "from coffee.orders import create_order\n\ndef test_create():\n    assert create_order('x')\n"},
                {"path": "runs/kit/REQ-001/ci/LTC.json", "content": '{"req_id": "REQ-001", "checks": []}'},
            ]
        elif phase == "integrity_eval":
            files = [{"path": "runs/kit/REQ-001/reports/integrity.json", "content": json.dumps({"verdict": "needs_hardening", "findings": ["no negative test"]})}]
    return {
        "ok": True,
        "phase": payload.get("phase"),
        "echo": "",
        "text": "",
        "files": files,
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "golden"},
        "warnings": [],
        "errors": [],
        "runId": payload.get("runId"),
    }


_VOLATILE_KEY_RE = re.compile(r"(timestamp|^ts$|_at$|latency|duration|elapsed)", re.I)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def _scrub(value, workspace: str):
    if isinstance(value, dict):
        return {k: ("<VOLATILE>" if _VOLATILE_KEY_RE.search(k) and isinstance(v, (int, float)) else _scrub(v, workspace)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, workspace) for v in value]
    if isinstance(value, str):
        out = value.replace(workspace, "<WORKSPACE>").replace(str(REPO_ROOT), "<REPO>")
        out = _UUID_RE.sub("<UUID>", out)
        return _TS_RE.sub("<TS>", out)
    return value


async def _run_scenario(phase: str, executor: str, methodology: str | None, variant: str = "") -> dict:
    calls = []

    async def fake_post_json(path, payload):
        calls.append({"path": path, "payload": copy.deepcopy(payload)})
        return _fake_gateway_response(payload, variant)

    with tempfile.TemporaryDirectory(prefix="clike-golden-") as tmp:
        workspace = Path(tmp).resolve()
        (workspace / "docs/harper").mkdir(parents=True)
        payload = _base_payload(phase, workspace, methodology, variant)
        payload["executionPreference"] = "local_agent_only" if executor == "local" else "cloud_only"
        policy = {
            "requested": payload["executionPreference"],
            "selected": "local_agent" if executor == "local" else "cloud",
            "reason": "golden",
            "phase_supported": True,
        }
        result: dict = {"scenario": {"phase": phase, "executor": executor, "methodology": methodology, "variant": variant}}
        with patch.object(harper, "_post_json", side_effect=fake_post_json), patch.object(
            harper, "resolve_llm_selection", side_effect=_fake_resolve_llm_selection
        ), patch.object(harper, "resolve_execution_policy", return_value=policy), patch.object(
            harper, "_write_stage_artifact", return_value=None
        ):
            try:
                out = await harper.run_phase(phase, payload)
                result["output"] = out
            except Exception as exc:  # the failure mode is part of the contract
                result["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        result["gateway_calls"] = calls
        return _scrub(json.loads(json.dumps(result, default=str, sort_keys=True)), str(workspace))


def _scenarios():
    for phase in PHASES_CLOUD:
        yield phase, "cloud", None, ""
    for phase in PHASES_LOCAL:
        yield phase, "local", None, ""
    for phase in ("spec", "kit"):
        yield phase, "cloud", "bmad", ""
        yield phase, "local", "bmad", ""
    yield "kit", "cloud", None, "fullchain"
    yield "idea", "cloud", None, "noattach"
    yield "idea", "local", None, "noattach"
    # WP8.0 characterization: variants that were not pinned before the phase-contract refactor
    for phase in ("spec", "plan", "kit"):
        yield phase, "cloud", None, "repo"
    for phase in ("plan", "kit", "eval"):
        yield phase, "local", None, "repo"
    for phase in ("idea", "plan", "eval", "finalize", "extend"):
        yield phase, "local", "bmad", ""  # extend: BMAD has no agent for it (error is the contract)
    for phase in ("idea", "plan", "finalize"):
        yield phase, "cloud", "bmad", ""
    yield "kit", "local", None, "codex"
    yield "spec", "local", None, "codex"
    yield "kit", "local", None, "repair"
    yield "kit", "local", None, "audit"
    yield "extend", "local", None, "attach"
    yield "extend", "cloud", None, "attach"
    yield "eval", "local", None, "contractblobs"
    yield "finalize", "local", None, "cloudinfra"
    yield "finalize", "cloud", None, "cloudinfra"
    yield "kit", "cloud", None, "fullchain_files"


class GoldenPhaseContractTests(unittest.TestCase):
    maxDiff = None

    def test_phase_boundary_snapshots(self):
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        for phase, executor, methodology, variant in _scenarios():
            name = f"{phase}__{executor}__{methodology or 'native'}" + (f"__{variant}" if variant else "")
            with self.subTest(name):
                actual = asyncio.run(_run_scenario(phase, executor, methodology, variant))
                rendered = json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                snap = SNAPSHOT_DIR / f"{name}.json"
                if UPDATE:
                    snap.write_text(rendered, encoding="utf-8")
                    continue
                self.assertTrue(snap.exists(), f"missing snapshot {snap.name}; run with CLIKE_GOLDEN_UPDATE=1")
                self.assertEqual(snap.read_text(encoding="utf-8"), rendered, f"golden drift: {name}")


if __name__ == "__main__":
    unittest.main()
