# orchestrator/app/routes_eval.py
from fastapi import APIRouter, Body, Query, HTTPException
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Dict, Optional, List
import logging

from eval_runner import EvalRunner, EvalReport  # vedi PATCH 2

router = APIRouter()
log = logging.getLogger("routes_eval")

# ------- Request models (accettano sia body che query per retro-compat) -------
class EvalRunRequest(BaseModel):
    profile: Optional[str] = None           # path LTC.json (relativo o assoluto)
    project_root: str = "."
    # opzionale: se in futuro vuoi collegare l’esito a un REQ specifico
    req_id: Optional[str] = None
    # modalità manuale (bypass esecuzione comandi)
    mode: Optional[str] = None            # "auto" (default) | "manual"
    verdict: Optional[str] = None           # "pass" | "fail" se manual
    ltc: Optional[Dict[str, Any]] = None  # <<< NEW: inline LTC.json



class GateCheckRequest(BaseModel):
    profile: str
    project_root: str = "."
    req_id: Optional[str] = None
    promote: Optional[bool] = False  # ignorato lato orchestrator per richiesta tua (promozione/aggiornamento restano alla estensione)


def _merge_args(profile_q: Optional[str], project_root_q: Optional[str], mode_q: Optional[str], verdict_q: Optional[str], req_id_q: Optional[str], body: Optional[EvalRunRequest]) -> EvalRunRequest:
    log.info("_merge_args profile_q=%s project_root_q=%s mode_q=%s verdict_q=%s req_id_q=%s", profile_q, project_root_q, mode_q, verdict_q, req_id_q)
    body = body or EvalRunRequest()
    
    runRequest = EvalRunRequest(
        profile = body.profile or profile_q,
        project_root = body.project_root or project_root_q,
        mode = (body.mode or mode_q or "auto").lower(),
        verdict = (body.verdict or verdict_q or None if (body.mode or mode_q) == "manual" else None),
        req_id = body.req_id or req_id_q,
        ltc=(body.ltc if body.ltc else None)

    )   
    log.info("*** _merge_args runRequest=%s", runRequest)

    return runRequest

# ------------------------------- /v1/eval/run -------------------------------
@router.post("/v1/eval/run")
def eval_run(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    payload: EvalRunRequest = Body(default=None)
):
    log.info("eval_run profile=%s project_root=%s mode=%s verdict=%s", profile, project_root, mode, verdict)
    
    #req = _coalesce_eval_req(req, profile, project_root)
    args = _merge_args(profile, project_root, mode, verdict, req_id, payload)
    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(status_code=422, detail="Provide either 'ltc' (inline) OR 'profile' + 'project_root'")


    log.info("eval_run profile=%s project_root=%s mode=%s verdict=%s", args.profile, args.project_root, args.mode, args.verdict)
    prj = Path(args.project_root or ".")
    prj = prj if prj.is_absolute() else (Path.cwd() / prj).resolve()
   
    runner = EvalRunner(prj)

    try:
        rep: EvalReport =  runner.run_profile(
            profile=args.profile,
            ltc=args.ltc,
            mode=args.mode,
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("eval_run unexpected")
        raise HTTPException(status_code=500, detail=f"eval_run error: {e}")


    return {
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "passed": rep.failed == 0,
        "failed": rep.failed,
        "passed_count": rep.passed,
        "junit": rep.junit_path,
        "json": rep.json_path,
        "cases": [{"name": c.name, "passed": c.passed, "code": c.code, "stdout": c.stdout, "stderr": c.stderr} for c in rep.cases],
    }

# ------------------------------ /v1/gate/check ------------------------------
@router.post("/v1/gate/check")
def gate_check(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    promote: Optional[bool] = Query(default=False),
    payload: GateCheckRequest = Body(default=None),
):
    args = _merge_args(profile, project_root, mode, verdict, req_id, payload)

    log.info("gate_check profile=%s project_root=%s req_id=%s promote=%s", args.profile, args.project_root, args.req_id, args.promote)
    if not profile:
        raise HTTPException(status_code=422, detail=[{"loc": ["profile"], "msg": "Field required"}])
    if not req_id:
        raise HTTPException(status_code=422, detail=[{"loc": ["req_id"], "msg": "Field required"}])

    
    prj = Path(args.project_root)
    runner = EvalRunner(prj)

    try:
        rep: EvalReport = runner.run_profile(
            profile=args.profile,
            mode=args.mode,
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("gate_check unexpected")
        raise HTTPException(status_code=500, detail=f"gate_check error: {e}")

    gate_result = "PASS" if rep.failed == 0 else "FAIL"

    promote_info = None

    return {
        "gate": gate_result,
        "profile": rep.profile,
        "req_id": rep.req_id,
        "passed": rep.failed == 0,
        "failed": rep.failed,
        "passed_count": rep.passed,
        "junit": rep.junit_path,
        "json": rep.json_path,
        "promote": bool(promote) if args.promote else None,
        "promote_info": promote_info if args.promote else None,
    }