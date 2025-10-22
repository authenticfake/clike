# routes/v1.py
import os, json, logging, re, uuid, base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, Query
import httpx
from pydantic import BaseModel
from config import settings
from services import utils as su
from services.llm_client import call_gateway_chat, call_gateway_generate
# --- LOGGING UTILS (aggiunta) ---
import time as _time
from copy import deepcopy as _deepcopy
from services.rag_store import RagStore

# --- Generated root selection -------------------------------------------------
import uuid
# compat: alcuni repo usano services.router, altri services.model_router
try:
    from services import model_router
except Exception:
    from services import router as model_router

# splitter (alcune funzioni potrebbero non essere usate, ma manteniamo le import per compat)
from services.splitter import (
    infer_language,
    split_python_per_symbol,
    split_ts_per_symbol,
    apply_strategy,
)
def build_response_format_files_bundle() -> dict:
    """
    OpenAI structured output schema for a bundle of files.
    Strict schema: properties == required (no extras).
    Minimal: path, content, mime.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "files_bundle_v1",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path":    {"type": "string"},
                                "content": {"type": "string"},
                                "mime":    {"type": "string"},
                            },
                            "required": ["path", "content", "mime"],
                            "additionalProperties": False,
                        },
                        "minItems": 1
                    }
                },
                "required": ["files"],
                "additionalProperties": False,
            },
        },
    }

router = APIRouter(prefix="/v1")
log = logging.getLogger("orchestrator.v1")

INLINE_MAX_FILE_KB   = int(os.getenv("INLINE_MAX_FILE_KB", "64"))
INLINE_MAX_TOTAL_KB  = int(os.getenv("INLINE_MAX_TOTAL_KB", "256"))
RAG_SIZE_THRESHOLD_KB = int(os.getenv("RAG_SIZE_THRESHOLD_KB", "64"))
RAG_TOP_K            = int(os.getenv("RAG_TOP_K", "12"))



# --- Classification for src/doc buckets ---
CODE_EXTS = {
    ".py",".ts",".tsx",".js",".jsx",".go",".java",".c",".h",".cpp",".hpp",".cs",".rs",".kt",".swift",
    ".php",".rb",".pl",".r",".m",".scala",".sh",".ps1",".sql",".html",".css",".scss",".less",".xml",".xsl",
    ".json",".yaml",".yml",".toml",".ini",".gradle",".pom",".mdx",".vue",".svelte",".sol",".dart"
}
DOC_EXTS = {
    ".md",".rst",".txt",".adoc",".pdf",".doc",".docx",".ppt",".pptx",".odt",".rtf",".csv",".xlsx",".xls",".ipynb",
    ".mendixmodel",".mxmodel"
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff"}
DATA_URL_RE = re.compile(r'data:(image/[\w\-\+\.]+);base64,([A-Za-z0-9+/=]+)')

def _get_cfg(name: str, default: str) -> str:
    """Legge prima da os.environ, poi da settings, altrimenti default."""
    v = os.getenv(name)
    if v is not None and str(v).strip():
        return str(v).strip()
    try:
        vv = getattr(settings, name, None)
        if vv is not None and str(vv).strip():
            return str(vv).strip()
    except Exception:
        pass
    return default

def _rag_base_url() -> str:
    # es.: "http://localhost:8080/v1/rag"
    base = _get_cfg("RAG_BASE_URL", "http://localhost:8080/v1/rag")
    return base.rstrip("/")

# --- RAG / attachments normalization helper ---------------------------------
def _normalize_context_from_body(body: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Return (inline_files, rag_files, attachments) normalized from request body.

    Accepted shapes:
      - inline_files / in_line_files: [{ "name"|"path", "content": "<text>" }]
      - rag_files: [{ "name"|"path", "path": "<abs-or-rel>", "bytes_b64": "<b64-optional>", "size": <int-optional> }]
      - attachments: VSCode-style attachment objects (will be auto-partitioned by _decide_inline_or_rag)

    We do NOT merge the legacy rag_paths/rag_inline here. That compatibility path
    is intentionally handled later and only if new-style inputs are empty.
    """
    if not isinstance(body, dict):
        return [], [], []

    inline_raw = body.get("in_line_files") or body.get("inline_files") or []
    rag_raw    = body.get("rag_files") or []
    atts_raw   = body.get("attachments") or []

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

# se vuoi forzare un base diverso
def _pick_generated_root() -> str:
    """
    Root di output per i file generati.
    Ordine preferenze:
    - env 'GENERATED_ROOT' (fallback al typo citato)
    - default: 'generated_<shortuuid>'
    """
    env = os.getenv("GENERATED_ROOT")
    if env:
        return env.rstrip("/")

    short = str(uuid.uuid4()).split("-")[0]
    return f"generated_{short}"

def _bucket_subdir(path: str) -> str:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext in CODE_EXTS:
        return "src"
    if ext in IMAGE_EXTS:
        return "images"
    if ext in DOC_EXTS:
        return "docs"
    return "docs"



def _retarget_files_under_generated(files: list[dict], prefix_path: str) -> list[dict]:
    """
    Riallincia i path dei file in base a GENERATED_ROOT e ai bucket {src, docs, images}.
    """
    log.info("_retarget_files_under_generated")
    base = _pick_generated_root()
    
    log.info("_retarget_files_under_generated --> Generated root:  %s", base)
    out: list[dict] = []
    temp_path =""
    for f in files or []:
        p = str(f.get("path") or "").lstrip("/").strip()
        
        c = f.get("content")
        if not p or c is None:
            continue
       
        sub = _bucket_subdir(p)
        
        intermediate_path = os.path.join(base, prefix_path)
        log.info(f"Retargeting 1 {p} to {intermediate_path} (subdir={sub})")
        # preserva solo il basename per evitare annidamenti sporchi
        bn = os.path.basename(p)
        log.info(f"Retargeting 2 bn to {bn} (subdir={sub})") 
        new_path = os.path.join(intermediate_path, sub, bn)
        out.append({"path": new_path, "content": c})
        log.info(f"Retargeting 3 {p} to {new_path}")
    return out


def _json_safe(obj):
    """Trasforma ricorsivamente set() -> list per garantire JSON serializzabile."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, set):
        return [_json_safe(x) for x in obj]  # list() di set
    return obj



def _inject_coding_system(msgs: list) -> list:
    """Garantisce un messaggio system che vieta prosa e impone il tool-call emit_files."""
    if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system" and "emit_files" in (msgs[0].get("content") or ""):
        return msgs
    sys = {
        "role": "system",
        "content": (
            "You are CLike code generator. You must produce output ONLY by CALLING the tool function "
            "'emit_files' with a JSON object: {\"files\":[{\"path\":\"<relative_path>\",\"content\":\"<file content>\"}]}. "
            "Never write normal assistant content. Do not include prose. If the user asks for code, return files via the tool call."
        ),
    }
    return [sys] + msgs

_CODE_FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-._]*)\s*\n(?P<code>.*?)(?:\r?\n)?```", re.DOTALL)

def _extract_files_from_fences(raw: str) -> list[dict]:
    files: list[dict] = []
    for i, m in enumerate(_CODE_FENCE_RE.finditer(raw or ""), start=1):
        lang = (m.group("lang") or "").strip().lower()
        code = m.group("code") or ""
        fname = _default_filename(lang, i)
        files.append({"path": fname, "content": code, "language": lang})
    return files

def _normalize_files_for_write(files: list[dict]) -> list[dict]:
    """
    Assicura path/content; se manca 'content' ma c'è 'text', usa text.
    Pulisce gli slash.
    """
    out: list[dict] = []
    for f in files or []:
        d = dict(f) if isinstance(f, dict) else {}
        path = (d.get("path") or "").strip()
        content = d.get("content")
        text = d.get("text")

        if (content is None or content == "") and isinstance(text, str) and text.strip():
            content = text
        if content is None:
            content = ""

        path = path.replace("\\", "/")
        out.append({"path": path, "content": content, "language": d.get("language","")})
    return out

def _extract_json(s: str) -> Dict[str, Any]:
    # 1) blocco ```json ... ```
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", s or "", re.M)
    if m:
        return json.loads(m.group(1))
    # 2) qualsiasi blocco ``` ... ``` con un oggetto json
    m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", s or "", re.M)
    if m:
        return json.loads(m.group(1))
    # 3) fallback: primo { ... } nel testo
    i = (s or "").find("{"); j = (s or "").rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(s[i:j+1])
    raise ValueError("no valid JSON found")

def _default_filename(lang: str, idx: int = 1) -> str:
    l = (lang or "").lower()
    if l in ("py","python"): return f"module_{idx}.py"
    if l in ("ts","typescript"): return f"module_{idx}.ts"
    if l in ("js","javascript"): return f"module_{idx}.js"
    if l == "go": return f"module_{idx}.go"
    if l == "java": return f"module_{idx}.java"
    return f"module_{idx}.txt"

def _short_id(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]

def _build_generation_roots(generation_id: str) -> Tuple[str, str, str, str]:
    """
    Ritorna (code_root_abs, test_root_abs, code_root_rel, test_root_rel)
    Esempio: ( .../src/generated_ab12cd34, .../tests/generated_ab12cd34, 'src/generated_ab12cd34', 'tests/generated_ab12cd34')
    """
    code_root_rel = os.path.join(settings.CODE_ROOT_BASE, f"{settings.GEN_ID_PREFIX}_{generation_id}")
    test_root_rel = os.path.join(settings.TEST_ROOT_BASE, f"{settings.GEN_ID_PREFIX}_{generation_id}")
    code_root_abs = os.path.join(settings.WORKSPACE_ROOT, code_root_rel)
    test_root_abs = os.path.join(settings.WORKSPACE_ROOT, test_root_rel)
    os.makedirs(os.path.join(code_root_abs, "src"), exist_ok=True)
    os.makedirs(os.path.join(code_root_abs, "doc"), exist_ok=True)
    os.makedirs(os.path.join(code_root_abs, "images"), exist_ok=True)
    os.makedirs(test_root_abs, exist_ok=True)
    return code_root_abs, test_root_abs, code_root_rel, test_root_rel

def _write_file_any(path: str, fobj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if "content_base64" in fobj:
        data = base64.b64decode(fobj["content_base64"])
        with open(path, "wb") as wf:
            wf.write(data)
    else:
        content = fobj.get("content", "")
        with open(path, "w", encoding="utf-8") as wf:
            wf.write(content)

# ===== RAG hooks (best-effort; non bloccanti) =====
def _rag_project_id(body: dict) -> str:
    pid = (body or {}).get("project_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return "default"

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))

async def rag_index_items(project_id: str, items: list[dict]):
    # Optional server-side index; we prefer client-side, but keep for completeness.
    if not items:
        return
    payload = {"project_id": project_id, "items": []}
    for it in (items or []):
        p = (it.get("path") or "").strip()
        t = (it.get("text") or "").strip()
        if p and t:
            payload["items"].append({"path": p, "text": t})
    if not payload["items"]:
        return
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(f"{_rag_base_url()}/index", json=payload)
    except Exception as e:
        log.warning("rag_index_items failed: %s", e)

async def rag_query(project_id: str, query: str, top_k: int = None):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_rag_base_url()}/search",
                                  json={"project_id": project_id,
                                        "query": query or "",
                                        "top_k": int(top_k or RAG_TOP_K)})
            r.raise_for_status()
            data = r.json() or {}
            return data.get("hits") or []
    except Exception as e:
        log.warning("rag_query failed: %s", e)
        return []
# ----------------------------- models listing -------------------------------

def _mode_from_name(mid: str) -> str:
    if not mid:
        return "chat"
    low = mid.lower()
    if "embed" in low or "embedding" in low or "nomic-embed" in low:
        return "embed"
    return "chat"

def _normalize_models(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Case 1: CLike-style
    if isinstance(payload.get("models"), list):
        out = []
        for m in payload["models"]:
            name = m.get("name") or m.get("id") or m.get("model")
            if not name:
                continue
            mm = dict(m)
            mm.setdefault("name", name)
            mm.setdefault("modality", _mode_from_name(name))
            mm.setdefault("enabled", True)
            out.append(mm)
        return out
    # Case 2: OpenAI-style
    data = payload.get("data")
    if isinstance(data, list):
        out = []
        for m in data:
            mid = m.get("id")
            if not mid:
                continue
            out.append({
                "name": mid,
                "provider": "unknown",
                "modality": _mode_from_name(mid),
                "enabled": True,
                "capability": "medium",
                "latency": "medium",
                "cost": "medium",
                "privacy": "medium",
            })
        return out
    return []

def _filter_by_modality(models: List[Dict[str, Any]], modality: Optional[str]) -> List[Dict[str, Any]]:
    if modality in ("chat", "embed"):
        return [m for m in models if (m.get("modality") or "chat") == modality]
    return models

async def _load_models_or_fallback() -> List[Dict[str, Any]]:
    # gateway
    try:
        base = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
        async with httpx.AsyncClient(timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60))) as client:
            r = await client.get(f"{base}/v1/models")
            r.raise_for_status()
            models = _normalize_models(r.json())
            if models:
                return models
    except Exception:
        pass
    # fallback: YAML
    try:
        cfg = model_router._load_cfg()
        raw = cfg.get("models", [])
        out = []
        for m in raw:
            name = m.get("name") or m.get("id") or m.get("model")
            if not name:
                continue
            mm = dict(m)
            mm.setdefault("name", name)
            mm.setdefault("modality", _mode_from_name(name))
            mm.setdefault("enabled", True)
            out.append(mm)
        return out
    except Exception:
        return []

@router.get("/models")
async def list_models(
    modality: Optional[str] = Query(default="chat", pattern="^(chat|embed|all)$")
):
    try:
        models = await _load_models_or_fallback()
        if modality != "all":
            models = _filter_by_modality(models, modality)
        return {"version": "1.0", "models": models}
    except Exception as ex:
        raise HTTPException(502, f"cannot load models: {type(ex).__name__}: {ex}")

# --------------------------------- Chat -------------------------------------

@router.post("/chat")
async def chat( req: Request):
    body = await req.json()
    mode = (body.get("mode") or "free" or "harper").lower()
    if mode not in ("free","harper"):
        raise HTTPException(400, "mode must be 'free' for /v1/chat")

    provider = (body.get("provider") or "").lower().strip()
    model = body.get("model") or "auto"
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")

    # Attachments → inline vs rag
    attachments = body.get("attachments") or []
    # Normalize inputs: prefer explicit in_line_files/inline_files & rag_files.
    inline_files, rag_files, attachments = _normalize_context_from_body(body)
    log.info("chat extension & body fileds: %s, %s",  inline_files, rag_files)
    # If no explicit files were provided, but we have generic attachments, partition them.
    if not inline_files and not rag_files and attachments:
        inline_files, rag_files = await _decide_inline_or_rag(attachments)
    
    inline_files, rag_files = await _decide_inline_or_rag(attachments)
    log.info("chat attachments: %s, %s",  inline_files, rag_files)


    user_query = ""
    for m in reversed(messages):
        if (m.get("role") or "") == "user":
            user_query = (m.get("content") or "").strip()
            break

    # system + contesto
    sysmsg = {"role":"system","content":"You are CLike, a helpful and expert full-stack software engineering copilot."}
    msgs = [sysmsg] + list(messages)
    project_id = _rag_project_id(body)

    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query, project_id)

    # RAG paths/inline opzionali (compat) TODO: the following code depends on evaluation if SPEC.md, IDEA.md or other file driven by VS extension are needed.
    # Legacy compatibility: only apply if NO new-style inline/rag files were provided
    if not inline_files and not rag_files:
        rag_paths  = body.get("rag_paths") or []
        rag_inline = body.get("rag_inline") or []
        if rag_paths or rag_inline:
            blobs = []
            if rag_paths:
                blobs.extend(_gather_rag_context(rag_paths))
            if rag_inline:
                blobs.extend([str(x) for x in rag_inline if x])
            if blobs:
                ctx = "\n\n".join(blobs[:8])
                msgs = [{"role":"system","content":"Use the following context if relevant:\n"+ctx}] + msgs

    # validate modality
    all_models = await _load_models_or_fallback()
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==model)), None)
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{model}' is an embedding model and cannot be used for chat.")

       # log input (già presente, lascialo pure)
    log.info("chat request: %s", json.dumps({"model": model, "provider": provider, "messages_len": len(messages)}, ensure_ascii=False))

    # Prepara meta per log
    _gw = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
 
    payload = {
        "model": model,
        "messages": msgs,
        "temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens"),
        "provider": provider,
        "base_url": str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
        "remote_name": body.get("remote_name") or model,
        "profile": None,
    }

    log.info("chat request --> paylod: %s", json.dumps(payload))
    provider = body.get("provider")
    headers = {"Content-Type": "application/json"}
    _t0 = _time.time()
    try:
        all_models = await _load_models_or_fallback()
        model_entry = next((m for m in all_models if m.get("name") == model), None)
        req_max = int(body.get("max_tokens") or 2048)
        eff_max = su.tokens_per_model(msgs, model_entry, req_max)
        timeout_sec = min(240.0, 110.0 + (eff_max / 1000.0) * 3.8)


        
        text = await call_gateway_chat(
            model = body.get("model"),
            messages = msgs,
            temperature= body.get("temperature"),
            max_tokens= eff_max,
            # --- AGGIUNGI: provider-awareness end-to-end ---        
            base_url= str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")), 
            timeout=timeout_sec,
            response_format=None, 
            tools=None, 
            tool_choice=None, 
            profile=None, 
            provider= provider

        )
        _ms = int((_time.time() - _t0) * 1000)
        log.info("chat response: %s", json.dumps({"text_len": len(text or ""), "latency_ms": _ms}, ensure_ascii=False))
        return {"version": "1.0", "text": text, "usage": {}, "sources": []}
    except Exception as e:
        _ms = int((_time.time() - _t0) * 1000)
        log.error("chat error: %s", json.dumps({"error": f"{type(e).__name__}: {e}", "latency_ms": _ms}, ensure_ascii=False))
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")


def _gather_rag_context(paths: list[str], max_docs: int = 8, max_bytes: int = 200_000) -> list[str]:
    out = []
    for p in (paths or [])[:max_docs]:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                t = f.read(max_bytes)
                if t and t.strip():
                    out.append(f"# Context: {p}\n{t.strip()}")
        except Exception:
            continue
    return out

def _kb(n_bytes: int) -> int:
    try: return int(n_bytes) // 1024
    except: return 0

def _fence(fname: str, content: str) -> str:
    lang = ""
    if fname.endswith(".py"): lang="python"
    elif fname.endswith(".ts"): lang="ts"
    elif fname.endswith(".js"): lang="js"
    elif fname.endswith(".go"): lang="go"
    elif fname.endswith(".java"): lang="java"
    return f"```{lang}\n# {fname}\n{content}\n```"

async def _decide_inline_or_rag(attachments: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Regole:
      - se size_kb >= RAG_SIZE_THRESHOLD_KB => vai in RAG (a prescindere dal budget)
      - altrimenti, se c'è 'content' e c'è budget inline => inline
      - in tutti gli altri casi => RAG (con bytes_b64 se presente)
    """
    inline, rag = [], []
    if not attachments:
        return inline, rag

    budget = INLINE_MAX_TOTAL_KB
    for a in attachments:
        if not isinstance(a, dict):
            continue
        size = int(a.get("size") or 0)
        size_kb = _kb(size)
        name = a.get("name") or a.get("path") or "file"
        content = a.get("content")
        bytes_b64 = a.get("bytes_b64")
        origin = a.get("origin")
        path = a.get("path")
        log.info("decide inline or rag: %s", json.dumps({"name": name, "size": size, "size_kb": size_kb, "bytes_b64": bytes_b64, "origin": origin}, ensure_ascii=False))
        # 1) se oltre soglia → RAG
        if size_kb >= RAG_SIZE_THRESHOLD_KB:
            rag.append({"name": name, "path": path, "bytes_b64": bytes_b64, "size": size, "origin": origin})
            continue

        # 2) inline se possibile
        if isinstance(content, str) and content and size_kb <= INLINE_MAX_FILE_KB and (budget - size_kb) >= 0:
            inline.append({"name": name, "content": content})
            budget -= size_kb
        else:
            # 3) fallback → RAG
            rag.append({"name": name, "path": path, "bytes_b64": bytes_b64, "size": size, "origin": origin})

    log.info("attachments routing %s", json.dumps({
        "inline": len(inline), "rag": len(rag),
        "budget_left_kb": max(0, budget)
    }, ensure_ascii=False))
    return inline, rag


# --- REPLACE: _augment_messages_with_context ---------------------------------
async def _augment_messages_with_context(
    msgs: list[dict],
    inline_files: list[dict],
    rag_files: list[dict],
    user_query: str,
    project_id: str
) -> list[dict]:
    """
    Enrich messages with:
      1) Inline files (fenced) as a single system message.
      2) RAG retrieval on user_query (top-K) and prepend a 'Relevant project context' system message.

    Notes:
    - We assume large files were pre-indexed client-side.
    - We DO NOT re-index here (no rag_reindex_* or rag_search legacy calls).
    """
    out = list(msgs)

    # 1) Inline files → fenced block
    if inline_files:
        blocks = "\n\n".join(
            _fence(f.get("name") or f.get("path") or "file", f.get("content") or "")
            for f in inline_files
            if isinstance(f, dict) and (f.get("content") or "").strip()
        )
        if blocks.strip():
            out = [{"role": "system", "content": "You can use the following project files:\n\n" + blocks}] + out

    # 2) RAG retrieval (top-K)
    try:
        q = (user_query or "").strip()
        # (opzionale) leggero bias coi nomi dai rag_files
        if rag_files:
            names = []
            for rf in rag_files:
                n = (rf.get("path") or rf.get("name") or "").strip()
                if n:
                    names.append(n)
            if names:
                hint = " ".join(f"file:{n}" for n in names[:8])
                q = (q + " " + hint).strip()

        hits = await rag_query(project_id, q, top_k=RAG_TOP_K)
        def _norm(p: str) -> str:
            try:
                return os.path.normpath((p or "").strip()).lower()
            except Exception:
                return (p or "").strip().lower()

        allowed_full = {_norm(rf.get("path")) for rf in (rag_files or []) if isinstance(rf, dict) and rf.get("path")}
        allowed_base = {os.path.basename(p) for p in allowed_full if p}
        if hits and (allowed_full or allowed_base):
            filtered = []
            seen = set()  # (norm_path, chunk, first64)
            for h in hits:
                if not isinstance(h, dict):
                    continue
                hpath = (h.get("path") or h.get("source") or "").strip()
                npath = _norm(hpath)
                base  = os.path.basename(npath)

                # tieni SOLO se è uno dei file del turno corrente
                if npath not in allowed_full and base not in allowed_base:
                    continue

                text = (h.get("text") or "").strip()
                if not text:
                    continue

                chunk = int(h.get("chunk", 0))
                sig = (npath, chunk, text[:64])
                if sig in seen:
                    continue
                seen.add(sig)
                filtered.append({"path": hpath, "chunk": chunk, "text": text})

            hits = filtered
            if hits:
                blocks = []
                for h in hits[:RAG_TOP_K]:
                    t = h["text"]
                    if len(t) > 4000:
                        t = t[:4000] + "\n...[truncated]..."
                    blocks.append(f"### {h['path']}:{h['chunk']}\n{t}")
                if blocks:
                    out = [{"role": "system", "content": "Relevant project context:\n\n" + "\n\n".join(blocks)}] + out
    except Exception as e:
        log.warning("RAG enrichment failed: %s", e)

    return out



@router.post("/generate")
async def generate(req: Request):
    log.info("generate request +++")
    body = await req.json()
    mode = (body.get("mode") or "coding").lower()
    if mode not in ("harper", "coding"):
        raise HTTPException(400, "mode must be 'harper' or 'coding'")

    model = body.get("model") or "auto"
    provider = (body.get("provider") or "").lower().strip()  # <---

    PROVIDERS_RESPONSE_FORMAT = {"openai", "azure_openai"}
    PROVIDERS_TOOL_CALL      = {"ollama", "anthropic", "deepseek", "vllm"}

    prov = (provider or "").lower()
    _use_respfmt = prov in PROVIDERS_RESPONSE_FORMAT
    _use_tools   = prov in PROVIDERS_TOOL_CALL

    messages = body.get("messages") or []
    # Enforce tool-call in coding mode
    messages = _inject_coding_system(messages)

    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")

    # generation id + roots (path pianificati; nessuna scrittura ancora)
    gen_id = _short_id(8)
    _code_abs, _test_abs, code_root_rel, _test_rel = _build_generation_roots(gen_id)

    # System che “inchioda” lo schema di uscita (usato come contesto, ma non forziamo più response_format qui)
    sys_schema = {
        "role": "system",
        "content": (
            "You are CLike an expert code generator, Image and Video creator, UI/UX desinger with Cloud Skills, Application and Infrastructure Architect and more.  ALWAYS answer ONLY valid JSON with this schema:\n"
            "{\n"
            '  "files": [ { "path": "<relative/path/with/extension>", "content": "<full file content>" } ],\n'
            '  "messages": [ { "role": "assistant", "content": "<optional explanation>" } ]\n'
            "}\n"
            "No code fences. No 'Generated files:' lists. If multiple languages are needed, include multiple entries in files[].\n"
        )
    }

    # Attachments → inline vs rag
    attachments = body.get("attachments") or []
    # Normalize inputs: prefer explicit in_line_files/inline_files & rag_files.
    inline_files, rag_files, attachments = _normalize_context_from_body(body)

    # If no explicit files were provided, but we have generic attachments, partition them.
    if not inline_files and not rag_files and attachments:
        inline_files, rag_files = await _decide_inline_or_rag(attachments)
    
    inline_files, rag_files = await _decide_inline_or_rag(attachments)


    # RAG query dall’ultimo user
    user_query = ""
    for m in reversed(messages):
        if (m.get("role") or "") == "user":
            user_query = (m.get("content") or "").strip()
            break

    msgs = [sys_schema] + list(messages)
    project_id = _rag_project_id(body)
    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query, project_id)

    # modality check
    all_models = await _load_models_or_fallback()
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==model)), None)
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{model}' is an embedding model and cannot be used for code generation.")

    log.info("generate request: %s", json.dumps({"model": model, "messages_len": len(messages)}, ensure_ascii=False))

    # ======== Chiamata gateway (prima scelta: TOOL CALLING) ========
    # ======== Gateway payload builder (coding) ========
    base_url = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")

   

    # 2) JSON schema per response_format (OpenAI)
    FILES_BUNDLE_SCHEMA = {
        "name": "files_bundle_v1",
        "schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path":      {"type": "string"},
                            "content":   {"type": "string"},
                            "language":  {"type": "string"},
                            "executable":{"type": "boolean"}
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["files"],
            "additionalProperties": False
        },
        "strict": True
    }

    # 3) Decidi strategia in base al provider:
    #    - openai: niente tools → response_format JSON schema (evita l'errore 'tools' type)
    #    - altrimenti: tool-calling classico
    _use_tools = (provider or "").lower() not in ("openai", "azure_openai")

    # 4) Prompt di servizio per istruire l'output (robusto anche senza response_format)
    emit_files_guidance = (
        "When you propose code changes, you MUST return a bundle of files with paths and contents. "
        "Prefer the exact JSON schema if supported; otherwise return a single top-level JSON object "
        "with the structure {\"files\":[{\"path\":\"...\",\"content\":\"...\",\"language\":\"optional\",\"executable\":false}]} "
        "with no extra text before or after."
    )
    # Inseriamo un system aggiuntivo conciso (resta compatibile con il resto del prompt Harper)
    msgs = [{"role":"system","content": emit_files_guidance}] + msgs

    # 5) Costruisci payload
    temperature = body.get("temperature", 0.1)
    max_tokens  = body.get("max_tokens", 4048)

    payload = {
        "model": model,
        "messages": msgs,
        "base_url": base_url,
    }

    # Provider passato esplicitamente (utile per gateway routing)
    if provider is not None:
        payload["provider"] = provider

    # Token fields: GPT-5 usa max_completion_tokens, altri max_tokens
    if str(model).startswith("gpt-5"):
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
    else:
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

    # Temperature: tienila bassa in coding; per GPT-5 spesso è ignorata, non la inviamo.
    if temperature is not None and not str(model).startswith("gpt-5"):
        payload["temperature"] = temperature

    # --- Cross-provider: tools vs response_format ---
    PROVIDERS_RESPONSE_FORMAT = {"openai", "azure_openai"}
    PROVIDERS_TOOL_CALL      = {"ollama", "anthropic", "deepseek", "vllm"}

    prov = (provider or "").lower()

    if prov in PROVIDERS_TOOL_CALL:
        # Tool-calling classico (emit_files)
        emit_files_tool = {
            "type": "function",
            "function": {
                "name": "emit_files",
                "description": "Return source files to be written by the caller.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path":       {"type": "string"},
                                    "content":    {"type": "string"},
                                    "language":   {"type": "string"},
                                    "executable": {"type": "boolean"}
                                },
                                "required": ["path", "content"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["files"],
                    "additionalProperties": False
                }
            }
        }
        payload["tools"] = [emit_files_tool]
        payload["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
    else:
        # OpenAI/Azure (o default): niente tools, usa JSON schema response_format
        payload.pop("tools", None)
        payload.pop("tool_choice", None)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "files_bundle_v1",
                "schema": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path":       {"type": "string"},
                                    "content":    {"type": "string"},
                                    "executable": {"type": "boolean"}
                                },
                                "required": ["path", "content"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["files"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }

    # Safety: se per qualsiasi motivo in alto qualcuno ha messo tools/tool_choice, rimuovili per OpenAI/Azure
    if prov in PROVIDERS_RESPONSE_FORMAT:
        payload.pop("tools", None)
        payload.pop("tool_choice", None)

    if _use_tools:
        # Percorso tool-calling (Ollama, altri provider)
        payload["tools"] = [emit_files_tool]
        payload["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
    else:
        # Percorso OpenAI senza tools → JSON schema mode
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": FILES_BUNDLE_SCHEMA
        }
        # NOTA: nessun "tools" e nessun "tool_choice" nel payload

    # Sanitizza per sicurezza
    payload = _json_safe(payload)
    payload["response_format"] = build_response_format_files_bundle()


    # --- LOG rich: request/response gateway ---
    _headers = {"Content-Type": "application/json", "X-CLike-Profile": "code.strict"}
    if provider:
        _headers["X-CLike-Provider"] = provider

    log.info("gateway.request %s", json.dumps({
        "url": f"{base_url}/v1/chat/completions",
        "model": model,
        "profile": payload.get("profile"),
        "tools": bool(payload.get("tools")),
        "tool_choice": bool(payload.get("tool_choice")),
        "has_response_format": bool(payload.get("response_format")),
        "max_tokens": payload.get("max_tokens"),
        "provider": payload.get("provider"),
        "max_completion_tokens": payload.get("max_completion_tokens"),
    }, ensure_ascii=False))



        # --- LOG rich: request/response gateway ---
   
    _headers = {"Content-Type": "application/json", "X-CLike-Profile": "code.strict"}
    if provider:
        _headers["X-CLike-Provider"] = provider
   
    log.info("gateway.request %s", json.dumps({
        "url": f"{base_url}/v1/chat/completions",
        "model": model,
        "profile": payload.get("profile"),
        "tools": bool(payload.get("tools")),
        "tool_choice": bool(payload.get("tool_choice")),
        "max_tokens": payload.get("max_tokens"),
        "provider": payload.get("provider"),
        "max_completion_tokens": payload.get("max_completion_tokens"),
    }, ensure_ascii=False))
    
    try:
        all_models = await _load_models_or_fallback()
        model_entry = next((m for m in all_models if m.get("name") == model), None)
        req_max = int(body.get("max_tokens") or 2048)
        eff_max = su.tokens_per_model(msgs, model_entry, req_max)
        timeout_sec = min(240.0, 60.0 + (eff_max / 1000.0) * 2.0)
        payload["timeout"] = timeout_sec

        data = await call_gateway_generate(payload, _headers)

        # ---- Estrazione FILES in modo robusto cross-provider ----
        files: List[Dict[str, Any]] = []

        def _first_message(d: Any) -> Dict[str, Any]:
            """Ritorna in sicurezza il primo message da data['choices'][0]['message'] se presente e ben formato."""
            try:
                if isinstance(d, dict):
                    ch = d.get("choices")
                    if isinstance(ch, list) and ch:
                        c0 = ch[0]
                        if isinstance(c0, dict):
                            m = c0.get("message")
                            if isinstance(m, dict):
                                return m
            except Exception:
                pass
            return {}

        msg = _first_message(data)               # dict (o {})
        content_str = ""
        if isinstance(msg, dict):
            content_str = msg.get("content") or ""

        # 1) Preferisci tool_calls (OpenAI compat)
        tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
        if isinstance(tool_calls, list) and tool_calls:
            for tc in tool_calls:
                try:
                    if (tc.get("type") == "function") and (tc.get("function", {}).get("name") == "emit_files"):
                        args_raw = tc.get("function", {}).get("arguments")
                        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                        parsed = (args.get("files") or [])
                        files = _normalize_files_for_write(parsed)
                        log.info("generate tool_calls->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))
                        break
                except Exception:
                    # continua coi fallback
                    pass

        # 2) Fallback: top-level "files" (es. Ollama / adapter custom)
        if not files and isinstance(data, dict) and isinstance(data.get("files"), list):
            files = _normalize_files_for_write(data["files"])
            log.info("generate top-level->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))

        # 3) Fallback: JSON puro dentro message.content / oppure 'text'
        if not files:
            if not content_str and isinstance(data, dict) and "text" in data:
                content_str = data.get("text") or ""
            if isinstance(content_str, str) and content_str.strip():
                try:
                    obj = _extract_json(content_str)
                    jf = obj.get("files") if isinstance(obj, dict) else None
                    if isinstance(jf, list) and jf:
                        files = _normalize_files_for_write(jf)
                        log.info("generate content-json->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))
                except Exception:
                    # 4) Ultimo fallback: code fences → file singoli
                    from_fences = _extract_files_from_fences(content_str)
                    if from_fences:
                        files = _normalize_files_for_write(from_fences)
                        log.info("generate fences->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))

        log.info("generate files (post-extract) %s", json.dumps({"count": len(files)}, ensure_ascii=False))

        # 5) Se ancora vuoto → 422 coerente
        if not files:
            log.info("generate no-files (nothing from tool_calls/top-level/json/fences)")
            raise HTTPException(status_code=422, detail="model did not produce 'files' with path+content")

        # 6) retarget sotto generated_<uuid>/ {src|docs|images}
        temp_path = str(uuid.uuid4()).split("-")[0]
        files = _retarget_files_under_generated(files, temp_path)   # <— prima dei diff!

        # 7) diffs
        diffs: List[Dict[str, Any]] = []
        for fobj in files:
            path = fobj["path"]
            content = fobj.get("content", "")
            prev = su.read_file(path) or ""
            patch = su.to_diff(prev, content, path)
            diffs.append({"path": path, "diff": patch})

        # 8) risposta completa (popola "text" e "diffs" per i tab)
        result = {
            "version": "1.0",
            "files": files,
            "usage": (data.get("usage") if isinstance(data, dict) else {}) or {},
            "sources": [],
            "text": "Generated files:\n" + "\n".join(f"- {f['path']}" for f in files),
            "diffs": diffs or ["(No diffs computed: new files)"],
            "audit_id": "coding-toolcalls",
        }
        return result

    except httpx.HTTPStatusError as e:
        # Propaga il vero body (niente 502 generici)
        raise HTTPException(e.response.status_code, detail=f"gateway chat failed: {e.response.text}")
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    
   

# -------------------------------- Apply -------------------------------------

@router.post("/apply")
async def apply(req: Request):
    """
    Applica file **direttamente dal payload**:
      {
        "files": [{ "path":"...", "content":"..." }, ...],
        "selection": { "apply_all": true }    # oppure: { "paths": ["a","b"] }
      }

    Nota: supporto a run_dir è stato rimosso.
    """
    body = await req.json()

    # rifiuta legacy
    if body.get("run_dir"):
        raise HTTPException(400, "run_dir is no longer supported. Pass 'files' directly in the request body.")

    files = body.get("files")
    if not isinstance(files, list) or not files:
        raise HTTPException(400, "files (list) is required")

    selection = body.get("selection") or {}
    paths_selected: set[str] = set()
    if isinstance(selection, dict):
        if selection.get("apply_all"):
            paths_selected = { (f.get("path") or "").strip() for f in files if isinstance(f, dict) }
        else:
            for p in selection.get("paths", []):
                if isinstance(p, str) and p.strip():
                    paths_selected.add(p.strip())

    applied: list[str] = []
    failures: list[dict] = []

    for fobj in files:
        if not isinstance(fobj, dict):
            continue
        path = (fobj.get("path") or "").strip()
        if not path:
            continue
        if paths_selected and path not in paths_selected:
            continue
        try:
            _write_file_any(path, fobj)
            applied.append(path)
        except Exception as e:
            failures.append({"path": path, "error": f"{type(e).__name__}: {e}"})

    log.info("apply result: %s", json.dumps({"applied": len(applied), "failures": len(failures)}, ensure_ascii=False))

    if failures:
        return {"applied": applied, "failures": failures}
    return {"applied": applied}
