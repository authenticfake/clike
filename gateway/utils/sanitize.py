# utils/sanitize.py
import re
from pathlib import Path

# righe che sono fence: ``` , ```lang , ~~~ , ~~~lang (solo backtick/tilde + opz. lingua)
_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)([a-zA-Z0-9._+-]*)\s*$")

# alcune estensioni per cui è sicuro rimuovere fences "sciolti"
_STRIP_EXTS = {
    ".json",".jsonc",".yml",".yaml",
    ".js",".mjs",".cjs",".ts",".tsx",
    ".java",".mjs",".cjs",".ts",".tsx",
    ".py",".sql",".sh",".bash",".env",".ini",".toml",
    ".cfg",".conf",".csv",".html",".css"
    ".pyw",  ".jsx", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",  
    ".jsp", ".jspx", ".cs", ".cshtml", 
    ".php", ".phtml", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".swift", ".m", 
    ".mm", ".go", ".rb", ".rs", ".kt", ".kts", ".sql", ".html", ".css", ".scss", 
    ".less", ".xml", ".json", ".yaml", ".yml", ".ini", ".cfg", ".lua", ".pl", 
    ".pm", ".tcl", ".clj", ".cljs", ".erl", ".ex", ".exs", ".fs", ".fsi", ".r", 
    ".asm", ".s", ".v", ".sv", ".vhd", ".scala", ".groovy", ".pas", ".d", ".dart", 
    ".elm", ".hx", ".nim", ".rkt", ".ml", ".mli", ".tex", ".dll"    
}

def _strip_leading_trailing_fence_lines(txt: str) -> str:
    """Elimina TUTTE le righe fence in testa/coda, ripetutamente."""
    lines = txt.splitlines()
    # leading
    changed = True
    while changed and lines:
        changed = False
        if lines and _FENCE_LINE_RE.match(lines[0]):
            lines.pop(0)
            changed = True
        if lines and _FENCE_LINE_RE.match(lines[0]):
            lines.pop(0)
            changed = True
    # trailing
    changed = True
    while changed and lines:
        changed = False
        if lines and _FENCE_LINE_RE.match(lines[-1]):
            lines.pop()
            changed = True
        if lines and _FENCE_LINE_RE.match(lines[-1]):
            lines.pop()
            changed = True
    return "\n".join(lines).strip("\n\r\t ")

def _strip_orphan_fences_everywhere(txt: str) -> str:
    """
    Rimuove righe che sono SOLO fence in qualunque punto.
    Non tocca il contenuto tra i fence: elimina solo la riga '```xxx' e '```'.
    Utile per output che alterna più blocchi consecutivi.
    """
    out = []
    for ln in txt.splitlines():
        if _FENCE_LINE_RE.match(ln):
            continue
        out.append(ln)
    return "\n".join(out)

def sanitize_for_path(path: str, content: str) -> str:
    """
    Strategia 'loose':
    1) taglia fence in testa/coda (anche ripetuti),
    2) se l'estensione è tra quelle note, elimina anche le righe fence sparse,
    3) normalizza spazi finali.
    """
    ext = Path(path).suffix.lower()
    cur = content.strip("\ufeff \t\r\n")  # anche BOM/whitespace
    before = None

    # togli tutto ciò che è fence in testa/coda, ripeti finché serve
    while cur != before:
        before = cur
        cur = _strip_leading_trailing_fence_lines(cur)

    # per file noti, elimina fence-line "sciolte" ovunque
    if ext in _STRIP_EXTS:
        cur = _strip_orphan_fences_everywhere(cur)
        # di nuovo, ripulisci eventuali scie in coda
        before = None
        while cur != before:
            before = cur
            cur = _strip_leading_trailing_fence_lines(cur)

    return cur.strip("\n\r\t ")
