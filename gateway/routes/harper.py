# gateway/routes/harper.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class RunRequest(BaseModel):
    phase: str
    mode: str
    model: str
    profile: Optional[str] = None
    docRoot: str
    core: List[str] = []
    attachments: List[Dict[str, Any]] = []
    flags: Dict[str, Any] = {}
    runId: Optional[str] = None
    # Inline docs (optional, passthrough)
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    todo_ids: Optional[List[str]] = None

router = APIRouter(prefix="/v1/harper", tags=["harper"])

@router.post("/run")
async def run(req: RunRequest):
    # TODO: apply policy based on req.profile (cloud/local/redaction) and perform the actual work.
    echo = f"profile={req.profile or '—'} model={req.model} phase={req.phase}"
    return {
        "ok": True,
        "echo": echo,
        "diffs": [],   # fill with diffs when codegen happens
        "files": [],   # attach artifacts/reports here
        "tests": {"passed": 0, "failed": 0, "summary": "n/a"},
        "warnings": [],
        "errors": [],
        "runId": req.runId or "n/a"
    }
