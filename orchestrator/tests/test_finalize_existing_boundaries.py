"""Finalize reuses the promoted code (test project: the SQLite boundary already in src/ and an
env template with a project-named `SHORTLINK_DB_PATH` were rejected as a missing database
boundary). A boundary is evidence whether the agent returns it or leaves it unchanged."""

from services.local_agent.normalize import normalize_local_agent_result

_DB_PROFILE = {
    "services_detected": True,
    "detected_services": ["database"],
    "categories": {"database": True},
    "service_details": {"database": {"engines": ["sqlite"], "evidence": ["sqlite"]}},
}
_DB_ERRORS = {
    "finalize_database_env_placeholders_missing",
    "finalize_database_source_boundary_missing",
    "finalize_database_boundary_parked_in_todo",
}


def _finalize(env_example, existing=None, extra_files=()):
    files = [
        {"path": p, "content": "# doc\n"}
        for p in (
            "README.md",
            "docs/harper/HOWTO_RUN.md",
            "docs/harper/SANITY_CHECKS.md",
            "docs/harper/RELEASE_NOTES.md",
            "docs/harper/TODO_NEXT.md",
            "docs/harper/PR_BODY.md",
            "docs/harper/INFRA_READINESS.md",
            "scripts/check_runtime_services.sh",
            "scripts/check_runtime_services.ps1",
        )
    ]
    files.append({"path": ".env.example", "content": env_example})
    files.extend(extra_files)
    payload = {
        "phase": "finalize",
        "req_id": "SOLUTION",
        "exit_code": 0,
        "files": files,
        "runtime_service_profile": _DB_PROFILE,
    }
    if existing is not None:
        payload["existing_source_files"] = existing
    return normalize_local_agent_result(payload)


def _db_errors(result):
    return _DB_ERRORS & set(result.get("errors") or [])


def test_an_unchanged_sqlite_boundary_and_a_project_named_db_variable_are_accepted():
    result = _finalize(
        "SHORTLINK_DB_PATH=\nSHORTLINK_PORT=8000\n",
        existing=[{"path": "src/shortlink/storage.py", "content": "import sqlite3\n"}],
    )
    assert _db_errors(result) == set()


def test_a_returned_boundary_is_still_accepted_without_existing_sources():
    result = _finalize(
        "DATABASE_URL=<placeholder>\n",
        extra_files=[{"path": "src/app/db.py", "content": "engine = create_engine(DATABASE_URL)\n"}],
    )
    assert _db_errors(result) == set()


def test_no_database_variable_and_no_boundary_anywhere_is_still_rejected():
    result = _finalize(
        "APP_PORT=8000\nAPP_DEBUG_ROOT=x\n",
        existing=[{"path": "src/app/main.py", "content": "print('hello')\n"}],
    )
    assert _db_errors(result) == {
        "finalize_database_env_placeholders_missing",
        "finalize_database_source_boundary_missing",
    }
