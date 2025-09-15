# Phase services (SPEC/PLAN/KIT) orchestrating prompts, evals and runs.
# Iterations: each call may update documents and re-run gates.
# Branching (future): for KIT change-requests, create feature branches per request.

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
import os, json

from services.gateway import GatewayClient
from services.router import select_profile
from services.evals import run_phase_gates, run_global_gates

RUNS_DIR = "runs"

def _new_run_id(phase: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{phase}"

def _ensure_run_dir(run_id: str) -> str:
    path = os.path.join(RUNS_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    return path

def generate_spec(idea_md: Optional[str]) -> Dict[str, Any]:
    run_id = _new_run_id("spec")
    rdir = _ensure_run_dir(run_id)
    profile = select_profile("spec", None)
    client = GatewayClient(); _ = (client, profile)  # TODO: wire actual prompt/messages

    spec_md = "# SPEC\n\n## 1) Business Context\n...\n## 2) Goals & Outcomes\n...\n## 3) Constraints\n...\n## 4) Non-Goals\n...\n## 5) Success Metrics\n...\n## 6) Assumptions & Risks\n...\n"
    open(os.path.join(rdir, "SPEC.md"), "w", encoding="utf-8").write(spec_md)

    pg = run_phase_gates()
    manifest = {"phase":"spec","run_id":run_id,"ok":pg.get("ok",True),"summary":pg.get("summary",{}),"profile":profile}
    open(os.path.join(rdir, "manifest.json"), "w", encoding="utf-8").write(json.dumps(manifest, indent=2))
    return {"spec_md": spec_md, "phase_ok": manifest["ok"], "phase_summary": manifest["summary"], "run_id": run_id}

def generate_plan(spec_md: str) -> Dict[str, Any]:
    run_id = _new_run_id("plan")
    rdir = _ensure_run_dir(run_id)
    profile = select_profile("plan", None)
    client = GatewayClient(); _ = (client, profile)

    plan_md = "| ID | Desc | Priority | Status | Deps | Notes |\n|---|---|---|---|---|---|\n"
    open(os.path.join(rdir, "PLAN.md"), "w", encoding="utf-8").write(plan_md)

    pg = run_phase_gates()
    manifest = {"phase":"plan","run_id":run_id,"ok":pg.get("ok",True),"summary":pg.get("summary",{}),"profile":profile}
    open(os.path.join(rdir, "manifest.json"), "w", encoding="utf-8").write(json.dumps(manifest, indent=2))
    return {"plan_md": plan_md, "phase_ok": manifest["ok"], "phase_summary": manifest["summary"], "run_id": run_id}

def generate_kit(spec_md: str, plan_md: str, todo_ids: Optional[List[str]]) -> Dict[str, Any]:
    run_id = _new_run_id("kit")
    rdir = _ensure_run_dir(run_id)
    profile = select_profile("kit", None)
    client = GatewayClient(); _ = (client, profile)

    kit_md = "# KIT\n\n## Deliverables\n...\n## How to Run\n...\n## How to Test & Validate\n...\n"
    open(os.path.join(rdir, "KIT.md"), "w", encoding="utf-8").write(kit_md)

    pg = run_phase_gates()
    manifest = {"phase":"kit","run_id":run_id,"ok":pg.get("ok",True),"summary":pg.get("summary",{}),"profile":profile,"todo_ids":todo_ids or []}
    open(os.path.join(rdir, "manifest.json"), "w", encoding="utf-8").write(json.dumps(manifest, indent=2))
    return {"kit_md": kit_md, "phase_ok": manifest["ok"], "phase_summary": manifest["summary"], "run_id": run_id}

def build_next(spec_md: str, plan_md: str, batch_size: int) -> Dict[str, Any]:
    run_id = _new_run_id("build")
    rdir = _ensure_run_dir(run_id)
    profile = select_profile("build", None)
    client = GatewayClient(); _ = (client, profile)

    # TODO: select next N TODOs, generate diffs and tests via prompts, apply patches (dry-run first)
    gg = run_global_gates()
    manifest = {"phase":"build","run_id":run_id,"ok":gg.get("ok",True),"summary":gg.get("summary",{}),"profile":profile,"batch_size":batch_size}
    open(os.path.join(rdir, "manifest.json"), "w", encoding="utf-8").write(json.dumps(manifest, indent=2))
    return {"updated_plan_md": plan_md, "diffs": [], "ok": manifest["ok"], "gate_summary": manifest["summary"], "run_id": run_id}
