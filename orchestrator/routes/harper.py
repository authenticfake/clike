# FastAPI routes for Harper phases + utility endpoints.
from fastapi import APIRouter, HTTPException, Query
from services import harper as svc

import os, json

from schemas.harper import (
    SpecRequest, SpecResponse, PlanRequest, PlanResponse,
    KitRequest, KitResponse, BuildNextRequest, BuildNextResponse,
    SessionClearRequest, ModelsResponse, ProfilesResponse, DefaultsResponse,
    ResolveResponse
)
from services import harper as svc
from services.router import _load_cfg, resolve

router = APIRouter(prefix="/v1/harper", tags=["harper"])


@router.get("/health")
def health():
    return {"status":"ok","service":"orchestrator"}

@router.get("/version")
def version():
    return {"service":"orchestrator","version":"0.1.0"}

@router.get("/models", response_model=ModelsResponse)
def get_models():
    cfg = _load_cfg()
    return ModelsResponse(models=cfg.get("models") or [])

@router.get("/models/defaults", response_model=DefaultsResponse)
def get_models_defaults():
    cfg = _load_cfg()
    return DefaultsResponse(defaults=cfg.get("defaults") or {})

@router.get("/profiles", response_model=ProfilesResponse)
def get_profiles():
    cfg = _load_cfg()
    profs = list((cfg.get("profiles") or {}).keys())
    return ProfilesResponse(profiles=profs)

@router.get("/routing/resolve", response_model=ResolveResponse)
def get_routing_resolve(
    task: str = Query(..., pattern="^(spec|plan|kit|build|chat)$"),
    hint: str | None = None
):
    chosen, warnings = resolve(task=task, hint=hint)
    return ResolveResponse(task=task, hint=hint, chosen=chosen, warnings=warnings)

@router.post("/session/clear")
def session_clear(req: SessionClearRequest):
    # Placeholder: clear model sessions / caches; currently stateless
    return {"ok": True, "scope": req.scope}

@router.get("/runs/{run_id}")
def get_run(run_id: str):
    path = os.path.join("runs", run_id, "manifest.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(open(path, "r", encoding="utf-8").read())



# ... imports in testa restano uguali ...
from services import harper as svc

# --- SOSTITUISCI i 4 endpoint sottostanti ---

@router.post("/spec", response_model=SpecResponse)
async def post_spec(req: SpecRequest):
    out = await svc.run_phase("spec", req)
    # SPEC.md atteso in out.files/diffs a regime; qui esponiamo ok/run_id + echo
    return SpecResponse(
        spec_md=out.get("files", [{}])[0].get("content", "") if out.get("files") else req.idea_md or "# SPEC\n",
        ok=bool(out.get("ok", True)),
        violations=[],
        run_id=out.get("runId") or "n/a"
    )

@router.post("/plan", response_model=PlanResponse)
async def post_plan(req: PlanRequest):
    out = await svc.run_phase("plan", req)
    return PlanResponse(
        plan_md=out.get("files", [{}])[0].get("content", "") if out.get("files") else "# PLAN\n",
        ok=bool(out.get("ok", True)),
        violations=[],
        run_id=out.get("runId") or "n/a"
    )

@router.post("/kit", response_model=KitResponse)
async def post_kit(req: KitRequest):
    out = await svc.run_phase("kit", req)
    return KitResponse(
        kit_md=out.get("files", [{}])[0].get("content", "") if out.get("files") else "# KIT\n",
        artifacts={},
        ok=bool(out.get("ok", True)),
        violations=[],
        run_id=out.get("runId") or "n/a"
    )

@router.post("/build-next", response_model=BuildNextResponse)
async def post_build_next(req: BuildNextRequest):
    out = await svc.run_phase("build", req)
    return BuildNextResponse(
        updated_plan_md=req.plan_md,  # a regime puoi far ritornare il nuovo PLAN.md
        diffs=out.get("diffs", []),
        ok=bool(out.get("ok", True)),
        gate_summary=out.get("tests", {}),
        run_id=out.get("runId") or "n/a"
    )

