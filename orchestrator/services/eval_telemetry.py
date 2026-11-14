"""Eval and gate runs in the telemetry portal.

An eval or a gate runs the REQ's checks in the eval sandbox, with no model: no provider call goes
through the gateway, so nothing recorded it and the portal showed the KIT and its repairs but not
the minutes of the evals between them. Each run the developer (or the --fix loop, the autopilot)
starts is recorded with its time and outcome; an agent's own runs while it writes a KIT are not
(their minutes are already the KIT's). Best effort: telemetry never delays or fails an eval.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

log = logging.getLogger("clike.eval_telemetry")

EXECUTION = "eval_sandbox"
_pending: Set["asyncio.Task[Any]"] = set()


def project_id(project_root: Path, project_name: Optional[str] = None) -> str:
    """The project id the extension uses (the workspace folder name, lower case, spaces as '-')."""
    name = str(project_name or project_root.name or "default").strip() or "default"
    return re.sub(r"\s+", "-", name).lower()


def build_record(
    project_root: Path,
    project_name: Optional[str],
    phase: str,
    payload: Dict[str, Any],
    started: float,
    scope: str,
) -> Dict[str, Any]:
    """The portal row of an eval / gate run (`scope`: full, targeted, checks, gate)."""
    timings = payload.get("timings") if isinstance(payload.get("timings"), dict) else {}
    outcome = {
        "scope": scope,
        "status": payload.get("gate") or payload.get("status"),
        "passed": payload.get("passed_count"),
        "failed": payload.get("failed"),
        "blocked": payload.get("blocked_count"),
        "warnings": payload.get("warning_count"),
        "regression": bool(payload.get("regression")),
        "checks_s": timings.get("checks_s"),
        "regression_s": timings.get("regression_s"),
        "regression_workers": timings.get("regression_workers"),
        "reused": bool(payload.get("reused_eval_at") or payload.get("reused_targeted_at")),
    }
    return {
        "project_id": project_id(project_root, project_name),
        "run_id": None,
        "phase": phase,
        "provider": EXECUTION,
        "model": None,
        "usage": {},
        "pricing": {},
        "duration_ms": round((time.monotonic() - started) * 1000),
        "executor": EXECUTION,
        "execution": EXECUTION,
        "req_id": str(payload.get("req_id") or "").strip() or None,
        "outcome": {k: v for k, v in outcome.items() if v is not None},
    }


async def _send(record: Dict[str, Any]) -> None:
    try:
        from services.harper import _post_json

        await _post_json("/v1/harper/telemetry", record)
    except Exception as exc:  # telemetry never fails an eval
        log.warning("eval telemetry not recorded: %s", type(exc).__name__)


def record(
    project_root: Path,
    project_name: Optional[str],
    phase: str,
    payload: Dict[str, Any],
    started: float,
    scope: str,
) -> None:
    """Send the row in the background: the eval answers at once."""
    try:
        row = build_record(project_root, project_name, phase, payload, started, scope)
        task = asyncio.get_running_loop().create_task(_send(row))
    except Exception as exc:  # no running loop, a malformed payload: never the eval's problem
        log.warning("eval telemetry skipped: %s", type(exc).__name__)
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)
