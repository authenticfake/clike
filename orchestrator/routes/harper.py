# FastAPI routes for Harper phases + utility endpoints.
from typing import List, Union
from fastapi import APIRouter, HTTPException, Query
from services import harper as svc

import os, json, logging

from schemas.harper import (
    Attachment, DiffEntry, FileArtifact, HarperEnvelope, HarperRunResponse, SpecRequest, SpecResponse, PlanRequest, PlanResponse,
    KitRequest, KitResponse, BuildNextRequest, BuildNextResponse,
    SessionClearRequest, ModelsResponse, ProfilesResponse, DefaultsResponse,
    ResolveResponse, HarperPhaseRequest, HarperFlags, TestSummary
)
from services import harper as svc
from services.router import _load_cfg, resolve

router = APIRouter(prefix="/v1/harper", tags=["harper"])
log = logging.getLogger("orchestrator.harper")

def _normalize_attachments(atts: List[Union[str, Attachment]]) -> List[dict]:
    """Return a list of dicts with a stable shape for the gateway."""
    norm: List[dict] = []
    for a in atts or []:
        if isinstance(a, str):
            norm.append({"name": a})
        else:
            # pydantic BaseModel -> dict
            norm.append(a.model_dump())
    return norm

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


# ---- Endpoint SPEC ----------------------------------------------------------

@router.post("/spec")
async def post_spec(req: HarperPhaseRequest):
    """
    SPEC pass-through: preserva tutti i campi dal client, aggiunge solo 'phase' e
    lascia che il service risolva il modello. NON azzera idea_md/core/attachments/flags.
    """
    payload = req.model_dump()
    # Coerenza terminologica: manteniamo 'cmd' dal client ma imponiamo anche 'phase'
    payload["phase"] = "spec"
    payload.setdefault("cmd", "spec")

    # Normalizza attachments in una forma stabile (list[dict])
    payload["attachments"] = _normalize_attachments(req.attachments)

    log.info("run_phase spec (route): idea_md=%s core=%d attachments=%d flags=%s",
             bool(payload.get("idea_md")),
             len(payload.get("core") or []),
             len(payload.get("attachments") or []),
             "present" if payload.get("flags") else "none")

    # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
    out_dict = await svc.run_phase("spec", payload)
    # SPEC.md atteso in out.files/diffs a regime; qui esponiamo ok/run_id + echo
      
    out = HarperRunResponse(
        ok=bool(out_dict.get("ok", True)),
        phase=out_dict.get("phase") or "spec",
        echo=out_dict.get("echo"),
        text=out_dict.get("text"),
        files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
        tests=TestSummary(**(out_dict.get("tests") or {})),
        warnings=out_dict.get("warnings") or [],
        errors=out_dict.get("errors") or [],
        runId=out_dict.get("runId"),
        telemetry=out_dict.get("telemetry"),
    )
    # Retro-compat: spec_md, se disponibile (primo file markdown) oppure None
    spec_md = None
    if out.files:
        try:
            # se il primo file è SPEC.md lo esponiamo
            if out.files[0].path.lower().endswith("spec.md"):
                spec_md = out.files[0].content
        except Exception:
            pass

    return HarperEnvelope(out=out, spec_md=spec_md)
   

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

