from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_core_blob(payload: Dict[str, Any], suffix: str) -> str:
    core_blobs = payload.get("core_blobs") or {}
    suffix_norm = suffix.lower().strip()

    for key, value in core_blobs.items():
        if str(key or "").lower().strip().endswith(suffix_norm):
            return str(value or "")

    return ""


def _extract_req_from_plan(payload: Dict[str, Any], req_id: str) -> Dict[str, Any]:
    plan_json_text = _extract_core_blob(payload, "plan.json")
    if not plan_json_text:
        return {"id": req_id}

    try:
        plan = json.loads(plan_json_text)
    except Exception:
        return {"id": req_id}

    reqs = plan.get("req") or plan.get("requirements") or []
    if not isinstance(reqs, list):
        return {"id": req_id}

    req_id_norm = req_id.upper()
    for item in reqs:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").upper() == req_id_norm:
            return item

    return {"id": req_id}


def build_kit_local_agent_package(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for base /kit.

    The extension is only allowed to:
    - write package files;
    - execute the configured local CLI;
    - collect stdout/stderr/exit code and candidate files;
    - send the result back to the orchestrator.
    """
    
    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"kit-local-{req_id}"
    local_executor = _safe_text(payload.get("localAgentExecutor")) or "auto"
    local_executor = local_executor.strip().lower()

    if local_executor in {"codex", "gpt-codex"}:
        local_executor = "gpt_codex"
    elif local_executor in {"claude", "claude-code"}:
        local_executor = "claude_code"
    elif local_executor == "auto":
        local_executor = "gpt_codex"

    req = _extract_req_from_plan(payload, req_id)

    allowed_write_roots = [
        f"runs/kit/{req_id}/src",
        f"runs/kit/{req_id}/test",
        f"runs/kit/{req_id}/ci",
        f"runs/kit/{req_id}/docs",
    ]

    forbidden_paths = [
        "src",
        "test",
        "tests",
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        ".git",
    ]
    local_runtime = payload.get("localRuntime") or {}
    if not isinstance(local_runtime, dict):
        local_runtime = {}

    local_runtime = {
        "shell": str(local_runtime.get("shell") or "zsh"),
        "python": str(local_runtime.get("python") or "python3"),
        "python_fallbacks": list(local_runtime.get("python_fallbacks") or ["python3", "python"]),
        "package_install_policy": str(
            local_runtime.get("package_install_policy") or "never_install_global_packages"
        ),
        "dependency_strategy": str(
            local_runtime.get("dependency_strategy") or "create_project_local_venv_or_report_blocked"
        ),
    }
    context = {
        "schema_version": "clike.local_agent_execution_context.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "kit",
        "run_id": run_id,
        "req_id": req_id,
        "executor_hint": local_executor,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_cloud_only_when_not_local_agent_only",
        },
        "workflow_owner": "orchestrator",
        "extension_role": "local_actuator_only",
        "local_runtime": local_runtime,
        "req": req,
        "project": {
            "project_id": payload.get("project_id"),
            "project_name": payload.get("project_name"),
            "doc_root": payload.get("docRoot") or "docs/harper",
            "workspace": payload.get("workspace") or {},
        },
        "inputs": {
            "idea_md_path": "docs/harper/IDEA.md",
            "spec_md_path": "docs/harper/SPEC.md",
            "plan_md_path": "docs/harper/PLAN.md",
            "plan_json_path": "docs/harper/plan.json",
            "lane_guides_path": "docs/harper/lane-guides",
        },
        "repository_analysis_required": {
            "must_read_plan": True,
            "must_read_plan_json": True,
            "must_identify_target_req_dependencies": True,
            "must_inspect_dependency_kits": True,
            "must_inspect_canonical_src": True,
            "must_inspect_canonical_tests": True,
            "dependency_kit_roots_pattern": "runs/kit/<DEPENDENCY_REQ_ID>",
            "canonical_source_roots": ["src"],
            "canonical_test_roots": ["test", "tests"],
            "purpose": (
                "Generate candidate code that is directly promotable and consistent "
                "with already generated dependency KITs and canonical promoted code."
            ),
        },
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "expected_outputs": {
            "required": [
                f"runs/kit/{req_id}/ci/LTC.json",
                f"runs/kit/{req_id}/ci/HOWTO.md",
            ],
            "recommended": [
                f"runs/kit/{req_id}/ci/requirements.txt",
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
        },
        "hard_rules": [
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
            "Do not commit, branch, push, tag, or open pull requests.",
            "Only write files under allowed_write_roots.",
            "Patch operations are allowed only under allowed_write_roots.",
            "Do not create or modify files outside runs/kit/<REQ-ID>/ for this phase.",
            "Do not install packages globally or into system Python.",
            "If declared tools/dependencies are missing, you may create a local virtualenv under .clike/eval-venvs or runs/kit/<REQ-ID>/.venv and install only from the REQ requirements file.",
            "Use local_runtime.python from this context for Python commands.",
            "If dependency installation is unavailable, report checks as environment-blocked and run compile/smoke checks.",
            "Never install undeclared packages; only install dependencies listed in the REQ requirements file.",
            "Before generating code, read docs/harper/PLAN.md and docs/harper/plan.json to identify the target REQ dependencies.",
            "Before generating code, inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when they exist.",
            "Before generating code, inspect canonical promoted source roots under src/ when they exist.",
            "Before generating tests, inspect canonical promoted test roots under test/ and tests/ when they exist.",
            "Generated code must be immediately promotable into canonical src/ and test roots without changing public contracts unexpectedly.",
            "Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical src/test roots.",
            "Reuse dependency KIT contracts and canonical source contracts whenever they exist.",
            "If a dependency KIT or canonical source root is missing, explicitly report it as an implementation assumption or gap.",
            "Produce repository-aware, dependency-aware, promotable candidate code and tests.",
            "Prefer minimal, verifiable changes aligned to the REQ acceptance criteria.",
        ],
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            "You are a local software-generation agent executing a CLike Harper /kit package.",
            "",
            "The orchestrator is the workflow owner. The VS Code extension is only the actuator.",
            "",
            "Read this file before acting:",
            f"- runs/kit/{req_id}/docs/AGENT_EXECUTION_CONTEXT.json",
            "",
            f"Target REQ: {req_id}",
            "",
            "Strict rules:",
            "- Follow AGENT_EXECUTION_CONTEXT.json as the primary execution contract.",
            f"""- Before writing any code, read docs/harper/PLAN.md and docs/harper/plan.json.
            - Identify the target REQ dependencies from the plan.
            - Inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when present.
            - Inspect canonical promoted source roots under src/ when present.
            - Inspect canonical promoted test roots under test/ and tests/ when present.
            - Reuse existing dependency KIT contracts and canonical source/test contracts.
            - Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical roots.
            - Generate candidate code that is directly promotable into canonical src/test roots.
            - If a dependency KIT, canonical source root, or canonical test root is missing, explicitly report the gap before generating the implementation.
            """
            "- Write only under the allowed candidate roots.",
            "- Do not modify canonical src/, test/, tests/ roots.",
            "- Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "- Do not perform git operations.",
            "- Do not promote candidate files into canonical workspace roots.",
            "",
            "Required candidate outputs:",
            f"- runs/kit/{req_id}/src/...",
            f"- runs/kit/{req_id}/test/...",
            f"- runs/kit/{req_id}/ci/LTC.json",
            f"- runs/kit/{req_id}/ci/HOWTO.md",
            "",
            "Recommended candidate outputs:",
            f"- runs/kit/{req_id}/ci/requirements.txt",
            f"- runs/kit/{req_id}/docs/README_{req_id}.md",
            f"- runs/kit/{req_id}/docs/KIT_{req_id}.md",
            "",
            "At the end, print a concise summary with:",
            "- target REQ and detected dependencies;",
            "- dependency KITs inspected;",
            "- canonical src/test roots inspected;",
            "- files created/updated;",
            "- existing contracts reused;",
            "- commands run;",
            "- tests/lint/type checks executed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
            "",
            f"""- Use the local runtime declared in AGENT_EXECUTION_CONTEXT.json.
            - Prefer `python3` when `python` is unavailable.
            - Do not install packages globally or into the system Python.\n- If declared tools/dependencies are missing, you may create a local virtualenv under `.clike/eval-venvs` or `runs/kit/<REQ-ID>/.venv` and install only from the REQ requirements file.
            - If pytest, ruff, mypy, or another declared dependency is missing, first use an existing project virtualenv if present; otherwise create a local virtualenv under `.clike/eval-venvs` or `runs/kit/<REQ-ID>/.venv` and install from the REQ requirements file.
            - If dependencies cannot be installed because the environment is offline, externally managed, or blocked by policy, report the test as environment-blocked and run dependency-free compile/smoke checks instead.
            - Patch operations are allowed only under the allowed_write_roots declared in AGENT_EXECUTION_CONTEXT.json.
            """
        ]
    )

    context_path = f"runs/kit/{req_id}/docs/AGENT_EXECUTION_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_PROMPT.md"

    return {
        "ok": True,
        "phase": "kit",
        "echo": f"Local agent execution package prepared for {req_id}",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
        ],
        "errors": [],
        "runId": run_id,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "phase_supported": execution_policy.get("phase_supported"),
        },
        "local_agent": {
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:kit",
            "phase": "kit",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": {
                "schema_version": "clike.local_agent_invocation.v1",
                "executor": local_executor,
                "command_ref": local_executor,
                "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
                "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
                "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
                "cwd": "."
            },
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "expected_outputs": context["expected_outputs"],
            "package_files": [
                {
                    "path": context_path,
                    "content": context_json,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": prompt_path,
                    "content": prompt,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
            ],
        },
    }

def build_eval_local_agent_package(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the orchestrator-owned local agent execution package for /eval pre-pass.

    The local agent is not the judge.
    It is allowed to harden candidate code/tests under runs/kit/<REQ-ID>/ only.
    Canonical CLike eval still runs after this pre-pass.
    """
    req_id = _safe_text(req_id).upper()
    run_id = _safe_text(payload.get("runId")) or f"eval-local-{req_id}"

    local_executor = _safe_text(payload.get("localAgentExecutor")) or "auto"
    local_executor = local_executor.strip().lower()

    if local_executor in {"codex", "gpt-codex"}:
        local_executor = "gpt_codex"
    elif local_executor in {"claude", "claude-code"}:
        local_executor = "claude_code"
    elif local_executor == "auto":
        local_executor = "gpt_codex"

    req = _extract_req_from_plan(payload, req_id)

    local_runtime = payload.get("localRuntime") or {}
    if not isinstance(local_runtime, dict):
        local_runtime = {}

    local_runtime = {
        "shell": str(local_runtime.get("shell") or "zsh"),
        "python": str(local_runtime.get("python") or "python3"),
        "python_fallbacks": list(local_runtime.get("python_fallbacks") or ["python3", "python"]),
        "package_install_policy": str(
            local_runtime.get("package_install_policy") or "never_install_global_packages"
        ),
        "dependency_strategy": str(
            local_runtime.get("dependency_strategy") or "create_project_local_venv_or_report_blocked"
        ),
    }

    allowed_write_roots = [
        f"runs/kit/{req_id}/src",
        f"runs/kit/{req_id}/test",
        f"runs/kit/{req_id}/ci",
        f"runs/kit/{req_id}/docs",
        f"runs/kit/{req_id}/reports",
    ]

    read_only_roots = [
        "docs/harper",
        "src",
        "test",
        "tests",
        "runs/kit",
    ]

    forbidden_paths = [
        "src",
        "test",
        "tests",
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        ".git",
    ]

    context = {
        "schema_version": "clike.local_agent_eval_context.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "eval",
        "run_id": run_id,
        "req_id": req_id,
        "executor_hint": local_executor,
        "workflow_owner": "orchestrator",
        "extension_role": "local_actuator_only",
        "agent_role": "pre_eval_hardener_only",
        "canonical_eval_owner": "clike",
        "local_runtime": local_runtime,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "fallback_policy": "extension_may_fallback_to_canonical_eval_only_when_not_local_agent_only",
        },
        "req": req,
        "project": {
            "project_id": payload.get("project_id"),
            "project_name": payload.get("project_name"),
            "doc_root": payload.get("docRoot") or "docs/harper",
            "workspace": payload.get("workspace") or {},
        },
        "inputs": {
            "idea_md_path": "docs/harper/IDEA.md",
            "spec_md_path": "docs/harper/SPEC.md",
            "plan_md_path": "docs/harper/PLAN.md",
            "plan_json_path": "docs/harper/plan.json",
            "lane_guides_path": "docs/harper/lane-guides",
            "ltc_json_path": f"runs/kit/{req_id}/ci/LTC.json",
            "howto_md_path": f"runs/kit/{req_id}/ci/HOWTO.md",
            "kit_notes_path": f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            "readme_path": f"runs/kit/{req_id}/docs/README_{req_id}.md",
        },
        "repository_analysis_required": {
            "must_read_plan": True,
            "must_read_plan_json": True,
            "must_identify_target_req_dependencies": True,
            "must_inspect_dependency_kits": True,
            "must_inspect_candidate_src": True,
            "must_inspect_candidate_tests": True,
            "must_inspect_candidate_ci": True,
            "must_inspect_canonical_src": True,
            "must_inspect_canonical_tests": True,
            "dependency_kit_roots_pattern": "runs/kit/<DEPENDENCY_REQ_ID>",
            "candidate_source_roots": [f"runs/kit/{req_id}/src"],
            "candidate_test_roots": [f"runs/kit/{req_id}/test"],
            "candidate_ci_roots": [f"runs/kit/{req_id}/ci"],
            "canonical_source_roots": ["src"],
            "canonical_test_roots": ["test", "tests"],
            "purpose": (
                "Harden candidate code and tests so canonical CLike eval can execute "
                "against promotable artifacts consistent with dependency KITs and canonical code."
            ),
        },
        "allowed_read_roots": read_only_roots,
        "allowed_write_roots": allowed_write_roots,
        "forbidden_paths": forbidden_paths,
        "expected_eval_inputs": {
            "required": [
                f"runs/kit/{req_id}/ci/LTC.json",
                f"runs/kit/{req_id}/ci/HOWTO.md",
                f"runs/kit/{req_id}/src",
                f"runs/kit/{req_id}/test",
            ],
            "recommended": [
                f"runs/kit/{req_id}/ci/requirements.txt",
                f"runs/kit/{req_id}/docs/README_{req_id}.md",
                f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
            ],
        },
        "allowed_test_doubles_policy": {
            "allowed": True,
            "scope": "tests_only",
            "allowed_for": [
                "external infrastructure boundaries",
                "object storage adapters",
                "queue adapters",
                "event transport adapters",
                "secret providers",
                "identity providers",
                "observability sinks",
                "network clients outside this candidate slice",
            ],
            "forbidden_for": [
                "business logic under test",
                "domain rules",
                "state transition rules",
                "validation rules",
                "public contracts being evaluated",
            ],
            "rule": (
                "Mocks and stubs are allowed only for external infrastructure boundaries "
                "and only inside candidate test files. They must not hide missing business logic."
            ),
        },
        "hard_rules": [
            "This is an eval pre-pass, not the canonical eval judge.",
            "After this pre-pass, CLike canonical /eval must still run and decide pass/fail.",
            "Do not modify canonical src/, test/, tests/ roots.",
            "Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "Do not run git commands.",
            "Do not commit, branch, push, tag, or open pull requests.",
            "Only write files under allowed_write_roots.",
            "Patch operations are allowed only under allowed_write_roots.",
            "Do not create or modify files outside runs/kit/<REQ-ID>/ for this phase.",
            "Do not install packages globally or into system Python.",
            "If declared tools/dependencies are missing, you may create a local virtualenv under .clike/eval-venvs or runs/kit/<REQ-ID>/.venv and install only from the REQ requirements file.",
            "Use local_runtime.python from this context for Python commands.",
            "If dependency installation is unavailable, report checks as environment-blocked and run compile/smoke checks.",
            "Never install undeclared packages; only install dependencies listed in the REQ requirements file.",
            "Before changing code, read docs/harper/PLAN.md and docs/harper/plan.json to identify target REQ dependencies.",
            "Before changing code, inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when they exist.",
            "Before changing code, inspect candidate source and test roots for this REQ.",
            "Before changing tests, inspect canonical promoted test roots under test/ and tests/ when they exist.",
            "Before changing code, inspect canonical promoted source roots under src/ when they exist.",
            "Generated or repaired code must be immediately promotable into canonical src/test roots without changing public contracts unexpectedly.",
            "Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical src/test roots.",
            "Reuse dependency KIT contracts and canonical source contracts whenever they exist.",
            "If tests are insufficient, extend tests under runs/kit/<REQ-ID>/test only.",
            "Mocks/stubs are allowed only for external infrastructure boundaries and only inside candidate tests.",
            "Do not mock the business logic under test.",
            "If a dependency KIT or canonical source root is missing, explicitly report it as an implementation assumption or gap.",
            "Produce repository-aware, dependency-aware, promotable candidate code and tests.",
            "Prefer minimal, verifiable repairs aligned to the REQ acceptance criteria.",
        ],
    }

    context_json = json.dumps(context, indent=2, ensure_ascii=False)

    prompt = "\n".join(
        [
            "You are a local software-generation agent executing a CLike Harper /eval pre-pass package.",
            "",
            "The orchestrator is the workflow owner. The VS Code extension is only the actuator.",
            "The canonical CLike eval remains the final judge and will run after your pre-pass.",
            "",
            "Read this file before acting:",
            f"- runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json",
            "",
            f"Target REQ: {req_id}",
            "",
            "Strict rules:",
            "- Follow AGENT_EVAL_CONTEXT.json as the primary execution contract.",
            "- This is an eval pre-pass: you may harden candidate code/tests, but you must not declare the final eval result.",
            "- Before writing anything, read docs/harper/PLAN.md and docs/harper/plan.json.",
            "- Identify the target REQ dependencies from the plan.",
            "- Inspect existing dependency KIT artifacts under runs/kit/<DEPENDENCY_REQ_ID>/ when present.",
            "- Inspect candidate source roots under runs/kit/<REQ-ID>/src.",
            "- Inspect candidate test roots under runs/kit/<REQ-ID>/test.",
            "- Inspect candidate CI/eval contracts under runs/kit/<REQ-ID>/ci, especially LTC.json and HOWTO.md.",
            "- Inspect canonical promoted source roots under src/ when present.",
            "- Inspect canonical promoted test roots under test/ and tests/ when present.",
            "- Reuse existing dependency KIT contracts and canonical source/test contracts.",
            "- Do not duplicate modules, adapters, ports, models, services, or test helpers already present in dependency KITs or canonical roots.",
            "- You may extend candidate tests if they are not exhaustive enough for the REQ acceptance criteria.",
            "- You may use mocks/stubs only inside candidate tests and only for external infrastructure boundaries.",
            "- Do not mock the business logic under test.",
            "- Write only under allowed_write_roots from AGENT_EVAL_CONTEXT.json.",
            "- Do not modify canonical src/, test/, tests/ roots.",
            "- Do not modify docs/harper/PLAN.md or docs/harper/plan.json.",
            "- Do not perform git operations.",
            "- Do not promote candidate files into canonical workspace roots.",
            "- Use the local runtime declared in AGENT_EVAL_CONTEXT.json.",
            "- Prefer `python3` when `python` is unavailable.",
            "- Do not install packages globally or into the system Python.\n- If declared tools/dependencies are missing, you may create a local virtualenv under `.clike/eval-venvs` or `runs/kit/<REQ-ID>/.venv` and install only from the REQ requirements file.",
            "- If pytest or another dependency is missing, first use an existing project virtualenv if present.",
            "- If dependencies cannot be installed because the environment is offline, externally managed, or blocked by policy, report the check as environment-blocked and run dependency-free compile/smoke checks instead.",
            "- Patch operations are allowed only under allowed_write_roots.",
            "",
            "Required eval actions:",
            f"- Read runs/kit/{req_id}/ci/LTC.json.",
            f"- Read runs/kit/{req_id}/ci/HOWTO.md when present.",
            f"- Inspect runs/kit/{req_id}/src and runs/kit/{req_id}/test.",
            "- Execute the LTC/HOWTO commands when possible.",
            "- Repair candidate code/tests under allowed_write_roots when checks fail for code reasons.",
            "- Create reports under runs/kit/<REQ-ID>/reports when useful.",
            "",
            "At the end, print a concise summary with:",
            "- target REQ and detected dependencies;",
            "- dependency KITs inspected;",
            "- canonical src/test roots inspected;",
            "- candidate files created/updated;",
            "- tests extended or added;",
            "- existing contracts reused;",
            "- commands run;",
            "- tests/lint/type checks executed;",
            "- checks passed;",
            "- checks blocked by environment, with exact reason;",
            "- unresolved gaps, if any.",
        ]
    )

    context_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_CONTEXT.json"
    prompt_path = f"runs/kit/{req_id}/docs/AGENT_EVAL_PROMPT.md"

    return {
        "ok": True,
        "phase": "eval",
        "echo": f"Local agent eval pre-pass package prepared for {req_id}",
        "text": "",
        "files": [],
        "diffs": [],
        "tests": {"passed": 0, "failed": 0, "summary": "local-agent-eval-package-prepared"},
        "warnings": [
            "execution_package:local_agent_required",
            "extension_role:local_actuator_only",
            "canonical_eval_still_required",
        ],
        "errors": [],
        "runId": run_id,
        "execution": {
            "requested": execution_policy.get("requested"),
            "selected": execution_policy.get("selected"),
            "reason": execution_policy.get("reason"),
            "phase_supported": execution_policy.get("phase_supported"),
        },
        "local_agent": {
            "action": "local_agent_required",
            "package_id": f"{run_id}:{req_id}:eval",
            "phase": "eval",
            "req_id": req_id,
            "executor_hint": local_executor,
            "context_path": context_path,
            "prompt_path": prompt_path,
            "prompt_content": prompt,
            "invocation": {
                "schema_version": "clike.local_agent_invocation.v1",
                "executor": local_executor,
                "command_ref": local_executor,
                "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
                "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
                "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
                "cwd": ".",
            },
            "allowed_write_roots": allowed_write_roots,
            "forbidden_paths": forbidden_paths,
            "expected_outputs": {
                "required": [
                    f"runs/kit/{req_id}/ci/LTC.json",
                    f"runs/kit/{req_id}/ci/HOWTO.md",
                ],
                "recommended": [
                    f"runs/kit/{req_id}/reports",
                    f"runs/kit/{req_id}/docs/KIT_{req_id}.md",
                    f"runs/kit/{req_id}/docs/README_{req_id}.md",
                ],
            },
            "package_files": [
                {
                    "path": context_path,
                    "content": context_json,
                    "mime": "application/json",
                    "encoding": "utf-8",
                },
                {
                    "path": prompt_path,
                    "content": prompt,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                },
            ],
        },
    }

def normalize_local_agent_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize the extension actuator result back into a Harper-compatible envelope.
    """
    phase = _safe_text(payload.get("phase")) or "kit"
    req_id = _safe_text(payload.get("req_id")).upper()
    run_id = _safe_text(payload.get("runId")) or _safe_text(payload.get("run_id"))

    files = payload.get("files") or []
    stdout = _safe_text(payload.get("stdout"))
    stderr = _safe_text(payload.get("stderr"))
    exit_code = payload.get("exit_code")

    expected_prefix = f"runs/kit/{req_id}/"
    bad_paths: List[str] = []
    normalized_files: List[Dict[str, Any]] = []

    for item in files:
        if not isinstance(item, dict):
            continue
        file_path = _safe_text(item.get("path"))
        content = item.get("content")
        if not file_path:
            continue
        if not file_path.startswith(expected_prefix):
            bad_paths.append(file_path)
            continue
        if isinstance(content, str):
            normalized_files.append(
                {
                    "path": file_path,
                    "content": content,
                    "mime": item.get("mime"),
                    "encoding": item.get("encoding") or "utf-8",
                }
            )

    errors: List[str] = []
    warnings: List[str] = [
        "execution_selected:local_agent",
        "local_agent_result:normalized_by_orchestrator",
    ]

    ok = True
    if exit_code not in (0, "0", None):
        ok = False
        errors.append(f"local_agent_exit_code:{exit_code}")

    if bad_paths:
        ok = False
        errors.append("local_agent_wrote_outside_allowed_roots")
        warnings.append("blocked_paths:" + ",".join(bad_paths[:20]))

    if not normalized_files:
        ok = False
        errors.append(f"no_candidate_files_returned_for:{req_id}")

    return {
        "ok": ok,
        "phase": phase,
        "echo": f"Local agent result normalized for {req_id}",
        "text": "\n".join(
            [
                "Local agent execution completed.",
                "",
                "STDOUT:",
                stdout[:4000],
                "",
                "STDERR:",
                stderr[:4000],
            ]
        ).strip(),
        "files": normalized_files,
        "diffs": [],
        "tests": {
            "passed": 0,
            "failed": 0 if ok else 1,
            "summary": "local-agent-normalized" if ok else "local-agent-normalization-failed",
        },
        "warnings": warnings,
        "errors": errors,
        "runId": run_id,
        "execution": {
            "requested": payload.get("executionPreference"),
            "selected": "local_agent",
            "reason": "extension_actuator_completed_and_orchestrator_normalized_result",
            "phase_supported": True,
        },
    }