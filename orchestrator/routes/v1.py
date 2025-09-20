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

# --- add imports se non ci sono già ---
import json
from typing import Any, Dict, List, Optional

# --- helper Structured Outputs per i file generati ---
def _clike_files_response_format() -> Dict[str, Any]:
    """
    response_format compatibile con OpenAI Structured Outputs.
    Richiede un oggetto: { "files": [ { "path": str, "content": str, "mime_type"?: str } ] }
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "clike_files",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "path":    {"type": "string"},
                                "content": {"type": "string"},
                                "mime_type": {"type": "string"}
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


# -------------------- helpers: bucket & schema coercion ---------------------

def _bucketize_path(root_rel: str, rel_or_name: str) -> str:
    """
    Mapping:
      - code:    <root_rel>/src/<basename>
      - docs:    <root_rel>/doc/<basename>
      - images:  images/<generated_xxxx>/<basename>   (top-level)
    """
    base = os.path.basename(rel_or_name or "file.txt")
    ext = os.path.splitext(base)[1].lower()

    if ext in IMAGE_EXTS:
        gen_dir = os.path.basename(root_rel)  # es: generated_ab12cd34
        return os.path.join("images", gen_dir, base).replace("\\", "/")

    sub = "src" if (ext in CODE_EXTS) else ("doc" if (ext in DOC_EXTS) else "doc")
    return os.path.join(root_rel, sub, base).replace("\\", "/")

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

def _coerce_to_schema(raw_text: str, lang_hint: str = "") -> tuple[list[dict], list[dict]]:
    """
    Ritorna (files, messages) secondo schema CLike.
    1) Prova JSON; valido SOLO se files[] ha almeno 1 item
    2) Fences
    3) Normalizza
    4) Se niente ma c’è testo → messages (no .txt di eco)
    """
    files: list[dict] = []
    messages: list[dict] = []

    # 1) JSON
    try:
        pj = _extract_json(raw_text or "")
        jf = pj.get("files") if isinstance(pj, dict) else None
        if isinstance(jf, list) and jf:
            files = jf
            jm = pj.get("messages") or pj.get("message") or []
            if isinstance(jm, list):
                messages = jm
            elif isinstance(jm, dict) and jm.get("content"):
                messages = [jm]
    except Exception:
        pass

    # 2) code fences
    if not files:
        files = _extract_files_from_fences(raw_text or "")

    # 3) normalizza
    files = _normalize_files_for_write(files)

    # 4) se ancora vuoto ma c'è testo → message
    if not files and (raw_text or "").strip():
        messages = messages or [{"role": "assistant", "content": (raw_text or "").strip()}]

    return files, messages

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

def _strip_markdown_and_noise(text: str) -> str:
    # rimuove blocchi ```...``` e la stringa "Generated files:"
    s = re.sub(r'```.*?```', '', text or "", flags=re.DOTALL|re.IGNORECASE)
    s = re.sub(r'Generated files:\s*', '', s, flags=re.IGNORECASE)
    return (s or "").strip()[:2000]

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

    # log input
    log.info("chat request: %s", json.dumps({"model": model, "messages_len": len(messages)}, ensure_ascii=False))

    try:
        text = await llm_client.call_gateway_chat(
            model, msgs,
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.2),
            max_tokens=body.get("max_tokens", 512),
        )
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    log.info("chat response: %s", json.dumps({"text_len": len(text or "")}, ensure_ascii=False))
    return {"version": "1.0", "text": text, "usage": {}, "sources": []}

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

def _harvest_data_urls_to_files(text: str, gen_id: str) -> list[dict]:
    files = []
    for i, m in enumerate(DATA_URL_RE.finditer(text or "")):
        mime = m.group(1)     # es: image/png
        b64  = m.group(2)
        ext  = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
        }.get(mime, ".bin")
        path = f"images/generated_{gen_id}/asset_{i}{ext}"
        files.append({"path": path, "content_base64": b64, "mime": mime})
    return files

# ------------------------------- Generate -----------------------------------

def _system_for_generate(mode: str) -> str:
    base = ("You are CLike, a super expert software and product-engineering copilot. "
            "Output strictly JSON, no prose.")
    if mode == "harper":
        return base + ' Return: {"files":[{"path":"...","content":"..."}], "messages":[{"role":"assistant","content":"..."}]}'
    return base + ' Return: {"files":[{"path":"...","content":"..."}]}'

@router.post("/generate")
async def generate(req: Request):
    body = await req.json()
    mode = (body.get("mode") or "coding").lower()
    if mode not in ("harper", "coding"):
        raise HTTPException(400, "mode must be 'harper' or 'coding'")

    model = body.get("model") or "auto"
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")
    # generation id + roots (path pianificati; nessuna scrittura ancora)
    gen_id = _short_id(8)
    _code_abs, _test_abs, code_root_rel, _test_rel = _build_generation_roots(gen_id)
    rf = _clike_files_response_format()
    # Impone Structured Outputs per ottenere files[] dal provider
    

    # System che “inchioda” lo schema di uscita
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

    # Chiamata gateway
    try:
        raw = await llm_client.call_gateway_chat(
            model, msgs,
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.1),
            max_tokens=body.get("max_tokens", 2048),
            response_format=rf,
            profile="code.strict"
        )
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    # --- parsing standard Chat Completions ---
    content_str: Optional[str] = None
    try:
        if "choices" in data and data["choices"]:
            msg = data["choices"][0].get("message", {})
            # Se Structured Outputs, il JSON arriva in message.content (stringa)
            content_str = msg.get("content") if isinstance(msg, dict) else None
            # Supporto (raro) ad alte varianti: se "text" è presente
            if not content_str and "text" in data:
                content_str = data["text"]
    except Exception:
        content_str = None

    if not content_str:
        # Se il provider restituisce refusal strutturata (vedi cookbook),
        # mostra un errore esplicito
        try:
            refusal = data["choices"][0]["message"].get("refusal")
            if refusal:
                raise HTTPException(status_code=422, detail=f"model refusal: {refusal}")
        except Exception:
            pass
        raise HTTPException(status_code=422, detail="model did not return content for structured files")

    # Decodifica JSON strutturato
    try:
        parsed = json.loads(content_str)
    except Exception as e:
        # utile in caso di provider legacy che non garantisce JSON valido
        raise HTTPException(status_code=422, detail=f"invalid JSON from model: {e}")

    files = parsed.get("files") or []
    norm_files: List[Dict[str, Any]] = []
    for f in files:
        path = (f or {}).get("path")
        content = (f or {}).get("content")
        if path and content:
            norm_files.append({
                "path": str(path),
                "content": str(content),
                "mime_type": (f or {}).get("mime_type") or "text/plain"
            })

    if not norm_files:
        # Forziamo l’invariante che ti serve a valle
        raise HTTPException(status_code=422, detail="model did not produce 'files' with path+content")

    # Risposta normalizzata Clike
    return {
        "version": "1.0",
        "files": norm_files,
        "usage": data.get("usage") or {},
        "sources": [],
        "audit_id": "coding-structured",
    }

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
