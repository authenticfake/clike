"""The cloud prompt carries what a local agent reads from the workspace (audit 2026-10-18)."""
import json

import pytest

from services.cloud_prompt import messages as m
from services.cloud_prompt.context_budget import plan_json_index, plan_md_digest, plan_md_slice

PLAN = {"reqs": [
    {"id": "REQ-001", "title": "Config", "status": "done", "lane": "python", "dependsOn": [], "acceptance": ["a"]},
    {"id": "REQ-002", "title": "Discovery", "status": "done", "lane": "python", "dependsOn": ["REQ-001"], "acceptance": ["b"]},
    {"id": "REQ-003", "title": "Login", "status": "open", "lane": "python", "dependsOn": ["REQ-002"], "acceptance": ["c"]},
]}
PLAN_MD = "\n".join([
    "# PLAN", "", "## REQ-IDs Table", "", "| ID | Title |", "|---|---|", "| REQ-001 | Config |", "| REQ-002 | Discovery |", "| REQ-003 | Login |", "",
    "### Acceptance — REQ-001", "- a", "", "### Acceptance — REQ-002", "- b", "", "### Acceptance — REQ-003", "- c", "",
    "## Release v2", "", "**REQ-003 — Login**", "", "Traceability: F09.", "", "**REQ-004 — Other**", "", "x" * 50000, "",
])


@pytest.fixture(autouse=True)
def _trust_everything(monkeypatch):
    monkeypatch.setattr(m, "validate_current_canonical_core_blobs",
                        lambda blobs: {"trusted_core_blobs": dict(blobs or {}), "invalid_canonical": []})


def _user(payload):
    return m.compose_phase_messages(payload)[-1]["content"]


def test_plan_md_slice_keeps_the_req_and_its_dependencies_only():
    text = plan_md_slice(PLAN_MD, ["REQ-003", "REQ-002"])
    assert "| REQ-003 | Login |" in text and "### Acceptance — REQ-002" in text and "**REQ-003 — Login**" in text
    assert "REQ-001 | Config" not in text and "x" * 100 not in text
    assert "| REQ-003 |" in plan_md_digest(PLAN_MD) and "x" * 100 not in plan_md_digest(PLAN_MD)
    assert "REQ-003 [open] python deps=REQ-002" in plan_json_index(json.dumps(PLAN))


def test_cloud_kit_sees_plan_slice_dependency_code_locked_tests_manifests_and_companions():
    core = {
        "PLAN.md": PLAN_MD, "plan.json": json.dumps(PLAN), "SPEC.md": "# SPEC\n## Goals\nx\n",
        "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n",
        "REQ_PROMOTION_MANIFEST.md": "# REQ Promotion Manifest — REQ-003\npromote src/",
        "REPO_STRUCTURE_EVIDENCE.md": "src/leadintel/app.py",
        "candidate::runs/kit/REQ-003/test/test_login.py": "def test_login():\n    assert login()\n",
        "companion::runs/kit/REQ-003/docs/NOTES.md": "Use the OIDC port.",
        "DEPENDENCY_SURFACE.md": "### REQ-002 — Discovery\n#### src/leadintel/discovery/contracts.py\nclass SearchPort: ...",
    }
    user = _user({"phase": "kit", "cmd": "kit", "kit": {"targets": ["REQ-003"]}, "core_blobs": core})
    assert "### PLAN.md — REQ-003 and its dependencies (verbatim excerpt)" in user and "**REQ-003 — Login**" in user
    assert "x" * 1000 not in user                                            # not the whole PLAN.md
    assert "class SearchPort" in user and "## DEPENDENCY SURFACE" in user
    assert "def test_login" in user and "(candidate file, verbatim)" in user  # locked tests visible
    assert "promote src/" in user and "src/leadintel/app.py" in user          # manifests
    assert "Use the OIDC port." in user                                       # REQ companion document


def test_cloud_follow_up_gets_the_req_slice_not_the_whole_plan():
    core = {"PLAN.md": PLAN_MD, "plan.json": json.dumps(PLAN), "SPEC.md": "# SPEC\n"}
    user = _user({"phase": "integrity_eval", "cmd": "integrity_eval", "kit": {"targets": ["REQ-003"]}, "core_blobs": core})
    assert "REQ-003 and its dependencies (verbatim excerpt)" in user and "x" * 1000 not in user
    assert '"id": "REQ-001"' not in user                                    # plan.json sliced too


def test_cloud_finalize_sees_documents_a_plan_digest_and_the_solution_code():
    core = {"IDEA.md": "# IDEA\nvision", "SPEC.md": "# SPEC\ngoals", "PLAN.md": PLAN_MD, "plan.json": json.dumps(PLAN),
            "SOLUTION_SURFACE.md": "#### pyproject.toml\n[project]\nname='leadintel'"}
    user = _user({"phase": "finalize", "cmd": "finalize", "core_blobs": core})
    assert "vision" in user and "goals" in user
    assert "(digest: outline and every REQ)" in user and "x" * 1000 not in user
    assert "name='leadintel'" in user


def test_cloud_cascade_sees_the_idea_it_merges_and_bmad_companions_have_content():
    core = {"IDEA.md": "# IDEA\nthe v1 vision", "SPEC.md": "# SPEC\n", "PLAN.md": "# PLAN\n", "plan.json": json.dumps(PLAN),
            "companion::docs/harper/bmad/spec/PRD.md": "PRD content here"}
    user = _user({"phase": "extend", "cmd": "extend", "core_blobs": core,
                  "extend": {"mode": "cascade", "release": "v2", "baseline": "v1"}})
    assert "the v1 vision" in user and "PRD content here" in user


def test_a_cloud_run_that_cannot_fit_is_refused_with_its_size(monkeypatch):
    from services import harper

    monkeypatch.setenv("CLIKE_CLOUD_MAX_PROMPT_CHARS", "1000")
    with pytest.raises(harper.GatewayUpstreamError) as err:
        harper._check_cloud_budget({"phase": "kit"}, [{"role": "user", "content": "x" * 2000}])
    assert err.value.status == 413 and err.value.code == "cloud_context_too_large" and "local agent" in err.value.detail
    monkeypatch.setenv("CLIKE_CLOUD_MAX_PROMPT_CHARS", "10000000")
    monkeypatch.setenv("CLIKE_CLOUD_MAX_OUTPUT_CHARS", "100")
    cascade = {"phase": "extend", "extend": {"mode": "cascade"}, "core_blobs": {"PLAN.md": "p" * 500}}
    with pytest.raises(harper.GatewayUpstreamError) as err:
        harper._check_cloud_budget(cascade, [{"role": "user", "content": "small"}])
    assert "write back" in err.value.detail
    harper._check_cloud_budget({"phase": "extend", "core_blobs": {"PLAN.md": "p" * 500}}, [{"role": "user", "content": "x"}])


def test_dependency_sources_are_found_past_the_first_page_of_the_collection(monkeypatch):
    import asyncio

    from services import rag_store

    pages = [  # 600 unrelated points before the dependency source
        [{"payload": {"path": f"docs/harper/lane-guides/g{i}.md", "chunk": 0, "text": "guide"}} for i in range(512)],
        [{"payload": {"path": f"runs/kit/REQ-009/src/x{i}.py", "chunk": 0, "text": "other"}} for i in range(88)]
        + [{"payload": {"path": "runs/kit/REQ-002/src/app/contracts.py", "chunk": 0, "text": "class SearchPort: ..."}}],
    ]

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *a, **k):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            index = 0 if json.get("offset") is None else 1
            return FakeResponse({"result": {"points": pages[index], "next_page_offset": 1 if index == 0 else None}})

    store = rag_store.RagStore("p")

    async def no_ensure():
        return None

    monkeypatch.setattr(store, "ensure", no_ensure)
    monkeypatch.setattr(rag_store.httpx, "AsyncClient", FakeClient)
    docs = asyncio.run(store.fetch_docs_by_prefix("runs/kit/REQ-002/src", limit_points=200))
    assert [d.get("path") for d in docs] == ["runs/kit/REQ-002/src/app/contracts.py"]
