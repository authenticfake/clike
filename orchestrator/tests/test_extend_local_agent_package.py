import json
from pathlib import Path

import pytest

from services.local_agent_package import (
    build_extend_local_agent_package,
    normalize_local_agent_result,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTEND_SYSTEM = REPO_ROOT / "gateway/prompts/harper/extend_system.md"


def _execution_policy():
    return {
        "requested": "prefer_local_agent",
        "selected": "local_agent",
        "reason": "test",
        "phase_supported": True,
    }


def _package(payload=None):
    return build_extend_local_agent_package(
        payload=payload or {"runId": "ext-run", "extend": {"rawInput": "Add retention policy"}},
        execution_policy=_execution_policy(),
    )


def _context_file(package):
    agent = package["local_agent"]
    for entry in agent["package_files"]:
        if entry["path"] == agent["context_path"]:
            return json.loads(entry["content"])
    raise AssertionError("context file missing")


def _materialized(package):
    agent = package["local_agent"]
    skip = {agent["context_path"], agent["prompt_path"]}
    return [f for f in agent["package_files"] if f["path"] not in skip]


# --- A. Package paths / reads / prompt ---

def test_extend_package_internals_under_runs_extend_not_docs_harper():
    agent = _package()["local_agent"]
    assert agent["context_path"] == "runs/extend/docs/AGENT_EXTEND_CONTEXT.json"
    assert agent["prompt_path"] == "runs/extend/docs/AGENT_EXTEND_PROMPT.md"
    for f in agent["package_files"]:
        assert not f["path"].startswith("docs/harper/"), f["path"]
        assert f["path"].startswith("runs/extend/")


def test_extend_required_reads_include_canonical_docs():
    reads = " ".join(_context_file(_package())["required_reads"])
    assert "docs/harper/IDEA.md" in reads
    assert "docs/harper/SPEC.md" in reads
    assert "docs/harper/PLAN.md" in reads
    assert "docs/harper/plan.json" in reads
    assert "docs/harper/lane-guides/" in reads


def test_extend_allowed_write_roots_are_narrow():
    roots = _package()["local_agent"]["allowed_write_roots"]
    assert "docs/harper" not in roots  # no broad catch-all
    assert set(roots) == {
        "docs/harper/IDEA.md",
        "docs/harper/SPEC.md",
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        "docs/harper/lane-guides",
        "docs/harper/EXTEND_*.md",
    }


def test_extend_prompt_mentions_conditional_and_mandatory_outputs():
    prompt = _package()["local_agent"]["prompt_content"]
    assert "Update IDEA.md only" in prompt
    assert "Update SPEC.md only" in prompt
    assert "Always update PLAN.md and plan.json" in prompt
    assert "lane-guides only if new concern guidance is needed" in prompt
    assert "EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md" in prompt
    assert "BINDING planning constraints" in prompt
    assert "Return FULL file artifacts" in prompt


def test_extend_prompt_embeds_gateway_canonical_anchors():
    prompt = _package()["local_agent"]["prompt_content"]
    gateway = EXTEND_SYSTEM.read_text(encoding="utf-8")
    anchors = [
        "EXTEND appends new requirements to an existing Harper plan",
        "Do not regenerate the plan from scratch.",
        "Preserve the existing `plan.json` object shape",
        "Emit an EXTEND audit report.",
        "Each new REQ appears in both PLAN.md and plan.json.",
    ]
    for anchor in anchors:
        assert anchor in prompt, f"prompt missing anchor: {anchor!r}"
        assert anchor in gateway, f"anchor not in extend_system.md: {anchor!r}"


# --- B. Attachments ---

def test_extend_from_attachment_without_attachments_raises():
    with pytest.raises(ValueError) as exc:
        build_extend_local_agent_package(
            payload={"runId": "ext-run", "extend": {"fromAttachment": True}},
            execution_policy=_execution_policy(),
        )
    assert "without at least one attached source file" in str(exc.value)


def test_extend_materializes_attachments_into_workspace_paths():
    payload = {
        "runId": "ext-run",
        "extend": {"fromAttachment": True, "rawInput": "Add policy"},
        "attachments": [
            {"name": "policy.md", "path": "/external/policy.md", "content": "rules\n", "mime": "text/markdown"},
            {"name": "notes.txt", "path": "/external/notes.txt", "content": "notes\n"},
        ],
    }
    package = build_extend_local_agent_package(payload=payload, execution_policy=_execution_policy())
    mats = _materialized(package)
    paths = {f["path"] for f in mats}
    assert paths == {"runs/extend/attachments/policy.md", "runs/extend/attachments/notes.txt"}

    item = _context_file(package)["attachments"]["items"][0]
    assert item["workspace_path"] == "runs/extend/attachments/policy.md"
    assert item["original_path"] == "/external/policy.md"
    prompt = package["local_agent"]["prompt_content"]
    assert "runs/extend/attachments/policy.md" in prompt
    assert "Do NOT read original_path" in prompt


# --- E. Normalization ---

VALID_PLAN_MD = (
    "# PLAN — Demo\n\n"
    "## REQ-1 — Existing\nVerification checkpoints: tests.\n\n"
    "## REQ-2 — Added by extend\nVerification checkpoints: tests.\n"
)
VALID_PLAN_JSON = json.dumps(
    {
        "snapshot": {"total": 2},
        "reqs": [
            {"id": "REQ-1", "title": "Existing", "status": "done", "acceptance": ["a1"], "dependsOn": []},
            {"id": "REQ-2", "title": "Added", "status": "open", "acceptance": ["a2"], "dependsOn": ["REQ-1"]},
        ],
    }
)
AUDIT = (
    "# EXTEND Report\n\nCommand: /extend\nInput Sources: PLAN.md\n"
    "Added Requirements: REQ-2\nValidation: plan.json valid\nRisks: none\n"
)


def _file(path, content):
    return {"path": path, "content": content}


def _normalize_extend(files, exit_code=0):
    return normalize_local_agent_result(
        {"phase": "extend", "req_id": "SOLUTION", "files": files, "exit_code": exit_code, "runId": "ext-run"}
    )


def test_extend_accepts_canonical_and_conditional_outputs():
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),
        _file("docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md", AUDIT),
        _file("docs/harper/IDEA.md", "# IDEA — Demo\n\n## Vision\nx\n"),
        _file("docs/harper/SPEC.md", "# SPEC — Demo\n"),
        _file("docs/harper/lane-guides/python.md", "## Lane Guide — python\nstuff\n"),
    ]
    result = _normalize_extend(files)
    assert result["ok"] is True
    assert "local_agent_wrote_outside_allowed_roots" not in result["errors"]


def test_extend_rejects_agent_internal_and_arbitrary_docs_harper():
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),
        _file("docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md", AUDIT),
        _file("docs/harper/AGENT_EXTEND_CONTEXT.json", "{}"),
        _file("docs/harper/NOTES.md", "x"),
    ]
    result = _normalize_extend(files)
    assert result["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in result["errors"]
    blocked = " ".join(result["warnings"])
    assert "docs/harper/AGENT_EXTEND_CONTEXT.json" in blocked
    assert "docs/harper/NOTES.md" in blocked


def test_extend_requires_plan_planjson_and_audit():
    files = [_file("docs/harper/PLAN.md", VALID_PLAN_MD)]  # missing plan.json + audit
    result = _normalize_extend(files)
    assert result["ok"] is False
    assert "extend_required_outputs_missing" in result["errors"]
    miss = " ".join(result["warnings"])
    assert "docs/harper/plan.json" in miss
    assert "EXTEND_" in miss


def test_extend_stdout_only_is_not_success():
    result = _normalize_extend([])
    assert result["ok"] is False
    assert "extend_required_outputs_missing" in result["errors"]
    # No misleading kit REQ-ID message for the document-mutation phase.
    assert not any(e.startswith("no_candidate_files_returned_for") for e in result["errors"])


def test_extend_rejects_invalid_plan_json():
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", "{not valid json"),
        _file("docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md", AUDIT),
    ]
    result = _normalize_extend(files)
    assert result["ok"] is False
    assert "extend_output_incomplete" in result["errors"]
    assert any("plan_json_invalid_json" in w for w in result["warnings"])


def test_extend_rejects_plan_md_req_missing_from_plan_json():
    plan_json_missing = json.dumps(
        {"snapshot": {"total": 1}, "reqs": [
            {"id": "REQ-1", "title": "Existing", "status": "done", "acceptance": ["a1"], "dependsOn": []}
        ]}
    )
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),  # references REQ-1 and REQ-2
        _file("docs/harper/plan.json", plan_json_missing),  # only REQ-1
        _file("docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md", AUDIT),
    ]
    result = _normalize_extend(files)
    assert result["ok"] is False
    assert "extend_output_incomplete" in result["errors"]
    assert any("REQ-2" in w for w in result["warnings"])
