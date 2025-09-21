# routes/v1.py
import os, json, logging, re, uuid, base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, Query
import httpx
from config import settings
from services import utils as su
from services import llm_client
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

# --- LOGGING UTILS (aggiunta) ---
import time as _time
from copy import deepcopy as _deepcopy

# --- Generated root selection -------------------------------------------------
import uuid

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
    path= "docs"
    if ext in CODE_EXTS:
        path = "src"
    if ext in IMAGE_EXTS:
        path = "images"
    if ext in DOC_EXTS:
        path = "docs"
    # default: documentazione
    return path

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

def _shrink_text(s: str, limit: int = 1200) -> str:
    if not isinstance(s, str):
        return str(s)
    if len(s) <= limit:
        return s
    return s[:limit] + f"... <+{len(s)-limit} chars>"

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
async def rag_reindex_paths(paths: list[str]):
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            await client.post("http://localhost:8080/v1/rag/reindex", json={"paths": paths})
        except Exception as e:
            log.warning("rag_reindex_paths failed: %s", e)

async def rag_reindex_uploads(uploads: list[dict]):
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            await client.post("http://localhost:8080/v1/rag/reindex", json={"uploads": uploads})
        except Exception as e:
            log.warning("rag_reindex_uploads failed: %s", e)

async def rag_search(query: str, top_k: int):
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post("http://localhost:8080/v1/rag/search", json={"query": query, "top_k": top_k})
            r.raise_for_status()
            return r.json().get("results") or []
        except Exception as e:
            log.warning("rag_search failed: %s", e)
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
async def chat(req: Request):
    body = await req.json()
    mode = (body.get("mode") or "free").lower()
    if mode not in ("free",):
        raise HTTPException(400, "mode must be 'free' for /v1/chat")

    provider = (body.get("provider") or "").lower().strip()
    model = body.get("model") or "auto"
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")

    # Attachments → inline vs rag
    attachments = body.get("attachments") or []
    inline_files, rag_files = await _decide_inline_or_rag(attachments)
    
    # query per RAG
    user_query = ""
    for m in reversed(messages):
        if (m.get("role") or "") == "user":
            user_query = (m.get("content") or "").strip()
            break

    # system + contesto
    sysmsg = {"role":"system","content":"You are CLike, a helpful and expert full-stack software engineering copilot."}
    msgs = [sysmsg] + list(messages)
    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query)

    # RAG paths/inline opzionali (compat)
    rag_paths  = (body.get("rag_paths") or []) + (body.get("rag_files") or [])
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
    _t0 = _time.time()
    _gw = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
 

    try:
        text = await llm_client.call_gateway_chat(
            model, msgs,
            base_url=_gw,
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.2),
            max_tokens=body.get("max_tokens", 512),
            provider=provider or None,
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
    inline, rag = [], []
    if not attachments: return inline, rag
    budget = INLINE_MAX_TOTAL_KB
    for a in attachments:
        size = int(a.get("size") or 0)
        name = a.get("name") or a.get("path") or "file"
        content = a.get("content")
        bytes_b64 = a.get("bytes_b64")
        if content and _kb(size) <= INLINE_MAX_FILE_KB and budget - _kb(size) >= 0:
            inline.append({"name": name, "content": content})
            budget -= _kb(size)
        else:
            rag.append({
                "name": name,
                "path": a.get("path"),
                "bytes_b64": bytes_b64,
                "size": size,
                "origin": a.get("origin")
            })
    return inline, rag

async def _augment_messages_with_context(msgs: list[dict], inline_files: list[dict], rag_files: list[dict], user_query: str) -> list[dict]:
    out = list(msgs)
    # 1) inline
    if inline_files:
        blocks = "\n\n".join(_fence(f["name"], f["content"]) for f in inline_files if f.get("content"))
        if blocks.strip():
            out = [{"role":"system","content": f"You can use the following project files:\n\n{blocks}"}] + out
    # 2) RAG paths / uploads (no-op qui: gli upload li indicizzerei via altri endpoint se servono)
    paths = [f.get("path") for f in rag_files if f.get("path")]
    if paths:
        try:
            await rag_reindex_paths(paths)
            chunks = await rag_search(user_query or "", top_k=RAG_TOP_K)
            if chunks:
                ctx = "\n\n".join(f"### {c['source']}:{c.get('line_start',1)}-{c.get('line_end',1)}\n{c['text']}" for c in chunks)
                out = [{"role":"system","content": f"Relevant project context:\n\n{ctx}"}] + out
        except Exception as e:
            log.warning("RAG enrichment failed: %s", e)
    return out

@router.post("/generate")
async def generate(req: Request):
    body = await req.json()
    mode = (body.get("mode") or "coding").lower()
    if mode not in ("harper", "coding"):
        raise HTTPException(400, "mode must be 'harper' or 'coding'")

    model = body.get("model") or "auto"
    provider = (body.get("provider") or "").lower().strip()  # <---

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
            "You are CLike code generator. ALWAYS answer ONLY valid JSON with this schema:\n"
            "{\n"
            '  "files": [ { "path": "<relative/path/with/extension>", "content": "<full file content>" } ],\n'
            '  "messages": [ { "role": "assistant", "content": "<optional explanation>" } ]\n'
            "}\n"
            "No code fences. No 'Generated files:' lists. If multiple languages are needed, include multiple entries in files[].\n"
        )
    }

    # Attachments → inline vs RAG
    attachments = body.get("attachments") or []
    inline_files, rag_files = await _decide_inline_or_rag(attachments)

    # RAG query dall’ultimo user
    user_query = ""
    for m in reversed(messages):
        if (m.get("role") or "") == "user":
            user_query = (m.get("content") or "").strip()
            break

    msgs = [sys_schema] + list(messages)
    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query)

    # modality check
    all_models = await _load_models_or_fallback()
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==model)), None)
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{model}' is an embedding model and cannot be used for code generation.")

    log.info("generate request: %s", json.dumps({"model": model, "messages_len": len(messages)}, ensure_ascii=False))

    # ======== Chiamata gateway (prima scelta: TOOL CALLING) ========
    base_url = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
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
            }
        }
    }

    temperature =body.get("temperature", 0.1)
    max_tokens = body.get("max_tokens", 2048)
    payload = {
        "model": model,
        "messages": msgs,
    }
    payload["tools"] = [emit_files_tool]
    payload["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
    if provider is not None:
        payload["provider"] = provider
        
    if temperature is not None:
        if not model.startswith("gpt-5"):
            payload["temperature"] = temperature

    # GPT-5 usa max_completion_tokens sulla Chat Completions API; le altre famiglie restano su max_tokens
    if model.startswith("gpt-5"):
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
    else:
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

    if str(model).startswith("gpt-5"):
        payload["max_completion_tokens"] = body.get("max_tokens", 2048)
    
    if str(model).startswith("gpt-5"):
        payload["max_completion_tokens"] = body.get("max_tokens", 2048)
    # Sanitizer finale: elimina ogni set residuo che romperebbe json=
    payload = _json_safe(payload)


        # --- LOG rich: request/response gateway ---
    _t0 = _time.time()
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
        async with httpx.AsyncClient(timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60))) as client:
            r = await client.post(f"{base_url}/v1/chat/completions", json=payload, headers=_headers)
            txt = r.text
            _ms = int((_time.time() - _t0) * 1000)
            if r.is_success:
                log.info("gateway.response %s", json.dumps({
                    "status": r.status_code,
                    "latency_ms": _ms
                }, ensure_ascii=False))
                # log body (ridotto) a livello DEBUG
                try:
                    data = r.json()
                    
                    log.debug("gateway.response.body %s", _shrink_text(json.dumps(data, ensure_ascii=False), 4000))
                except Exception:
                    log.debug("gateway.response.text %s", _shrink_text(txt, 4000))
                
                # Log sintetico di risposta
                try:
                    log.info("gateway.response %s", json.dumps({"status": 200, "latency_ms": _ms}, ensure_ascii=False))
                    log.debug("gateway.response.body %s", _shrink_text(json.dumps(data, ensure_ascii=False), 4000))
                except Exception:
                    pass

                # 1) preferisci tool_calls
                choices = (data.get("choices") or [])
                msg = (choices[0].get("message") if choices else {}) or {}
                tool_calls = msg.get("tool_calls") or []

                if tool_calls:
                    for tc in tool_calls:
                        if (tc.get("type") == "function") and (tc.get("function", {}).get("name") == "emit_files"):
                            args_raw = tc.get("function", {}).get("arguments")
                            try:
                                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                            except Exception:
                                args = {}
                            parsed = (args.get("files") or [])
                            
                            files = _normalize_files_for_write(parsed)  # tua utility già presente

                            log.info("generate tool_calls->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))
                            break;
                            

                # 2) fallback: JSON puro in content
                text = msg.get("content") or ""
                if text:
                    try:
                        obj = json.loads(text)
                        files = (obj.get("files") or [])
                        files = _normalize_files_for_write(files)
                        log.info("generate content-json->files %s", json.dumps({"count": len(files)}, ensure_ascii=False))
                        
                    except Exception:
                        pass

                log.info("Estrai dai tool_calls files=%s", json.dumps({"count": len(files)}, ensure_ascii=False))
                # se ancora vuoto → 422 coerente
                if not files:
                    log.info("generate no-files (nothing from tool_calls/json/fences)")
                    raise HTTPException(status_code=422, detail="model did not produce 'files' with path+content")
                temp_path = str(uuid.uuid4()).split("-")[0]
                # 4) retarget sotto generated_<uuid> (o GENERATED_ROOT)
                files = _retarget_files_under_generated(files, temp_path)   # <— prima dei diff!
                diffs: List[Dict[str, Any]] = []
                for fobj in files:
                    path = fobj["path"]
                    content = fobj.get("content", "")
                    prev = su.read_file(path) or ""
                    patch = su.to_diff(prev, content, path)
                    diffs.append({"path": path, "diff": patch})
                # 6) risultato completo (text + diffs)
                result = {
                    "version": "1.0",
                    "files": files,
                    "usage": data.get("usage") or {},
                    "sources": [],
                    "text": "Generated files:\n" + "\n".join(f"- {f['path']}" for f in files),
                    "diffs": diffs or ["(No diffs computed: new files)"],
                    "audit_id": "coding-toolcalls",
                }
                
                return result

            else:
                log.error("gateway.response %s", json.dumps({
                    "status": r.status_code,
                    "latency_ms": _ms,
                    "error_text": _shrink_text(txt, 2000)
                }, ensure_ascii=False))
                r.raise_for_status()

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
