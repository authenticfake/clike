# FastAPI routes for Harper phases + utility endpoints.
from typing import List, Union
from fastapi import APIRouter, HTTPException, Query
from services import harper as svc

import os, json, logging

from schemas.harper import (
    Attachment, DiffEntry, FileArtifact, HarperEnvelope, HarperRunResponse, 
    SessionClearRequest, ModelsResponse, ProfilesResponse, DefaultsResponse,
    ResolveResponse, HarperPhaseRequest, TestSummary
)
from services.router import _load_cfg, resolve, resolve_explain
from services.methodologies.errors import MethodologyError
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
    hint: str | None = None,
    model: str | None = "auto",
    provider: str | None = None,
):
    explained = resolve_explain(task=task, hint=hint, model=model, provider=provider)
    chosen = dict(explained.get("catalog_entry") or {})
    resolved = explained.get("resolved") or {}

    if resolved.get("model"):
        chosen.setdefault("id", resolved["model"])
        chosen.setdefault("name", chosen.get("name") or resolved["model"])
    if resolved.get("provider"):
        chosen["provider"] = resolved["provider"]
    if resolved.get("remote_name"):
        chosen["remote_name"] = resolved["remote_name"]
    if resolved.get("profile"):
        chosen["profile"] = resolved["profile"]

    return ResolveResponse(
        task=task,
        hint=hint,
        chosen=chosen,
        warnings=[],
    )
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
    # --- PATCH START ---
    log.info("run_phase %s: idea_md=%s core=%s attachments=%s messages=%s",
         req.phase, bool(req.idea_md), len(req.core), len(req.attachments), len(req.messages))
# --- PATCH END ---


    # Normalizza attachments in una forma stabile (list[dict])
    payload["attachments"] = _normalize_attachments(req.attachments)

    repo_ctx = payload.get("repository_context") or {}
    log.info(
        "run_phase spec (route): idea_md=%s core=%d attachments=%d flags=%s git_detected=%s repo_root=%s branch=%s",
        bool(payload.get("idea_md")),
        len(payload.get("core") or []),
        len(payload.get("attachments") or []),
        bool(payload.get("flags")),
        repo_ctx.get("git_detected"),
        repo_ctx.get("repo_root"),
        repo_ctx.get("branch"),
    )

    # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
    out_dict = await svc.run_phase("spec", payload)
    # SPEC.md atteso in out.files/diffs a regime; qui esponiamo ok/run_id + echo
      
    out = HarperRunResponse(
        ok=bool(out_dict.get("ok", True)),
        phase=out_dict.get("phase") or "spec",
        echo=out_dict.get("echo"),
        text=out_dict.get("text"),
        files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
        diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
        tests=TestSummary(**(out_dict.get("tests") or {})),
        warnings=out_dict.get("warnings") or [],
        errors=out_dict.get("errors") or [],
        error_code=out_dict.get("error_code"),
        rejected=out_dict.get("rejected") or [],
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


@router.post("/idea", response_model=HarperEnvelope)
async def post_idea(req: HarperPhaseRequest):
    
    payload = req.model_dump()
    # Coerenza terminologica: manteniamo 'cmd' dal client ma imponiamo anche 'phase'
    payload["phase"] = "idea"
    payload.setdefault("cmd", "idea")
    log.info("run_phase idea (route) core=%d attachments=%d flags=%s",
            len(payload.get("core") or []),
            len(payload.get("attachments") or []),
            "present" if payload.get("flags") else "none")

    # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
    out_dict = await svc.run_phase("idea", payload)
    out = None
    try: 
        out = HarperRunResponse(
            ok=bool(out_dict.get("ok", True)),
            phase=out_dict.get("phase") or "idea",
            echo=out_dict.get("echo"),
            text=out_dict.get("text"),
            files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
            diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
            tests=TestSummary(**(out_dict.get("tests") or {})),
            warnings=out_dict.get("warnings") or [],
            errors=out_dict.get("errors") or [],
            error_code=out_dict.get("error_code"),
            rejected=out_dict.get("rejected") or [],
            runId=out_dict.get("runId"),
            telemetry=out_dict.get("telemetry"),
        )

    
    except MethodologyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.info( "Error in idea phase %s", e)
        raise HTTPException(status_code=500, detail="Error in idea phase")    
    
    log.info("out text: %s len=%d",out.text,len(out.text))
    # Retro-compat: spec_md, se disponibile (primo file markdown) oppure None
    plan_md = None
    if out.files:
        try:
            # se il primo file è SPEC.md lo esponiamo
            if out.files[0].path.lower().endswith("plan.md"):
                plan_md = out.files[0].content
        except Exception:
            pass

    return HarperEnvelope(out=out, plan_md=plan_md)

@router.post("/plan", response_model=HarperEnvelope)
async def post_plan(req: HarperPhaseRequest):
    
    payload = req.model_dump()
    # Coerenza terminologica: manteniamo 'cmd' dal client ma imponiamo anche 'phase'
    payload["phase"] = "plan"
    payload.setdefault("cmd", "plan")
    log.info("run_phase spec (route): idea_md=%s spec_md=%s core=%d attachments=%d flags=%s",
            bool(payload.get("idea_md")),
            bool(payload.get("spec_md")),
            len(payload.get("core") or []),
            len(payload.get("attachments") or []),
            "present" if payload.get("flags") else "none")

    out = None
    try: 
        # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
        out_dict = await svc.run_phase("plan", payload)
        
        log.info("post_plan out files len: %s", len(out_dict.get("files")));

        out = HarperRunResponse(
            ok=bool(out_dict.get("ok", True)),
            phase=out_dict.get("phase") or "plan",
            echo="Plan phase: %s" % out_dict.get("echo"),
            text=out_dict.get("text"),
            files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
            diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
            tests=TestSummary(**(out_dict.get("tests") or {})),
            warnings=out_dict.get("warnings") or [],
            errors=out_dict.get("errors") or [],
            error_code=out_dict.get("error_code"),
            rejected=out_dict.get("rejected") or [],
            runId=out_dict.get("runId"),
            usage=out_dict.get("usage"),
            execution=out_dict.get("execution"),
            local_agent=out_dict.get("local_agent"),
            telemetry=out_dict.get("telemetry"),
        )
        log.info("inside try out files len: %s", len(out_dict.get("files")));

    except MethodologyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as e:
        log.info( "Error in plan phase %s", e)
        raise HTTPException(status_code=500, detail="Error in plan phase")    
    
    log.info("out text: %s len=%d",out.text,len(out.text))
    plan_md = None
    if out.files:
        try:
            # se il primo file è PLAN.md lo esponiamo
            if out.files[0].path.lower().endswith("plan.md"):
                plan_md = out.files[0].content
        except Exception:
            pass
    return HarperEnvelope(out=out, plan_md=plan_md)


@router.post("/extend", response_model=HarperEnvelope)
async def post_extend(req: HarperPhaseRequest):
    """
    Harper EXTEND phase.

    Append new REQs to an existing PLAN.md/plan.json without rewriting
    consolidated requirements. SPEC.md and lane-guides may be updated only
    when the extension introduces new capability scope or lane guidance.
    """
    payload = req.model_dump()
    payload["phase"] = "extend"
    payload.setdefault("cmd", "extend")
    payload["attachments"] = _normalize_attachments(req.attachments)

    repo_ctx = payload.get("repository_context") or {}
    extend_opts = payload.get("extend") or payload.get("gen") or {}

    log.info(
        "run_phase extend (route): plan_md=%s spec_md=%s core=%d attachments=%d anchor=%s explicit_req=%s git_detected=%s repo_root=%s branch=%s",
        bool(payload.get("plan_md")),
        bool(payload.get("spec_md")),
        len(payload.get("core") or []),
        len(payload.get("attachments") or []),
        extend_opts.get("anchorReq") or extend_opts.get("anchor_req"),
        extend_opts.get("explicitReq") or extend_opts.get("explicit_req"),
        repo_ctx.get("git_detected"),
        repo_ctx.get("repo_root"),
        repo_ctx.get("branch"),
    )

    try:
        out_dict = await svc.run_phase("extend", payload)
        out = HarperRunResponse(
            ok=bool(out_dict.get("ok", True)),
            phase=out_dict.get("phase") or "extend",
            echo=out_dict.get("echo"),
            text=out_dict.get("text"),
            files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
            diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
            tests=TestSummary(**(out_dict.get("tests") or {})),
            warnings=out_dict.get("warnings") or [],
            errors=out_dict.get("errors") or [],
            error_code=out_dict.get("error_code"),
            rejected=out_dict.get("rejected") or [],
            runId=out_dict.get("runId"),
            usage=out_dict.get("usage"),
            execution=out_dict.get("execution"),
            local_agent=out_dict.get("local_agent"),
            telemetry=out_dict.get("telemetry"),
        )
        return HarperEnvelope(out=out)
    except MethodologyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Error in extend phase: %s", exc)
        raise HTTPException(status_code=500, detail="Error in extend phase") from exc


@router.post("/kit", response_model=HarperEnvelope)
async def post_kit(req: HarperPhaseRequest):
    payload = req.model_dump()
    # Coerenza terminologica: manteniamo 'cmd' dal client ma imponiamo anche 'phase'
    payload["phase"] = "kit"
    payload.setdefault("cmd", payload["phase"])
    repo_ctx = payload.get("repository_context") or {}
    kit_opts = payload.get("kit") or {}
    log.info(
        "run_phase kit (route): targets=%s phases=%s executionPreference=%s",
        kit_opts.get("targets"),
        kit_opts.get("phases") or ["kit"],
        payload.get("executionPreference"),
    )

    log.info(
        "run_phase kit (route): idea_md=%s  plan_md=%s kit_md=%s core=%d gen=%s attachments=%d flags=%s",
        bool(payload.get("idea_md")),
        bool(payload.get("plan_md")),
        bool(payload.get("kit_md")),
        len(payload.get("core") or []),
        bool(payload.get("gen")),
        len(payload.get("attachments") or []),
        "present" if payload.get("flags") else "none",
    )

    log.info(
        "run_phase kit (route): git_detected=%s repo_root=%s branch=%s repo_url=%s",
        repo_ctx.get("git_detected"),
        repo_ctx.get("repo_root"),
        repo_ctx.get("branch"),
        repo_ctx.get("repo_url"),
    )

    try:
        # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
        out_dict = await svc.run_phase("kit", payload)

        out = HarperRunResponse(
            ok=bool(out_dict.get("ok", True)),
            phase=out_dict.get("phase") or "kit",
            echo=out_dict.get("echo"),
            text=out_dict.get("text"),
            files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
            diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
            tests=TestSummary(**(out_dict.get("tests") or {})),
            warnings=out_dict.get("warnings") or [],
            errors=out_dict.get("errors") or [],
            error_code=out_dict.get("error_code"),
            rejected=out_dict.get("rejected") or [],
            runId=out_dict.get("runId"),
            usage=out_dict.get("usage"),
            execution=out_dict.get("execution"),
            local_agent=out_dict.get("local_agent"),
            telemetry=out_dict.get("telemetry"),
        )
        if out_dict.get("local_agent"):
            log.info(
                "run_phase kit (route): returning local_agent package action=%s req=%s executor_hint=%s package_files=%d",
                (out_dict.get("local_agent") or {}).get("action"),
                (out_dict.get("local_agent") or {}).get("req_id"),
                (out_dict.get("local_agent") or {}).get("executor_hint"),
                len((out_dict.get("local_agent") or {}).get("package_files") or []),
            )
        execution = out_dict.get("execution") or {}
        requested_pref = payload.get("executionPreference")
        actual_selected = execution.get("selected")
        actual_reason = execution.get("reason")

        if requested_pref and actual_selected:
            log.info(
                "run_phase kit (route): executionPreference=%s selected=%s reason=%s",
                requested_pref,
                actual_selected,
                actual_reason,
            )

            if actual_selected != "local_agent" and requested_pref in {"prefer_local_agent", "prefer_claude_code"}:
                out.warnings = list(out.warnings or [])
                out.warnings.append(
                    f"Execution preference '{requested_pref}' fell back to '{actual_selected}' ({actual_reason or 'no reason provided'})."
                )

    except MethodologyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)

        prefix = "Gateway upstream error "
        if msg.startswith(prefix):
            rest = msg[len(prefix):]
            status_str, sep, detail = rest.partition(":")
            if sep:
                try:
                    status_code = int(status_str.strip())
                except ValueError:
                    status_code = 502

                raise HTTPException(
                    status_code=status_code,
                    detail=detail.strip() or msg,
                )

        raise HTTPException(status_code=502, detail=msg)

    except Exception as exc:
        log.exception("Error in kit phase: %s", exc)
        raise HTTPException(status_code=500, detail="Error in kit phase")

    # Retro-compat: kit_md, se disponibile (primo file markdown) oppure None
    kit_md = None
    if out.files:
        try:
            if out.files[0].path.lower().endswith("kit.md"):
                kit_md = out.files[0].content
        except Exception:
            pass

    return HarperEnvelope(out=out, kit_md=kit_md)

@router.post("/finalize", response_model=HarperEnvelope)
async def post_build_next(req: HarperPhaseRequest):
    payload = req.model_dump()
    # Coerenza terminologica: manteniamo 'cmd' dal client ma imponiamo anche 'phase'
    payload["phase"] = "finalize"
    payload.setdefault("cmd", payload["phase"])
    log.info("run_phase finalize (route): idea_md=%s spec_md=%s plan_md=%s kit_md=%s build_report_md=%s release_notes_md=%s core=%d attachments=%d flags=%s",
            bool(payload.get("idea_md")),
            bool(payload.get("spec_md")),
            bool(payload.get("plan_md")),
            bool(payload.get("kit_md")),
            bool(payload.get("build_report_md")),
            bool(payload.get("release_notes_md")),
            len(payload.get("core") or []),
            len(payload.get("attachments") or []),
            "present" if payload.get("flags") else "none")

    # Delego al service che farà SOLO il merge del modello/profilo, senza perdere campi
    out_dict = await svc.run_phase("finalize", payload)
    
    execution_meta = out_dict.get("execution") or {}
    execution_selected = execution_meta.get("selected") or "cloud"

    out = HarperRunResponse(
        ok=bool(out_dict.get("ok", True)),
        phase=out_dict.get("phase") or "finalize",
        echo=(out_dict.get("echo") or "finalize completed") + f" | execution={execution_selected}",
        text=out_dict.get("text"),
        files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
        diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
        tests=TestSummary(**(out_dict.get("tests") or {})),
        warnings=out_dict.get("warnings") or [],
        errors=out_dict.get("errors") or [],
        error_code=out_dict.get("error_code"),
        rejected=out_dict.get("rejected") or [],
        runId=out_dict.get("runId"),
        usage=out_dict.get("usage"),
        execution=out_dict.get("execution"),
        local_agent=out_dict.get("local_agent"),
        telemetry=out_dict.get("telemetry"),
    )
    # Retro-compat: spec_md, se disponibile (primo file markdown) oppure None
    release_notes_md = None
    if out.files:
        try:
            # se il primo file è SPEC.md lo esponiamo
            if out.files[0].path.lower().endswith("kit.md"):
                release_notes_md = out.files[0].content
        except Exception:
            pass

    return HarperEnvelope(out=out, release_notes_md=release_notes_md)

@router.post("/eval", response_model=HarperEnvelope)
async def post_eval_prepass(req: HarperPhaseRequest):
    """
    Prepare an optional local-agent /eval pre-pass package.

    This endpoint does not replace canonical /v1/eval/run.
    It only lets the orchestrator prepare a local-agent hardening package.
    The extension must run canonical eval afterwards.
    """
    payload = req.model_dump()
    payload["phase"] = "eval"
    payload.setdefault("cmd", "eval")

    eval_opts = payload.get("eval") or {}
    log.info(
        "run_phase eval-prepass (route): targets=%s executionPreference=%s",
        eval_opts.get("targets"),
        payload.get("executionPreference"),
    )

    try:
        out_dict = await svc.run_phase("eval", payload)

        out = HarperRunResponse(
            ok=bool(out_dict.get("ok", True)),
            phase=out_dict.get("phase") or "eval",
            echo=out_dict.get("echo"),
            text=out_dict.get("text"),
            files=[FileArtifact(**f) for f in (out_dict.get("files") or [])],
        partial_files=[FileArtifact(**f) for f in (out_dict.get("partial_files") or [])],
        diagnostic_files=[FileArtifact(**f) for f in (out_dict.get("diagnostic_files") or [])],
            diffs=[DiffEntry(**d) for d in (out_dict.get("diffs") or [])],
            tests=TestSummary(**(out_dict.get("tests") or {})),
            warnings=out_dict.get("warnings") or [],
            errors=out_dict.get("errors") or [],
            error_code=out_dict.get("error_code"),
            rejected=out_dict.get("rejected") or [],
            runId=out_dict.get("runId"),
            usage=out_dict.get("usage"),
            execution=out_dict.get("execution"),
            local_agent=out_dict.get("local_agent"),
            telemetry=out_dict.get("telemetry"),
        )

        if out_dict.get("local_agent"):
            log.info(
                "run_phase eval-prepass (route): returning local_agent package action=%s req=%s executor_hint=%s package_files=%d",
                (out_dict.get("local_agent") or {}).get("action"),
                (out_dict.get("local_agent") or {}).get("req_id"),
                (out_dict.get("local_agent") or {}).get("executor_hint"),
                len((out_dict.get("local_agent") or {}).get("package_files") or []),
            )

        return HarperEnvelope(out=out)

    except MethodologyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Error in eval pre-pass phase: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/local-agent/complete")
async def post_local_agent_complete(payload: dict):
    """
    Normalize a local-agent actuator result.

    The extension runs the local CLI, then sends stdout/stderr/exit code and
    produced candidate files back here. The orchestrator remains the owner of
    output normalization and root validation.
    """
    from services.local_agent_package import normalize_local_agent_result

    try:
        normalized = normalize_local_agent_result(payload)
        return {"out": normalized}
    except Exception as exc:
        log.exception("local-agent complete failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
