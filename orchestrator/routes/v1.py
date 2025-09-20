# routes/v1.py
import os, json, uuid, time, logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
import httpx
import re, uuid

from config import settings
from services import utils as su
from services import llm_client
from services import model_router
from services.splitter import (
    infer_language,
    split_python_per_symbol,
    split_ts_per_symbol,
    apply_strategy,
)
from services.tests_scaffold import ensure_min_tests
import uuid
import re
from datetime import datetime
from types import SimpleNamespace
import importlib.util
from typing import Tuple
from collections import defaultdict

def split_python_per_symbol_heuristic(text: str): return []
def split_ts_per_symbol_heuristic(text: str): return []
def split_go_per_symbol(text: str): return []
def split_go_per_symbol_heuristic(text: str): return []
def split_java_per_symbol(text: str): return []
def split_java_per_symbol_heuristic(text: str): return []
def split_react_per_symbol(text: str): return []
def split_react_per_symbol_heuristic(text: str): return []

router = APIRouter(prefix="/v1")
log = logging.getLogger("orchestrator.v1")
INLINE_MAX_FILE_KB = int(os.getenv("INLINE_MAX_FILE_KB", "64"))
INLINE_MAX_TOTAL_KB = int(os.getenv("INLINE_MAX_TOTAL_KB", "256"))
RAG_SIZE_THRESHOLD_KB = int(os.getenv("RAG_SIZE_THRESHOLD_KB", "64"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "12"))
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
DATA_URL_RE = re.compile(r'data:(image/[\w\-\+\.]+);base64,([A-Za-z0-9+/=]+)')
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff"}

def _bucketize_path(root_rel: str, rel_or_name: str) -> str:
    """
    Mapinf in:
      - code:    <root_rel>/src/<basename>
      - docs:    <root_rel>/doc/<basename>
      - images:  images/<generated_xxxx>/<basename>   (folder top-level, cross-run safe)
    """
    base = os.path.basename(rel_or_name or "file.txt")
    ext = os.path.splitext(base)[1].lower()

    if ext in IMAGE_EXTS:
        gen_dir = os.path.basename(root_rel)  # es: generated_ab12cd34
        return os.path.join("images", gen_dir, base).replace("\\", "/")

    sub = "src" if (ext in CODE_EXTS) else ("doc" if (ext in DOC_EXTS) else "doc")
    return os.path.join(root_rel, sub, base).replace("\\", "/")


def _coerce_to_schema(raw_text: str, lang_hint: str = "") -> tuple[list[dict], list[dict]]:
    """
    Restituisce (files, messages) secondo schema CLike:
      files: [{path, content, language?}]
      messages: [{"role":"assistant","content": "..."}]
    Strategia:
      1) Prova JSON; valido SOLO se files[] non vuoto
      2) Se niente, prova code fences
      3) Normalizza per il writer
      4) Se ancora vuoto ma c'è testo → messages (non creare .txt da JSON eco)
    """
    files: list[dict] = []
    messages: list[dict] = []

    # 1) JSON
    try:
        pj = _extract_json(raw_text)
        jf = pj.get("files") if isinstance(pj, dict) else None
        if isinstance(jf, list) and len(jf) > 0:
            files = jf
            jm = pj.get("messages") or pj.get("message") or []
            if isinstance(jm, list):
                messages = jm
            elif isinstance(jm, dict) and jm.get("content"):
                messages = [jm]
    except Exception:
        pass

    # 2) Code fences
    if not files:
        files = _extract_files_from_fences(raw_text)

    # 3) Normalizza
    files = _normalize_files_for_write(files)

    # 4) Se ancora niente, ma c’è testo → restituisci come message (no .txt con eco JSON)
    if not files and raw_text and raw_text.strip():
        messages = messages or [{"role": "assistant", "content": raw_text.strip()}]

    return files, messages

def _read_text_file(p: str, max_bytes: int = 200_000) -> str:
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            s = f.read(max_bytes)
            return s.strip()
    except Exception:
        return ""

def _gather_rag_context(paths: list[str], max_docs: int = 8, max_bytes: int = 200_000) -> list[str]:
    out = []
    for p in (paths or [])[:max_docs]:
        t = _read_text_file(p, max_bytes=max_bytes)
        if t:
            out.append(f"# Context: {p}\n{t}")
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
    """Ritorna (inline, rag). Inline ha 'name' e 'content'. RAG ha almeno uno tra path/bytes_b64."""
    inline, rag = [], []
    if not attachments: return inline, rag
    budget = INLINE_MAX_TOTAL_KB
    for a in attachments:
        size = int(a.get("size") or 0)
        name = a.get("name") or a.get("path") or "file"
        content = a.get("content")
        bytes_b64 = a.get("bytes_b64")
        # inline se content presente e stiamo nel budget
        if content and _kb(size) <= INLINE_MAX_FILE_KB and budget - _kb(size) >= 0:
            inline.append({"name": name, "content": content})
            budget -= _kb(size)
        else:
            # tutto il resto va su RAG (path nel workspace o bytes_b64 esterno)
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

    # 1) Inline: prepend un system con i blocchi
    if inline_files:
        blocks = "\n\n".join(_fence(f["name"], f["content"]) for f in inline_files if f.get("content"))
        if blocks.strip():
            out = [{"role":"system","content": f"You can use the following project files:\n\n{blocks}"}] + out

    # 2) RAG: indicizza e recupera chunk pertinenti
    if rag_files:
        # Reindex: path locali e/o bytes caricati
        # - paths locali
        paths = [f["path"] for f in rag_files if f.get("path")]
        if paths:
            try:
                await rag_reindex_paths(paths)   # definito sotto
            except Exception as e:
                print(f"[WARN] rag reindex paths failed: {e}")
        # - upload bytes esterni
        uploads = [f for f in rag_files if f.get("bytes_b64")]
        if uploads:
            try:
                await rag_reindex_uploads(uploads)  # definito sotto
            except Exception as e:
                print(f"[WARN] rag reindex uploads failed: {e}")

        # Search e inserimento chunk
        try:
            chunks = await rag_search(user_query or "", top_k=RAG_TOP_K)  # definito sotto
            if chunks:
                ctx = "\n\n".join(f"### {c['source']}:{c.get('line_start',1)}-{c.get('line_end',1)}\n{c['text']}" for c in chunks)
                out = [{"role":"system","content": f"Relevant project context:\n\n{ctx}"}] + out
        except Exception as e:
            print(f"[WARN] rag search failed: {e}")

    return out

# ===== Chiamate RAG (usa i tuoi endpoint esistenti) =====
async def rag_reindex_paths(paths: list[str]):
    async with httpx.AsyncClient(timeout=60) as client:
        await client.post("http://localhost:8080/v1/rag/reindex", json={"paths": paths})

async def rag_reindex_uploads(uploads: list[dict]):
    # ciascun item: {name, bytes_b64, mime?}
    async with httpx.AsyncClient(timeout=60) as client:
        await client.post("http://localhost:8080/v1/rag/reindex", json={"uploads": uploads})

async def rag_search(query: str, top_k: int):
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("http://localhost:8080/v1/rag/search", json={"query": query, "top_k": top_k})
        r.raise_for_status()
        return r.json().get("results") or []

# --- DEBUG/OBSERVABILITY HELPERS ---------------------------------
def _dump_artifact(run_dir: str, name: str, data) -> None:
    """
    Scrive un file di debug dentro il run_dir:
    - se dict/list -> JSON pretty
    - altrimenti -> testo
    """
    try:
        path = os.path.join(run_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(data, (dict, list)):
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(data))
    except Exception:
        pass  # il debug non deve mai rompere la request

def _lang_from_ext(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "react",
        ".js": "javascript",
        ".jsx": "react",
        ".go": "go",
        ".java": "java",
    }.get(ext, "")


def _short_id(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]

def _expected_ext_for_lang(lang: str) -> str:
    l = (lang or "").lower()
    return {
        "python": ".py",
        "py": ".py",
        "typescript": ".ts",
        "ts": ".ts",
        "javascript": ".js",
        "js": ".js",
        "tsx": ".tsx",
        "jsx": ".jsx",
        "go": ".go",
        "java": ".java",
    }.get(l, ".txt")


def _fix_names_and_ext(
    files_planned: list[dict],
    extracted_files: list[dict],
    code_root_rel: str,
) -> list[dict]:
    """
    Forza estensioni corrette in base alla language del *singolo* file.
    Se il modello aveva già dato un path con estensione (es. main.go),
    proviamo a riusarne il basename per rendere il risultato più naturale.
    """
    # mappa lang -> primo basename “buono” arrivato dal modello
    by_lang_basename: dict[str, str] = {}
    for ef in (extracted_files or []):
        if not isinstance(ef, dict):
            continue
        lang = (ef.get("language") or "").lower()
        # se la language non c'è, prova inferenza dall’estensione originale
        if not lang:
            lang = _lang_from_ext(ef.get("path") or "")
        base = os.path.basename(ef.get("path") or "")
        if lang and base and os.path.splitext(base)[1]:
            by_lang_basename.setdefault(lang, base)

    out: list[dict] = []
    for f in files_planned:
        d = dict(f)
        lang = (d.get("language") or "").lower()
        expected_ext = _expected_ext_for_lang(lang)
        # basename attuale (potrebbe essere “generated.txt”)
        cur_base = os.path.basename(d.get("path") or "")
        base_noext, cur_ext = os.path.splitext(cur_base)

        # se estensione non combacia, sistemala
        if cur_ext.lower() != expected_ext:
            # preferisci il basename originario del modello per quella lang
            prefer = by_lang_basename.get(lang)
            if prefer and os.path.splitext(prefer)[1].lower() == expected_ext:
                new_base = prefer
            else:
                # altrimenti riusa il nome base, cambiando solo l’estensione
                new_base = (base_noext or "generated") + expected_ext
            d["path"] = os.path.join(code_root_rel, new_base).replace("\\", "/")

        out.append(d)
    return out

def _infer_lang_from_path(path: str, default_hint: str = "") -> str:
    p = (path or "").lower()
    if p.endswith(".py"): return "python"
    if p.endswith(".ts"): return "typescript"
    if p.endswith(".tsx"): return "tsx"
    if p.endswith(".jsx"): return "jsx"
    if p.endswith(".js"): return "javascript"
    if p.endswith(".go"): return "go"
    if p.endswith(".java"): return "java"
    return (default_hint or "").lower()

def _ensure_language(files: list[dict], default_hint: str = "") -> list[dict]:
    out: list[dict] = []
    for f in files:
        d = dict(f)
        lang = (d.get("language") or "").lower()
        if not lang:
            lang = _infer_lang_from_path(d.get("path") or "", default_hint)
        d["language"] = lang
        out.append(d)
    return out


def _build_generation_roots(generation_id: str) -> tuple[str, str, str, str]:
    """
    Ritorna (code_root_abs, test_root_abs, code_root_rel, test_root_rel)
    Esempio: ( .../src/generated_ab12cd34, .../tests/generated_ab12cd34, 'src/generated_ab12cd34', 'tests/generated_ab12cd34')
    """
    code_root_rel = os.path.join(settings.CODE_ROOT_BASE, f"{settings.GEN_ID_PREFIX}_{generation_id}")
    test_root_rel = os.path.join(settings.TEST_ROOT_BASE, f"{settings.GEN_ID_PREFIX}_{generation_id}")
    code_root_abs = os.path.join(settings.WORKSPACE_ROOT, code_root_rel)
    test_root_abs = os.path.join(settings.WORKSPACE_ROOT, test_root_rel)
    os.makedirs(code_root_abs, exist_ok=True)
    os.makedirs(test_root_abs, exist_ok=True)
    return code_root_abs, test_root_abs, code_root_rel, test_root_rel

_CODE_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9+\-._]*)\s*\n(?P<code>.*?)(?:\r?\n)?```",
    re.DOTALL
)
def _normalize_files_for_write(files: list[dict]) -> list[dict]:
    """
    Assicura che ogni voce abbia 'path' e 'content' corretti.
    - Se 'content' manca ma esiste 'text', usa 'text'.
    - Se 'content' coincide (sospettosamente) con 'path', prova a usare 'text'.
    - Pulisce i path (slash forward).
    """
    norm: list[dict] = []
    for f in files:
        if not isinstance(f, dict):
            # nel caso arrivino oggetti, serializziamo le proprietà principali
            f = {
                "path": getattr(f, "path", ""),
                "content": getattr(f, "content", ""),
                "text": getattr(f, "text", ""),
                "language": getattr(f, "language", "")
            }
        path = (f.get("path") or "").strip()
        content = f.get("content")
        text = f.get("text")

        # se manca 'content' ma c'è 'text', usa text
        if (content is None or content == "") and isinstance(text, str) and text.strip():
            content = text

        # se content è “sospetto” (uguale al path), prova a usare 'text'
        if isinstance(content, str) and path and content.strip() == path:
            if isinstance(text, str) and text.strip():
                content = text

        # fallback estremo: almeno stringa vuota
        if content is None:
            content = ""

        # normalizza slash
        path = path.replace("\\", "/")
        norm.append({"path": path, "content": content, "language": f.get("language", "")})
    return norm


def _default_filename(lang: str, idx: int = 1) -> str:
    lang = (lang or "").lower()
    if lang in ("py", "python"): ext = ".py"
    elif lang in ("ts", "typescript"): ext = ".ts"
    elif lang in ("js", "javascript"): ext = ".js"
    elif lang == "go": ext = ".go"
    elif lang == "java": ext = ".java"
    else: ext = ".txt"
    return f"module_{idx}{ext}"

_GEN_LIST_RE = re.compile(r"(?mi)^Generated files:\s*(?:\r?\n)+(?P<body>(?:^\s*-\s+.*\r?\n?)+)")
def _extract_paths_from_generated_list(raw: str) -> list[str]:
    m = _GEN_LIST_RE.search(raw or "")
    if not m:
        return []
    body = m.group("body") or ""
    paths = []
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln.startswith("-"):
            continue
        p = ln.lstrip("-").strip()
        if p:
            paths.append(p)
    return paths

def _stub_for(lang: str, base: str) -> str:
    l = (lang or "").lower()
    if l in ("py","python"):
        return f"def {base or 'func'}():\n    pass\n"
    if l == "go":
        return f"package main\n\nfunc {base or 'Func'}() {{}}\n"
    if l == "java":
        cls = (base or "Class").capitalize()
        return f"public class {cls} {{ }}\n"
    if l in ("ts","typescript","js","javascript"):
        return f"export function {base or 'fn'}() {{}}\n"
    if l in ("tsx","jsx","react"):
        return f"export default function {base or 'Component'}() {{ return null; }}\n"
    # mendix o altro:
    return ""

def _extract_files_from_fences(raw: str) -> list[dict]:
    files: list[dict] = []
    for i, m in enumerate(_CODE_FENCE_RE.finditer(raw), start=1):
        lang = (m.group("lang") or "").strip().lower()
        code = m.group("code") or ""
        fname = _default_filename(lang, i)
        files.append({"path": fname, "content": code, "language": lang})
    return files
def _fallback_single_file_from_text(raw: str, lang_hint: str) -> list[dict]:
    """
    Ultimo fallback: crea 1 file dal testo grezzo.
    Prova a ripulire un minimo (togli blocchi di quote Markdown).
    """
    text = raw.strip()
    # Rimuovi eventuali backticks sparsi (non ben formati)
    text = re.sub(r"^```.*?$", "", text, flags=re.M)
    text = re.sub(r"```$", "", text)
    # Heuristica semplice: se troviamo una riga che sembra codice Python, Java, Go, JS/TS, bene;
    # altrimenti prendiamo tutto.
    lines = text.splitlines()
    # se il modello ha messo JSON "verboso" con prose, prova a estrarre un minimo di codice
    code_lines = []
    for ln in lines:
        if any(kw in ln for kw in ("def ", "class ", "import ", "package ", "func ", "public class", "function ")):
            code_lines = lines  # per ora: prendi tutto
            break
    if not code_lines:
        code_lines = lines
    code = "\n".join(code_lines).strip()
    lang = (lang_hint or "").lower()
    fname = _default_filename(lang, 1)
    return [{"path": fname, "content": code, "language": lang or ""}]


def _relocate_files_under_code_root(files: list[dict], code_root_rel: str) -> list[dict]:
    """
    Forza tutti i file in code_root_rel mantenendo solo il nome base.
    Se un file appare già come path relativo 'src/...' lo normalizziamo al nuovo root.
    """
    out = []
    for f in files:
        # prendi solo il basename per evitare path arbitrari
        base = os.path.basename(f.get("path") or _default_filename(f.get("language",""), 1))
        out.append({
            "path": os.path.join(code_root_rel, base).replace("\\", "/"),
            "content": f.get("content", ""),
            "language": f.get("language")
        })
    return out

def _minimal_test_stub(lang: str, code_filename: str, code_content: str = "") -> Tuple[str, str]:
    """
    Ritorna (test_filename, content) minimo per la lingua, oppure ('','') se non supportata.

    - Python: prova a individuare funzioni; se ne trova una invocabile senza argomenti,
      la chiama davvero. Altrimenti smoke-test sul modulo.
    - Go/Java: stub minimale (smoke) con nome coerente con il file sorgente.
      (Nota: il posizionamento 'tests/...' è volontario per coerenza con gli altri linguaggi;
       non è un setup Go/JAVA eseguibile out-of-the-box, ma fornisce scaffolding immediato.)
    """
    l = (lang or "").lower()
    base = os.path.splitext(os.path.basename(code_filename))[0]
    src_dir = os.path.dirname(code_filename).replace("\\", "/")

    if l in ("py", "python"):
        import re as _re
        func_matches = _re.findall(r"(?m)^\s*def\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:", code_content or "")
        functions: list[tuple[str, str]] = []
        for name, params in func_matches:
            functions.append((name.strip(), (params or "").strip()))

        zero_arg_fn: str | None = None
        for fn_name, params in functions:
            p = params.replace(" ", "")
            if p == "" or p == "self":
                zero_arg_fn = fn_name
                break

        if zero_arg_fn:
            test_code = f'''import os, importlib.util

THIS_DIR = os.path.dirname(__file__)
MODULE_PATH = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "{src_dir}", "{base}.py"))

spec = importlib.util.spec_from_file_location("{base}", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_{zero_arg_fn}_callable():
    assert hasattr(mod, "{zero_arg_fn}")
    _ = getattr(mod, "{zero_arg_fn}")()
'''
        else:
            if functions:
                fn0 = functions[0][0]
                test_code = f'''import os, importlib.util

THIS_DIR = os.path.dirname(__file__)
MODULE_PATH = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "{src_dir}", "{base}.py"))

spec = importlib.util.spec_from_file_location("{base}", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_has_{fn0}():
    assert hasattr(mod, "{fn0}")
'''
            else:
                test_code = f'''import os, importlib.util

THIS_DIR = os.path.dirname(__file__)
MODULE_PATH = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "{src_dir}", "{base}.py"))

spec = importlib.util.spec_from_file_location("{base}", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_module_imports():
    assert True
'''
        return (f"test_{base}.py", test_code)

    if l == "go":
        # Stub minimale (non eseguibile out-of-the-box), ma chiaro per l’utente
        test_code = f'''// Package: test scaffold for {base}.go
// TODO: spostare questo test accanto a {base}.go e convertirlo in un vero *_test.go
package main

import "testing"

func TestSmoke_{base}(t *testing.T) {{
    // TODO: chiamare funzioni esposte in {base}.go
    if false {{
        t.Fatal("replace with real assertions")
    }}
}}
'''
        return (f"test_{base}.go", test_code)

    if l == "java":
        # JUnit5 stub (package non definito: volutamente generico)
        class_name = f"{base.capitalize()}Test"
        test_code = f'''import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class {class_name} {{

    @Test
    void smoke() {{
        assertTrue(true);
    }}
}}
'''
        return (f"{class_name}.java", test_code)

    return ("", "")


def _runs_root() -> str:
    return getattr(settings, "RUNS_DIR", os.path.join(os.getcwd(), "runs"))

def _new_run_dir(prefix: str = "run") -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    aid = uuid.uuid4().hex[:8]
    root = _runs_root()
    os.makedirs(root, exist_ok=True)
    d = os.path.join(root, f"{ts}_{prefix}_{aid}")
    os.makedirs(d, exist_ok=True)
    log.info("Create run dir: %s", d)
    return d
from typing import Any, Dict, List, Optional

def _mode_from_name(mid: str) -> str:
    """Heuristic: classify model id/name as 'embed' or 'chat'."""
    if not mid:
        return "chat"
    low = mid.lower()
    if "embed" in low or "embedding" in low or "nomic-embed" in low:
        return "embed"
    return "chat"

def _normalize_models(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize gateway responses into:
    [{"name": str, "modality": "chat"|"embed", "enabled": bool, ...}]
    Supports:
      - CLike-style: {"models":[{...}]}
      - OpenAI-style: {"data":[{"id": "..."}]}
    """
    # Case 1: CLike-style
    if isinstance(payload.get("models"), list):
        out = []
        for m in payload["models"]:
            name = m.get("name") or m.get("id") or m.get("model")
            if not name:
                continue
            mm = dict(m)  # copy
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
    """
    If modality is 'chat' or 'embed', filter accordingly.
    If None, return as-is.
    """
    if modality in ("chat", "embed"):
        return [m for m in models if (m.get("modality") or "chat") == modality]
    return models

def _first_by_modality(models: List[Dict[str, Any]], modality: str) -> Optional[str]:
    for m in models:
        if (m.get("modality") or "chat") == modality:
            return m.get("name")
    return None

async def _load_models_or_fallback() -> List[Dict[str, Any]]:
    # try gateway
    try:
        payload = await _gateway_get("/v1/models")
        models = _normalize_models(payload)
        if models:
            return models
    except Exception:
        pass
    # fallback YAML
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

async def _gateway_get(path: str) -> Dict[str, Any]:
    base = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
    url = f"{base}{path}"
    timeout = float(getattr(settings, "REQUEST_TIMEOUT_S", 60))
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

from fastapi import Query

@router.get("/models")
async def list_models(
    modality: Optional[str] = Query(default="chat", regex="^(chat|embed|all)$")
):
    """
    Returns {"version":"1.0","models":[...]}
    Default modality='chat' (so UI won't show embedding-only models).
    Use modality=embed to list embed models, or modality=all to return all.
    """
    try:
        models = await _load_models_or_fallback()
        if modality != "all":
            models = _filter_by_modality(models, modality)
        return {"version": "1.0", "models": models}
    except Exception as ex:
        raise HTTPException(502, f"cannot load models: {type(ex).__name__}: {ex}")

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
    

    # Attachments → inline vs rag + arricchimento messaggi
    attachments = body.get("attachments") or []
    inline_files, rag_files = await _decide_inline_or_rag(attachments)

    # l’ultimo user message come query
    user_query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_query = (m.get("content") or "").strip()
            break
    sysmsg = {"role":"system","content":"You are CLike, a helpful an expert software engineering developer fullstack copilot."}

    msgs = [sysmsg] + list(messages)
    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query)

    run_dir = _new_run_dir("chat")
    with open(os.path.join(run_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    # validate model modality
    all_models = await _load_models_or_fallback()
    requested = model
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==requested)), None)

    # A) STRICT: errore se l’utente seleziona un embed
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{requested}' is an embedding model and cannot be used for chat. Pick a chat model.")

    # B) (OPZIONALE) AUTO-CORRECT:
    # if requested_modality == "embed":
    #     fallback = _first_by_modality(all_models, "chat")
    #     if not fallback:
    #         raise HTTPException(400, "no chat-capable models available")
    #     model = fallback
    #RAG 
    rag_paths = (body.get("rag_paths") or []) + (body.get("rag_files") or [])
    rag_inline = body.get("rag_inline") or []
    rag_blobs  = []
    if rag_paths:
        rag_blobs.extend(_gather_rag_context(rag_paths))
    if rag_inline:
        rag_blobs.extend([str(x) for x in rag_inline if x])

    if rag_blobs:
        # Iniettiamo 1 msg di contesto “consolidato” per non esplodere i tokens
        ctx = "\n\n".join(rag_blobs[:8])
        msgs = [{"role": "system", "content": "Use the following context if relevant:\n" + ctx}] + msgs

    try:
        # usa i messaggi arricchiti (sys + inline + RAG)
        text = await llm_client.call_gateway_chat(
            model, msgs,  # <— messaggi arricchiti (system + RAG + inline files)
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.2),
            max_tokens=body.get("max_tokens", 512),
        )

        # dump del provider text (sintetico) e, se serve, raw
        try:
            _dump_artifact(run_dir, "gateway_text.txt", text)
        except Exception:
            pass
      
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    with open(os.path.join(run_dir, "response.json"), "w", encoding="utf-8") as f:
        json.dump({"text": text}, f, ensure_ascii=False, indent=2)

    return {
        "version": "1.0",
        "text": text,
        "usage": {},
        "sources": [],
        "audit_id": os.path.basename(run_dir),
        "run_dir": run_dir
    }

def _extract_json(s: str) -> Dict[str, Any]:
    # 1) blocco ```json ... ```
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", s, re.M)
    if m:
        return json.loads(m.group(1))
    # 2) qualsiasi blocco ``` ... ``` che contenga un oggetto json
    m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", s, re.M)
    if m:
        return json.loads(m.group(1))
    # 3) fallback: primo oggetto { ... } nella risposta
    i = s.find("{"); j = s.rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(s[i:j+1])
    raise ValueError("no valid JSON found")

def _system_for_generate(mode: str) -> str:
    base = "You are CLike, an super expert software and product-engineering copilot with skills in java, go ,python, node, react,c#, next.js, typesccript, javascript and mendix. You have skills in CLoud on AWS, Azure e GPC, you have expirience in DevOps and DevSecOps, you have expirience in on-premise enterprse solution and Cloud NAtive Solution and All PaaS provided By any Cloud Provider and Confluent/ kafka, Redhat Stack Sotware ,microservices, OPC and servelss solution. Output strictly JSON, no prose."
    if mode == "harper":
        return base + ' Return: {"files":[{"path":"...","content":"..."}], "notes":[]}'
    return base + ' Return: {"files":[{"path":"...","content":"..."}]}'

def _harvest_data_urls_to_files(text: str, gen_id: str) -> list[dict]:
    files = []
    for i, m in enumerate(DATA_URL_RE.finditer(text)):
        mime = m.group(1)     # es: image/png
        b64  = m.group(2)
        ext  = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            # fallback
        }.get(mime, ".bin")
        path = f"images/generated_{gen_id}/asset_{i}{ext}"

        files.append({"path": path, "content_base64": b64, "mime": mime})
    return files

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

    # --- generation id + root dinamico ---
    gen_id = _short_id(8)
    # riuso del tuo helper esistente: ci serve solo il code_root_rel
    code_root_abs, test_root_abs, code_root_rel, _test_root_rel_unused = _build_generation_roots(gen_id)
    # ma creiamo noi le sottocartelle src/doc
    os.makedirs(os.path.join(code_root_abs, "src"), exist_ok=True)
    os.makedirs(os.path.join(code_root_abs, "doc"), exist_ok=True)
    os.makedirs(os.path.join(code_root_abs, "images"), exist_ok=True)

    # Preparazione prompt (inchiodiamo lo schema d'uscita)
    sys_schema = {
        "role": "system",
        "content": (
            "You are CLike code generator with skills on all code languages and cloud cpabilities. you are an expert software architect ALWAYS answer ONLY as valid JSON with this schema:\n"
            "{\n"
            '  "files": [ { "path": "<relative/path/with/extension>", "content": "<full file content>" } ],\n'
            '  "messages": [ { "role": "assistant", "content": "<optional explanation>" } ]\n'
            "}\n"
            "Do not wrap JSON in code fences. Do not include 'Generated files:' lists.\n"
            "If user asks multiple languages, include multiple entries in files[].\n"
        )
    }
   # sysmsg = {"role": "system", "content": _system_for_generate(mode)} if ' _system_for_generate' in globals() else sys_schema

    # Attachments → inline vs rag + context (se presenti nel body)
    attachments = body.get("attachments") or []
    inline_files, rag_files = await _decide_inline_or_rag(attachments)
    # l’ultimo messaggio user per query RAG
    user_query = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_query = (m.get("content") or "").strip()
            break
    msgs = [sys_schema] + list(messages)
    msgs = await _augment_messages_with_context(msgs, inline_files, rag_files, user_query)

    run_dir = _new_run_dir("gen")
    with open(os.path.join(run_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    # validate modello: niente embedding
    all_models = await _load_models_or_fallback()
    requested = model
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==requested)), None)
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{requested}' is an embedding model and cannot be used for code generation. Pick a chat model.")
    
    #RAG 
    rag_paths = (body.get("rag_paths") or []) + (body.get("rag_files") or [])
    rag_inline = body.get("rag_inline") or []
    rag_blobs  = []
    if rag_paths:
        rag_blobs.extend(_gather_rag_context(rag_paths))
    if rag_inline:
        rag_blobs.extend([str(x) for x in rag_inline if x])

    if rag_blobs:
        # Iniettiamo 1 msg di contesto “consolidato” per non esplodere i tokens
        ctx = "\n\n".join(rag_blobs[:8])
        msgs = [{"role": "system", "content": "Use the following context if relevant:\n" + ctx}] + msgs

    # Chiamata gateway
    try:
        raw = await llm_client.call_gateway_chat(
            model, msgs,
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.1),
            max_tokens=body.get("max_tokens", 1024),
        )
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    with open(os.path.join(run_dir, "raw_model.txt"), "w", encoding="utf-8") as f:
        f.write(raw)
    
     # --- nuovo blocco di normalizzazione spiegazione ---
    assistant_text = ""
    # 1) Se il JSON del modello ha già messaggi testuali compatibili
    if isinstance(body, dict):
        # preferenze comuni nei vari modelli
        if isinstance(body.get("messages"), list):
            assistant_msgs = [m.get("content","") for m in body["messages"] if m.get("role") in ("assistant","system")]
            assistant_text = "\n\n".join([t for t in assistant_msgs if t]).strip()
        elif isinstance(body.get("text"), str):
            assistant_text = body["text"].strip()
        elif isinstance(body.get("explanation"), str):
            assistant_text = body["explanation"].strip()

    # 2) Fallback: se ancora vuoto, prendi dal raw una porzione non-code-fence
    if not assistant_text:
        assistant_text = _strip_markdown_and_noise(raw)[:2000].strip()  # funzione semplice: togli ```...```, “Generated files:” ripetuti, ecc.

    # Salva anche su file per auditing
    try:
        with open(os.path.join(run_dir, "explanation.txt"), "w", encoding="utf-8") as f:
            f.write(assistant_text or "")
    except Exception:
        pass

    # --- Impone schema files/messages (niente scaffolding) ---
    files, messages_out = _coerce_to_schema(raw, (body.get("language") or ""))
    extra_imgs = _harvest_data_urls_to_files(raw, gen_id)
    if extra_imgs:
        files.extend(extra_imgs)

    # Fallback robusti: fences → file; altrimenti doc pulito (solo se c'è testo vero)
    if not files:
        files = _extract_files_from_fences(raw)
    if not files:
        cleaned = _strip_markdown_and_noise(raw)
        if cleaned:
            base_dir = f"src/generated_{gen_id[:8]}/doc"
            files = [{
                "path": f"{base_dir}/module_1.txt",
                "content": cleaned
            }]

    if not files:
        raise HTTPException(422, "model did not produce 'files' with path+content")


    # Bucketizza in src/ o doc/ dentro generated_<id>
    files_planned: list[dict] = []
    for fobj in files:
        path = (fobj.get("path") or "").strip() or "generated.txt"
        content = fobj.get("content") or ""
        lang = (fobj.get("language") or "").lower()
        new_path = _bucketize_path(code_root_rel, path)
        files_planned.append({"path": new_path, "content": content, "language": lang})

    # Calcolo diffs (non scriviamo su disco: Apply lo farà dalla UI)
    diffs: List[Dict[str, Any]] = []
    for fobj in files_planned:
        path = fobj["path"]
        content = fobj.get("content", "")
        prev = su.read_file(path) or ""
        patch = su.to_diff(prev, content, path)
        diffs.append({"path": path, "diff": patch})

    # Risposta
    resp = {
        "version": "1.0",
        "files": files_planned,
        "diffs": diffs,
        "messages": messages_out or [{"role": "assistant", "content": "Generated files ready."}],
        "eval_report": {"status": "skipped"},
        "audit_id": os.path.basename(run_dir),
        "run_dir": run_dir,
        "assistant_text": assistant_text,   # <--- NUOVO
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ"),
    }
    with open(os.path.join(run_dir, "response.json"), "w", encoding="utf-8") as f:
        json.dump(resp, f, ensure_ascii=False, indent=2)
        # Salva un files.json che /apply si aspetta
    try:
        with open(os.path.join(run_dir, "files.json"), "w", encoding="utf-8") as ff:
            json.dump(files_planned, ff, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return resp

def _strip_markdown_and_noise(text: str) -> str:
    """
    Pulisce una stringa di testo rimuovendo:
    1. Blocchi di codice Markdown (delimitati da ```).
    2. Ripetizioni della frase "Generated files:".
    
    Il risultato viene poi troncato a 2000 caratteri e gli spazi
    iniziali e finali vengono rimossi.

    Args:
        text: La stringa di testo da pulire.

    Returns:
        La stringa pulita, troncata e senza spazi extra.
    """
    
    # Rimuove tutti i blocchi di codice delimitati da ```...```.
    # L'opzione re.DOTALL permette di far corrispondere i caratteri newline.
    stripped_text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # Rimuove tutte le occorrenze della frase "Generated files:", ignorando il case.
    stripped_text = re.sub(r'Generated files:', '', stripped_text, flags=re.IGNORECASE)
    
    # Tronca la stringa ai primi 2000 caratteri.
    assistant_text = stripped_text[:2000]
    
    # Rimuove gli spazi iniziali e finali.
    return assistant_text.strip()
import base64, os

def _write_file_any(path: str, fobj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if "content_base64" in fobj:
        data = base64.b64decode(fobj["content_base64"])
        with open(path, "wb") as wf:
            wf.write(data)
    else:
        # default: testo
        content = fobj.get("content", "")
        with open(path, "w", encoding="utf-8") as wf:
            wf.write(content)

@router.post("/apply")
async def apply(req: Request):
    body = await req.json()
    run_dir = body.get("run_dir")
    selection = body.get("selection") or {}
    if not run_dir or not os.path.isdir(run_dir):
        raise HTTPException(400, "run_dir is required and must exist")

    files_path = os.path.join(run_dir, "files.json")
    if not os.path.isfile(files_path):
        raise HTTPException(400, "files.json not found in run_dir")

    try:
        with open(files_path, "r", encoding="utf-8") as f:
            files = json.load(f)
    except Exception as e:
        raise HTTPException(400, f"invalid files.json: {type(e).__name__}: {e}")

    # Filtra selezione (se presente)
    paths_selected: set[str] = set()
    if isinstance(selection, dict):
        if selection.get("apply_all"):
            paths_selected = set(f.get("path", "") for f in files if isinstance(f, dict))
        else:
            for p in selection.get("paths", []):
                if isinstance(p, str) and p.strip():
                    paths_selected.add(p.strip())

    applied: list[str] = []
    failures: list[dict] = []

    # Audit di ciò che stiamo per scrivere
    audit_apply = []

    for fobj in files:
        if not isinstance(fobj, dict):
            # sanity: ignora record non dict
            continue
        path = (fobj.get("path") or "").strip()
        content = fobj.get("content")
        if not path:
            continue
        # Se è stata fornita una selezione, rispettiamola
        if paths_selected and path not in paths_selected:
            continue

        # Usa sempre il content del record corrente (niente variabili condivise globali)
        if content is None:
            content = fobj.get("text", "") or ""

        # Scrittura sul filesystem
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # _write_file_any scrive lui sul FS (non è un context manager)
            _write_file_any(path, fobj)
            applied.append(path)

            audit_apply.append({
                "path": path,
                "content_preview": (content[:120] if isinstance(content, str) else str(type(content)))
            })

        except Exception as e:
            failures.append({"path": path, "error": f"{type(e).__name__}: {e}"})

    # Salva audit per debug rapido
    try:
        with open(os.path.join(run_dir, "apply_debug.json"), "w", encoding="utf-8") as fa:
            json.dump({"applied": audit_apply, "failures": failures}, fa, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if failures:
        # Rientro 207 Multi-Status: gestito via detail, ma usiamo 200 con payload per semplicità
        return {"applied": applied, "failures": failures, "run_dir": run_dir}

    return {"applied": applied, "run_dir": run_dir}