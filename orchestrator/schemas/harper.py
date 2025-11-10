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
    origin: Optional[str] = None  # e.g., "external" | "workspace" | "upload"
    mime: Optional[str] = None
    content_base64: Optional[str] = None  # optional payload if provided
    size: Optional[int] = None
    content: Optional[str] = None
    bytes_b64: Optional[str] = None
               

# --- NEW/UPDATED: options in input for /kit ---
class HarperKitOptions(BaseModel):
    """
    Options to drive /kit targeting behavior.
    - targets: explicit list of REQ-IDs to implement now
    - batch: take the next N open REQ-IDs (ignored if 'targets' given)
    - req_ids: legacy alias (read-only for backward compat)
    - rescope: if True, incorporate Product Owner notes into plan.json view
    """
    targets: Optional[List[str]] = Field(default=None)
    batch: Optional[int] = Field(default=None, ge=1)
    req_ids: Optional[List[str]] = Field(default=None)  # backward-compat alias
    rescope: Optional[bool] = Field(default=False)
class FileItem(BaseModel):
    path: str
    bytes_b64: str

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
    repoUrl: Optional[str] = None
    rag_queries: Optional[List[str]] = None
    gen: Optional[Dict[str, Any]] = None
   
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    kit_md: Optional[str] = None
    release_notes_md: Optional[str] = None
    telemetry: Optional[Dict[str, Any]] = None 
    core_blobs: Optional[Dict[str, str]] = None
    workspace: Optional[dict] = None  # {root, repo, branch}
    kit: Optional[HarperKitOptions] = None
    rag_strategy: Optional[str] = None
    context_hard_limit: Optional[int] = None
    rag_prefer_for: Optional[List[str]] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    rag_chunks: Optional[List[dict]] = None
    rag_queries: Optional[List[str]] = None
    rag_top_k: Optional[int] = None
    files: Optional[List[FileItem]] = None







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

# --- facoltativo: risposta con echo dei target interpretati ---
class HarperKitResult(BaseModel):
    targets: List[str] = Field(default_factory=list)
    req_ids: List[str] = Field(default_factory=list)  # echo legacy if sent
    rescope:Optional[bool] = None
    batch: Optional[int] = None
    resolved_from: Optional[str] = Field(
        default=None, description="one of {targets,batch,auto}"
    )
class TelemetryFile(BaseModel):
    path: str
    bytes: int


class TelemetryUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class TelemetryPricingUnit(BaseModel):
    input_per_1k: float
    output_per_1k: float


class TelemetryPricing(BaseModel):
    input_cost: float
    output_cost: float
    total_cost: float
    unit: TelemetryPricingUnit


class HarperTelemetry(BaseModel):
    """
    Strongly-typed telemetry payload. Keys mirror the gateway payload
    to avoid any snake_case/camelCase mismatch on the extension.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    timestamp: float
    project_name: Optional[str] = None
    docRoot: Optional[str] = None
    phase_params: Optional[Dict[str, Any]]
    files: Optional[List[TelemetryFile]] = []
    text_len: int
    files_len: int
    usage: Optional[TelemetryUsage]
    provider: Optional[str] = None
    pricing: Optional[TelemetryPricing] = None

class UsageInputTokensDetails(BaseModel):
    cached_tokens: Optional[int] = None


class UsageOutputTokensDetails(BaseModel):
    reasoning_tokens: Optional[int] = None


class HarperUsage(BaseModel):
    """
    Canonical usage model across providers.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int] = None
    

    input_tokens_details: UsageInputTokensDetails = UsageInputTokensDetails()
    output_tokens_details: UsageOutputTokensDetails = UsageOutputTokensDetails()

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
    release_notes_md: Optional[str] = None
    telemetry: Optional[HarperTelemetry] = None  # token usage, route info, etc.
    usage: Optional[HarperUsage] = None

    kit: Optional[HarperKitResult] = None
    rag_strategy: Optional[str] = None
    context_hard_limit: Optional[int] = None
    rag_prefer_for: Optional[List[str]] = None
    project_id: Optional[str] = None
    rag_chunks: Optional[List[dict]] = None
    rag_queries: Optional[List[str]] = None
    rag_top_k: Optional[int] = None
    


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
    task: Literal["idea","spec","plan","kit","finalize"]
    hint: Optional[str] = None
    chosen: Dict[str, Any]
    warnings: List[str] = []
    profile: Optional[str] = None
