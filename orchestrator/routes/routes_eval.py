# orchestrator/app/routes_eval.py
import os
import re
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
    profile: Optional[str] = None
    project_root: str = "."
    req_id: Optional[str] = None
    mode: Optional[str] = None
    verdict: Optional[str] = None
    ltc: Optional[Dict[str, Any]] = None  
    project_name: Optional[str] = None  



class GateCheckRequest(BaseModel):
    
    profile: Optional[str] = None
    project_root: Optional[str] = None
    mode: Optional[str] = "auto"      # "auto" | "manual"
    verdict: Optional[str] = None     # when mode=="manual"
    req_id: Optional[str] = None
    promote: Optional[bool] = False
    ltc: Optional[Dict[str, Any]] = None  # INLINE LTC SUPPORT
    project_name: Optional[str] = None  

    class Config:
        extra = "ignore"


_PROJECT_NAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')  # niente slash, niente traversal

def _sanitize_project_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    name = name.strip()
    if not _PROJECT_NAME_RE.match(name):
        return None
    return name

def _resolve_project_root_from_env(project_name: Optional[str]) -> Optional[Path]:
    """
    If DEV_FOLDER is set and project_name is safe, return DEV_FOLDER / project_name, if it exists.
    """
    dev = os.getenv('DEV_FOLDER', '').strip()
    pname = _sanitize_project_name(project_name)
    if not dev or not pname:
        return None
    base = Path(dev)
    candidate = (base / pname)
    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        return None
    return None


def _merge_args(profile_q: Optional[str], project_root_q: Optional[str],project_name_q: Optional[str], mode_q: Optional[str], verdict_q: Optional[str], req_id_q: Optional[str], body: Optional[EvalRunRequest]) -> EvalRunRequest:
    log.info("_merge_args profile_q=%s project_root_q=%s mode_q=%s verdict_q=%s req_id_q=%s", profile_q, project_root_q, mode_q, verdict_q, req_id_q)
    body = body or EvalRunRequest()
    
    runRequest = EvalRunRequest(
        profile = body.profile or profile_q,
        project_root = body.project_root or project_root_q,
        mode = (body.mode or mode_q or "auto").lower(),
        verdict = (body.verdict or verdict_q or None if (body.mode or mode_q) == "manual" else None),
        req_id = body.req_id or req_id_q,
        project_name = body.project_name or project_name_q,
        ltc=(body.ltc if body.ltc else None)

    )   
    log.info("*** _merge_args runRequest=%s", runRequest)

    return runRequest
def _merge_args_check(profile_q: Optional[str], project_root_q: Optional[str], project_name_q: Optional[str], mode_q: Optional[str], verdict_q: Optional[str], req_id_q: Optional[str], body: Optional[GateCheckRequest]) -> EvalRunRequest:
    log.info("_merge_args profile_q=%s project_root_q=%s mode_q=%s verdict_q=%s req_id_q=%s", profile_q, project_root_q, mode_q, verdict_q, req_id_q)
    body = body or GateCheckRequest()
    
    runRequest = GateCheckRequest(
        profile = body.profile or profile_q,
        project_root = body.project_root or project_root_q,
        mode = (body.mode or mode_q or "auto").lower(),
        verdict = (body.verdict or verdict_q or None if (body.mode or mode_q) == "manual" else None),
        req_id = body.req_id or req_id_q,
        ltc=(body.ltc if body.ltc else None),
        project_name = body.project_name or project_name_q,
        promote=body.promote

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
    project_name: Optional[str] = Query(default=None),
    payload: EvalRunRequest = Body(default=None)
):
    log.info("eval_run profile=%s project_root=%s mode=%s verdict=%s", profile, project_root, mode, verdict)
    
    #req = _coalesce_eval_req(req, profile, project_root)
    args = _merge_args(profile, project_root, project_name,mode, verdict, req_id, payload)
    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(status_code=422, detail="Provide either 'ltc' (inline) OR 'profile' + 'project_root'")
    log.info("eval_run profile=%s project_root=%s mode=%s verdict=%s", args.profile, args.project_root, args.mode, args.verdict)
    
    # 1) prova con DEV_FOLDER + project_name
    prj = _resolve_project_root_from_env(args.project_name)
    # 2) se non risolto, usa project_root (se passato)
    if prj is None and args.project_root:
        p = Path(args.project_root)
        prj = p if p.is_absolute() else (Path.cwd() / p)
        prj = prj.resolve()
    

    # 3) se ancora nulla ma c'è un bundle inline (se lo supporti), lo estrai come abbiamo visto a parte
    # if prj is None and args.bundle_b64: prj = _extract_zip_base64(...)

    # 4) fallback: current working dir (non consigliato, ma evita crash)
    if prj is None:
        prj = Path.cwd().resolve()

    
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
        "json": 'runs/eval/' + args.req_id,
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
    project_name: Optional[str] = Query(default=None),

    payload: GateCheckRequest = Body(default=None),
):
    log.info("gate_check profile=%s project_root=%s mode=%s verdict=%s promote=%s", profile, project_root, mode, verdict, promote)
    args = _merge_args_check(profile, project_root, project_name, mode, verdict, req_id, payload)

    log.info("gate_check profile=%s project_root=%s req_id=%s promote=%s", args.profile, args.project_root, args.req_id, args.promote)
    # ... hai già 'req' con i campi merge da query+body
    if not args.ltc and (not  args.profile or not args.project_root):
        # accetta EITHER ltc inline OR path+root
        raise HTTPException(status_code=422, detail="Provide either 'ltc' (inline) OR 'profile' + 'project_root'")
    

    
    prj = Path(args.project_root)
    runner = EvalRunner(prj)

    try:
        rep: EvalReport = runner.run_profile(
            ltc=args.ltc,
            profile=args.profile,
            mode=args.mode,
            verdict=args.verdict,
            req_id=args.req_id,
        )
        log.info("gate_check rep=%s", rep)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("gate_check unexpected")
        raise HTTPException(status_code=500, detail=f"gate_check error: {e}")
    log.info("gate_check rep=%s", rep)
    gate_result = "PASS" if rep.failed == 0 else "FAIL"

    promote_info = None
    log.info("gate_check rep mode=%s", rep.mode)

    return {
        "gate": gate_result,
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "passed": rep.passed,
        "failed": rep.failed,
        "passed_count": rep.passed,
        "json": 'runs/gate/' + args.req_id,
        "promote": bool(promote) if args.promote else None,
        "promote_info": promote_info if args.promote else None,
    }