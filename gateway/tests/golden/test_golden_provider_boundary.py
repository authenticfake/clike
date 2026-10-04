"""Golden snapshots of the Gateway -> provider boundary (WP0.4).

Inputs are the exact payloads the Orchestrator posts to ``/v1/harper/run``,
taken from the Orchestrator golden snapshots
(``orchestrator/tests/golden/snapshots/*__cloud__*.json``), so the chain
extension -> orchestrator -> gateway -> provider is frozen end to end.

For each scenario this records:

* every provider call (provider, model, messages, generation params);
* the HTTP outcome of ``/v1/harper/run`` (status + normalized body), which
  freezes file-block extraction and canonical validation as well.

Provider responses are canned from CoffeeBuddy material already in the repo
(never from client telemetry).

Regenerate after an *intended* change with::

    CLIKE_GOLDEN_UPDATE=1 pytest gateway/tests/golden -q
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_ROOT = REPO_ROOT / "gateway"
ORCH_SNAPSHOTS = REPO_ROOT / "orchestrator/tests/golden/snapshots"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"
UPDATE = os.getenv("CLIKE_GOLDEN_UPDATE") == "1"

_TMP = tempfile.mkdtemp(prefix="clike-gw-golden-")
_PROMPTS = GATEWAY_ROOT / "prompts/harper"
_ENV = {
    "OPENAI_API_KEY": "sk-golden-not-a-real-key",
    "ANTHROPIC_API_KEY": "sk-ant-golden-not-a-real-key",
    "MODELS_CONFIG": str(REPO_ROOT / "configs/models.yaml"),
    "HARPER_TELEMETRY_DIR": _TMP,
    "HARPER_STUB_DIR": _TMP,
    "GATEWAY_DUMP_DIR": _TMP,
    "SPEC_TEMPLATE_PATH": str(GATEWAY_ROOT / "templates/SPEC_TEMPLATE.md"),
    "PROMPT_IDEA_SYSTEM_PATH": str(_PROMPTS / "idea_system.md"),
    "PROMPT_SPEC_SYSTEM_PATH": str(_PROMPTS / "spec_system.md"),
    "PROMPT_PLAN_SYSTEM_PATH": str(_PROMPTS / "plan_system.md"),
    "PROMPT_KIT_SYSTEM_PATH": str(_PROMPTS / "kit_system.md"),
    "PROMPT_INTEGRITY_EVAL_SYSTEM_PATH": str(_PROMPTS / "integrity_eval.md"),
    "PROMPT_PROMOTION_HARDENER_SYSTEM_PATH": str(_PROMPTS / "promotion_hardener.md"),
    "PROMPT_PROMOTION_EVAL_SYSTEM_PATH": str(_PROMPTS / "promotion_eval.md"),
    "PROMPT_FINALIZE_SYSTEM_PATH": str(_PROMPTS / "finalize_system.md"),
    "PROMPT_EXTEND_SYSTEM_PATH": str(_PROMPTS / "extend_system.md"),
    "RAG_BASE_URL": "http://127.0.0.1:9/v1/rag",  # unroutable: any stray RAG call fails fast
}
os.environ.update(_ENV)
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routes import harper as harper_route  # noqa: E402

COFFEEBUDDY = REPO_ROOT / "CoffeeBuddy"
KIT_FIXTURE = GATEWAY_ROOT / "tests/fixtures/openai_gpt-5.5__kit__a4316f4afefd.json"


def _doc_block(path: str, content: str) -> str:
    return f"BEGIN_FILE {path}\n{content.rstrip()}\nEND_FILE\n"


def _canned_llm_result(phase: str) -> dict:
    if phase == "kit":
        return json.loads(KIT_FIXTURE.read_text(encoding="utf-8"))["llm_result"]
    texts = {
        "idea": _doc_block("docs/harper/IDEA.md", (COFFEEBUDDY / "IDEA.md").read_text(encoding="utf-8")),
        "spec": _doc_block("docs/harper/SPEC.md", (COFFEEBUDDY / "SPEC.md").read_text(encoding="utf-8")),
    }
    text = texts.get(phase, f"Golden canned response for phase {phase}.")
    return {"ok": True, "text": text, "files": [], "usage": {"input_tokens": 1, "output_tokens": 1}, "finish_reason": "stop", "raw": {}, "errors": []}


_VOLATILE_KEY_RE = re.compile(r"(timestamp|^ts$|_at$|latency|duration|elapsed)", re.I)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX_RE = re.compile(r"\b[0-9a-f]{12,32}\b")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
_DUR_RE = re.compile(r'("(?:latency|duration|elapsed)[a-z_]*"\s*:\s*)[0-9.]+')


def _scrub(value):
    if isinstance(value, dict):
        return {k: ("<VOLATILE>" if _VOLATILE_KEY_RE.search(k) and isinstance(v, (int, float)) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        out = value.replace(os.path.realpath(_TMP), "<TMP>").replace(_TMP, "<TMP>").replace(str(REPO_ROOT), "<REPO>")
        out = _UUID_RE.sub("<UUID>", out)
        out = _TS_RE.sub("<TS>", out)
        return _HEX_RE.sub("<HEX>", out)
    return value


def _scenarios():
    """(name, gateway payload, provider override) from orchestrator cloud snapshots."""
    for snap in sorted(ORCH_SNAPSHOTS.glob("*__cloud__*.json")):
        data = json.loads(snap.read_text(encoding="utf-8"))
        for index, call in enumerate(data.get("gateway_calls") or []):
            if call.get("path") != "/v1/harper/run":
                continue
            base = snap.stem + (f"__call{index}" if index else "")
            yield base, call["payload"], None
            if snap.stem in {"spec__cloud__native", "kit__cloud__native"}:
                yield base + "__anthropic", call["payload"], "anthropic:claude-sonnet-4-6"


def _run(payload: dict, model_override: str | None) -> dict:
    payload = json.loads(json.dumps(payload).replace("<WORKSPACE>", _TMP).replace("<REPO>", str(REPO_ROOT)))
    if model_override:
        payload["model"] = model_override
    phase = payload.get("phase") or payload.get("cmd")
    calls = []

    async def fake_openai(**kwargs):
        calls.append({"provider": "openai", **kwargs})
        return _canned_llm_result(phase)

    async def fake_anthropic(base, api_key, model, messages, **kwargs):
        calls.append({"provider": "anthropic", "model": model, "messages": messages, **kwargs})
        return _canned_llm_result(phase)

    app = FastAPI()
    app.include_router(harper_route.router)
    with patch.object(harper_route.oai, "openai_complete_unified", side_effect=fake_openai), patch.object(
        harper_route.anth, "chat", side_effect=fake_anthropic
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/harper/run", json=payload)
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    for call in calls:
        call.pop("api_key", None)
    return _scrub(json.loads(json.dumps({"provider_calls": calls, "status": resp.status_code, "response": body}, default=str, sort_keys=True)))


class GoldenProviderBoundaryTests(unittest.TestCase):
    maxDiff = None

    def test_provider_boundary_snapshots(self):
        scenarios = list(_scenarios())
        self.assertTrue(scenarios, "orchestrator golden snapshots are missing; generate them first")
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        for name, payload, model_override in scenarios:
            with self.subTest(name):
                rendered = json.dumps(_run(payload, model_override), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                snap = SNAPSHOT_DIR / f"{name}.json"
                if UPDATE:
                    snap.write_text(rendered, encoding="utf-8")
                    continue
                self.assertTrue(snap.exists(), f"missing snapshot {snap.name}; run with CLIKE_GOLDEN_UPDATE=1")
                self.assertEqual(snap.read_text(encoding="utf-8"), rendered, f"golden drift: {name}")


if __name__ == "__main__":
    unittest.main()
