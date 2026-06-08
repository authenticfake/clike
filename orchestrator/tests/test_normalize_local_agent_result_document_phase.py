from services.local_agent_package import normalize_local_agent_result


def _normalize(phase, files, *, req_id=None, exit_code=0):
    payload = {
        "phase": phase,
        "files": files,
        "exit_code": exit_code,
        "runId": f"{phase}-run",
    }
    if req_id is not None:
        payload["req_id"] = req_id
    return normalize_local_agent_result(payload)


def _file(path, content="content\n"):
    return {"path": path, "content": content}


# --- Substantive canonical fixtures (meet the gateway quality bar) ---

VALID_IDEA = """# IDEA — Demo Project

## Vision
Deliver a measurable first slice that proves the product value to early users.

## Problem Statement
Operators waste time reconciling data manually every morning before reporting.

## Target Users & Context
Primary users are operations analysts working inside the internal back office.

## Value & Outcomes
Reduce reconciliation time and surface anomalies earlier in the daily workflow.

## Out of Scope
Mobile clients and third-party marketplace integrations are deferred past slice 1.

## Technology Constraints
```yaml
tech_constraints:
  version: 1
  classification:
    solution_type: unknown
```

## Risks & Assumptions
We assume source exports remain CSV; data volume risk is tracked as an assumption.

## Success Metrics
Time-to-first-reconciliation under five minutes for the initial pilot cohort.
"""

VALID_SPEC = """# SPEC — Demo Project

## Summary
A testable featurelet that reconciles morning exports into a single review queue.

## Functional Requirements
The system ingests CSV exports and produces a normalized reconciliation queue.

## Non-Functional Requirements
Processing must complete within five minutes for the pilot data volume.

## Acceptance Criteria
- Given a valid CSV, when ingested, then a queue row is created per record.
- Given a malformed CSV, when ingested, then the file is rejected with an error.
- Given duplicate records, when ingested, then duplicates are flagged not dropped.
- Given completion, when finished, then total processed count is reported.
- Given a failure, when retried, then processing is idempotent.

SPEC_END
"""

VALID_PLAN_MD = """# PLAN — Demo Project

## REQ-1 — Ingestion pipeline
Build the CSV ingestion slice.

Verification checkpoints: unit tests for parsing and acceptance test for the queue.
"""

VALID_PLAN_JSON = """{
  "snapshot": {"total": 1},
  "reqs": [
    {
      "id": "REQ-1",
      "title": "Ingestion pipeline",
      "status": "todo",
      "acceptance": ["Valid CSV produces one queue row per record"],
      "dependsOn": []
    }
  ]
}
"""

VALID_LANE = """# Backend lane

## Purpose
Own the ingestion and reconciliation services.

## Boundaries
Expected files live under the backend module only.

## Commands
Run the backend test command for validation.

## Eval/Gate expectations
Gate expectations require all acceptance tests to pass.
"""


def test_idea_accepts_canonical_idea_md():
    result = _normalize("idea", [_file("docs/harper/IDEA.md", VALID_IDEA)], req_id="SOLUTION")
    assert result["ok"] is True
    assert {f["path"] for f in result["files"]} == {"docs/harper/IDEA.md"}
    assert "local_agent_wrote_outside_allowed_roots" not in result["errors"]
    assert "document_phase_output_incomplete" not in result["errors"]


def test_spec_accepts_canonical_spec_md():
    result = _normalize("spec", [_file("docs/harper/SPEC.md", VALID_SPEC)], req_id="SOLUTION")
    assert result["ok"] is True
    assert {f["path"] for f in result["files"]} == {"docs/harper/SPEC.md"}


def test_plan_accepts_plan_md_plan_json_and_lane_guides():
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),
        _file("docs/harper/lane-guides/backend.md", VALID_LANE),
    ]
    result = _normalize("plan", files, req_id="SOLUTION")
    assert result["ok"] is True
    assert {f["path"] for f in result["files"]} == {
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        "docs/harper/lane-guides/backend.md",
    }


def test_idea_rejects_agent_context_internal():
    result = _normalize(
        "idea",
        [_file("docs/harper/AGENT_IDEA_CONTEXT.json", "{}\n")],
        req_id="SOLUTION",
    )
    assert result["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in result["errors"]
    assert not result["files"]


def test_idea_rejects_arbitrary_docs_harper_file():
    result = _normalize("idea", [_file("docs/harper/OTHER.md", VALID_IDEA)], req_id="SOLUTION")
    assert result["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in result["errors"]


def test_kit_behavior_unchanged_requires_runs_kit_prefix():
    files = [
        _file("runs/kit/REQ-1/src/foo.py"),
        _file("docs/harper/IDEA.md", VALID_IDEA),  # not allowed for kit
    ]
    result = normalize_local_agent_result(
        {"phase": "kit", "req_id": "REQ-1", "files": files, "exit_code": 0}
    )
    assert {f["path"] for f in result["files"]} == {"runs/kit/REQ-1/src/foo.py"}
    assert result["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in result["errors"]


def test_kit_accepts_only_runs_kit_prefix():
    result = normalize_local_agent_result(
        {
            "phase": "kit",
            "req_id": "REQ-1",
            "files": [_file("runs/kit/REQ-1/src/foo.py")],
            "exit_code": 0,
        }
    )
    assert result["ok"] is True
    assert {f["path"] for f in result["files"]} == {"runs/kit/REQ-1/src/foo.py"}


def test_idea_missing_required_output_fails_clearly():
    result = _normalize("idea", [], req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_required_outputs_missing" in result["errors"]
    # Must NOT report the misleading kit REQ-ID message for document phases.
    assert not any(e.startswith("no_candidate_files_returned_for") for e in result["errors"])
    assert any("docs/harper/IDEA.md" in w for w in result["warnings"])


def test_spec_missing_required_output_fails():
    result = _normalize("spec", [], req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_required_outputs_missing" in result["errors"]
    assert not any(e.startswith("no_candidate_files_returned_for") for e in result["errors"])


def test_plan_missing_plan_json_fails():
    result = _normalize("plan", [_file("docs/harper/PLAN.md", VALID_PLAN_MD)], req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_required_outputs_missing" in result["errors"]
    assert any("docs/harper/plan.json" in w for w in result["warnings"])


def test_kit_empty_still_reports_candidate_files_message():
    result = normalize_local_agent_result(
        {"phase": "kit", "req_id": "REQ-1", "files": [], "exit_code": 0}
    )
    assert result["ok"] is False
    assert "no_candidate_files_returned_for:REQ-1" in result["errors"]


# --- Completeness (non-skeletal) validation ---

def test_idea_headings_only_skeleton_is_rejected():
    skeleton = "\n".join(
        [
            "# IDEA — Demo",
            "## Vision",
            "## Problem Statement",
            "## Target Users & Context",
            "## Value & Outcomes",
            "## Out of Scope",
            "## Technology Constraints",
            "## Risks & Assumptions",
            "## Success Metrics",
            "",
        ]
    )
    result = _normalize("idea", [_file("docs/harper/IDEA.md", skeleton)], req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_output_incomplete" in result["errors"]
    assert any(w.startswith("idea:empty_section") for w in result["warnings"])
    assert any("missing_fenced_yaml" in w for w in result["warnings"])


def test_spec_with_too_few_acceptance_criteria_is_rejected():
    weak = VALID_SPEC.replace(
        "- Given a failure, when retried, then processing is idempotent.\n",
        "",
    ).replace(
        "- Given completion, when finished, then total processed count is reported.\n",
        "",
    )
    result = _normalize("spec", [_file("docs/harper/SPEC.md", weak)], req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_output_incomplete" in result["errors"]
    assert any(w.startswith("spec:acceptance_criteria_below_minimum") for w in result["warnings"])


def test_spec_missing_spec_end_is_rejected():
    no_end = VALID_SPEC.replace("SPEC_END\n", "")
    result = _normalize("spec", [_file("docs/harper/SPEC.md", no_end)], req_id="SOLUTION")
    assert result["ok"] is False
    assert "spec:missing_SPEC_END" in result["warnings"]


def test_plan_json_with_empty_acceptance_is_rejected():
    empty_acceptance = VALID_PLAN_JSON.replace(
        '"acceptance": ["Valid CSV produces one queue row per record"]',
        '"acceptance": []',
    )
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", empty_acceptance),
    ]
    result = _normalize("plan", files, req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_output_incomplete" in result["errors"]
    assert any("empty_acceptance" in w for w in result["warnings"])


def test_plan_md_without_req_ids_is_rejected():
    files = [
        _file("docs/harper/PLAN.md", "# PLAN — Demo\n\nNo requirements here.\n"),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),
    ]
    result = _normalize("plan", files, req_id="SOLUTION")
    assert result["ok"] is False
    assert "plan:missing_req_ids_in_plan_md" in result["warnings"]


def test_plan_md_req_missing_from_plan_json_is_rejected():
    # PLAN.md references REQ-1 and REQ-2 but plan.json only has REQ-1.
    plan_md = (
        "# PLAN — Demo\n\n"
        "## REQ-1 — Ingestion\nVerification checkpoints: tests.\n\n"
        "## REQ-2 — Reporting\nVerification checkpoints: tests.\n"
    )
    files = [
        _file("docs/harper/PLAN.md", plan_md),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),  # only REQ-1
    ]
    result = _normalize("plan", files, req_id="SOLUTION")
    assert result["ok"] is False
    assert "document_phase_output_incomplete" in result["errors"]
    assert any(
        w.startswith("plan:plan_md_reqs_missing_from_plan_json") and "REQ-2" in w
        for w in result["warnings"]
    )


def test_plan_accepts_lane_guides_alongside_plan_outputs():
    # Lane guides are accepted (not rejected) for /plan completion.
    files = [
        _file("docs/harper/PLAN.md", VALID_PLAN_MD),
        _file("docs/harper/plan.json", VALID_PLAN_JSON),
        _file("docs/harper/lane-guides/python.md", VALID_LANE),
        _file("docs/harper/lane-guides/sql.md", VALID_LANE),
    ]
    result = _normalize("plan", files, req_id="SOLUTION")
    assert result["ok"] is True
    paths = {f["path"] for f in result["files"]}
    assert "docs/harper/lane-guides/python.md" in paths
    assert "docs/harper/lane-guides/sql.md" in paths
