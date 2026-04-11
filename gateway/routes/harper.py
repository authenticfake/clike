# gateway/routes/harper.py
from __future__ import annotations
import asyncio
import json
import traceback
import uuid
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any, Union
import logging, time, ast
from pathlib import Path
import os, datetime
import httpx
from utils.sanitize import sanitize_for_path
from utils.utils import   collect_rag_materials_http, decide_inline_or_rag
from utils.rag_store import RagStore
from routes.chat import ANTHROPIC_API_KEY, ANTHROPIC_BASE, DEEPSEEK_BASE, OLLAMA_BASE, OPENAI_API_KEY, DEEPSEEK_API_KEY, OPENAI_BASE, VLLM_BASE, _json
from providers import openai_compat as oai
from providers import anthropic as anth
from providers import deepseek as deepseek
from providers import ollama as oll
from providers import vllm as vll
import yaml
import mimetypes
from pricing import PricingManager  # [pricing]

# --- Defaults per modelli che non hanno context definito ---
DEFAULT_CONTEXT_WINDOW = 128_000     # conservativo
DEFAULT_MAX_OUTPUT = 16_384          # conservativo
router = APIRouter(prefix="/v1/harper", tags=["harper"])

log = logging.getLogger("harper")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ----     context builders ---------------------------------------------------
PROMPT_IDEA_SYSTEM_PATH = os.getenv("PROMPT_IDEA_SYSTEM_PATH", "/app/prompts/harper/idea_system.md")
PROMPT_SPEC_SYSTEM_PATH = os.getenv("PROMPT_SPEC_SYSTEM_PATH", "/app/prompts/harper/spec_system.md")
SPEC_TEMPLATE_PATH = os.getenv("SPEC_TEMPLATE_PATH", "/app/templates/SPEC_TEMPLATE.md")
PROMPT_PLAN_SYSTEM_PATH = os.getenv("PROMPT_PLAN_SYSTEM_PATH", "/app/prompts/harper/plan_system.md")
PROMPT_KIT_SYSTEM_PATH = os.getenv("PROMPT_KIT_SYSTEM_PATH", "/app/prompts/harper/kit_system.md")
PROMPT_INTEGRITY_EVAL_SYSTEM_PATH = os.getenv("PROMPT_INTEGRITY_EVAL_SYSTEM_PATH", "/app/prompts/harper/integrity_eval.md")
PROMPT_PROMOTION_HARDENER_SYSTEM_PATH = os.getenv("PROMPT_PROMOTION_HARDENER_SYSTEM_PATH", "/app/prompts/harper/promotion_hardener.md")
PROMPT_PROMOTION_EVAL_SYSTEM_PATH = os.getenv("PROMPT_PROMOTION_EVAL_SYSTEM_PATH", "/app/prompts/harper/promotion_eval.md")
PROMPT_BUILD_SYSTEM_PATH = os.getenv("PROMPT_BIULD_SYSTEM_PATH", "/app/prompts/harper/build_system.md")
PROMPT_FINALIZE_SYSTEM_PATH = os.getenv("PROMPT_FINALIZE_SYSTEM_PATH", "/app/prompts/harper/finalize_system.md")

TELEMETRY_DIR = os.getenv("HARPER_TELEMETRY_DIR", "/workspace/telemetry")  # scrive qui i .jsonl
STUB_DIR = os.getenv("HARPER_STUB_DIR", "/workspace/gateway/stub")  # scrive qui i .jsonl

_REPO_PLACEHOLDER = "[x]"
_FILE_BLOCK_FENCED_RE = re.compile(
    r"(?:^|\n)```[^\n]*\n\s*file:([^\n]+)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE
)
_FILE_BLOCK_PLAIN_RE = re.compile(
    r"(?:^|\n)file:([^\n]+)\n(.*?)(?=(?:\nfile:[^\n]+\n)|\Z)",
    re.DOTALL | re.IGNORECASE
)
_FILE_BLOCK_BEGIN_RE = re.compile(
    r"(?:^|\n)BEGIN_FILE\s+([^\n]+)\n(.*?)(?:\nEND_FILE|$)",
    re.DOTALL | re.IGNORECASE
)
_FILE_BLOCK_FENCED_INLINE_RE = re.compile(
    r"(?:^|\n)```file:([^\n]+)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE
)

# --- Model parameters per phase (output budget & style) ----------------------
PHASE_MODEL_PARAMS = {
    "idea":                 {"max_tokens": 23500, "temperature": 0.2, "top_p": 1.0},
    "spec":                 {"max_tokens": 29500, "temperature": 0.2, "top_p": 1.0},
    "plan":                 {"max_tokens": 45000, "temperature": 0.2, "top_p": 0.8},  # raise to 6500 only if many lanes
    "kit":                  {"max_tokens": 48000, "temperature": 0.1, "top_p": 1.0},
    "integrity_eval":       {"max_tokens": 17000, "temperature": 0.1, "top_p": 1.0},
    "promotion_hardener":   {"max_tokens": 22000, "temperature": 0.1, "top_p": 1.0},
    "promotion_eval":       {"max_tokens": 18000, "temperature": 0.1, "top_p": 1.0},
    "eval":     {"max_tokens": 6500, "temperature": 0.1, "top_p": 1.0},
    "gate":     {"max_tokens": 6000, "temperature": 0.1, "top_p": 1.0},
    "finalize": {"max_tokens": 31000, "temperature": 0.1, "top_p": 1.0},
}
# --- RAG helpers: filter out docs and non-source hits -----------------------

_DOC_EXTS: set[str] = {".md", ".markdown", ".rst", ".txt", ".adoc", ".tex", ".pdf", ".doc",".docx", ".xlsx", "xls", ".ppt", ".pptx" }


def _is_source_rag_path(path: str | None) -> bool:
    """
    Returns True only for paths we consider 'source-ish'.

    Rules:
    - Reject anything under docs/ (or containing /docs/).
    - Reject classic documentation extensions (.md, .rst, .txt, ...).
    - Everything else is allowed (code, config, schema, etc.).
    """
    if not path:
        return False

    p = (path or "").strip().lower()
    if not p:
        return False

    # Reject docs folders (project docs, harper docs, etc.)
    if p.startswith("docs/") or "/docs/" in p:
        return False

    # Reject pure documentation extensions
    base, ext = os.path.splitext(p)
    if ext in _DOC_EXTS:
        return False

    return True

_PRICING = None  # [pricing-singleton]

def _get_pricing_manager():
    global _PRICING
    if _PRICING is None:
        _PRICING = PricingManager.from_models_yaml(os.getenv("MODELS_CONFIG", "../config/models.yaml"))
    return _PRICING

# --- Harper: Dynamic Context Budgeting (messages builder) --------------------
from dataclasses import dataclass

def _safe_len(s: str|None) -> int:
    return len(s or "")


def _canonicalize_path(p: str) -> str:
    """
    Normalizza i path per evitare duplicati logici:
    - slash forward
    - rimuove prefissi './' e slash iniziali
    - mappa 'doc/...' -> 'docs/...'
    - compattazione di slash ripetuti
    - normalizza 'docs/harper/plan.md' e 'docs/harper/plan.json' case-preserving
    """
    if not p:
        return p
    p = p.replace("\\", "/").lstrip().lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    # mappa alias 'doc/' in 'docs/'
    if p.startswith("doc/"):
        p = "docs/" + p[len("doc/"):]
    # compattazione degli slash multipli
    while "//" in p:
        p = p.replace("//", "/")
    return p


def get_model_params(phase: str) -> dict:
    return PHASE_MODEL_PARAMS.get((phase or "").lower(), {"max_tokens": 6000, "temperature": 0.25, "top_p": 1.0})


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


def _load_plan_json(core_blobs: dict | None) -> dict | None:
    """
    Load plan.json from core_blobs (functional use only, never sent to the LLM).

    We expect an entry whose name ends with 'plan.json' and whose value is the
    JSON payload as string. If not found or invalid, return None.
    """
    if not core_blobs:
        return None

    for name, content in (core_blobs or {}).items():
        lname = (name or "").lower().strip()
        if not lname.endswith("plan.json"):
            continue
        try:
            data = json.loads(content or "")
        except Exception as e:
            log.warning("harper.plan: failed to parse plan.json from core_blobs[%s]: %s", name, e)
            return None
        if not isinstance(data, dict):
            log.warning("harper.plan: plan.json in core_blobs[%s] is not a JSON object", name)
            return None
        return data

    log.info("harper.plan: no plan.json entry found in core_blobs")
    return None

# ---  collect gate_policy_ref paths for KIT --------------------------
def _collect_gate_policy_refs(plan_data: dict, targets: list[str]) -> list[str]:
    """
    Return lane/plan references (gate_policy_ref) for the given target REQ-IDs.

    We support both a single string and a list of strings for gate_policy_ref.
    """
    try:
        if not plan_data:
            return []

        reqs = plan_data.get("reqs") or []
        target_ids = {
            str(t or "").strip()
            for t in (targets or [])
            if str(t or "").strip()
        }

        refs: set[str] = set()
        for r in reqs:
            rid = str(r.get("id") or "").strip()
            if not rid or rid not in target_ids:
                continue

            ref_val = r.get("gate_policy_ref")
            
            if not ref_val:
                continue

            if isinstance(ref_val, str):
                v = ref_val.strip()
                if v:
                    refs.add(v)
            elif isinstance(ref_val, (list, tuple)):
                for x in ref_val:
                    v = str(x or "").strip()
                    if v:
                        refs.add(v)

        return sorted(refs)
    except Exception as exc:
        log.warning("collect_gate_policy_refs failed: %s", exc)
        return []


def _collect_req_deps(plan_data: dict, targets: list[str]) -> list[str]:
    """
    Given plan.json and a list of target REQ IDs, compute the transitive closure
    of their dependencies (dependsOn), excluding the targets themselves.

    Returns a sorted list of REQ IDs that are *dependencies* of the targets.
    """
    if not plan_data:
        return []

    reqs = (plan_data or {}).get("reqs") or []
    id2deps: dict[str, list[str]] = {}
    for r in reqs:
        rid = str(r.get("id") or "").strip()
        if not rid:
            continue
        deps = []
        for d in (r.get("dependsOn") or []):
            dd = str(d or "").strip()
            if dd:
                deps.append(dd)
        id2deps[rid] = deps

    targets_norm = [str(t or "").strip() for t in (targets or []) if str(t or "").strip()]
    visited: set[str] = set()
    stack: list[str] = list(targets_norm)

    while stack:
        cur = stack.pop()
        for dep in id2deps.get(cur, []):
            if dep not in visited:
                visited.add(dep)
                stack.append(dep)

    # escludi i target: ci interessano solo le *dipendenze*
    for t in targets_norm:
        if t in visited:
            visited.discard(t)

    return sorted(visited)


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

def _enforce_single_req_output(files_list: list[dict], target_req: str | None) -> list[dict]:
    """
    Reject any file outside the current target REQ staging root.
    """
    if not files_list or not target_req:
        return files_list or []

    prefix = f"runs/kit/{target_req}/"
    filtered: list[dict] = []

    for item in files_list:
        path = _canonicalize_path(str(item.get("path") or ""))
        if not path.startswith(prefix):
            log.warning(
                "harper.kit dropping file outside target req root: target=%s path=%s",
                target_req,
                path,
            )
            continue
        cloned = dict(item)
        cloned["path"] = path
        filtered.append(cloned)

    return filtered

def _dedupe_by_path(files_list: list[dict]) -> list[dict]:
    """
    Deduplica per path canonico. Se ci sono duplicati, tiene il contenuto più lungo.
    """
    seen: dict[str, dict] = {}
    for f in files_list or []:
        raw_path = (f.get("path") or "")
        canon = _canonicalize_path(raw_path)
        content = f.get("content") or ""
        if not canon:
            # salta file senza path
            continue
        best = seen.get(canon)
        if (best is None) or (len(content) > len(best.get("content") or "")):
            ff = dict(f)
            ff["path"] = canon
            seen[canon] = ff
    return list(seen.values())



def _extract_file_blocks(text: str, *, allow_plain: bool = True) -> tuple[list[dict], str]:
    """
    Extract file blocks from model output.

    Supported formats:
      A) FENCED:
         ```text
         file:/path/to/file.ext
         <content>
         ```

      A2) INLINE FENCED:
         ```file:/path/to/file.ext
         <content>
         ```

      B) PLAIN (optional, disabled for KIT):
         file:/path/to/file.ext
         <content until next file: or EOF>

      C) BEGIN_FILE:
         BEGIN_FILE path/to/file.ext
         <content>
         END_FILE

    Returns:
      - files: list of {path, content, mime, encoding}
      - remainder: text outside recognized file blocks
    """
    files: list[dict] = []
    if not text:
        return [], ""

    intervals: list[tuple[int, int]] = []

    # A) FENCED
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

    # A2) INLINE FENCED
    for m in _FILE_BLOCK_FENCED_INLINE_RE.finditer(text):
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

    # B) PLAIN (disabled for KIT)
    if allow_plain:
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

    # C) BEGIN_FILE
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
        log.info("no file blocks found")
        return [], text.strip()

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
    "idea": "IDEA.md",
    "spec": "SPEC.md",
    "plan": "PLAN.md",
    "kit": "KIT.md",
    "build": "BUILD_REPORT.md",
    "finalize": "RELEASE_NOTES.md",
}
PHASE_INPUT_FILE = {
    "idea": [],
    "spec": ["IDEA.md"],
    "plan": ["IDEA.md", "SPEC.md"],
    "kit": ["SPEC.md", "PLAN.md"],
    "finalize":["IDEA.md", "SPEC.md", "PLAN.md"],
}# Pass-through opzionali dal req.gen (se presenti)

def _filter_core_blobs_for_kit(
    core_blobs: dict | None,
    target_req: str | None,
) -> dict[str, str]:
    """
    Keep only the blobs that are useful for the current KIT target.

    This reduces prompt drift by removing unrelated manifest noise and stale REQ
    material from previous runs.
    """
    if not core_blobs:
        return {}

    target_req = str(target_req or "").strip()
    kept: dict[str, str] = {}

    always_keep_suffixes = (
        "spec.md",
        "plan.md",
        "plan.json",
        "tech_constraints.yaml",
    )
    always_keep_prefixes = (
        "REPO_ACCESS_MANIFEST",
        "REPO_STRUCTURE_EVIDENCE",
        "REPO_COMPOSITION_MANIFEST",
    )

    for name, content in core_blobs.items():
        key = str(name or "").strip()
        lkey = key.lower()

        if any(lkey.endswith(sfx) for sfx in always_keep_suffixes):
            kept[key] = content
            continue

        if any(key.startswith(prefix) for prefix in always_keep_prefixes):
            kept[key] = content
            continue

        if key.startswith("REQ_PROMOTION_MANIFEST"):
            if target_req and target_req in key:
                kept[key] = content
            elif target_req and f"REQ Promotion Manifest — {target_req}" in str(content):
                kept[key] = content
            continue

    return kept


def _build_kit_user_message(
    phase: str,
    user: str,
    core_blobs: dict | None,
    targets: list[str] | None,
) -> str:
    """
    For KIT, replace the giant narrative prompt with a smaller target-first prompt.
    """
    if (phase or "").lower() != "kit":
        return user

    target_req = str((targets or [None])[0] or "").strip()
    filtered_core = _filter_core_blobs_for_kit(core_blobs, target_req)

    refs = []
    for name, content in filtered_core.items():
        refs.append(f"- {name} ({len(content or '')} chars)")

    concise_parts = [
        "## CLike Principles (short)",
        "- Harper pipeline: IDEA→SPEC→PLAN→KIT, eval-driven quality, outcome-first.",
        "- Keep output concise but testable; Acceptance Criteria are mandatory.",
        "- Maintain human-in-control tone; do not invent facts.",
        "",
        "## KIT EXECUTION MODE",
        f"- Current phase: {phase}",
        f"- Current target REQ-ID: {target_req}",
        "- Use only the current target REQ staging root.",
        "- Dependencies are context only and must not receive emitted files.",
        "- If context conflicts with the target block, obey the target block.",
        "",
        "## Included references",
    ]
    concise_parts.extend(refs if refs else ["- none"])
    concise_parts.extend([
            "",
            "## OUTPUT CONFORMITY CHECKLIST",
            "- Emit one or more `file:/path` fenced blocks with complete file contents.",
            "- Respect the module/package and namespace structure defined by PLAN.md.",
            "- No trailing prose outside fenced blocks.",
            "- Any file path outside the target REQ staging root is invalid.",
            "",
            "## Task",
            "Produce/Transform the KIT output that strictly follows the Output contract.",
        ])

    return "\n".join(concise_parts).strip()

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
        )

    if p == "finalize":
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            f"- Top-level heading is `# {p.upper()}`.\n"
            "- Emit one or more `file:/path/...` block.\n"
            "- If additional metadata (tags/version) is included, keep it at the end in a clearly labeled section.\n"
            "- No ASCII art; diagrams (if any) use proper fenced blocks.\n"
            "- Clean Markdown bullets (one space after `-` or `*`).\n"
        )

    # KIT (file-based outputs)
    return (
        "### OUTPUT CONFORMITY CHECKLIST\n"
        "- Emit one or more `file:/path` blocks with complete file contents.\n"
        "- Rispect the Module/Package & Namespace structure defined in the PLAN.md during kit command"
        "- No trailing prose outside fenced blocks, except a short append-only iteration log if specified.\n"
    )
  
def _append_kit_target_to_user(user_text: str, targets: list[str], acceptance: Optional[list[str]] = None,) -> str:
    """
    Force a single authoritative KIT target block at the very top of the user prompt.

    This is intentionally strict because GPT-5.4 drifts when the target is only
    mentioned later in a long prompt body.
    """
    if not targets:
        return user_text

    target_req = str(targets[0]).strip()
    acc = [str(item).strip() for item in (acceptance or []) if str(item).strip()]

    header_lines = [
        "## KIT TARGET (AUTHORITATIVE)",
        f"- Target REQ-ID: {target_req}",
        f"- Only valid staging root: runs/kit/{target_req}/",
        f"- Only valid source root for this response: runs/kit/{target_req}/src/",
        f"- Only valid test root for this response: runs/kit/{target_req}/test/",
        f"- Only valid docs root for this response: runs/kit/{target_req}/docs/",
        f"- Only valid ci root for this response: runs/kit/{target_req}/ci/",
        "- Do not emit files for any other REQ-ID.",
        "- Do not emit paths for dependencies under their own REQ staging roots.",
        "- Dependency REQs are read-only context only.",
        "- If any manifest, repo evidence, or prior context conflicts with this target block, this target block wins.",
        "- Any file path outside the target REQ staging root is an invalid response.",
    ]

    if acc:
        header_lines.append("- Acceptance criteria for this target:")
        header_lines.extend([f"  - {item}" for item in acc])

    authoritative_block = "\n".join(header_lines).strip()
    return f"{authoritative_block}\n\n{user_text.lstrip()}"


def _compose_system_messages(phase: str,
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
        "idea": PROMPT_IDEA_SYSTEM_PATH,
        "spec": PROMPT_SPEC_SYSTEM_PATH,
        "plan": PROMPT_PLAN_SYSTEM_PATH,
        "kit": PROMPT_KIT_SYSTEM_PATH,
        "integrity_eval": PROMPT_INTEGRITY_EVAL_SYSTEM_PATH,
        "finalize": PROMPT_FINALIZE_SYSTEM_PATH,
        "promotion_hardener": PROMPT_PROMOTION_HARDENER_SYSTEM_PATH,
        "promotion_eval": PROMPT_PROMOTION_EVAL_SYSTEM_PATH,
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
        "- Harper pipeline: IDEA→SPEC→PLAN→KIT, eval-driven quality, outcome-first.\n"
        "- Keep output concise but testable; Acceptance Criteria are mandatory.\n"
        "- Maintain human-in-control tone; do not invent facts.\n"
    )
    log.debug("componse message nmber: %s", len(system.split("\n")))

    # Background context (IDEA + optional core blobs names)
    idea_md or ""
    constraints_keys: list[str] = []
    other_core: dict[str, str] = {}
    constraints_chunks: list[str] = []

    if core_blobs:
       
        log.debug("componse message nmber: %s", len(system.split("\n")))
        for name, content in core_blobs.items():
            lname = (name or "").lower()
            # if name.endswith('plan.json'):
            #     continue
            log.debug("componse message nmber: %s", len(system.split("\n")))
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
    log.debug("componse message nmber: %s", len(system.split("\n")))

    NORMATIVE_PREFIXES = (
        "REQ_PROMOTION_MANIFEST",
        "REPO_ACCESS_MANIFEST",
        "REPO_STRUCTURE_EVIDENCE",
        "REPO_COMPOSITION_MANIFEST",
    )

    if other_core:
        for n, c in other_core.items():
            if any((n or "").startswith(prefix) for prefix in NORMATIVE_PREFIXES):
                suffix_parts.append(f"\n\n### {n} (verbatim)\n{c}")
            else:
                suffix_parts.append(f"\n\n### {n} (reference only)\nIncluded as project context; do not ignore if relevant.")

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
        f"### Route\n\n"
        f"{idea_txt}"
        f"{refs}\n\n"
        f"{_output_checklist_for_phase(phase)}"
        f"### Task\nProduce/Transform the {phase.upper()} output that strictly follows the Output contract. Returns files as requested for this pahse.{suffix}"
    )
    # --- se fase KIT, inietta direttiva target ---
    if (phase or "").lower() == "kit":
        user = _build_kit_user_message(
            phase=phase,
            user=user,
            core_blobs=core_blobs,
            targets=targets,
        )
        user = _append_kit_target_to_user(user, targets=targets)
    
    messages_output = [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user.strip()},
    ]
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
    source: Optional[str] = None  # e.g., "external" | "workspace" | "upload"
    origin: Optional[str] = None  # e.g., "external" | "workspace" | "upload"
    mime: Optional[str] = None
    content_base64: Optional[str] = None  # optional payload if provided
    size: Optional[int] = None
    content: Optional[str] = None
    bytes_b64: Optional[str] = None


class HarperKitOptions(BaseModel):
    targets: Optional[List[str]] = Field(default=None)
    batch: Optional[int] = Field(default=None, ge=1)
    req_ids: Optional[List[str]] = Field(default=None)  # backward-compat alias
    rescope: Optional[bool] = Field(default=False)

class HarperRunRequest(BaseModel):
    project_id: Optional[str] = None
    project_name: Optional[str] = None
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
    rag_chunks: Optional[List[dict]] = None
    rag_queries: Optional[List[str]] = None
    rag_top_k: Optional[int] = None

    in_line_files: Optional[List[dict]] = None
    rag_files: Optional[List[dict]] = None


# --- RAG: helper locale (RagStore) per recupero per path ---------------------
def _collect_dependency_candidate_paths(plan_data: dict, targets: list[str]) -> list[str]:
    reqs = plan_data.get("reqs") or []
    target_ids = {str(t or "").strip() for t in (targets or []) if str(t or "").strip()}
    dep_ids: set[str] = set()

    for r in reqs:
        rid = str(r.get("id") or "").strip()
        if rid in target_ids:
            for dep in r.get("dependsOn") or []:
                dep = str(dep or "").strip()
                if dep:
                    dep_ids.add(dep)

    paths: list[str] = []
    for dep in sorted(dep_ids):
        paths.extend([
            f"runs/kit/{dep}/src",
            f"runs/kit/{dep}/test",
        ])
    return paths

async def _append_attachs_by_files(messages: list[dict], project_id: str, paths: list[str],contents: list[str], max_materials: int = 12, max_chars_each: int = 200000):
    """
    It loads documents from the RagStore by exact paths and appends them to the user message as '### RAG Context'. 
    It does not use HTTP; it communicates directly with the RagStore/Qdrant
    """
    try:
        store = RagStore(project_id=project_id or "default_id") if RagStore else None
    except Exception:
        store = None
    log.info("RAG Store for _append_attachs_by_files")

    if not paths and not contents:
        return 0

    materials = []
    for p in paths:
        try:
            doc = await store.get_by_path(
                        p,
                        base_url=os.getenv("RAG_BASE_URL", "http://localhost:8080/v1/rag")
                    )
            txt = (doc or {}).get("text", "")
            log.info("RAG retrieve doc '%s'", p)
            if txt:
                # trim prudenziale
                if len(txt) > max_chars_each:
                    txt = txt[:max_chars_each] + "\n# ... truncated"
                materials.append({"title": p, "text": txt})
        except Exception:
            continue

    for c in contents:
        log.info("INLINE retrieve content '%s'", c['name']) # type: ignore
        content_text = c['content'] # pyright: ignore[reportArgumentType]
        if content_text:
            if (len(content_text) > max_chars_each):
                content_text= content_text[:max_chars_each] + "\n# ... truncated"
            materials.append({"title": c['name'], "text": content_text}) # type: ignore

    if not materials:
        return 0
    appendix =  "\n\n### RAG Context – Attachments" + "\n\n".join(
        f"#### {m['title']}\n{m['text']}" for m in materials[:max_materials]
    )
    # appendiamo al messaggio 'user' (index 1 by contract)
    #log.info("FILES appendix '%s' ", appendix)
    messages[1]["content"] += appendix
    return len(materials[:max_materials])


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

def _telemetry_path(project_id: str) -> Path:
    # un file per progetto, append in JSONL
    fname = f"{(project_id or 'default').strip()}.json"
    path = Path(TELEMETRY_DIR).joinpath(fname)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _write_telemetry(project_id: str, record: dict) -> None:
    try:
        path = _telemetry_path(project_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("telemetry write failed: %s", e)

def _dump_llm_provider_raw(
    *,
    project_id: str,
    phase: str,
    model_label: str,
    provider: str,
    raw_payload: dict | None,
) -> None:
    """
    Persist the *provider raw* payload (as returned in `llm_result['raw']`).

    File name pattern (under TELEMETRY_DIR/llm_provider_raw/):
        provider-<provider>__<model>__<phase>__<uuid>.json

    - provider: 'openai', 'anthropic', 'ollama', ecc.
    - model: sanitized model label (':' '/' ' ' → '_')
    - phase: harper phase (idea/spec/plan/kit/...)
    """
    try:
        if not isinstance(raw_payload, dict) or not raw_payload:
            return

        phase_slug = (phase or "phase").strip().lower() or "phase"
        model_slug = (model_label or "model").strip() or "model"
        model_slug = (
            model_slug
            .replace(":", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )
        provider_slug = (provider or "provider").strip().lower() or "provider"

        uid = uuid.uuid4().hex[:12]
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        # Directory dedicata ai RAW provider dentro TELEMETRY_DIR
        root = Path(TELEMETRY_DIR).joinpath("llm_provider_raw")
        root.mkdir(parents=True, exist_ok=True)

        filename = f"provider-{provider_slug}__{model_slug}__{phase_slug}__{uid}.json"
        path = root.joinpath(filename)

        payload: dict[str, object] = {
            "timestamp": ts,
            "project_id": project_id,
            "phase": phase_slug,
            "provider": provider_slug,
            "model_label": model_label,
            "raw": raw_payload,
        }

        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info("harper.llm_dump: saved provider raw response to %s", path)
    except Exception as e:
        # Non deve mai rompere il flusso Harper, è solo telemetria aggiuntiva.
        log.warning("harper.llm_dump: failed to save provider raw response: %s", e)


def _dump_llm_response(
    *,
    project_id: str,
    phase: str,
    model_label: str,
    provider: str,
    messages: list[dict],
    gen: dict | None,
    llm_result: dict | None,
) -> None:
    """
    Persist raw LLM response for debugging/forensics.

    File name pattern:
        <model>__<phase>__<uuid>.json

    - model: sanitized (':' and '/' replaced with '_')
    - phase: lowercased harper phase (idea/spec/plan/kit/...)
    - uuid: short hex, unique per call
    """
    try:
        if not isinstance(llm_result, dict):
            return

        phase_slug = (phase or "phase").strip().lower() or "phase"
        model_slug = (model_label or "model").strip() or "model"
        model_slug = (
            model_slug
            .replace(":", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )
        provider_slug = (provider or "provider").strip().lower() or "provider"

        uid = uuid.uuid4().hex[:12]
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        # Directory dedicata ai dump LLM dentro TELEMETRY_DIR
        root = Path(TELEMETRY_DIR).joinpath("clike_raw")
        root.mkdir(parents=True, exist_ok=True)

        filename = f"{model_slug}__{phase_slug}__{uid}.json"
        path = root.joinpath(filename)

        payload: dict[str, object] = {
            "timestamp": ts,
            "project_id": project_id,
            "phase": phase_slug,
            "provider": provider_slug,
            "model_label": model_label,
            "gen": gen or {},
            "messages": messages or [],
            "llm_result": llm_result,
        }

        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info("harper.llm_dump: saved LLM response to %s", path)
    except Exception as e:
        # Non deve mai rompere il flusso Harper, è solo telemetria.
        log.warning("harper.llm_dump: failed to save LLM response: %s", e)


async def gather_rag_materials(rag_chunks, rag_top_k, store, rag_queries=None) -> list[dict]:
    """
    Build useful RAG materials for Harper prompts.

    Policy:
      1) client rag_chunks are included first (ephemeral)
      2) store search is deduplicated by path
      3) prefer source-ish files
      4) keep only the best chunk per file
    """
    log.info("--- gather_rag_materials")

    materials: list[dict] = []
    ragTopK = int(rag_top_k or os.getenv("RAG_TOP_K") or 12)

    # 1) client-side ephemeral chunks
    cmap = _chunk_map_from_client(rag_chunks)
    for (name, idx), txt in list(cmap.items())[:24]:
        materials.append({
            "title": f"{name}#{idx}",
            "text": txt,
            "source": "client",
        })

    # 2) server-side semantic retrieval
    queries = rag_queries or []
    if not store or not queries:
        return materials

    best_by_path: dict[str, dict] = {}

    for q in queries[:24]:
        try:
            res = await store.search(q, top_k=ragTopK)
            log.info("harper.rag query=%r hits=%d", q, len(res or []))
        except Exception as e:
            log.warning("harper.rag search failed for query=%r: %s", q, e)
            res = []

        for hit in res or []:
            path = (hit.get("path") or "").strip()
            if not path:
                continue

            if not _is_source_rag_path(path):
                log.debug("harper.rag skip non-source path: %s", path)
                continue

            txt = (hit.get("text") or "").strip()
            if not txt:
                key = (hit.get("path", "").split("/")[-1], int(hit.get("chunk", 0)))
                txt = cmap.get(key, "")

            if not txt:
                continue

            score = float(hit.get("score", 0.0))
            prev = best_by_path.get(path)

            if prev is None or score > float(prev.get("score", 0.0)):
                best_by_path[path] = {
                    "title": f"{path}#{hit.get('chunk', 0)} (score={score:.3f})",
                    "text": txt,
                    "source": "store",
                    "score": score,
                    "path": path,
                }

    if best_by_path:
        ranked = sorted(
            best_by_path.values(),
            key=lambda x: float(x.get("score", 0.0)),
            reverse=True,
        )
        materials.extend(ranked[:ragTopK])

    log.info(
        "harper.rag gathered materials total=%d client=%d store_unique=%d",
        len(materials),
        min(len(cmap), 24),
        len(best_by_path),
    )

    try:
        material_titles = []
        for m in materials:
            title = (m.get("title") or "").strip()
            if title:
                material_titles.append(title)

        if material_titles:
            log.info("harper.rag selected materials -> %s", " | ".join(material_titles[:24]))
        else:
            log.info("harper.rag selected materials -> none")
    except Exception as log_err:
        log.warning("harper.rag selected materials logging failed: %s", log_err)

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
            log.info("rag_queries not found (rag_chunks) '%s' ", len(rag_chunks)) # type: ignore
            qs = []
            for ch in (rag_chunks or []):
                name = (ch.get("name") or "").lower()
                if name in ("idea.md","spec.md"):
                    # prime heading line come query
                    for ln in (ch.get("text") or "").splitlines():
                        if ln.strip().startswith("#"):
                            qs.append(ln.strip("# ").strip())
                            break
            rag_queries = qs[:12]  # cap

        materials = await gather_rag_materials(rag_chunks, rag_top_k, store, rag_queries=rag_queries)
        log.info("materials length '%s' ", len(materials))

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

    available_ctx = max(10000, ctx_window - prompt_tokens)
    eff_max = max(1, min(req_max, available_ctx, max_out_cap))

    return eff_max

def normalize_context_from_body(req: HarperRunRequest) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Return (inline_files, rag_files, attachments) normalized from request body.

    Accepted shapes:
      - inline_files / in_line_files: [{ "name"|"path", "content": "<text>" }]
      - rag_files: [{ "name"|"path", "path": "<abs-or-rel>", "bytes_b64": "<b64-optional>", "size": <int-optional> }]
      - attachments: VSCode-style attachment objects (will be auto-partitioned by _decide_inline_or_rag)

    We do NOT merge the legacy rag_paths/rag_inline here. That compatibility path
    is intentionally handled later and only if new-style inputs are empty.
    """
    if not isinstance(req, HarperRunRequest):
        return [], [], []
    payload = req.model_dump()
    inline_raw = payload.get("in_line_files") or []
    rag_raw    = payload.get("rag_files") or []
    atts_raw   = payload.get("attachments") or []
    inline_files: list[dict] = []
    for item in inline_raw or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("path") or "file").strip()
        content = item.get("content")
        if isinstance(content, str) and content:
            inline_files.append({"name": name, "content": content})

    rag_files: list[dict] = []
    for item in rag_raw or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("path") or "").strip()
        path = (item.get("path") or "").strip()
        b64  = item.get("bytes_b64")
        size = item.get("size")
        rag_files.append({"name": name or (path or "file"), "path": path, "bytes_b64": b64, "size": size})

    attachments: list[dict] = []
    for item in atts_raw or []:
        if isinstance(item, dict):
            attachments.append(item)

    return inline_files, rag_files, attachments

def load_anthropic_stub_from_file(path: str = "stub/anthropic_stub.json") -> dict:
    """
    Load a local stub response for Anthropics so we can test the VS Code
    extension without calling the real API.
    The file must contain a single JSON object with the same shape as
    the real Anthropic response (keys: ok, text, files, usage, ...).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Anthropic stub must be a JSON object at top level")

        return data

    except FileNotFoundError:
        log.error("harper.gateway anthropic stub file not found at %s", path)
        raise HTTPException(
            status_code=500,
            detail="Anthropic stub file not found. Please create docs/harper/anthropic_stub.json",
        )
    except json.JSONDecodeError as e:
        log.error("harper.gateway anthropic stub JSON decode error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Anthropic stub JSON invalid, cannot be parsed",
        )
    except Exception as e:
        log.error("harper.gateway anthropic stub unexpected error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Anthropic stub load failed",
        )

async def loadAttachments(rag_enabled: bool, project_id: str, phase: str, messages: list[dict], inline_files: list[str], rag_files: list[dict], attachments: list[dict], model_route_label: str, runId: str) -> dict:
    appended = []   # <--- evita UnboundLocalError
    if rag_enabled and (len(rag_files) > 0 or len(inline_files) > 0):
            pathFiles = [item.get('path') for item in attachments if isinstance(item, dict) and item.get('path')]
            log.info("harper.rag enabled pathFiles=%s", pathFiles)
           
            # 1) tentativo locale via RagStore
            try:
                appended = await _append_attachs_by_files(messages, project_id, paths=pathFiles, contents=inline_files)
            except Exception as e:
                log.warning("RAG (local RagStore) append failed: %s", e)
                appended = 0
            if appended > 0:
                log.info("RAG context appended (%d materials)", appended)
            else:
                log.info("RAG context not appended, no materials found")
                return {
                        "ok": False,
                        "phase": phase,
                        "echo": f"{model_route_label} :: {phase.upper()} generation",
                        "text": f"No RAG context. No file attachments found. {phase.upper()} phase failed.",
                        "diffs": [],
                        "files": [],
                        "tests": {"passed": 0, "failed": 1, "summary": "Error no attachments found. phase.upper() - phase failed."},
                        "warnings": ['Please send an attachment. Idea phase failed.'],
                        "errors": ['Error no attachments found. Idea phase failed.'],
                        "runId": runId or "n/a",
                        "telemetry": None,
                    }
    return {
        "ok": True,
        "phase": phase,
        "rag_enalbed": rag_enabled,
        "echo": f"RAG context {rag_enabled} defined for attachments - {model_route_label} :: {phase.upper()} generation",
        "text": f"RAG context {rag_enabled} defined for attachments. {appended} materials appended. {phase.upper()} phase succeeded.",
    }

def _infer_provider_from_model_name(raw: str | None) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return ""

    if ":" in s:
        pref = s.split(":", 1)[0].strip()
        if pref in {"openai", "anthropic", "ollama", "vllm", "deepseek", "azure_openai"}:
            return pref

    if s.startswith("gpt-") or "codex" in s or s.startswith(("o1", "o3", "o4")):
        return "openai"
    if s.startswith("claude"):
        return "anthropic"
    if s.startswith("deepseek"):
        return "deepseek"

    return ""   
  

async def _append_dep_req_sources_by_path(
    messages: list[dict],
    project_id: str,
    dep_ids: list[str],
    max_materials: int = 24,
    max_chars_each: int = 12000,
) -> int:
    """
    Prefix-based retrieval for previous KIT source files only.
    Policy for /kit:
    - include only promoted source files under runs/kit/<REQ>/src/**
    - exclude tests, HOWTO, LTC, README and other CI/document artifacts
    """
    if not dep_ids:
        return 0

    try:
        store = RagStore(project_id=project_id or "default_id") if RagStore else None
    except Exception:
        store = None

    if not store:
        return 0

    materials: list[dict] = []

    for dep in dep_ids:
        dep_norm = str(dep or "").strip().upper()
        if not dep_norm:
            continue

        src_prefix = f"runs/kit/{dep_norm}/src"
        log.info("harper.kit.rag source prefix=%s", src_prefix)

        try:
            docs = await store.fetch_docs(
                path_prefix=src_prefix,
                limit_docs=max_materials,
                max_chars_per_doc=max_chars_each,
                search_top_k=200,
                base_url=os.getenv("RAG_BASE_URL", "http://orchestrator:8080/v1/rag"),
            )
        except Exception as e:
            log.warning("harper.kit.rag prefix fetch failed for %s: %s", src_prefix, e)
            docs = []

        for doc in docs or []:
            path = str(doc.get("path") or "").strip()
            txt = str(doc.get("text") or "")
            if not path or not txt:
                continue

            if len(txt) > max_chars_each:
                txt = txt[:max_chars_each] + "\n# ... truncated"

            materials.append({"title": path, "text": txt})

    if not materials:
        return 0

    appendix = (
        "\n\n### RAG Context – Promoted dependency source files\n"
        + "\n\n".join(
            f"#### {m['title']}\n{m['text']}" for m in materials[:max_materials]
        )
    )
    messages[1]["content"] += appendix
    return len(materials[:max_materials])

@router.post("/run")
async def run(req: HarperRunRequest,  request: Request):
    # TODO: apply policy based on req.profile (cloud/local/redaction) and perform the actual work.
    log.info("harper.run cmd=%s model=%s idea_md=%s core_blobs=%d",
             req.cmd, req.model, bool(req.idea_md), len(req.core_blobs or {}))
    phase = (req.phase or req.cmd or "").strip()
    default_params_reasoning =get_model_params(phase);
    resolved_entry = None
    if req.model:
        resolved_entry = _gw_try_match_model(str(req.model))
        if resolved_entry:
            log.info(
                "harper.gateway normalized model '%s' -> id=%s (provider=%s)",
                req.model,
                resolved_entry.get("id"),
                resolved_entry.get("provider"),
            )

    # --- Context budgeting ---
    ctx_window, max_out_cap = _resolve_ctx_caps(resolved_entry)
    project_id = req.project_id or "default_id"
    project_name = req.project_name  or "default_name"
    if not phase:
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

    attachments = req.attachments or []
    inline_files, rag_files, attachments = normalize_context_from_body(req)
    # If no explicit files were provided, but we have generic attachments, partition them.
    if not inline_files and not rag_files and attachments:
        inline_files, rag_files = await decide_inline_or_rag(attachments)

    
    log.info("inline_files  rag_files & attachments fileds: %s, %s, %s",  len(inline_files), len(rag_files), len(attachments))

    # --- PATCH: RAG logging (opzionale) ---
    rag_enabled = bool(req.attachments)
    if rag_enabled:
        log.info("harper.rag enabled attachments=%s", len(req.attachments))

    provider = (
        request.headers.get("X-CLike-Provider")
        or (resolved_entry.get("provider") if isinstance(resolved_entry, dict) else None)
        or _infer_provider_from_model_name(req.model)
        or ""
    ).lower().strip()

    model = (
        (resolved_entry.get("remote_name") if isinstance(resolved_entry, dict) else None)
        or (resolved_entry.get("name") if isinstance(resolved_entry, dict) else None)
        or str(req.model or "").strip()
    )

    if not provider:
        raise HTTPException(400, f"unable to resolve provider for model '{req.model}'")

    if req.kit is not None:
        targets = req.kit.targets or []
        log.info("harper targets=%s", targets)
    else:
        targets = []
    context_hard_limit =  getattr(req, "context_hard_limit", 6500)
    rag_strategy         = req.rag_strategy
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
       # Normalize generation settings defensively.
    # Harper requests may legitimately arrive with req.gen = None.
    g = dict(req.gen or {})
    req.gen = g
    # Defensive normalization for provider-facing generation params
    tool_choice = g.get("tool_choice")
    if isinstance(tool_choice, str) and not tool_choice.strip():
        g.pop("tool_choice", None)

    response_format = g.get("response_format")
    if response_format == "":
        g.pop("response_format", None)

    log.info("harper.run params=%s", default_params_reasoning)

    req.gen["temperature"] = default_params_reasoning.get("temperature") or req.gen.get("temperature", 0.2)
    req.gen["max_tokens"] = default_params_reasoning.get("max_tokens") or req.gen.get("max_tokens", 6500)
    # req.gen["top_p"] = default_params_reasoning.get("top_p") or req.gen.get("top_p")
    req.gen["stop"] = req.gen.get("stop") or "`PLAN_END`"
    # If gen["api"] == "responses" use /v1/responses, otherwise /v1/chat/completions.
    req.gen["api"] = req.gen.get("api") or "responses"

    gen_temperature = req.gen.get("temperature", 0.2)
    gen_max_tokens = req.gen.get("max_tokens", 6500)
    gen_top_p = default_params_reasoning.get("top_p") or req.gen.get("top_p")
    gen_stop = req.gen.get("stop")
    gen_presence_penalty = req.gen.get("presence_penalty")
    gen_frequency_penalty = g.get("frequency_penalty")
    gen_seed = g.get("seed")
    gen_tools = g.get("tools")
    gen_remote = g.get("remote")
    gen_response_format = g.get("response_format")
    gen_reasoning = g.get("reasoning")
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
    log.info("model_route_label (too long) %s", model_route_label)

    messages = _compose_system_messages(
                            phase,
                            idea,
                            core_blobs,
                            req.profileHint,
                            model_route_label,
                            req.runId,
                            repourl,
                            targets)

    #RAG context loading     
    result = await loadAttachments(rag_enabled, project_id, phase, messages, inline_files, rag_files, attachments, model_route_label, req.runId)
    log.info("loadAttachments result=%s", result) 
    if (phase or "").lower() == "idea":      
        if not rag_enabled:
        
            log.info("RAG context not appended, no materials found for IDEA.md")
            return {
                    "ok": False,
                    "phase": phase,
                    "echo": f"{model_route_label} :: {phase.upper()} generation",
                    "text": f"No RAG context. No file attachments found. {phase.upper()} phase failed.",
                    "diffs": [],
                    "files": [],
                    "tests": {"passed": 0, "failed": 1, "summary": "Error no attachments found for IDEA.md - phase failed."},
                    "warnings": ['Please send an attachment. Idea phase failed.'],
                    "errors": ['Error no attachments found. Idea phase failed.'],
                    "runId": req.runId or "n/a",
                    "telemetry": None,
            }
        
    
    # --- KIT: rag_strategy="deps_only" → usa plan.json da core_blobs per recuperare codice dei REQ dipendenti ---
    if (phase or "").lower() == "kit":
        log.info("harper.kit.rag: Retrive source code via RAG")
        strategy = (rag_strategy or "").strip().lower()
        log.info("harper.kit.rag: strtegy:%s", strategy)

        if strategy == "deps_only":
            try:
                appended_exact = 0
                plan_data = _load_plan_json(core_blobs)
                dep_candidate_paths = _collect_dependency_candidate_paths(plan_data, targets)
                if dep_candidate_paths:
                    messages[1]["content"] += (
                        "\n\n### Dependency code to inspect first\n"
                        + "\n".join(f"- {p}" for p in dep_candidate_paths)
                        + "\nUse these promoted or dependency-aligned code paths as canonical before creating new local modules."
                    )
                if not plan_data:
                    log.info("harper.kit.rag: no plan.json in core_blobs; skip deps_only RAG")
                else:
                    dep_ids = _collect_req_deps(plan_data, targets)
                    gate_refs = _collect_gate_policy_refs(plan_data, targets)

                    log.info("harper.kit.rag: dep_ids=%s gate_refs=%s", dep_ids, gate_refs)

                    if not dep_ids:
                        log.debug("harper.kit.rag: no deps for targets=%s", targets)
                    if not gate_refs:
                        log.debug("harper.kit.rag: no refs for targets=%s", targets)
                    appended_exact = 0
                    if dep_ids or gate_refs:
                            # 1) Retrieve dependent REQ source materials
                        if dep_ids:
                                appended_exact = await _append_dep_req_sources_by_path(
                                    messages,
                                    project_id,
                                    dep_ids,
                                )

                                if appended_exact > 0:
                                    log.info(
                                        "harper.kit.rag: appended %d exact-path materials for deps=%s",
                                        appended_exact,
                                        dep_ids,
                                    )
                                else:
                                    log.info(
                                        "harper.kit.rag: no source materials found for deps=%s; semantic fallback disabled for /kit to avoid PLAN/SPEC noise",
                                        dep_ids,
                                    )

                        # /kit RAG policy:
                        # - include only promoted source files from dependent REQs: runs/kit/<REQ>/src/**
                        # - exclude tests, HOWTO, LTC, README and CI artifacts
                        # - exclude PLAN/SPEC/KIT docs from semantic fallback because they are already passed in the payload
                        # - keep one target lane-guide as direct support material
                        # 2) Retrieve lane guide / gate policy refs by exact path
                        if gate_refs:
                            try:
                                appended_refs = await _append_attachs_by_files(
                                    messages,
                                    project_id,
                                    paths=gate_refs,
                                    contents=[],
                                    max_materials=6,
                                )
                                log.info(
                                    "harper.kit.rag: appended %d gate_policy_ref docs for refs=%s",
                                    appended_refs,
                                    gate_refs,
                                )
                            except Exception as e:
                                log.warning(
                                    "harper.kit.rag: failed to append gate_policy_ref docs: %s",
                                    e,
                                )
            except Exception as e:
                log.warning("harper.kit.rag: failed to append deps_only RAG: %s", e)
            
            log.info(
                "harper.kit.rag summary: targets=%s deps=%s source_materials_appended=%d gate_refs=%s",
                targets,
                dep_ids,
                appended_exact if dep_ids else 0,
                gate_refs,
            )


    if (phase or "").lower() == "finalize":
        # --- RAG: append al prompt (via utils.rag_query) -------------------------
        log.info("RAG append phase=%s", phase)
        try:
            materials = await collect_rag_materials_http(
                project_id=project_id,
                queries=req.rag_queries,          # opzionale dal client
                core_blobs=core_blobs,            # per estrarre heading SPEC/PLAN
                top_k=req.rag_top_k,
            )
            if materials:
                appendix = "\n\n### RAG Context\n" + "\n\n".join(
                    f"#### {m['title']}\n{m['text']}" for m in materials[:12]
                )
                messages[1]["content"] += appendix
                log.info("RAG context appended (%d materials)", len(materials))
        except Exception as e:
            log.warning("RAG append failed: %s", e)
    
    
    
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
    requested_out = int((req.gen or {}).get("max_tokens", 7500))
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
    # Dynamic timeout tuned for heavy Harper phases.
    timeout_sec = min(900.0, 180.0 + (eff_max / 1000.0) * 9.0)

    # Give /plan and /finalize extra headroom because they emit long structured artifacts.
    if phase in {"plan", "spec", "idea", "finalize"}:
        timeout_sec = max(timeout_sec, 1000.0)
    elif phase == "kit":
        timeout_sec = max(timeout_sec, 920.0)
    elif phase in {"promotion_hardener", "promotion_eval", "integrity_eval"}:
        timeout_sec = max(timeout_sec, 900.0)

    log.info("harper.gateway eff_max & timeout '%s' '%s'",
                    eff_max, timeout_sec)
    log.info("harper.gateway eff_max=%s ctx_window=%s prompt_tokens≈%s cap=%s",
        eff_max,
        (_resolve_ctx_caps(resolved_entry)[0]),
        approx_tokens_from_chars("".join(m.get("content","") for m in messages if isinstance(m.get("content"), str))),
        (_resolve_ctx_caps(resolved_entry)[1]))
    log.info("harper.gateway normalized messages '%s' ", len(messages))

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
                raise HTTPException(401, "missing OpenAI api key")
            llm_text = await oai.openai_complete_unified(api_key=OPENAI_API_KEY, model=model, messages=messages, gen=req.gen, timeout_s=timeout_sec)
            
        elif provider == "deepseek":
            if not DEEPSEEK_API_KEY:
                raise HTTPException(401, "missing OpenAI api key")

            llm_text = await deepseek.chat(DEEPSEEK_API_KEY, DEEPSEEK_BASE, model, messages, gen_temperature, eff_max, gen_top_p)  

        elif provider == "vllm":
            llm_text =  await vll.chat(VLLM_BASE, model, messages, gen_temperature, eff_max, gen_response_format, gen_tools, gen_tool_choice, gen_top_p)
        elif provider == "ollama":
            llm_text =  await oll.chat(OLLAMA_BASE, model, messages, gen_temperature, eff_max, gen_top_p)   

        elif provider == "anthropic":
            if not ANTHROPIC_API_KEY:
                raise HTTPException(401, "missing ANTHROPIC api key")
            llm_text = await anth.chat(
                ANTHROPIC_BASE, 
                ANTHROPIC_API_KEY, 
                model, 
                messages, 
                temperature=gen_temperature,
                max_tokens=gen_max_tokens,
                tools=gen_tools,
                tool_choice=gen_tool_choice,
                response_format=gen_response_format,
                timeout=timeout_sec)
            # llm_text = load_anthropic_stub_from_file()
            # log.info(
            #     "harper.gateway anthropic stub loaded ok=%s text_len=%s files=%s",
            #     llm_text.get("ok"),
            #     len(llm_text.get("text") or ""),
            #     len(llm_text.get("files") or []),
            # )
            # log.info("harper_plan_debug: start")
            # await asyncio.sleep(30)  # 400 secondi
            # log.info("harper_plan_debug: end")
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
        error_stack = traceback.format_exc()
        log.error("httpx error (error_stack): %s", error_stack)
        log.error("httpx error: %s", e, exc_info=True)
        errors.append(f"provider_error: {type(e).__name__}: {e}")
        spec_md_txt, llm_diag = ("", {})
    
    #llm_text = {"text": "", "usage": {'input_tokens':3033, 'output_tokens':5050 }, "files": []}
    #text_len=0
    log.info("harper.gateway llm_text length '%s' ", len(llm_text))
    #log.info("harper.gateway llm_text  '%s' ", (llm_text))
    
    # --- Dump raw LLM response + provider raw for debugging/forensics (non-blocking) ---
    try:
        log.debug("--- Dump Clike LLM response  ---")

        if "llm_text" in locals() and isinstance(llm_text, dict):
            # 1) risposta unificata (normalized Harper envelope)
            _dump_llm_response(
                project_id=project_id,
                phase=phase,
                model_label=model_route_label,
                provider=provider,
                messages=messages,
                gen=req.gen or {},
                llm_result=llm_text,
            )
            log.debug("--- Dump Clike LLM response done ---")

            # 2) payload grezzo del provider (campo 'raw' dell'envelope)
            provider_raw = llm_text.get("raw")
            log.debug("--- Dump Provider LLM response  ---")

            if isinstance(provider_raw, dict) and provider_raw:
                _dump_llm_provider_raw(
                    project_id=project_id,
                    phase=phase,
                    model_label=model_route_label,
                    provider=provider,
                    raw_payload=provider_raw,
                )
            log.debug("--- Dump Clike Provider response done ---")

        else:
            log.info("harper.llm_dump: skip (llm_text not available or not a dict)")
    except Exception as e:
        # Non deve mai interferire con il flusso principale
        log.warning("harper.llm_dump: error while dumping response: %s", e)

    if not isinstance(llm_text, dict):
        raise HTTPException(502, f"provider returned invalid response type for phase={phase}")

    llm_usage = llm_text.get("usage") or {}
    system_md_txt = (llm_text.get("text") or "").strip()
    provider_files = llm_text.get("files") or []
    provider_errors = llm_text.get("errors") or []
    provider_ok = llm_text.get("ok")

    text_len = len(system_md_txt)
    log.info("harper.llm.result text_len=%d usage=%s ok=%s errors=%s", text_len, llm_usage, provider_ok, provider_errors)

    fail_hard_phases = {
        "spec",
        "plan",
        "kit",
        "integrity_eval",
        "promotion_hardener",
        "promotion_eval",
        "finalize",
    }

    has_files = isinstance(provider_files, list) and len(provider_files) > 0
    has_text = bool(system_md_txt)

    if (phase or "").lower() in fail_hard_phases:
        if provider_ok is False:
            raise HTTPException(
                502,
                f"provider failed for phase={phase}: {provider_errors or ['unknown provider failure']}",
            )

        if not has_text and not has_files:
            raise HTTPException(
                502,
                f"empty provider result for phase={phase}: no text and no files returned",
            )

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
           "Summary", "Goals", "Problem", "Users & Context", "Functional Requirements", "Non-Goals", "Non-Functional Requirements",
            "High-Level Architecture", "", "Interfaces", "Data Model", "Assumptions"
        ]
        missing = [s for s in required_sections if f"## {s}" not in system_md_txt]
        if missing:
            warnings.append(f"SPEC missing sections: {', '.join(missing)}")


    
    # --- Multi-file support ---
    output_name = PHASE_OUTPUT_FILE.get(phase, f"{phase.upper()}.md")
    default_doc_path = f"{req.docRoot or 'docs/harper'}/{output_name}"
    
    # --- Multi-file support
    files: list[dict] = []
    gen_files: list[dict] = [] 
    # Se il provider (es. anthropic.py / openai_compat.py) ha già estratto i file, usali.
    if provider_files:
        log.info("harper.files from provider: %d", len(provider_files))
        for pf in provider_files:
            p = (pf.get("path") or "").lstrip().lstrip("/")
            c = pf.get("content") or ""
            if not p:
                p = default_doc_path  # fallback per non perdere contenuti
            files.append({
                "path": p,
                "content": c,
                "mime": _guess_mime(p),
                "encoding": "utf-8",
            })

        # Se nel testo rimane del contenuto "fuori" dai blocchi file, salvalo nel doc di fase
        remainder_txt = (system_md_txt or "").strip()
        if remainder_txt:
            files.append({
                "path": default_doc_path,
                "content": remainder_txt,
                "mime": "text/markdown",
                "encoding": "utf-8",
            })

    else:
        # Prova a estrarre blocchi `file:...` dal testo grezzo
        gen_files, remainder = _extract_file_blocks(system_md_txt)

        if gen_files:
            files.extend(gen_files)
            if remainder:
                files.append({
                    "path": default_doc_path,
                    "content": remainder,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                })
        else:
            structured_only_phases = {"integrity_eval", "promotion_hardener", "promotion_eval"}
            if phase in structured_only_phases:
                warnings.append(f"{phase}_no_file_blocks: model did not emit valid file blocks")
            else:
                # Fallback: un solo documento di fase
                files.append({
                    "path": default_doc_path,
                    "content": system_md_txt,
                    "mime": "text/markdown",
                    "encoding": "utf-8",
                }) 


    # Deduplica finale (per evitare file doppi o path ripetuti tra provider_files e parsing)
    files = _dedupe_by_path(files)
    if (phase or "").lower() == "kit":
        current_target = str((targets or [None])[0] or "").strip()
        files = _enforce_single_req_output(files, current_target)
    #saniize files removing 
    # ```
    #
    #``` json
    for i, file_name in enumerate(files):
        file_path = file_name["path"]
        file_content = file_name["content"]
        clean_content = sanitize_for_path(file_path, file_content)
        files[i]["content"] = clean_content


    for _f in files:
         _f["path"] = _canonicalize_path(_f.get("path") or "")


    # --- plan.json derivation from PLAN.md (only for phase=plan) ---
    if phase == "plan":
        has_plan_md = any((f.get("path") or "").endswith("/PLAN.md") for f in files)
        has_plan_json = any((f.get("path") or "").endswith("/plan.json") for f in files)

        if not has_plan_md:
            raise HTTPException(502, "plan phase did not emit docs/harper/PLAN.md")

        if not has_plan_json:
            raise HTTPException(
                502,
                "plan phase did not emit docs/harper/plan.json; markdown-derived fallback is disabled for promotion-grade planning"
            )
        # Path atteso
        plan_doc_path = f"{req.docRoot or 'docs/harper'}/PLAN.md"
        plan_json_path = f"{req.docRoot or 'docs/harper'}/plan.json"

        # 1) Trova il contenuto del PLAN.md
        plan_md_text = None
        for f in files:
            p = (f.get("path") or "").strip()
            if p.endswith("/PLAN.md") or p == plan_doc_path:
                plan_md_text = f.get("content") or ""
                break

        if plan_md_text is None and not gen_files:
            # no file-blocks: usa l'intero testo di fase
            plan_md_text = system_md_txt or ""

        # 2) Deriva plan.json e gestisci duplicati
        if plan_md_text:
            try:
                plan_json = _derive_plan_json_from_md(plan_md_text)
            except Exception as e:
                plan_json = None
                warnings.append(f"plan_json_derivation_error: {e}")

            if plan_json is not None:
                new_payload = json.dumps(plan_json, indent=2, ensure_ascii=False)
                # verifica se esiste già un plan.json
                existing_idx = None
                for i, f in enumerate(files):
                    p = (f.get("path") or "").strip()
                    if p == plan_json_path or p.endswith("/plan.json"):
                        existing_idx = i
                        break

                if existing_idx is None:
                    files.append({
                        "path": plan_json_path,
                        "content": new_payload,
                        "mime": "application/json",
                        "encoding": "utf-8",
                    })
                else:
                    # tieni la versione più informativa (contenuto più lungo)
                    old = files[existing_idx].get("content") or ""
                    if len(new_payload) > len(old):
                        files[existing_idx] = {
                            "path": plan_json_path,
                            "content": new_payload,
                            "mime": "application/json",
                            "encoding": "utf-8",
                        }
                    else:
                        warnings.append("plan_json_existing_kept: provider version longer")
    # --- Safety dedupe by path: keep longer content ---
    seen = {}
    deduped = []
    for f in files:
        k = (f.get("path") or "").strip()
        c = f.get("content") or ""
        if not k:
            continue
        if k not in seen or len(c) > len(seen[k].get("content") or ""):
            seen[k] = f
    deduped = list(seen.values())
    files = deduped

    
    # --- Telemetry ---
    telemetry = {}
    ts = time.time()
    telemetry["timestamp"] = ts
    telemetry["project_name"] = project_id
    telemetry["docRoot"] = req.docRoot
    telemetry["phase_params"] = {
        "temperature": gen_temperature,
        "max_tokens": gen_max_tokens,
        "top_p": gen_top_p,
    }
    telemetry["files"] = [ {"path": f["path"], "bytes": len(f.get("content") or "")} for f in files ]

    telemetry.update({
        "text_len": text_len,
        "files_len": len(files),
        "usage": llm_usage or {},
        "provider": provider,    
    })
    pm = _get_pricing_manager()  # [pricing]
    pricing_info = pm.estimate_cost(
        model_id=resolved_entry.get("id") if isinstance(resolved_entry, dict) else None,
        provider=resolved_entry.get("provider") if isinstance(resolved_entry, dict) else provider,
        name=resolved_entry.get("name") if isinstance(resolved_entry, dict) else model,
        usage=llm_usage,
    )  # [pricing]
    log.info("pricing_info=%s", pricing_info)
    telemetry.setdefault("pricing", {})  # dict
    telemetry["pricing"].update(pricing_info)  # {input_cost, output_cost, total_cost}  # [pricing]

    # opzionale ma utile: salva anche i prezzi unitari se disponibili
    p_cfg = _get_pricing_manager().for_model(
        model_id=resolved_entry.get("id") if isinstance(resolved_entry, dict) else None,
        provider=resolved_entry.get("provider") if isinstance(resolved_entry, dict) else provider,
        name=resolved_entry.get("name") if isinstance(resolved_entry, dict) else model
    )
    telemetry["pricing"].setdefault("unit", {
        "input_per_1k": p_cfg.input_per_1k,
        "output_per_1k": p_cfg.output_per_1k,
    })

    _write_telemetry( project_id, {
        "project_id": project_id,
        "project_name": project_id,
        "run_id": req.runId,
        "phase": phase,
        "model": model,
        "pricing": telemetry.get("pricing"),
        "files": telemetry.get("files"),
        "timestamp": ts,
        "snapshot": telemetry.get("usage") or {},
        "text_len": text_len,
        "files_len": len(files),
        "usage": llm_usage or {},
        "provider": provider})
    log.info("Telemetry saved for project_id=%s phase=%s model=%s len(telemetry)=%s", project_id, phase, model, len(telemetry))
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
        "usage": llm_usage,
        "telemetry": telemetry,
    }
    
