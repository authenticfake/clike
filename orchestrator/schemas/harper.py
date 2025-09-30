# Pydantic schemas with iteration fields and execution context.
# Comments in English.

from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field,ConfigDict, constr

# Messaggio chat semplice (solo user/assistant)
class HarperMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    
class HarperFlags(BaseModel):
    neverSendSourceToCloud: bool = True
    redaction: bool = True
    # NEW: rich attachment model (back-compat friendly)
class Attachment(BaseModel):
    name: str
    path: Optional[str] = None
    id: Optional[str] = None
    source: Optional[str] = None  # e.g., "external" | "workspace" | "upload"
    mime: Optional[str] = None
    content_base64: Optional[str] = None  # optional payload if provided

class HarperPhaseRequest(BaseModel):
    cmd: str
    phase: str
    mode: str = "harper"
    model: Optional[str] = None
    profileHint: Optional[str] = None
    docRoot: Optional[str] = "docs/harper"
    core: List[str] = []
    attachments: List[Union[str, Attachment]] = []
    flags: Optional[HarperFlags] = None
    messages: List[HarperMessage] = Field(default_factory=list)
    runId: Optional[str] = None
    historyScope: Optional[str] = None

    # --- NEW optional payloads ---
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    kit_md: Optional[str] = None
    build_report_md: Optional[str] = None
    release_notes_md: Optional[str] = None
    telemetry: Optional[Dict[str, Any]] = None 
    core_blobs: Optional[Dict[str, str]] = None
    workspace: Optional[dict] = None  # {root, repo, branch}






# ---------------------------
# Shared execution context
# ---------------------------
class ExecContext(BaseModel):
    """Common execution context propagated from UI → orchestrator → gateway."""
    mode: Optional[str] = Field("harper", description="UI mode: 'harper'|'coding'|'free'.")
    model: Optional[str] = Field("auto", description="Explicit model id or 'auto' to use router.")
    profile_hint: Optional[str] = Field(
        None, alias="profileHint",
        description="Routing hint (e.g., 'plan.fast'|'code.strict') used only when model=='auto'."
    )
    doc_root: Optional[str] = Field("docs/harper", alias="docRoot", description="Docs root.")
    core: List[str] = Field(default_factory=list, description="Core docs for this phase.")
    attachments: List[Dict[str, Any]] = Field(default_factory=list, description="User attachments.")
    flags: Dict[str, Any] = Field(default_factory=dict, description="Exec flags (privacy, redaction...).")
    run_id: Optional[str] = Field(None, alias="runId", description="Correlation id.")
    history_scope: Optional[Literal["singleModel", "allModels"]] = Field(
        None, alias="historyScope", description="Chat history scope."
    )

    # Pydantic v2 config
    model_config = ConfigDict(
        populate_by_name=True,   # (ex allow_population_by_field_name)
        extra="ignore")
    
class FileArtifact(BaseModel):
    path: str
    content: str
    mime: Optional[str] = None
    encoding: Optional[str] = None

class DiffEntry(BaseModel):
    path: str
    diff: str  # unified diff or patch text

class TestSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    summary: str = "n/a"

class HarperRunResponse(BaseModel):
    ok: bool = True
    phase: Optional[str] = None
    echo: Optional[str] = None
    text: Optional[str] = None
    files: List[FileArtifact] = []
    diffs: List[DiffEntry] = []
    tests: TestSummary = TestSummary()
    warnings: List[str] = []
    errors: List[str] = []
    runId: Optional[str] = None
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    kit_md: Optional[str] = None
    build_report_md: Optional[str] = None
    release_notes_md: Optional[str] = None
    telemetry: Optional[Dict[str, Any]] = None  # token usage, route info, etc.

class HarperEnvelope(BaseModel):
    out: HarperRunResponse
    # facoltativo: spec_md per retro-compat con UI che lo usa direttamente
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    kit_md: Optional[str] = None



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
    profile: Optional[str] = None
