# FastAPI routes for Harper phases + utility endpoints.
from fastapi import APIRouter, HTTPException, Query
import os, json

from schemas.harper import (
    SpecRequest, SpecResponse, PlanRequest, PlanResponse,
    KitRequest, KitResponse, BuildNextRequest, BuildNextResponse,
    SessionClearRequest, ModelsResponse, ProfilesResponse, DefaultsResponse,
    ResolveResponse
)
from services import harper as svc
from services.router import _load_cfg, resolve

router = APIRouter(tags=["harper"])

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

@router.post("/spec", response_model=SpecResponse)
def post_spec(req: SpecRequest):
    out = svc.generate_spec(req.idea_md)
    return SpecResponse(spec_md=out["spec_md"], ok=out["phase_ok"],
                        violations=out.get("phase_summary", {}).get("violations", []),
                        run_id=out["run_id"])

@router.post("/plan", response_model=PlanResponse)
def post_plan(req: PlanRequest):
    out = svc.generate_plan(req.spec_md)
    return PlanResponse(plan_md=out["plan_md"], ok=out["phase_ok"],
                        violations=out.get("phase_summary", {}).get("violations", []),
                        run_id=out["run_id"])

@router.post("/kit", response_model=KitResponse)
def post_kit(req: KitRequest):
    out = svc.generate_kit(req.spec_md, req.plan_md, req.todo_ids)
    return KitResponse(kit_md=out["kit_md"], ok=out["phase_ok"],
                       violations=out.get("phase_summary", {}).get("violations", []),
                       run_id=out["run_id"])

@router.post("/build-next", response_model=BuildNextResponse)
def post_build_next(req: BuildNextRequest):
    out = svc.build_next(req.spec_md, req.plan_md, req.batch_size)
    return BuildNextResponse(updated_plan_md=out["updated_plan_md"], diffs=out["diffs"],
                             ok=out["ok"], gate_summary=out["gate_summary"], run_id=out["run_id"])
