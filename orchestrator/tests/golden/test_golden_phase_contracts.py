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

PHASES_CLOUD = ["idea", "spec", "plan", "kit", "eval", "finalize", "extend"]
PHASES_LOCAL = ["idea", "spec", "plan", "kit", "eval", "finalize", "extend"]


def _bmad_vendor_core_blobs():
    blobs = {".clike/skills/vendor/bmad/manifest.json": (BMAD_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")}
    for path in sorted(BMAD_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _plan_json():
    return {
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


def _base_payload(phase: str, workspace: Path, methodology: str | None, variant: str = "") -> dict:
    idea = (COFFEEBUDDY / "IDEA.md").read_text(encoding="utf-8")
    spec = (COFFEEBUDDY / "SPEC.md").read_text(encoding="utf-8")
    core_blobs = {
        "IDEA.md": idea,
        "SPEC.md": spec,
        "PLAN.md": "# PLAN — CoffeeBuddy\n\n| REQ | Title |\n|---|---|\n| REQ-001 | Coffee order intake |\n| REQ-002 | Order status notifications |\n",
        "plan.json": json.dumps(_plan_json()),
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
    if phase == "kit" and variant == "fullchain":
        payload["kit"]["phases"] = ["kit", "integrity_eval", "promotion_hardener", "promotion_eval"]
    if phase == "eval":
        payload["eval"] = {"targets": ["REQ-001"]}
    if phase == "extend":
        payload["messages"] = [{"role": "user", "content": "/extend add loyalty points for frequent buyers"}]
    if methodology:
        payload["methodology"] = methodology
        payload["agent"] = {"idea": "analyst", "spec": "pm", "plan": "architect"}.get(phase, "developer")
    return payload


async def _fake_resolve_llm_selection(**kwargs):
    return {}


def _fake_gateway_response(payload):
    return {
        "ok": True,
        "phase": payload.get("phase"),
        "echo": "",
        "text": "",
        "files": [],
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
        return _fake_gateway_response(payload)

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
