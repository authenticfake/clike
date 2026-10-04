"""Eval sandbox service (WP6.4).

Runs LTC profiles for eval/gate in a separate container that holds no secrets,
cannot reach the gateway or the vector store, runs as a non-root user on a
read-only root filesystem, and sees the projects directory read-only.

The sandbox trusts only the workspace: it receives a project root and a profile
path, re-validates both against its own allowed roots and loads the LTC from
disk itself. It never accepts commands from the request.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from eval_runner import _SECRET_ENV_NAME_RE, EvalRunner, report_to_dict
from services.gate_integrity import allowed_eval_roots
from utils.safe_paths import UnsafePathError, is_within_any, resolve_within

logging.basicConfig(level=logging.INFO, format="[eval-sandbox] | %(levelname)-8s %(message)s", force=True)
log = logging.getLogger("eval-sandbox")

_leaked = sorted(k for k in os.environ if _SECRET_ENV_NAME_RE.search(k))
if _leaked:
    # Fail closed: a misconfigured deployment must not expose credentials to LTC commands.
    raise RuntimeError(f"eval sandbox refuses to start with credentials in its environment: {_leaked}")

app = FastAPI(title="CLike eval sandbox", docs_url=None, redoc_url=None, openapi_url=None)


class SandboxRunRequest(BaseModel):
    project_root: str
    profile: str
    mode: str = "auto"
    verdict: Optional[str] = None
    req_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "eval-sandbox"}


@app.post("/run")
def run(req: SandboxRunRequest):
    roots = allowed_eval_roots()
    prj = Path(req.project_root).resolve()
    if not roots or not is_within_any(prj, roots) or not prj.is_dir():
        raise HTTPException(status_code=403, detail="project_root is outside the allowed eval roots")
    try:
        profile_path = resolve_within(prj, req.profile, allow_absolute_inside=True)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile path: {exc}") from exc

    manual = (req.mode or "auto").lower() == "manual"
    ltc = None
    if profile_path.is_file():
        try:
            ltc = json.loads(profile_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="profile is not valid JSON") from exc
    elif not manual:
        raise HTTPException(status_code=404, detail="profile not found under project_root")

    log.info("run project=%s profile=%s req=%s mode=%s", prj.name, profile_path.name, req.req_id, req.mode)
    rep = EvalRunner(prj).run_profile(
        profile=str(profile_path), ltc=ltc, mode=req.mode or "auto", verdict=req.verdict, req_id=req.req_id
    )
    return report_to_dict(rep)
