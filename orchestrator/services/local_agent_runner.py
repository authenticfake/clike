from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from services.local_agent_package import (
    build_kit_local_agent_package,
    normalize_local_agent_result,
)

log = logging.getLogger("service.router")


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_executor(value: Any) -> str:
    raw = _safe_text(value).lower()
    if raw in {"codex", "gpt_codex", "gpt-codex"}:
        return "gpt_codex"
    if raw in {"claude", "claude_code", "claude-code"}:
        return "claude_code"
    return ""


def _repo_root_from_payload(payload: Dict[str, Any]) -> str:
    repo_ctx = payload.get("repository_context") or {}
    repo_root = (
        repo_ctx.get("repo_root")
        or repo_ctx.get("workspace_folder")
        or payload.get("repo_root")
        or payload.get("workspace_root")
    )

    if not _safe_text(repo_root):
        raise RuntimeError("Missing repository_context.repo_root for local agent execution.")

    return _safe_text(repo_root)


def _runner_url() -> str:
    return os.getenv(
        "CLIKE_LOCAL_AGENT_RUNNER_URL",
        "http://host.docker.internal:8787/v1/local-agent/run",
    ).rstrip("/")


async def run_kit_via_local_agent_runner(
    *,
    payload: Dict[str, Any],
    req_id: str,
    execution_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Orchestrator-owned local-agent execution.

    Model 1 contract:
    Extension -> Orchestrator -> Workspace Agent Runner -> Agent -> Runner -> Orchestrator -> Extension.

    The VS Code extension must never spawn Claude/Codex directly.
    The runner is a dumb workspace-side actuator.
    The orchestrator owns policy, prompt, context, fallback, validation and normalization.
    """
    req_id = _safe_text(req_id).upper()
    local_executor = _safe_text(payload.get("localAgentExecutor")) or "auto"
    if local_executor in {"codex", "gpt-codex"}:
        local_executor = "gpt_codex"
    if local_executor in {"claude", "claude-code"}:
        local_executor = "claude_code"
    if local_executor == "auto":
        local_executor = "gpt_codex"

    executor = _normalize_executor(payload.get("localAgentExecutor"))
    if not executor:
        raise RuntimeError(
            "Missing concrete localAgentExecutor. Expected claude_code or gpt_codex."
        )

    package_envelope = build_kit_local_agent_package(
        payload={**payload, "localAgentExecutor": executor},
        req_id=req_id,
        execution_policy=execution_policy,
    )

    local_agent = package_envelope.get("local_agent") or {}
    repo_root = _repo_root_from_payload(payload)
    timeout_seconds = int(os.getenv("CLIKE_LOCAL_AGENT_TIMEOUT_SECONDS", "1800"))

    runner_payload = {
        "schema_version": "clike.local_agent_runner.request.v1",
        "phase": "kit",
        "req_id": req_id,
        "runId": payload.get("runId"),
        "repo_root": repo_root,
        "executor": executor,
        "timeout_seconds": timeout_seconds,
        "package_files": local_agent.get("package_files") or [],
        "prompt": local_agent.get("prompt_content") or "",
        "allowed_write_roots": local_agent.get("allowed_write_roots") or [],
        "forbidden_paths": local_agent.get("forbidden_paths") or [],
        "expected_outputs": local_agent.get("expected_outputs") or {},
    }

    url = _runner_url()

    log.info(
        "harper.local_agent orchestrator_call runner=%s req=%s executor=%s repo_root=%s",
        url,
        req_id,
        executor,
        repo_root,
    )

    timeout = httpx.Timeout(timeout_seconds + 30.0, connect=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=runner_payload)
        response.raise_for_status()
        runner_result = response.json()

    normalized = normalize_local_agent_result(
        {
            "phase": "kit",
            "req_id": req_id,
            "runId": payload.get("runId"),
            "executionPreference": payload.get("executionPreference"),
            "localAgentExecutor": executor,
            "exit_code": runner_result.get("exit_code"),
            "stdout": runner_result.get("stdout") or "",
            "stderr": runner_result.get("stderr") or "",
            "files": runner_result.get("files") or [],
        }
    )

    normalized["echo"] = f"Local agent {executor} executed by orchestrator for {req_id}"

    normalized["warnings"] = list(normalized.get("warnings") or []) + [
        "local_agent_called_by:orchestrator",
        f"local_agent_runner:{url}",
    ]

    normalized["execution"] = {
        "requested": execution_policy.get("requested"),
        "selected": "local_agent",
        "reason": execution_policy.get("reason"),
        "phase_supported": True,
        "executor": executor,
        "called_by": "orchestrator",
        "runner_url": url,
    }
    normalized["invocation"] =  {
                "schema_version": "clike.local_agent_invocation.v1",
                "executor": local_executor,
                "command_ref": local_executor,
                "args": ["exec"] if local_executor == "gpt_codex" else ["-p", "--permission-mode", "acceptEdits"],
                "prompt_transport": "stdin" if local_executor == "gpt_codex" else "argv_last",
                "timeout_seconds": int(payload.get("localAgentTimeoutSeconds") or 1800),
                "cwd": ".",
            },

    # Important: never return local_agent package to the extension.
    normalized.pop("local_agent", None)

    return normalized