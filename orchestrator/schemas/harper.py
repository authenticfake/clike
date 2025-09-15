# Pydantic schemas with iteration fields. Comments in English.
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal

class SpecRequest(BaseModel):
    idea_md: Optional[str] = Field(None, description="Optional IDEA.md to guide SPEC.")
    revision_note: Optional[str] = None

class SpecResponse(BaseModel):
    spec_md: str
    ok: bool
    violations: List[str] = []
    run_id: str

class PlanRequest(BaseModel):
    spec_md: str
    revision_note: Optional[str] = None

class PlanResponse(BaseModel):
    plan_md: str
    ok: bool
    violations: List[str] = []
    run_id: str

class KitRequest(BaseModel):
    spec_md: str
    plan_md: str
    todo_ids: Optional[List[str]] = None
    revision_note: Optional[str] = None

class KitResponse(BaseModel):
    kit_md: str
    artifacts: Dict[str, Any] = {}
    ok: bool = True
    violations: List[str] = []
    run_id: str

class BuildNextRequest(BaseModel):
    plan_md: str
    spec_md: str
    batch_size: int = 1

class BuildNextResponse(BaseModel):
    updated_plan_md: str
    diffs: List[str] = []
    ok: bool = True
    gate_summary: Dict[str, Any] = {}
    run_id: str

class SessionClearRequest(BaseModel):
    scope: Literal["singleModel","allModels"] = "singleModel"

class ModelsResponse(BaseModel):
    models: List[Dict[str, Any]]

class ProfilesResponse(BaseModel):
    profiles: List[str]

class DefaultsResponse(BaseModel):
    defaults: Dict[str, Any]

class ResolveResponse(BaseModel):
    task: Literal["spec","plan","kit","build","chat"]
    hint: Optional[str] = None
    chosen: Dict[str, Any]
    warnings: List[str] = []
