# orchestrator/app/routes_eval.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from eval_runner import EvalRunner
from constraints.canonicalize import sync_constraints
import json

router = APIRouter()

@router.post("/v1/eval/run")
def eval_run(profile: str, project_root: str = "."):
    runner = EvalRunner(Path(project_root))
    rep = runner.run_profile(profile)
    return {
        "profile": rep.profile,
        "passed": rep.failed == 0,
        "failed": rep.failed,
        "passed_count": rep.passed,
        "junit": rep.junit_path,
        "json": rep.json_path,
        "cases": [{"name": c.name, "passed": c.passed} for c in rep.cases],
    }

@router.post("/v1/gate/check")
def gate_check(profile: str, project_root: str = "."):
    runner = EvalRunner(Path(project_root))
    rep = runner.run_profile(profile)
    return {"gate": "PASS" if rep.failed == 0 else "FAIL"}
