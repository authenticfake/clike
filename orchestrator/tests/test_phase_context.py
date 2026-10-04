"""PhaseContext v1 (WP8.4): typed, versioned contract with a byte-identical wire mapping."""

import json
import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import pytest  # noqa: E402

from services.phase_context import BlobKind, PhaseContext, classify_blob, phase_context_json_schema  # noqa: E402

SNAPSHOTS = ORCHESTRATOR_ROOT / "tests/golden/snapshots"
SCHEMA_FILE = ORCHESTRATOR_ROOT.parent / "docs/contracts/phase_context.v1.schema.json"


def _golden_payloads():
    for snap in sorted(SNAPSHOTS.glob("*__cloud__*.json")):
        for i, call in enumerate(json.loads(snap.read_text(encoding="utf-8")).get("gateway_calls") or []):
            yield f"{snap.stem}#{i}", call["payload"]


def test_round_trip_is_identical_for_every_golden_payload():
    seen = 0
    for name, payload in _golden_payloads():
        ctx = PhaseContext.from_payload(payload)
        rebuilt = ctx.to_core_blobs()
        assert list(rebuilt) == list(payload["core_blobs"]), name  # order drives the gateway prompt
        assert rebuilt == payload["core_blobs"], name
        assert ctx.schema_version == "clike.phase_context.v1"
        seen += 1
    assert seen >= 20


def test_no_golden_blob_is_unclassified_by_accident():
    kinds = {}
    for _, payload in _golden_payloads():
        for name in payload["core_blobs"]:
            kinds[name] = classify_blob(name)
    assert kinds["IDEA.md"] == BlobKind.canonical_document
    assert kinds["plan.json"] == BlobKind.plan_json
    assert kinds["TECH_CONSTRAINTS.yaml"] == BlobKind.tech_constraints
    assert kinds["TARGET_CONTRACT.json"] == BlobKind.target_contract
    assert kinds["FILE_REQUIREMENTS.json"] == BlobKind.file_requirements
    assert kinds["REPO_STRUCTURE_EVIDENCE.json"] == BlobKind.repo_manifest
    assert kinds["CLIKE_SELECTED_CAPABILITY_CONTEXT.json"] == BlobKind.selected_capability_context
    assert kinds["REQ_PROMOTION_MANIFEST.md"] == BlobKind.req_promotion_manifest
    assert all(k == BlobKind.candidate for n, k in kinds.items() if n.startswith("candidate::"))
    assert all(k == BlobKind.methodology_vendor for n, k in kinds.items() if n.startswith(".clike/skills/vendor/"))
    assert BlobKind.workspace_reference not in kinds.values()


def test_typed_accessors_parse_json_blobs():
    payload = next(p for n, p in _golden_payloads() if n.startswith("kit__cloud__native#"))
    ctx = PhaseContext.from_payload(payload)
    assert ctx.req_id == "REQ-001"
    assert ctx.target_contract and ctx.target_contract.get("req_id") == "REQ-001"
    assert isinstance(ctx.file_requirements, dict)
    assert [r["id"] for r in ctx.plan["reqs"]] == ["REQ-001", "REQ-002"]
    assert set(ctx.canonical_documents) == {"IDEA.md", "SPEC.md", "PLAN.md"}


def test_candidates_and_invalid_json_are_kept_verbatim():
    ctx = PhaseContext.from_payload({"phase": "integrity_eval", "core_blobs": {
        "candidate::runs/kit/REQ-001/src/a.py": "x = 1\n", "TARGET_CONTRACT.json": "{not json"}})
    assert ctx.candidates == {"runs/kit/REQ-001/src/a.py": "x = 1\n"}
    assert ctx.target_contract is None
    assert ctx.to_core_blobs()["TARGET_CONTRACT.json"] == "{not json"


def test_non_text_blobs_are_rejected():
    with pytest.raises(TypeError):
        PhaseContext.from_payload({"phase": "spec", "core_blobs": {"SPEC.md": {"not": "text"}}})


def test_published_json_schema_is_current():
    expected = json.dumps(phase_context_json_schema(), indent=2, sort_keys=True) + "\n"
    assert SCHEMA_FILE.read_text(encoding="utf-8") == expected, "regenerate docs/contracts/phase_context.v1.schema.json"


def test_post_json_sends_identical_core_blobs():
    import asyncio
    from unittest.mock import patch

    import httpx

    from services import gateway_http, harper

    payload = next(p for n, p in _golden_payloads() if n.startswith("kit__cloud__native__repo#"))
    sent = []

    def handler(request):
        sent.append(request.content)
        return httpx.Response(200, json={"ok": True})

    async def go():
        try:
            return await harper._post_json("/v1/harper/run", payload)
        finally:
            await gateway_http.aclose()

    with patch.object(gateway_http, "TRANSPORT", httpx.MockTransport(handler)):
        asyncio.run(go())
    body = json.loads(sent[0])
    assert list(body["core_blobs"]) == list(payload["core_blobs"])
    assert body["core_blobs"] == payload["core_blobs"]
