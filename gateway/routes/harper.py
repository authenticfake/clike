# gateway/routes/harper.py
from __future__ import annotations
import json

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any, Union
import logging
import os, datetime
import httpx, random, math, asyncio
from utils.rag_store import RagStore
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
log = logging.getLogger("harper")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ---- SPEC context builders ---------------------------------------------------
PROMPT_SPEC_SYSTEM_PATH = os.getenv("PROMPT_SPEC_SYSTEM_PATH", "/app/prompts/harper/spec_system.md")
SPEC_TEMPLATE_PATH = os.getenv("SPEC_TEMPLATE_PATH", "/app/templates/SPEC_TEMPLATE.md")
PROMPT_PLAN_SYSTEM_PATH = os.getenv("PROMPT_PLAN_SYSTEM_PATH", "/app/prompts/harper/plan_system.md")
PROMPT_KIT_SYSTEM_PATH = os.getenv("PROMPT_KIT_SYSTEM_PATH", "/app/prompts/harper/kit_system.md")
PROMPT_BUILD_SYSTEM_PATH = os.getenv("PROMPT_BIULD_SYSTEM_PATH", "/app/prompts/harper/build_system.md")
PROMPT_FINALIZE_SYSTEM_PATH = os.getenv("PROMPT_FINALIZE_SYSTEM_PATH", "/app/prompts/harper/finlize_system.md")

_REPO_PLACEHOLDER = "[x]"

# Sostituisci queste righe in alto:
# _FILE_BLOCK_RE = re.compile(
#     r"(?:^|\n)```[^\n]*\n\s*file:([^\n]+)\n(.*?)\n```",
#     re.DOTALL | re.IGNORECASE
# )

# Con queste due regex (supporto fenced + non-fenced):
_FILE_BLOCK_FENCED_RE = re.compile(
    r"(?:^|\n)```[^\n]*\n\s*file:([^\n]+)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE
)
_FILE_BLOCK_PLAIN_RE = re.compile(
    r"(?:^|\n)file:([^\n]+)\n(.*?)(?=(?:\nfile:[^\n]+\n)|\Z)",
    re.DOTALL | re.IGNORECASE
)
# Supporto wire-format "BEGIN_FILE <path>\n... \nEND_FILE"
_FILE_BLOCK_BEGIN_RE = re.compile(
    r"(?:^|\n)BEGIN_FILE\s+([^\n]+)\n(.*?)(?:\nEND_FILE|$)",
    re.DOTALL | re.IGNORECASE
)


# --- Model parameters per phase (output budget & style) ----------------------
PHASE_MODEL_PARAMS = {
    "spec":     {"max_tokens": 5500, "temperature": 0.25, "top_p": 1.0},
    "plan":     {"max_tokens": 10500, "temperature": 0.2, "top_p": 0.8},  # raise to 6500 only if many lanes
    "kit":      {"max_tokens": 7500, "temperature": 0.25, "top_p": 1.0},
    "eval":     {"max_tokens": 3500, "temperature": 0.15, "top_p": 1.0},
    "gate":     {"max_tokens": 3000, "temperature": 0.15, "top_p": 1.0},
    "finalize": {"max_tokens": 3000, "temperature": 0.20, "top_p": 1.0},
}

# --- Harper: Dynamic Context Budgeting (messages builder) --------------------
from dataclasses import dataclass

@dataclass
class TokenPrefs:
    hard_limit: int = 6500        # max token INPUT desiderato (prompt)
    headroom: int = 800           # margine (tool/formatting)
    max_snippet_chars: int = 6000 # limiti estratti inline
    abstract_lines: int = 12      # righe abstract sintetico

def _safe_len(s: str|None) -> int:
    return len(s or "")

def _make_abstract(text: str, max_lines: int = 12) -> str:
    lines = (text or "").strip().splitlines()
    core = [l.strip() for l in lines if l.strip()][:max_lines]
    return "\n".join(core)

def _fits_budget(current_chars: int, prefs: TokenPrefs) -> bool:
    # stima grezza: 4 chars ≈ 1 token
    est_tokens = max(1, current_chars // 4)
    return est_tokens <= max(1, prefs.hard_limit - prefs.headroom)

def _pack_rag_ref(name: str, path: str|None = None, doc_id: str|None = None, abstract: str|None = None) -> dict:
    return {"name": name, "path": path, "doc_id": doc_id, "abstract": (abstract or "")[:2000]}

def compose_harper_messages(
    phase: str,
    system_text: str,
    idea_md: str|None,
    core_blobs: dict|None,
    profile_hint: str|None,
    model_route_label: str|None,
    run_id: str|None,
    repo_url: str|None,
    targets: list[str]|None,
    prefs: TokenPrefs = TokenPrefs(),
    rag_strategy: str = "prefer",                   # "prefer" (default) | "force" | "off"
    rag_prefer_for: list[str] | None = None         # p.es. ["IDEA.md","SPEC.md"]
) -> list[dict]:
    """
    Costruisce i messaggi (system+user) applicando:
    - budget dinamico (TokenPrefs)
    - RAG policy (prefer/force/off) + lista documenti preferiti per RAG
    """
    rag_prefer_for = set((rag_prefer_for or []))

    # 1) system
    system = (system_text or "# Harper System\nFollow the phase contract strictly.").strip()

    # 2) foreground minimal
    foreground = (
        "## CLike Principles (short)\n"
        "- Harper pipeline: SPEC→PLAN→KIT→EVAL→GATE→FINALIZE; eval-driven quality.\n"
        "- Output must be concise, testable; Acceptance Criteria are mandatory.\n"
        "- Human-in-control; do not invent facts; cite RAG refs.\n"
    )

    # 3) inventario core
    core_blobs = core_blobs or {}
    idea_text = idea_md or ""
    spec_text = core_blobs.get("SPEC.md", "")
    tech_yaml  = core_blobs.get("TECH_CONSTRAINTS.yaml", "") or core_blobs.get("TECH_CONSTRAINTS.yml","")

    # 4) costruzione user content progressiva a budget
    parts: list[str] = []
    parts.append(foreground)
    parts.append(f"### Route\n- profile: {profile_hint or '—'}\n- model: {model_route_label or '—'}\n- runId: {run_id or 'n/a'}\n")

    rag_refs: list[dict] = []
    inline_chars = sum(_safe_len(x) for x in parts)

    # Helper per decidere RAG/inlining
    def _should_rag(name: str, text: str) -> bool:
        if rag_strategy == "force":
            return True
        if rag_strategy == "off":
            return False
        # prefer: se nel set preferiti o se sforiamo budget
        prefer = (name in rag_prefer_for)
        overflow = not _fits_budget(inline_chars + _safe_len(text), prefs)
        return prefer or overflow

    # IDEA
    if idea_text:
        n = "IDEA.md"
        if _should_rag(n, idea_text):
            parts.append("### IDEA (abstract)\n" + _make_abstract(idea_text, prefs.abstract_lines))
            rag_refs.append(_pack_rag_ref(n, path="docs/harper/IDEA.md"))
        else:
            parts.append("### IDEA.md (verbatim)\n" + idea_text[:prefs.max_snippet_chars])
        inline_chars = sum(_safe_len(x) for x in parts)

    # SPEC
    if spec_text:
        n = "SPEC.md"
        if _should_rag(n, spec_text):
            parts.append("### SPEC (abstract)\n" + _make_abstract(spec_text, prefs.abstract_lines))
            rag_refs.append(_pack_rag_ref(n, path="docs/harper/SPEC.md"))
        else:
            parts.append("### SPEC.md (verbatim)\n" + spec_text[:prefs.max_snippet_chars])
        inline_chars = sum(_safe_len(x) for x in parts)

    # TECH_CONSTRAINTS → inline (troncato) + ref
    if tech_yaml:
        trimmed_yaml = tech_yaml
        if _safe_len(trimmed_yaml) > prefs.max_snippet_chars:
            trimmed_yaml = trimmed_yaml[:prefs.max_snippet_chars] + "\n# ... truncated"
        parts.append("### Technology Constraints (YAML)\n```yaml\n" + trimmed_yaml + "\n```")
        rag_refs.append(_pack_rag_ref("TECH_CONSTRAINTS.yaml", path="docs/harper/TECH_CONSTRAINTS.yaml"))
        inline_chars = sum(_safe_len(x) for x in parts)

    # altri core minori → solo refs
    for name, content in core_blobs.items():
        if name in ("SPEC.md","TECH_CONSTRAINTS.yaml","TECH_CONSTRAINTS.yml"): 
            continue
        rag_refs.append(_pack_rag_ref(name, path=f"docs/harper/{name}"))

    # targets/REQ hint
    if targets:
        parts.append("### Targets\n- " + "\n- ".join(targets))

    # task generico (il system specifica l'Output Contract per fase)
    parts.append(
        f"### Task\nPhase={phase.upper()}. Produce the phase output, strictly following the Output Contract.\n"
        f"- Prefer citing RAG refs where large.\n"
        f"- Return only the Markdown for this phase, plus any declared side artifacts.\n"
    )

    user_text = "\n\n".join(parts).strip()
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_text}
    ]
    # attach pragmatic RAG metadata for the gateway (not exposed to model)
    messages[-1]["rag_refs"] = rag_refs
    # --- Emit-first nudge in USER message (harmless for other phases) ---
    if (phase or "").lower() == "plan":
        messages[1]["content"] += (
            "\n\n### EMIT-NOW\n"
            "Begin immediately by writing the first file block:\n"
            "```\nfile:docs/harper/PLAN.md\n# PLAN — <Project Name>\n```\n"
            "Do not preface with analysis. Complete PLAN.md first (end with ```PLAN_END```), "
            "then emit plan.json and lane-guides in the same response."
        )
    return messages



def get_model_params(phase: str) -> dict:
    return PHASE_MODEL_PARAMS.get((phase or "").lower(), {"max_tokens": 6000, "temperature": 0.25, "top_p": 1.0})
# === PATCH 1A: Helpers per derivare plan.json dal PLAN.md (Markdown table) ===
import re
import json

def _extract_req_table_md(plan_md: str) -> str | None:
    """
    Estrae la sezione '## REQ-IDs Table' come markdown table (header + sep + rows).
    Ritorna la table come stringa o None.
    """
    if not plan_md:
        return None
    # Match dalla sezione fino alla prossima sezione (##) o fine testo
    sec_rx = re.compile(r'(##\s*REQ-IDs Table)([\s\S]*?)(?=^##\s|\Z)', re.MULTILINE)
    m = sec_rx.search(plan_md)
    if not m:
        return None
    block = m.group(2).strip()
    # cerca la tabella markdown (header | sep | rows)
    # molto permissivo: prima riga con |, seconda riga con ---
    lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2 or '|' not in lines[0]:
        return None
    return "\n".join(lines)

def _parse_md_table(md_table: str) -> list[dict]:
    """
    Parsifica una markdown table GitHub-style in array di dict.
    Richiede header + sep + rows. Gestisce celle con contenuto semplice (pipe-split).
    """
    rows = [ln.strip() for ln in md_table.splitlines() if ln.strip()]
    if len(rows) < 2:
        return []
    header = [c.strip() for c in rows[0].strip('|').split('|')]
    # salta la riga di separatori
    data_rows = []
    for ln in rows[2:]:
        if '|' not in ln:
            continue
        cols = [c.strip() for c in ln.strip('|').split('|')]
        # normalizza lunghezze
        while len(cols) < len(header):
            cols.append('')
        item = { header[i]: cols[i] for i in range(len(header)) }
        data_rows.append(item)
    return data_rows

def _norm_list(val: str) -> list[str]:
    """
    Converte una cella tipo 'REQ-001,REQ-002' -> ['REQ-001','REQ-002'].
    Supporta <br> come separatore multiplo.
    """
    if not val:
        return []
    # sostieni eventuali <br> inseriti in Acceptance
    parts = re.split(r'(?:<br>|,)', val)
    return [p.strip() for p in parts if p and p.strip()]

def _derive_plan_json_from_md(plan_md: str) -> dict | None:
    """
    Deriva un plan.json con forma:
    {
      "reqs":[
        {"id":"REQ-001","title":"...","acceptance":["..."],"dependsOn":["REQ-002"],"track":"App","status":"open"},
        ...
      ],
      "snapshot":{"total":N,"open":n1,"in_progress":n2,"done":n3,"deferred":n4,"progressPct":...}
    }
    """
    table_md = _extract_req_table_md(plan_md)
    if not table_md:
        return None
    rows = _parse_md_table(table_md)
    if not rows:
        return None

    # mapping robusto by column names (case-insensitive)
    def _get(row: dict, name: str) -> str:
        for k, v in row.items():
            if k.strip().lower() == name:
                return v or ''
        return ''

    reqs = []
    for r in rows:
        rid       = _get(r, 'id')
        title     = _get(r, 'title')
        acc_cell  = _get(r, 'acceptance (bullets)')
        deps_cell = _get(r, 'dependson')
        track     = _get(r, 'track (app|infra)') or _get(r, 'track') or 'App'
        status    = _get(r, 'status (open|done|deferred)') or _get(r, 'status') or 'open'

        # acceptance: ogni bullet può essere separato da <br> o nuovi a capo già fusi
        # Rimuovi eventuali prefissi "• " inseriti in tabella
        acceptance = [re.sub(r'^[\-\*\u2022]\s*', '', x).strip() for x in _norm_list(acc_cell)]

        depends = [x for x in _norm_list(deps_cell) if x]

        if rid:
            reqs.append({
                "id": rid,
                "title": title,
                "acceptance": acceptance,
                "dependsOn": depends,
                "track": track if track in ("App","Infra") else "App",
                "status": status if status in ("open","done","deferred","in_progress") else "open"
            })

    # snapshot
    total = len(reqs)
    cnt = {"open":0,"done":0,"deferred":0,"in_progress":0}
    for r in reqs:
        st = r["status"]
        if st in cnt:
            cnt[st] += 1
    progress = round((cnt["done"]/total)*100) if total else 0

    return {
        "reqs": reqs,
        "snapshot": {
            "total": total,
            "open": cnt["open"],
            "in_progress": cnt["in_progress"],
            "done": cnt["done"],
            "deferred": cnt["deferred"],
            "progressPct": progress
        }
    }

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
    url = _normalize_repo_url(repo_url) or "https:/afucompany.it/"
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
    Estrae blocchi file in tre varianti:

    A) FENCED:
      ```<qualcosa>
      file:/path/to/file.ext
      <contenuto>
      ```

    B) PLAIN:
      file:/path/to/file.ext
      <contenuto fino al prossimo "file:" o EOF>

    C) BEGIN_FILE:
      BEGIN_FILE path/to/file.ext
      <contenuto>
      END_FILE

    Ritorna (files, remainder) dove:
      - files: lista di {path, content, mime, encoding}
      - remainder: testo rimanente senza i blocchi estratti
    """
    files: list[dict] = []
    if not text:
        return [], ""

    intervals: list[tuple[int, int]] = []

    # --- A) FENCED ---
    for m in _FILE_BLOCK_FENCED_RE.finditer(text):
        start, end = m.span()
        intervals.append((start, end))
        raw_path = (m.group(1) or "").strip()
        content = (m.group(2) or "")
        norm_path = raw_path.lstrip().lstrip("/")
        files.append({
            "path": norm_path,
            "content": content,
            "mime": _guess_mime(norm_path),
            "encoding": "utf-8",
        })

    # --- B) PLAIN ---
    for m in _FILE_BLOCK_PLAIN_RE.finditer(text):
        start, end = m.span()
        intervals.append((start, end))
        raw_path = (m.group(1) or "").strip()
        content = (m.group(2) or "")
        content = re.sub(r"\n```+\s*\Z", "\n", content)
        norm_path = raw_path.lstrip().lstrip("/")
        files.append({
            "path": norm_path,
            "content": content.strip("\n"),
            "mime": _guess_mime(norm_path),
            "encoding": "utf-8",
        })

    # --- C) BEGIN_FILE ---
    for m in _FILE_BLOCK_BEGIN_RE.finditer(text):
        start, end = m.span()
        intervals.append((start, end))
        raw_path = (m.group(1) or "").strip()
        content = (m.group(2) or "")
        norm_path = raw_path.lstrip().lstrip("/")
        files.append({
            "path": norm_path,
            "content": content.strip("\n"),
            "mime": _guess_mime(norm_path),
            "encoding": "utf-8",
        })

    if not intervals:
        return [], text.strip()

    # Rimuovi gli intervalli estratti per ottenere il remainder
    intervals.sort()
    remainder_parts: list[str] = []
    last = 0
    for s, e in intervals:
        if last < s:
            remainder_parts.append(text[last:s])
        last = max(last, e)
    if last < len(text):
        remainder_parts.append(text[last:])
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
}# Pass-through opzionali dal req.gen (se presenti)


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

def _append_kit_target_to_user(user_text: str, targets: list[str], acceptance: Optional[list[str]] = list[str]) -> str:
    
    if not targets:
        return user_text
    rid = targets[0]
    # opzionale: acceptance passata dal client
    acc = acceptance or []
    section = [ "\n### KIT Target", f"- REQ: {rid}" ]
    if isinstance(acc, list) and acc:
        section.append("- Acceptance (from plan):")
        section.extend([f"  - {a}" for a in acc])
    return user_text + "\n" + "\n".join(section) + "\n"

def compose_system_messages(phase: str,  repo_url: str | None) -> list[dict]: 
    "Build OpenAI/Anthropic style chat messages: system + user. Minimal, RAG-light."""
    log.info("Compose system messages for phase %s", phase)
    system_by_phase = {
        "spec": PROMPT_SPEC_SYSTEM_PATH,
        "plan": PROMPT_PLAN_SYSTEM_PATH,
        "kit": PROMPT_KIT_SYSTEM_PATH,
        "finalize": PROMPT_FINALIZE_SYSTEM_PATH,
    }
    system_path = system_by_phase.get(phase)
    system = _read_text(system_path).strip() or "# Harper System Prompt\nFollow the phase contract strictly."
    #log.info("System prdockeompt for phase %s: %s", phase, system)
    if phase == "kit" and repo_url:
        system = _inject_repo_url_in_system(system, repo_url) 
    #log.debug("System w/ repo url prompt for phase %s: %s", phase, system)
    return system

# deprecated
def _too_long_compose_system_messages(phase: str,
                            idea_md: Optional[str],
                            core_blobs: dict | None,
                            profile_hint: str | None,
                            model_route_label: str | None,
                            run_id: str | None,
                            repo_url: str | None,
                            targets: Optional[list[str]]) -> list[dict]:
    log.info("Compose system messages for phase (too long) %s", phase)
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
    log.info("componse message nmber: %s", len(system.split("\n")))

    # Background context (IDEA + optional core blobs names)
    idea_md or ""
    constraints_keys: list[str] = []
    other_core: dict[str, str] = {}
    constraints_chunks: list[str] = []

    if core_blobs:
       
        log.info("componse message nmber: %s", len(system.split("\n")))
        for name, content in core_blobs.items():
            lname = (name or "").lower()
            
            log.info("componse message nmber: %s", len(system.split("\n")))
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
    log.info("componse message nmber: %s", len(system.split("\n")))

    if other_core:
        for n, c in other_core.items():
            suffix_parts.append(f"\n\n### {n} (verbatim)\n{c}")

    # Technology Constraints unified block (if any were found under core)
    if constraints_chunks:
        # Non forziamo il parsing; mostriamo come testo YAML fenced per massima compatibilità
        constraints_text = "\n\n---\n\n".join(constraints_chunks)
        suffix_parts.append("### Technology Constraints (YAML)\n```yaml\n" + constraints_text + "\n```")

    suffix = "".join(suffix_parts)
    idea_txt = ""
    if idea_md and phase.lower() == 'spec':
        idea_txt = f"### IDEA.md (verbatim)\n{idea_md}\n\n"
    user = (
        f"{foreground}\n\n"
        f"### Route\n- profile: {profile_hint or '—'}\n- model: {model_route_label or '—'}\n- runId: {run_id or 'n/a'}\n\n"
        f"{idea_txt}"
        f"{refs}\n\n"
        f"{_output_checklist_for_phase(phase)}"
        f"### Task\nProduce/Transform the {phase.upper()} output that strictly follows the Output contract. Return only the Markdown document for this phase.{suffix}"
    )
    # --- se fase KIT, inietta direttiva target ---
    if (phase or "").lower() == "kit":
        user = _append_kit_target_to_user(user, targets=targets)

    user_ummy = (
        "### Task\n"
        "Produce the 3 files as specified by the system message.\n"
        "Project: 'CoffeeBuddy (On-Prem)'"
        "### Inputs IDEA.md title: # IDEA — CoffeeBuddy (On-Prem)\n"
        "CoffeeBuddy streamlines office coffee runs entirely within the corporate network: teammates submit orders via Slack,\n"
        "teammates submit orders via Slack, one teammate is fairly assigned as runner, reminders are sent, and preferences are remembered—without relying on public cloud\n"
        "eams coordinate coffee orders in ad-hoc Slack threads. Messages get buried, someone forgets to pick up, and no one remembers preferences. In regulated environments, external cloud services are restricted, so the solution must run fully on-prem.\n"

        "### Constraints\n"
        "- Keep it minimal and deterministic.\n"
    )
    user_dummy= (f"{user_ummy}\n\n")
    
    #log.debug("User prompt for phase %s: %s", phase, user)
    messages_output = [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user.strip()},
    ]
    #log.debug("User prompt for phase %s: %s", phase, user)
    #log.debug("System prompt for phase %s: %s", phase, system)

    return messages_output

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

class HarperKitOptions(BaseModel):
    targets: Optional[List[str]] = Field(default=None)
    batch: Optional[int] = Field(default=None, ge=1)
    req_ids: Optional[List[str]] = Field(default=None)  # backward-compat alias
    rescope: Optional[bool] = Field(default=False)

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
    kit: Optional[HarperKitOptions] = None
    rag_strategy: Optional[str] = None
    context_hard_limit: Optional[int] = None
    rag_prefer_for: Optional[List[str]] = None
    project_id: Optional[str] = None
    rag_chunks: Optional[List[dict]] = None
    rag_queries: Optional[List[str]] = None
    rag_top_k: Optional[int] = None



def _normalize_attachments(atts: List[Union[str, Attachment]]) -> List[dict]:
    out: List[dict] = []
    for a in atts or []:
        if isinstance(a, str):
            out.append({"name": a})
        else:
            out.append(a.model_dump())
    return out

# --- RAG merging: ephemeral chunks + store retrieval -------------------------

def merge_rag_material(rag_prefer_for,rag_refs,messages,store):
#(body: dict, store) -> list[dict]:
    """
    Restituisce una lista di 'materials' usabili dal prompt builder.
    Ogni item: {title, text, source}
    - Preferisce 'rag_prefer_for' dal client (ephemeral, testuali).
    - Poi usa 'rag_refs' (metadati) per recuperare dal rag_store (se disponibile).
    """
    materials = []

    # 1) client-provided chunks (preferred)
    for ch in (rag_prefer_for or []):
        txt = (ch.get("text") or "").strip()
        if not txt: continue
        title = f"{ch.get('name','doc')}"
        idx = ch.get("idx")
        if idx is not None: title += f"#{idx}"
        materials.append({"title": title, "text": txt, "source": "client"})

    # 2) server store by refs
    refs = (rag_refs or messages[-1].get("rag_refs") or [])
    for ref in refs:
        try:
            doc = None
            if hasattr(store, "get_by_path") and ref.get("path"):
                doc = store.get_by_path(ref["path"])
            elif hasattr(store, "get_by_id") and ref.get("doc_id"):
                doc = store.get_by_id(ref["doc_id"])
            if doc and doc.get("text"):
                # puoi fare anche chunking qui se necessario
                materials.append({"title": ref.get("name") or ref.get("path") or "doc", "text": doc["text"], "source": "store"})
        except Exception:
            continue

    return materials

# --- RAG merging: client chunks + server search (Qdrant) --------------------

def _chunk_map_from_client(rag_chunks: dict) -> dict:
    """Crea un dizionario {(name, idx) -> text} dai rag_chunks client."""
    cmap = {}
    for ch in (rag_chunks or []):
        name = (ch.get("name") or "").strip()
        idx  = ch.get("idx")
        txt  = (ch.get("text") or "").strip()
        if not name or idx is None or not txt:
            continue
        cmap[(name, int(idx))] = txt
    return cmap

async def gather_rag_materials(rag_chunks,rag_top_k, store, rag_queries = None) -> list[dict]:
    """
    Restituisce lista di materiali da includere nel prompt:
    [{title, text, source}]
    Strategia:
      1) client 'rag_chunks' (IDEA/SPEC) → sempre inclusi (ephemeral)
      2) server 'rag_queries' → search(top-k), preferendo 'text' dal payload;
         se assente, prova a mappare (path,chunk) sui rag_chunks client.
    """
    log.info("--- gather_rag_materials")
    materials = []
    ragTopK =  rag_top_k or os.getenv("RAG_TOP_K") or 12

    # 1) Ephemeral chunks dal client
    cmap = _chunk_map_from_client(rag_chunks)
    for (name, idx), txt in list(cmap.items())[:48]:  # cap di sicurezza
        materials.append({"title": f"{name}#{idx}", "text": txt, "source": "client"})

    # 2) Query sullo store (se definito e se arrivano rag_queries)
    queries = rag_queries or []
    if store and queries:
        for q in queries[:8]:  # cap query
            try:
                res = await store.search(q, top_k=ragTopK or 6)
            except Exception:
                res = []
            for hit in res:
                txt = (hit.get("text") or "").strip()
                if not txt:
                    # fallback: mappa su client chunks se possibile
                    key = (hit.get("path","").split("/")[-1], int(hit.get("chunk",0)))
                    txt = cmap.get(key, "")
                if txt:
                    title = f"{hit.get('path','') or 'doc'}#{hit.get('chunk',0)} (score={hit.get('score',0.0):.3f})"
                    materials.append({"title": title, "text": txt, "source": "store"})
    return materials

async def _retrive_rag_chunks(messages: list[dict], rag_chunks: list[dict] | None, rag_queries: list[str] | None, rag_top_k: int | None,  project_id: str | None ) -> list[dict]:
    # 2) RAG: client-first + server-search (Qdrant)

    materials = []
    try:
        log.info("Clike with '%s' ", project_id)
        store = RagStore(project_id=project_id or "default") if RagStore else None
        log.info("store  '%s' ", store)

        # Prepara 'rag_queries' se non arrivano dal client: estrai da IDEA/SPEC headings nei chunks
        if not rag_queries:
            log.info("rag_queries not found (rag_chunks) '%s' ", rag_chunks)
            qs = []
            for ch in (rag_chunks or []):
                name = (ch.get("name") or "").lower()
                if name in ("idea.md","spec.md"):
                    # prime heading line come query
                    for ln in (ch.get("text") or "").splitlines():
                        if ln.strip().startswith("#"):
                            qs.append(ln.strip("# ").strip())
                            break
            rag_queries = qs[:6]  # piccolo cap

        materials = await gather_rag_materials(rag_chunks, rag_top_k, store)
       #log.info("materials '%s' ", materials)

    except Exception as _e:
        log.exception("Failed to gather RAG materials: %s", _e)
    return materials

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
    default_params_reasoning =get_model_params(phase);
    log.info("harper.run phase=%s model=%s params=%s gen=%s", phase, req.model, default_params_reasoning, req.gen)
    resolved_entry = None
    if req.model and not str(req.model).lower().startswith(("openai:","anthropic:","ollama:","vllm:","deepseek:","azure:","google:")):
        resolved_entry = _gw_try_match_model(str(req.model))
        if resolved_entry:
            log.info("harper.gateway normalized model '%s' -> id=%s (provider=%s)",
                     req.model, resolved_entry.get("id"), resolved_entry.get("provider"))
    
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
    log.info("harper enabled model=%s", model)

    log.info("harper run req.kit=%s", req.kit)

    if req.kit is not None:
        targets = req.kit.targets or []
        log.info("harper targets=%s", targets)

    else:
        targets = []

   
    context_hard_limit =  getattr(req, "context_hard_limit", 6500)
    rag_strategy         = req.rag_strategy
    rag_prefer_for       = req.rag_prefer_for 
    reasoning =''
    #req.gen =  {}
    # ---- Gen params allineati a chat ----
    # --- Emission guards for /plan: visible text + low reasoning ---
    if (phase or "").lower() == "plan":
        # Forza formato testuale se non già impostato
        try:
            g = req.gen or {}
            if not g.get("response_format"):
                g["response_format"] = {"type": "text"}
            # if not g.get("reasoning"):
            #     g["reasoning"] = {"effort": "low"}
            #     g.setdefault("reasoning", {"effort": "low"})
            # if not g.get("stop"):
            #     g["stop"] = ["PLAN_END"]  
            
            # Hint per modelli reasoning (se supportato dal provider)
            
            req.gen = g
        except Exception:
            pass
    g = req.gen or {}

    
    log.info("harper.run gen=%s", g)
    log.info("harper.run params=%s", default_params_reasoning)
    req.gen["temperature"] = default_params_reasoning.get("temperature") or req.gen.get("temperature", 0.2)
    req.gen["max_tokens"] = default_params_reasoning.get("max_tokens") or req.gen.get("max_tokens", 6500)
    #req.gen["top_p"] = default_params_reasoning.get("top_p") or req.gen.get("top_p")
    req.gen["stop"] = req.gen.get("stop") or ("```PLAN_END```")
    #    - Se gen["api"] == "responses" usa /v1/responses, altrimenti /v1/chat/completions.
    req.gen["api"] = "responses"

    gen_temperature = default_params_reasoning.get("temperature") or g.get("temperature", 0.2)
    gen_max_tokens = default_params_reasoning.get("max_tokens") or  g.get("max_tokens", 6500)
    gen_top_p = default_params_reasoning.get("top_p") or g.get("top_p")
    gen_stop = g.get("stop")
    gen_presence_penalty = g.get("presence_penalty")
    gen_frequency_penalty = g.get("frequency_penalty")
    gen_seed = g.get("seed")
    gen_tools = g.get("tools")
    gen_remote = g.get("remote")
    gen_response_format = g.get("response_format")
    gen_reasoning = g.get("reasoning")
    gen_tool_choice = g.get("tool_choice")
    
    repourl = getattr(req, "repoUrl", None)
    
    
    prefs = TokenPrefs(
        hard_limit = int(context_hard_limit or 6500),
        headroom   = 800,
        max_snippet_chars = 6000,
        abstract_lines = 12,
    )
    log.info("harper enabled TokenPrefs=%s", prefs)


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
    log.info("model_route_label (too long) %s", model_route_label)

    # system_txt = compose_system_messages(phase, repourl)
    # #log.info("harper.gateway system_txt messages '%s' ", system_txt)

    messages = _too_long_compose_system_messages(
                            phase,
                            idea,
                            core_blobs,
                            req.profileHint,
                            model_route_label,
                            req.runId,
                            repourl,
                            targets)
    
    materials = await _retrive_rag_chunks(messages, req.rag_chunks, req.rag_queries, req.rag_top_k,  req.project_id )
    if materials:
        appendix = "\n\n### RAG Context\n" + "\n\n".join(
            f"#### {m['title']}\n{m['text']}" for m in materials[:12]
        )
        #log.info("materials appendix '%s' ", appendix)

        messages[1]["content"] += appendix
    
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
    requested_out = int((req.gen or {}).get("max_tokens", 6500))
    # margine di sicurezza per header/model/tooling
    SAFETY_PROMPT_TOKENS = 250 #Soglia minima: se chat_budget < 200 token, non appendere “Recent Harper chat” (rumore > valore).
    # budget per chat = ctx - base_prompt - requested_out - safety (>=0)
    chat_budget = max(0, ctx_window - base_prompt_tokens - requested_out - SAFETY_PROMPT_TOKENS)
    if incoming and chat_budget > 0:
        raw_ctx = _render_chat_context(incoming)
        clipped_ctx = _clip_text_to_tokens(raw_ctx, chat_budget)
        if clipped_ctx:
            # Ricicliamo il messaggio 'user' già costruito, aggiungendo un blocco "Recent Harper chat"
            messages[1]["content"] += "\n\n### Recent Harper chat (trimmed)\n" + clipped_ctx
    # 0) Check token per model
    # --- Context budgeting ---
    eff_max = _tokens_per_model(messages, resolved_entry, gen_max_tokens)
    # timeout dinamico (60s base + 2s per 1k token, max 180s)
    # tuning: timeout dinamico (90s base + 3.5s per 1k token, max 3000)
    timeout_sec = min(300.0, 110 + (eff_max / 1000.0) * 3.5)
    #timeout_sec =300.0
    log.info("harper.gateway eff_max & timeout '%s' '%s'",
                    eff_max, timeout_sec)
    log.info("harper.gateway eff_max=%s ctx_window=%s prompt_tokens≈%s cap=%s",
        eff_max,
        (_resolve_ctx_caps(resolved_entry)[0]),
        approx_tokens_from_chars("".join(m.get("content","") for m in messages if isinstance(m.get("content"), str))),
        (_resolve_ctx_caps(resolved_entry)[1]))
    #log.info("harper.gateway normalized messages '%s' ", messages)

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

            llm_text = await oai.openai_complete_unified(OPENAI_API_KEY, model, messages, req.gen, timeout_sec)
                #llm_text = await oai.chat(OPENAI_BASE, OPENAI_API_KEY, model, messages, gen_temperature, eff_max, gen_response_format,gen_reasoning, gen_tools, gen_tool_choice, timeout=timeout_sec, top_p=gen_top_p, stop=gen_stop) 

        elif provider == "vllm":
            llm_text =  await vll.chat(VLLM_BASE, model, messages, gen_temperature, eff_max, gen_response_format, gen_tools, gen_tool_choice, gen_top_p)
        elif provider == "ollama":
            llm_text =  await oll.chat(OLLAMA_BASE, model, messages, gen_temperature, eff_max, gen_top_p)   

        elif provider == "anthropic":
            if not ANTHROPIC_API_KEY:
                raise HTTPException(401, "missing ANTHROPIC api key")
            llm_text = await anth.chat(ANTHROPIC_BASE, ANTHROPIC_API_KEY, model, messages, gen_temperature,eff_max, gen_top_p)
            
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
    # system_md_txt = ""
    # system_md_txt, llm_usage = oai.coerce_text_and_usage(llm_text)
    # system_md_txt = (system_md_txt or "").strip()


    provider_files: list[dict] = []
    llm_usage = {}
    llm_usage = llm_text.get("usage") or {}
    system_md_txt = (llm_text.get("text") or "").strip()
    provider_files = llm_text.get("files") or []



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


    # --- Multi-file support ---
    output_name = PHASE_OUTPUT_FILE.get(phase, f"{phase.upper()}.md")
    default_doc_path = f"{req.docRoot or 'docs/harper'}/{output_name}"
    
    files: list[dict] = []

    gen_files, remainder = _extract_file_blocks(system_md_txt)

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

    # --- plan.json derivation from PLAN.md (only for phase=plan) ---
    if phase == "plan":
        # 1) Trova il contenuto del PLAN.md che stiamo restituendo
        plan_md_text = None
        # path atteso del documento di fase
        plan_doc_path = f"{req.docRoot or 'docs/harper'}/PLAN.md"

        # Se ci sono file-block: preferisci il file esplicito PLAN.md
        for f in files:
            p = (f.get("path") or "").strip()
            if p.endswith("/PLAN.md") or p == plan_doc_path:
                plan_md_text = f.get("content") or ""
                break

        # Se non c'è un file esplicito, e non c’erano file-block,
        # allora il documento di fase è l’intero output di testo
        if plan_md_text is None and not gen_files:
            plan_md_text = system_md_txt or ""

        # 2) Deriva plan.json e aggiungilo ai files
        if plan_md_text:
            try:
                plan_json = _derive_plan_json_from_md(plan_md_text)
            except Exception as e:
                plan_json = None
                warnings.append(f"plan_json_derivation_error: {type(e).__name__}: {e}")

            if plan_json:
                files.append({
                    "path": f"{req.docRoot or 'docs/harper'}/plan.json",
                    "content": json.dumps(plan_json, indent=2),
                    "mime": "application/json",
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
    
