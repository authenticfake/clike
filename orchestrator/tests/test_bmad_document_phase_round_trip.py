"""BMAD companions of the local document phases, end to end without any LLM.

The orchestrator package is built, a simulated agent "writes" the files the contract asks
for (a sample project on PostgreSQL), and the result goes through normalize exactly as the
extension sends it (methodology + methodology_agent, files read from disk).
"""

from services.local_agent_package import (
    build_document_phase_local_agent_package,
    normalize_local_agent_result,
)
from tests.test_document_phase_local_agent_package import (
    _bmad_vendor_core_blobs,
    _execution_policy,
)
from tests.test_normalize_local_agent_result_document_phase import (
    VALID_LANE,
    VALID_PLAN_JSON,
    VALID_PLAN_MD,
    VALID_SPEC,
)

PG_PRD = "# PRD\n\nOrders are stored in PostgreSQL 16 (schema `orders`, migrations with Alembic).\n"
PG_ARCH = "# Architecture\n\nAPI (FastAPI) -> PostgreSQL 16 via SQLAlchemy; one database per environment.\n"


def _package(phase, agent):
    return build_document_phase_local_agent_package(
        phase=phase,
        payload={
            "runId": f"{phase}-bmad",
            "methodology": "bmad",
            "agent": agent,
            "core_blobs": _bmad_vendor_core_blobs(),
        },
        execution_policy=_execution_policy(),
    )["local_agent"]


def _complete(package, files):
    contract = package["active_output_contract"]
    return normalize_local_agent_result(
        {
            "phase": package["phase"],
            "req_id": "SOLUTION",
            "runId": "bmad-run",
            "exit_code": 0,
            "methodology": contract.get("methodology"),
            "methodology_agent": contract.get("agent"),
            "files": [{"path": path, "content": content} for path, content in files.items()],
        }
    )


def test_spec_pm_package_opens_the_companion_root_and_completion_keeps_companions():
    package = _package("spec", "pm")
    assert "docs/harper/SPEC.md" in package["allowed_write_roots"]
    assert "docs/harper/bmad/spec" in package["allowed_write_roots"]

    out = _complete(
        package,
        {
            "docs/harper/SPEC.md": VALID_SPEC,
            "docs/harper/bmad/spec/PRD.md": PG_PRD,
            "docs/harper/bmad/spec/EPICS.md": "# Epics\n\nE1 orders persisted in PostgreSQL.\n",
        },
    )
    assert out["ok"] is True, out["errors"]
    paths = {f["path"] for f in out["files"]}
    assert {"docs/harper/bmad/spec/PRD.md", "docs/harper/bmad/spec/EPICS.md"} <= paths
    assert "bmad_companions_returned:2" in out["warnings"]
    assert any(w.startswith("bmad_companions_missing:") for w in out["warnings"])


def test_spec_ux_is_companion_only_no_spec_md():
    package = _package("spec", "ux")
    assert "docs/harper/SPEC.md" not in package["allowed_write_roots"]
    assert "docs/harper/ux" in package["allowed_write_roots"]

    ok = _complete(package, {"docs/harper/ux/DESIGN.md": "# Design\n\nForms backed by PostgreSQL.\n"})
    assert ok["ok"] is True, ok["errors"]

    forbidden = _complete(
        package,
        {"docs/harper/ux/DESIGN.md": "# Design\n", "docs/harper/SPEC.md": VALID_SPEC},
    )
    assert forbidden["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in forbidden["errors"]

    empty = _complete(package, {})
    assert empty["ok"] is False
    assert "document_phase_required_outputs_missing" in empty["errors"]


def test_plan_architect_keeps_architecture_companions():
    package = _package("plan", "architect")
    assert "docs/harper/bmad/architecture" in package["allowed_write_roots"]
    out = _complete(
        package,
        {
            "docs/harper/PLAN.md": VALID_PLAN_MD,
            "docs/harper/plan.json": VALID_PLAN_JSON,
            "docs/harper/lane-guides/backend.md": VALID_LANE,
            "docs/harper/bmad/architecture/ARCHITECTURE.md": PG_ARCH,
            "docs/harper/bmad/architecture/DECISIONS.md": "# ADR-001 PostgreSQL over SQLite\n",
        },
    )
    assert out["ok"] is True, out["errors"]
    assert "docs/harper/bmad/architecture/ARCHITECTURE.md" in {f["path"] for f in out["files"]}


def test_companions_outside_the_agent_policy_are_rejected():
    package = _package("plan", "architect")
    base = {
        "docs/harper/PLAN.md": VALID_PLAN_MD,
        "docs/harper/plan.json": VALID_PLAN_JSON,
    }
    for bad in (
        "docs/harper/bmad/plan/STORIES.md",          # the pm agent's root
        "docs/harper/bmad/architecture/schema.sql",  # not Markdown
        "docs/harper/bmad/architecture/../SPEC.md",  # traversal
        "docs/harper/SPEC.md",                       # forbidden canonical for /plan
    ):
        out = _complete(package, {**base, bad: "x"})
        assert out["ok"] is False, bad
        assert "local_agent_wrote_outside_allowed_roots" in out["errors"], bad


def test_client_cannot_widen_paths_with_an_unknown_agent():
    out = normalize_local_agent_result(
        {
            "phase": "spec",
            "req_id": "SOLUTION",
            "exit_code": 0,
            "methodology": "bmad",
            "methodology_agent": "architect",  # not allowed for /spec
            "files": [
                {"path": "docs/harper/SPEC.md", "content": VALID_SPEC},
                {"path": "docs/harper/bmad/architecture/ARCHITECTURE.md", "content": PG_ARCH},
            ],
        }
    )
    assert out["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in out["errors"]


def test_native_clike_still_rejects_companion_paths():
    out = normalize_local_agent_result(
        {
            "phase": "spec",
            "req_id": "SOLUTION",
            "exit_code": 0,
            "files": [
                {"path": "docs/harper/SPEC.md", "content": VALID_SPEC},
                {"path": "docs/harper/bmad/spec/PRD.md", "content": PG_PRD},
            ],
        }
    )
    assert out["ok"] is False
    assert "local_agent_wrote_outside_allowed_roots" in out["errors"]
