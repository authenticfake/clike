# gateway/routes/harper.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any, Union
import logging
import os, datetime
import httpx, random, math, asyncio
from routes.chat import ANTHROPIC_API_KEY, ANTHROPIC_BASE, OLLAMA_BASE, OPENAI_API_KEY, OPENAI_BASE, VLLM_BASE, _json
from providers import openai_compat as oai
from providers import anthropic as anth
from providers import deepseek as dsk
from providers import ollama as oll
from providers import vllm as vll
import yaml, re
import mimetypes
_FILE_BLOCK_RE = re.compile(
    r"(?:^|\n)```[^\n]*\n\s*file:([^\n]+)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE
)
log = logging.getLogger("gateway.harper")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---- SPEC context builders ---------------------------------------------------
PROMPT_SPEC_SYSTEM_PATH = os.getenv("PROMPT_SPEC_SYSTEM_PATH", "/app/prompts/harper/spec_system.md")
SPEC_TEMPLATE_PATH = os.getenv("SPEC_TEMPLATE_PATH", "/app/templates/SPEC_TEMPLATE.md")
PROMPT_PLAN_SYSTEM_PATH = os.getenv("PROMPT_PLAN_SYSTEM_PATH", "/app/prompts/harper/plan_system.md")
PROMPT_KIT_SYSTEM_PATH = os.getenv("PROMPT_KIT_SYSTEM_PATH", "/app/prompts/harper/kit_system.md")
PROMPT_BUILD_SYSTEM_PATH = os.getenv("PROMPT_BIULD_SYSTEM_PATH", "/app/prompts/harper/build_system.md")
PROMPT_FINALIZE_SYSTEM_PATH = os.getenv("PROMPT_FINALIZE_SYSTEM_PATH", "/app/prompts/harper/finlize_system.md")

_REPO_PLACEHOLDER = "[PROJECT_REPO_URL]"


# --- Defaults per modelli che non hanno context definito ---
DEFAULT_CONTEXT_WINDOW = 128_000     # conservativo
DEFAULT_MAX_OUTPUT = 16_384          # conservativo
router = APIRouter(prefix="/v1/harper", tags=["harper"])

# --- PATCH START (helpers) ---
def _render_chat_context(msgs: list[dict]) -> str:
    """Rende la chat user/assistant in testo leggibile per il prompt."""
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        # Evita intestazioni troppo lunghe; niente markdown aggressivo
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

def _normalize_repo_url(url: str | None) -> str | None:
    if not url:
        return None
    # git@host:org/repo(.git)? -> https://host/org/repo
    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", url.strip())
    if m:
        host, repo = m.groups()
        return f"https://{host}/{repo}"
    # drop trailing .git in https
    return re.sub(r"\.git$", "", url.strip())

def _inject_repo_url_in_system(system_text: str, repo_url: str | None) -> str:
    url = _normalize_repo_url(repo_url) or "https://example.invalid/REPO_URL_NOT_SET"
    return system_text.replace(_REPO_PLACEHOLDER, url)

def _clip_text_to_tokens(text: str, max_tokens: int) -> str:
    """Taglia per stare sotto max_tokens (approssimazione char→token già usata altrove)."""
    if not text or max_tokens <= 0:
        return ""
    approx = approx_tokens_from_chars(text)
    if approx <= max_tokens:
        return text
    # taglio grezzo per sicurezza (≈ 4 char/token)
    target_chars = max(128, int(max_tokens * 4))
    return text[-target_chars:]

def _guess_mime(path: str) -> str:
    # Usa libreria standard per dedurre il MIME; fallback binario generico.
    mime, _ = mimetypes.guess_type(path or "", strict=False)
    return mime or "application/octet-stream"

def _extract_file_blocks(text: str) -> tuple[list[dict], str]:
    """
    Estrae blocchi del tipo:
      ```file:/path/to/file.ext
      <contenuto>
      ```
    Restituisce (files, remainder_text_senza_blocchi).
    """
    files: list[dict] = []
    if not text:
        return files, ""

    remainder_parts: list[str] = []
    idx = 0
    for m in _FILE_BLOCK_RE.finditer(text):
        start, end = m.span()
        # append porzione di testo fuori dai blocchi precedente
        remainder_parts.append(text[idx:start])
        idx = end

        raw_path = (m.group("path") or "").strip()
        # normalizza path: togli leading // o /
        norm_path = raw_path.lstrip().lstrip("/")
        content = (m.group("content") or "")
        files.append({
            "path": norm_path,
            "content": content,
            "mime": _guess_mime(norm_path),
            "encoding": "utf-8",
        })

    # coda finale del testo
    remainder_parts.append(text[idx:])
    remainder = "".join(remainder_parts).strip()

    return files, remainder


# --- PATCH END (helpers) ---

def approx_tokens_from_chars(text: str) -> int:
    # euristica stabile usata nel resto del repo (≈ 4 chars/token)
    return max(1, int(len(text) / 4))

def _messages_text_len(messages: list[dict]) -> int:
    return sum(len(m.get("content","")) for m in (messages or []) if isinstance(m.get("content"), str))

def _resolve_ctx_caps(model_entry: dict | None) -> tuple[int, int]:
    DEFAULT_CONTEXT_WINDOW = 128000
    DEFAULT_MAX_OUTPUT = 4096
    if not model_entry:
        return DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT
    cw = int(model_entry.get("context_window") or DEFAULT_CONTEXT_WINDOW)
    mo = int(model_entry.get("max_output_tokens") or DEFAULT_MAX_OUTPUT)
    return cw, mo

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
            log.info("Loading %s", path)
            return f.read()
    except Exception:
        log.error("Error reading %s", path)
        return ""



PHASE_OUTPUT_FILE = {
    "spec": "SPEC.md",
    "plan": "PLAN.md",
    "kit": "KIT.md",
    "build": "BUILD_REPORT.md",
    "finalize": "RELEASE_NOTES.md",
}
PHASE_INPUT_FILE = {
    "spec": ["IDEA.md"],
    "plan": ["IDEA.md", "SPEC.md"],
    "kit": ["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md"],
    "build": ["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md"],
    "finalize":["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "RELEASE_NOTES.md"],
}

# --- PATCH START: phase-aware output checklist ---
def _output_checklist_for_phase(phase: str) -> str:
    p = (phase or "").lower()

    if p in ("spec", "plan"):
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            f"- Top-level heading is `# {p.upper()}`.\n"
            "- All major sections use `## Section` headings (no numbered titles).\n"
            "- Required diagrams (if any) use fenced code blocks (e.g., Mermaid). No ASCII art.\n"
            "- Clean Markdown bullets (one space after `-` or `*`).\n"
            "- Output is a single Markdown document (no extra prose before/after).\n"
        )

    if p == "finalize":
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            f"- Top-level heading is `# {p.upper()}`.\n"
            "- Produce `RELEASE_NOTES.md` as a single Markdown document or as a `file:/...` block.\n"
            "- If additional metadata (tags/version) is included, keep it at the end in a clearly labeled section.\n"
            "- No ASCII art; diagrams (if any) use proper fenced blocks.\n"
            "- Clean Markdown bullets (one space after `-` or `*`).\n"
        )

    # KIT (file-based outputs)
    return (
        "### OUTPUT CONFORMITY CHECKLIST\n"
        "- Emit one or more `file:/path` blocks with complete file contents.\n"
        "- Include the phase log (`KIT.md`) as a file block if required.\n"
        "- No trailing prose outside fenced blocks, except a short append-only iteration log if specified.\n"
        "- Respect repository structure and composition-first design.\n"
    )

def _compose_system_messages(phase: str,
                            idea_md: Optional[str],
                            core_blobs: dict | None,
                            profile_hint: str | None,
                            model_route_label: str | None,
                            run_id: str | None,
                            repo_url: str | None) -> list[dict]:
    """Build OpenAI/Anthropic style chat messages: system + user. Minimal, RAG-light."""
    system_by_phase = {
        "spec": PROMPT_SPEC_SYSTEM_PATH,
        "plan": PROMPT_PLAN_SYSTEM_PATH,
        "kit": PROMPT_KIT_SYSTEM_PATH,
        "finalize": PROMPT_FINALIZE_SYSTEM_PATH,
    }
    system_path = system_by_phase.get(phase, PROMPT_SPEC_SYSTEM_PATH)
    system = _read_text(system_path).strip() or "# Harper System Prompt\nFollow the phase contract strictly."
    #log.info("System prdockeompt for phase %s: %s", phase, system)
    if phase == "kit" and repo_url:
        system = _inject_repo_url_in_system(system, repo_url) 
    #log.debug("System w/ repo url prompt for phase %s: %s", phase, system)

    
    # Foreground principles (tiny, inline to keep context short)
    foreground = (
        "## CLike Principles (short)\n"
        "- Harper pipeline: SPEC→PLAN→KIT, eval-driven quality, outcome-first.\n"
        "- Keep output concise but testable; Acceptance Criteria are mandatory.\n"
        "- Maintain human-in-control tone; do not invent facts.\n"
    )
    constraints_keys: list[str] = []
    other_core: dict[str, str] = {}
    constraints_chunks: list[str] = []

    if core_blobs:
        for name, content in core_blobs.items():
            lname = (name or "").lower()
            #if (lname.startswith("tech_constraints") or lname.startsWith("idea.md")) :
            if lname.startswith("tech_constraints"):
                    constraints_keys.append(name)
                    if isinstance(content, str) and content.strip():

                        constraints_chunks.append(content.strip())
            else:
                other_core[name] = content
    # Pack minimal project context (IDEA + optional core blobs names)
    refs = ""
    if other_core:
       refs = "### Included references:\n" + "\n".join(f"- {k} ({len(v or '')} chars)" for k, v in core_blobs.items())

    suffix_parts = []
     
    if other_core:
        for n, c in other_core.items():
            suffix_parts.append(f"\n\n### {n} (verbatim)\n{c}")

    # Technology Constraints unified block (if any were found under core)
    if constraints_chunks:
        # Non forziamo il parsing; mostriamo come testo YAML fenced per massima compatibilità
        constraints_text = "\n\n---\n\n".join(constraints_chunks)
        suffix_parts.append("### Technology Constraints (YAML)\n```yaml\n" + constraints_text + "\n```")

    suffix = "".join(suffix_parts)

    
    user = (
        f"{foreground}\n\n"
        f"### Route\n- profile: {profile_hint or '—'}\n- model: {model_route_label or '—'}\n- runId: {run_id or 'n/a'}\n\n"
        f"### IDEA.md (verbatim)\n{idea_md}\n\n"
        f"{refs}\n\n"
        f"{_output_checklist_for_phase(phase)}"
        f"### Task\nProduce/Transform the {phase.upper()} output that strictly follows the Output contract. Return only the Markdown document for this phase.{suffix}"
 
    )

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user.strip()},
    ]


def _route_label(model: str | None, profile: str | None) -> str:
    if model and profile:
        return f"{profile}::{model}"
    return model or profile or "auto"


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

class HarperMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

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
    messages: List[HarperMessage] = Field(default_factory=list)

    flags: Dict[str, Any] = {}
    runId: Optional[str] = None
    historyScope: Optional[str] = None
    # Inline docs (optional, passthrough)
    idea_md: Optional[str] = None
    spec_md: Optional[str] = None
    plan_md: Optional[str] = None
    todo_ids: Optional[List[str]] = None
    core_blobs: Optional[Dict[str, str]] = None
    gen: Optional[dict] = None  # {temperature, max_tokens, top_p, stop, presence_penalty, frequency_penalty, seed}
    workspace: Optional[dict] = None





def _normalize_attachments(atts: List[Union[str, Attachment]]) -> List[dict]:
    out: List[dict] = []
    for a in atts or []:
        if isinstance(a, str):
            out.append({"name": a})
        else:
            out.append(a.model_dump())
    return out


def _tokens_per_model(messages: list[dict], model_entry: dict | None, req_max: int) -> int:
    """
    Calcola i max tokens di completion effettivi nel rispetto di:
      ctx_window - prompt_tokens, req_max e max_output_tokens del modello.
    """
    ctx_window, max_out_cap = _resolve_ctx_caps(model_entry)
    prompt_text = "".join(m.get("content","") for m in (messages or []) if isinstance(m.get("content"), str))
    prompt_tokens = approx_tokens_from_chars(prompt_text)

    available_ctx = max(0, ctx_window - prompt_tokens)
    eff_max = max(1, min(req_max, available_ctx, max_out_cap))

    return eff_max

@router.post("/run")
async def run(req: HarperRunRequest,  request: Request):
    # TODO: apply policy based on req.profile (cloud/local/redaction) and perform the actual work.
    log.info("harper.run cmd=%s model=%s idea_md=%s core_blobs=%d",
             req.cmd, req.model, bool(req.idea_md), len(req.core_blobs or {}))
    phase = (req.phase or req.cmd or "").strip()
    resolved_entry = None
    if req.model and not str(req.model).lower().startswith(("openai:","anthropic:","ollama:","vllm:","deepseek:","azure:","google:")):
        resolved_entry = _gw_try_match_model(str(req.model))
        # if resolved_entry:
        #     log.info("harper.gateway normalized model '%s' -> id=%s (provider=%s)",
        #              req.model, resolved_entry.get("id"), resolved_entry.get("provider"))
    
    # --- Context budgeting ---
    ctx_window, max_out_cap = _resolve_ctx_caps(resolved_entry)
    
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
    req.attachments = atts
    # --- PATCH: RAG logging (opzionale) ---
    rag_enabled = bool(req.attachments)
    if rag_enabled:
        log.info("harper.rag enabled attachments=%s", len(req.attachments))

    provider = ( request.headers.get("X-CLike-Provider") or resolved_entry.get("provider") or "").lower().strip()

    # ----- Normalizza input per provider -----
    # ATTENZIONE: niente virgola -> niente tupla!
    model = req.model  # era: req.model,
   
   
    # ---- Gen params allineati a chat ----
    g = req.gen or {}
    gen_temperature = g.get("temperature", 0.2)
    gen_max_tokens = g.get("max_tokens", 8192)
    gen_top_p = g.get("top_p")
    gen_stop = g.get("stop")
    gen_presence_penalty = g.get("presence_penalty")
    gen_frequency_penalty = g.get("frequency_penalty")
    gen_seed = g.get("seed")
    gen_tools = g.get("tools")
    gen_remote = g.get("remote")
    gen_response_format = g.get("response_format")
    gen_tool_choice = g.get("tool_choice")
    repourl = getattr(req, "repoUrl", None)

    # Logging solo con tipi JSON-safe (evita oggetti pydantic)
    log.info(
        "harper payload (safe) %s",
        _json({
            "provider": provider,
            "model": model,
            "remote": gen_remote,
            "has_tools": bool(gen_tools),
            "has_tool_choice": bool(gen_tool_choice),
            "has_response_format": bool(gen_response_format),
            "max_tokens": gen_max_tokens,
            "temperature": gen_temperature,
        })
    )
    idea = req.idea_md or ""
    core_blobs = req.core_blobs or {}
    model_route_label = _route_label(req.model, req.profileHint)
    messages = _compose_system_messages(phase,idea, core_blobs, req.profileHint, model_route_label, req.runId, repourl)
    
    
    log.info("harper.gateway normalized messages '%s' ", messages)
     # 1) normalizza req.messages -> list[dict]
    incoming: list[dict] = []
    for m in (req.messages or []):
        try:
            d = m.model_dump() if hasattr(m, "model_dump") else (m.dict() if hasattr(m, "dict") else dict(m))
        except Exception:
            d = {"role": getattr(m, "role", None), "content": getattr(m, "content", "")}
        role = (d.get("role") or "").strip()
        content = (d.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            incoming.append({"role": role, "content": content})

    

    # 2) calcola budget token per la chat in base a ctx_window, prompt_base e max out richiesto
    base_prompt_tokens = approx_tokens_from_chars("".join(
        m.get("content","") for m in messages if isinstance(m.get("content"), str)
    ))
    ctx_window, max_out_cap = _resolve_ctx_caps(resolved_entry)
    requested_out = int((req.gen or {}).get("max_tokens", 8192))
    # margine di sicurezza per header/model/tooling
    SAFETY_PROMPT_TOKENS = 256
    # budget per chat = ctx - base_prompt - requested_out - safety (>=0)
    chat_budget = max(0, ctx_window - base_prompt_tokens - requested_out - SAFETY_PROMPT_TOKENS)

    if incoming and chat_budget > 0:
        raw_ctx = _render_chat_context(incoming)
        clipped_ctx = _clip_text_to_tokens(raw_ctx, chat_budget)
        if clipped_ctx:
            # Ricicliamo il messaggio 'user' già costruito, aggiungendo un blocco "Recent Harper chat"
            messages[1]["content"] += "\n\n### Recent Harper chat (trimmed)\n" + clipped_ctx

    # log.info("harper.gateway messages '%s' ", messages)

    # 0) Check token per model
    # --- Context budgeting ---
    eff_max = _tokens_per_model(messages, resolved_entry, gen_max_tokens)
    # timeout dinamico (60s base + 2s per 1k token, max 180s)
    timeout_sec = min(240.0, 60.0 + (eff_max / 1000.0) * 2.0)
    log.info("harper.gateway eff_max & timeout '%s' '%s'",
                    eff_max, timeout_sec)
    log.info("harper.gateway eff_max=%s ctx_window=%s prompt_tokens≈%s cap=%s",
        eff_max,
        (_resolve_ctx_caps(resolved_entry)[0]),
        approx_tokens_from_chars("".join(m.get("content","") for m in messages if isinstance(m.get("content"), str))),
        (_resolve_ctx_caps(resolved_entry)[1]))
    
    telemetry: dict[str, object] = {
        "phase": phase,
        "model": model_route_label,
        "runId": req.runId,
    }
    warnings: list[str] = []
    errors: list[str] = []
    llm_text = None
    llm_usage = {}
    try:
        # Routing per provider
        if provider == "openai":
            if not OPENAI_API_KEY:
                raise HTTPException(401, "missing ANTHROPIC api key")
            llm_text = await oai.chat(OPENAI_BASE, OPENAI_API_KEY, model, messages, gen_temperature, eff_max, gen_response_format, gen_tools, gen_tool_choice, timeout=timeout_sec) 

        elif provider == "vllm":
            llm_text =  await vll.chat(VLLM_BASE, model, messages, gen_temperature, eff_max, gen_response_format, gen_tools, gen_tool_choice)
        elif provider == "ollama":
            llm_text =  await oll.chat(OLLAMA_BASE, model, messages, gen_temperature, eff_max)   

        elif provider == "anthropic":
            if not ANTHROPIC_API_KEY:
                raise HTTPException(401, "missing ANTHROPIC api key")
            llm_text = await anth.chat(ANTHROPIC_BASE, ANTHROPIC_API_KEY, model, messages, gen_temperature,eff_max)
            
        else:
            raise HTTPException(400, f"unsupported provider for chat: {provider} for model '{req.model}")

    except httpx.HTTPStatusError as e:
            log.error("httpx error: %s", e)
            txt = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 502
            raise HTTPException(code, detail=f"provider error for model={model}: {txt}")
    except httpx.HTTPError as e:
            log.error("httpx error: %s", e)
            raise HTTPException(502, detail=f"provider connection error: {e}")
    except Exception as e:
        log.error("httpx error: %s", e)
        errors.append(f"provider_error: {type(e).__name__}: {e}")
        spec_md_txt, llm_diag = ("", {})

    text_len=0
    #log.info("harper.gateway llm_text '%s' ", llm_text)

    system_md_txt, llm_usage = oai.coerce_text_and_usage(llm_text)
    system_md_txt = (system_md_txt or "").strip()

    text_len = len((system_md_txt or "").strip())
    log.info("harper.llm.result text_len=%d usage=%s", text_len, (llm_usage or {}))

    # --- soft-fail & normalizzazione i.e. SPEC.md ---
    system_md_txt = (system_md_txt or "").strip()
    missing = []
    if phase == "spec":

        if not system_md_txt:
            warnings.append("empty_model_output: model returned empty content, used fallback SPEC template")
            system_md_txt = _fallback_spec_from_template(idea, model_route_label, req.runId)

        # garantiamo un H1 per consumer downstream
        if not system_md_txt.lstrip().startswith("#"):
            system_md_txt = "# SPEC — Generated\n\n" + system_md_txt
            warnings.append("normalized_heading: added H1 heading to SPEC")

        required_sections = [
            "Problem", "Objectives", "Scope", "Non-Goals", "Constraints",
            "KPIs", "Assumptions", "Risks", "Acceptance Criteria", "Sources"
        ]
        missing = [s for s in required_sections if f"## {s}" not in system_md_txt]
        if missing:
            warnings.append(f"SPEC missing sections: {', '.join(missing)}")

    # Nome file corretto per la fase

    # --- Multi-file support ---
    output_name = PHASE_OUTPUT_FILE.get(phase, f"{phase.upper()}.md")
    default_doc_path = f"{req.docRoot or 'docs/harper'}/{output_name}"

    gen_files, remainder = _extract_file_blocks(system_md_txt)

    files: list[dict] = []
    if gen_files:
        # I blocchi 'file:' sono path *relativi alla root repo* o assoluti '/...'
        files.extend(gen_files)

        # se rimane testo fuori dai blocchi file, lo salviamo nel documento della fase
        if remainder:
            files.append({
                "path": default_doc_path,
                "content": remainder,
                "mime": "text/markdown",
                "encoding": "utf-8",
            })
    else:
        # fallback compatibile: singolo documento della fase
        files.append({
            "path": default_doc_path,
            "content": system_md_txt,
            "mime": "text/markdown",
            "encoding": "utf-8",
        })


    telemetry.update({
        "text_len": text_len,
        "usage": llm_usage or {},
        "missing_sections": missing,
        "budget_max_tokens": eff_max,
        "provider": provider,    
    })

    return {
        "ok": len(errors) == 0,
        "phase": phase,
        "echo": f"{model_route_label} :: {phase.upper()} generation",
        "text": f"Generated {PHASE_OUTPUT_FILE.get(phase)} ({text_len} chars).",
        "diffs": [],
        "files": files,
        "tests": {"passed": 0, "failed": 0, "summary": "n/a"},
        "warnings": warnings,
        "errors": errors,
        "runId": req.runId or "n/a",
        "telemetry": telemetry,
    }
    
