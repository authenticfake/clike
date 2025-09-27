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

@router.post("/v1/kit/update-plan")
def kit_update_plan(plan_path: str = "PLAN.md", run_json: str = "", item_id: str = ""):
    p = Path(plan_path)
    if not p.exists():
        raise HTTPException(404, "PLAN.md not found")
    rep = {}
    if run_json:
        try:
            rep = json.loads(Path(run_json).read_text(encoding="utf8"))
        except Exception:
            rep = {}
    txt = p.read_text(encoding="utf8")
    marker = "## Progress"
    if marker not in txt:
        txt += f"\n\n{marker}\n"
    txt += f"- [{'x' if rep.get('failed',1)==0 else ' '}] {item_id or 'Batch'} — eval profile 'kit' passed={rep.get('failed',1)==0} (report: {run_json})\n"
    p.write_text(txt, encoding="utf8")
    return {"updated": True}

@router.post("/v1/constraints/sync")
def constraints_sync(md_path: str, out_dir: str = ".clike"):
    res = sync_constraints(md_path, out_dir)
    return res
