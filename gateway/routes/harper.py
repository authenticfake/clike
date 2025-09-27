# gateway/routes/harper.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import logging
import os, datetime
import httpx

log = logging.getLogger("gateway.harper")

# ---- SPEC context builders ---------------------------------------------------
PROMPT_SPEC_SYSTEM_PATH = os.getenv("PROMPT_SPEC_SYSTEM_PATH", "/workspace/gateway/prompts/harper/spec_system.md")
SPEC_TEMPLATE_PATH = os.getenv("SPEC_TEMPLATE_PATH", "/workspace/docs/templates/SPEC_TEMPLATE.md")
import yaml

def _gw_load_models() -> list[dict]:
    path = os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return [m for m in (data.get("models") or []) if m.get("enabled", False)]
    except Exception:
        return []

def _gw_try_match_model(alias_or_id: str) -> Optional[dict]:
    ms = (alias_or_id or "").strip().lower()
    if not ms:
        return None
    models = _gw_load_models()
    for m in models:
        mid = str(m.get("id","")).lower()
        name = str(m.get("name","")).lower()
        rname = str(m.get("remote_name","")).lower()
        if ms == mid or ms == name or ms == rname:
            return m
    return None

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def _compose_spec_messages(idea_md: str,
                           core_blobs: dict | None,
                           profile_hint: str | None,
                           model_route_label: str | None,
                           run_id: str | None) -> list[dict]:
    """Build OpenAI/Anthropic style chat messages: system + user. Minimal, RAG-light."""
    system = _read_text(PROMPT_SPEC_SYSTEM_PATH)
    # Foreground principles (tiny, inline to keep context short)
    foreground = (
        "## CLike Principles (short)\n"
        "- Harper pipeline: SPEC→PLAN→KIT, eval-driven quality, outcome-first.\n"
        "- Keep SPEC concise but testable; Acceptance Criteria are mandatory.\n"
        "- Maintain human-in-control tone; do not invent facts.\n"
    )
    # Pack minimal project context (IDEA + optional core blobs names)
    refs = ""
    if core_blobs:
        refs = "### Included references:\n" + "\n".join(f"- {k} ({len(v or '')} chars)" for k, v in core_blobs.items())

    user = (
        f"{foreground}\n\n"
        f"### Route\n- profile: {profile_hint or '—'}\n- model: {model_route_label or '—'}\n- runId: {run_id or 'n/a'}\n\n"
        f"### IDEA.md (verbatim)\n{idea_md}\n\n"
        f"{refs}\n\n"
        "### Task\nTransform the IDEA into a SPEC that strictly follows the Output contract. "
        "Return only the SPEC.md content as Markdown."
    )

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user.strip()},
    ]


def _route_label(model: str | None, profile: str | None) -> str:
    if model and profile:
        return f"{profile}::{model}"
    return model or profile or "auto"

async def _call_llm_chat(model: str | None, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.2) -> str | None:
    """
    Minimal provider-agnostic attempt:
    - If OPENAI_API_KEY is present and model looks like openai:..., call OpenAI Chat Completions.
    - Else return None so the caller can fallback.
    """
    if not model:
        return None
    if model.startswith("openai:"):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            return None
        # Strip "openai:" prefix if present
        model_id = model.split(":", 1)[1]
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{base_url}/chat/completions",
                                  headers={"authorization": f"Bearer {api_key}",
                                           "content-type": "application/json"},
                                  json=payload)
            if r.status_code != 200:
                return None
            data = r.json()
            try:
                return data["choices"][0]["message"]["content"]
            except Exception:
                return None
    # Other providers can be added here (anthropic:, mistral:, etc.)
    return None

def _fallback_spec_from_template(idea_md: str, model_route_label: str | None, run_id: str | None) -> str:
    """Deterministic SPEC using template + IDEA first paragraph(s)."""
    tpl = _read_text(SPEC_TEMPLATE_PATH)
    project_name = "Project"
    # Try to detect a first heading as project name
    for line in idea_md.splitlines():
        if line.strip().startswith("#"):
            project_name = line.strip("# ").strip()
            break
    out = (tpl
           .replace("${PROJECT_NAME}", project_name)
           .replace("${DATE}", datetime.date.today().isoformat())
           .replace("${OWNER:-Unassigned}", "Unassigned")
           .replace("${RUN_ID}", run_id or "n/a")
           .replace("${MODEL_ROUTE}", model_route_label or "auto"))
    # Drop obvious "${...}" leftovers if any
    return out


class Attachment(BaseModel):
    name: str
    path: Optional[str] = None
    id: Optional[str] = None
    source: Optional[str] = None
    mime: Optional[str] = None
    content_base64: Optional[str] = None

class HarperRunRequest(BaseModel):
    cmd: str
    phase: str
    mode: str = "harper"
    model: str
    profile: Optional[str] = None
    profileHint: Optional[str] = None
    docRoot: str
    core: List[str] = []
    attachments: List[Union[str, Attachment]] = []
    flags: Dict[str, Any] = {}
    runId: Optional[str] = None
    historyScope: Optional[str] = None
    # Inline docs (optional, passthrough)
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    todo_ids: Optional[List[str]] = None
    core_blobs: Optional[Dict[str, str]] = None


router = APIRouter(prefix="/v1/harper", tags=["harper"])

def _normalize_attachments(atts: List[Union[str, Attachment]]) -> List[dict]:
    out: List[dict] = []
    for a in atts or []:
        if isinstance(a, str):
            out.append({"name": a})
        else:
            out.append(a.model_dump())
    return out


@router.post("/run")
async def run(req: HarperRunRequest):
    # TODO: apply policy based on req.profile (cloud/local/redaction) and perform the actual work.
    log.info("harper.run cmd=%s model=%s idea_md=%s core_blobs=%d",
             req.cmd, req.model, bool(req.idea_md), len(req.core_blobs or {}))
    phase = (req.phase or req.cmd or "").strip()
    resolved_entry = None
    if req.model and not str(req.model).lower().startswith(("openai:","anthropic:","ollama:","vllm:","deepseek:","azure:","google:")):
        resolved_entry = _gw_try_match_model(str(req.model))
        if resolved_entry:
            log.info("harper.gateway normalized model '%s' -> id=%s (provider=%s)",
                     req.model, resolved_entry.get("id"), resolved_entry.get("provider"))
    if not phase:
    # Non 422 “duro”: rispondiamo comunque con errore soft dentro il payload
        return {
            "ok": False,
            "echo": "missing phase/cmd",
            "diffs": [],
            "files": [],
            "tests": {"passed": 0, "failed": 0, "summary": "n/a"},
            "warnings": [],
            "errors": ["Missing 'phase'/'cmd' in request"],
            "runId": req.runId or "n/a"
        }

    atts = _normalize_attachments(req.attachments)

    if phase == "spec":
        idea = req.idea_md or ""
        core_blobs = req.core_blobs or {}
        model_route_label = _route_label(req.model, req.profileHint)
        messages = _compose_spec_messages(idea, core_blobs, req.profileHint, model_route_label, req.runId)

        # 1) tenta LLM
        llm_text = await _call_llm_chat(req.model, messages, max_tokens=4096, temperature=0.2)

        # 2) fallback deterministico (template) se il modello non ha risposto
        spec_md = llm_text if (llm_text and llm_text.strip()) else _fallback_spec_from_template(idea, model_route_label, req.runId)

        files = [{
            "path": f"{req.docRoot or 'docs/harper'}/SPEC.md",
            "content": spec_md,
            "mime": "text/markdown",
            "encoding": "utf-8",
        }]

        warnings = []
        # mini-validazioni: presenza delle sezioni principali
        required_sections = [
            "Problem Statement", "Goals", "Users & Scenarios", "Scope", "Constraints",
            "Interfaces", "Data & Storage", "Risks & Mitigations", "Acceptance Criteria", "Evals & Gates"
        ]
        missing = [s for s in required_sections if f"## {s}" not in spec_md]
        if missing:
            warnings.append(f"SPEC missing sections: {', '.join(missing)}")
        # breve testo per la bubble della chat (prima riga del documento)
        first_heading = ""
        for line in (spec_md or "").splitlines():
            if line.strip().startswith("#"):
                first_heading = line.strip().lstrip("# ").strip()
                break
        chat_text = f"Generated SPEC.md — {first_heading or 'SPEC'} (apply from Files tab)."

        return {
            "ok": True,
            "echo": f"{model_route_label} :: SPEC generation",
            "text": chat_text,    # <— aggiunto: la webview può renderizzare questa bubble
            "diffs": [],
            "files": files,       # [{ path, content, mime, encoding }]
            "tests": {"passed": 0, "failed": 0, "summary": "n/a"},
            "warnings": warnings,
            "errors": [],
            "runId": req.runId or "n/a",
        }

    # Chiama il service/engine esistente; se non usa idea_md/core_blobs, li ignorerà.
    #result = await harper_engine_run(engine_input)  # funzione già presente nel tuo codice
    #return result
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
