from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from eval_runner import EvalReport, EvalRunner

router = APIRouter()
log = logging.getLogger("routes_eval")


class EvalRunRequest(BaseModel):
    profile: Optional[str] = None
    project_root: Optional[str] = None
    req_id: Optional[str] = None
    mode: Optional[str] = None
    verdict: Optional[str] = None
    ltc: Optional[Dict[str, Any]] = None
    project_name: Optional[str] = None

    class Config:
        extra = "ignore"


class GateCheckRequest(BaseModel):
    profile: Optional[str] = None
    project_root: Optional[str] = None
    mode: Optional[str] = "auto"
    verdict: Optional[str] = None
    req_id: Optional[str] = None
    promote: Optional[bool] = False
    ltc: Optional[Dict[str, Any]] = None
    project_name: Optional[str] = None

    class Config:
        extra = "ignore"


_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_project_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    value = name.strip()
    if not _PROJECT_NAME_RE.match(value):
        return None
    return value


def _resolve_project_root_from_env(project_name: Optional[str]) -> Optional[Path]:
    dev = os.getenv("DEV_FOLDER", "").strip()
    pname = _sanitize_project_name(project_name)
    if not dev or not pname:
        return None

    candidate = Path(dev) / pname
    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        return None
    return None


def _resolve_project_root(project_root: Optional[str], project_name: Optional[str]) -> Path:
    env_root = _resolve_project_root_from_env(project_name)
    if env_root is not None:
        return env_root

    if project_root:
        p = Path(project_root)
        return (p if p.is_absolute() else Path.cwd() / p).resolve()

    return Path.cwd().resolve()


def _manual_verdict(
    mode: Optional[str],
    body_verdict: Optional[str],
    query_verdict: Optional[str],
) -> Optional[str]:
    if (mode or "auto").lower() != "manual":
        return None
    return body_verdict or query_verdict


def _merge_eval_args(
    *,
    profile_q: Optional[str],
    project_root_q: Optional[str],
    project_name_q: Optional[str],
    mode_q: Optional[str],
    verdict_q: Optional[str],
    req_id_q: Optional[str],
    body: Optional[EvalRunRequest],
) -> EvalRunRequest:
    body = body or EvalRunRequest()
    mode = (body.mode or mode_q or "auto").lower()
    return EvalRunRequest(
        profile=body.profile or profile_q,
        project_root=body.project_root or project_root_q,
        mode=mode,
        verdict=_manual_verdict(mode, body.verdict, verdict_q),
        req_id=body.req_id or req_id_q,
        project_name=body.project_name or project_name_q,
        ltc=body.ltc if body.ltc else None,
    )


def _merge_gate_args(
    *,
    profile_q: Optional[str],
    project_root_q: Optional[str],
    project_name_q: Optional[str],
    mode_q: Optional[str],
    verdict_q: Optional[str],
    req_id_q: Optional[str],
    promote_q: Optional[bool],
    body: Optional[GateCheckRequest],
) -> GateCheckRequest:
    body = body or GateCheckRequest()
    mode = (body.mode or mode_q or "auto").lower()
    return GateCheckRequest(
        profile=body.profile or profile_q,
        project_root=body.project_root or project_root_q,
        mode=mode,
        verdict=_manual_verdict(mode, body.verdict, verdict_q),
        req_id=body.req_id or req_id_q,
        ltc=body.ltc if body.ltc else None,
        project_name=body.project_name or project_name_q,
        promote=bool(body.promote if body.promote is not None else promote_q),
    )


def _case_payload(case: Any) -> Dict[str, Any]:
    return {
        "name": case.name,
        "passed": case.passed,
        "code": case.code,
        "stdout": case.stdout,
        "stderr": case.stderr,
        "cmd": case.cmd,
        "cwd": case.cwd,
        "expect": case.expect,
        "blocked": case.blocked,
        "blocking": case.blocking,
    }


def _eval_payload(rep: EvalReport, req_id: Optional[str]) -> Dict[str, Any]:
    return {
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "status": rep.status,
        "passed": rep.status in {"PASS", "PASS_WITH_WARNINGS"},
        "failed": rep.failed,
        "passed_count": rep.passed,
        "blocked_count": rep.blocked,
        "warning_count": rep.warnings,
        "junit": rep.junit_path,
        "json": f"runs/eval/{req_id or rep.req_id or 'REQ-UNKNOWN'}",
        "cases": [_case_payload(c) for c in rep.cases],
    }


@router.post("/v1/eval/run")
def eval_run(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    project_name: Optional[str] = Query(default=None),
    payload: Optional[EvalRunRequest] = Body(default=None),
):
    args = _merge_eval_args(
        profile_q=profile,
        project_root_q=project_root,
        project_name_q=project_name,
        mode_q=mode,
        verdict_q=verdict,
        req_id_q=req_id,
        body=payload,
    )

    log.info(
        "eval_run profile=%s project_root=%s mode=%s req_id=%s project_name=%s inline_ltc=%s",
        args.profile,
        args.project_root,
        args.mode,
        args.req_id,
        args.project_name,
        bool(args.ltc),
    )

    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(
            status_code=422,
            detail="Provide either 'ltc' inline OR 'profile' + 'project_root'",
        )

    prj = _resolve_project_root(args.project_root, args.project_name)
    runner = EvalRunner(prj)

    try:
        rep = runner.run_profile(
            profile=args.profile or "LTC.json",
            ltc=args.ltc,
            mode=args.mode or "auto",
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("eval_run unexpected")
        raise HTTPException(status_code=500, detail=f"eval_run error: {exc}") from exc

    return _eval_payload(rep, args.req_id)


@router.post("/v1/gate/check")
def gate_check(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    promote: Optional[bool] = Query(default=False),
    project_name: Optional[str] = Query(default=None),
    payload: Optional[GateCheckRequest] = Body(default=None),
):
    args = _merge_gate_args(
        profile_q=profile,
        project_root_q=project_root,
        project_name_q=project_name,
        mode_q=mode,
        verdict_q=verdict,
        req_id_q=req_id,
        promote_q=promote,
        body=payload,
    )

    log.info(
        "gate_check profile=%s project_root=%s mode=%s req_id=%s promote=%s inline_ltc=%s",
        args.profile,
        args.project_root,
        args.mode,
        args.req_id,
        args.promote,
        bool(args.ltc),
    )

    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(
            status_code=422,
            detail="Provide either 'ltc' inline OR 'profile' + 'project_root'",
        )

    prj = _resolve_project_root(args.project_root, args.project_name)
    runner = EvalRunner(prj)

    try:
        rep = runner.run_profile(
            profile=args.profile or "LTC.json",
            ltc=args.ltc,
            mode=args.mode or "auto",
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("gate_check unexpected")
        raise HTTPException(status_code=500, detail=f"gate_check error: {exc}") from exc

    hard_gate = "PASS" if rep.status == "PASS" else "FAIL"

    reason_code = "GATE_PASS"
    if rep.status == "PASS_WITH_WARNINGS":
        reason_code = "GATE_BLOCKED_WARNINGS_PRESENT"
    elif rep.status == "FAIL":
        reason_code = "GATE_BLOCKED_FAILED_CHECKS"
    else:
        reason_code = f"GATE_BLOCKED_STATUS_{rep.status}"

    return {
        "gate": hard_gate,
        "status": rep.status,
        "reason_code": reason_code,
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "passed": rep.status == "PASS",
        "failed": rep.failed,
        "passed_count": rep.passed,
        "blocked_count": rep.blocked,
        "warning_count": rep.warnings,
        "json": f"runs/gate/{args.req_id or rep.req_id or 'REQ-UNKNOWN'}",
        "promote": bool(args.promote) if args.promote else None,
        "promote_info": None,
        "cases": [_case_payload(c) for c in rep.cases],
    }