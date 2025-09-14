# services/docstrings.py
# -----------------------------------------
# Clike – Docstring utilities (embedded + insertion of LLM output)
# Supports: python, java, go, javascript/typescript/react/node, mendix
#
# Public API:
#   - make_docstring(lang, orig, selection, prompt)  -> str  (fallback static)
#   - insert_docstring(lang, orig, selection, doc)   -> str  (apply LLM output)
#
# Notes:
#   * `selection` è opzionale; se presente, ha priorità come target di inserimento.
#   * Le funzioni evitano di duplicare docstring esistenti.
#   * Il codice è intenzionalmente conservativo: non prova refactoring “deep”,
#     ma copre le firme più comuni per ciascun linguaggio.

from __future__ import annotations
import re
from typing import List, Tuple


# ---------------------------
# Helpers generici
# ---------------------------

def _first_match(patterns: List[str], text: str, flags: int = re.M) -> re.Match | None:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None

def _leading_indent(s: str) -> str:
    m = re.match(r"^([ \t]*)", s)
    return m.group(1) if m else ""

def _has_triple_quoted_doc_after(src: str, pos: int) -> bool:
    # controlla se subito dopo c’è una triple-quoted string ("""/'''...)
    after = src[pos: pos + 300]
    return bool(re.match(r'^\s*(?P<q>"""|\'\'\')', after))

def _has_block_comment_before(src: str, start: int) -> bool:
    # controlla se immediatamente sopra c’è già un blocco commento /** ... */
    prev = src[max(0, start - 300): start]
    return "/**" in prev and "*/" in prev

def _insert_at_line_start(src: str, line_start_idx: int, to_insert: str) -> str:
    return src[:line_start_idx] + to_insert + src[line_start_idx:]

def _line_start_after_index(src: str, idx: int) -> int:
    if idx < 0:
        return 0
    nl = src.find("\n", idx)
    return (nl + 1) if nl != -1 else len(src)

def _normalize_newline(s: str) -> str:
    return s if s.endswith("\n") else s + "\n"


# ---------------------------
# PYTHON
# ---------------------------

_PY_DEF_PATTERNS = [
    r"^\s*def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*:\s*(?:#.*)?$",
    r"^\s*class\s+([A-Za-z_]\w*)\s*(\([^)]*\))?\s*:\s*(?:#.*)?$",
]

def _py_parse_params(param_str: str) -> List[str]:
    if not param_str.strip():
        return []
    # split “cheap & cheerful”; non gestiamo tutti i casi estremi, ma copre i più comuni
    parts = [p.strip() for p in param_str.split(",")]
    # rimuovi “self” / “cls”
    clean = []
    for p in parts:
        name = p.split(":")[0].split("=")[0].strip()
        if name in ("self", "cls", ""):
            continue
        clean.append(name)
    return clean

def _py_make_docstring_for(signature: str, name: str, params: List[str], is_class: bool, prompt: str) -> str:
    desc = prompt.strip() or (f"{'Class' if is_class else 'Function'} `{name}`: describe what it does.")
    lines = [desc]
    if params:
        lines.append("")
        lines.append("Args:")
        for p in params:
            lines.append(f"    {p}: ...")
    if not is_class:
        lines.append("")
        lines.append("Returns:")
        lines.append("    ...")
    body = "\n".join(lines)
    return f'"""{body}\n"""'

def _py_insert_docstring(orig: str, selection: str, prompt: str) -> str:
    # target: function o class; se selection non matcha, cerca nel file
    src = orig
    m = _first_match(_PY_DEF_PATTERNS, selection or src)
    if not m:
        # docstring di modulo, se assente
        if re.match(r'^\s*(?P<q>"""|\'\'\')', src):
            return src  # già presente docstring di modulo
        module_ds = f'"""{prompt.strip() or "Module description."}"""\n\n'
        return module_ds + src

    # capisci se è def o class dall’espressione che ha fatto match
    text = selection or src
    matched = m.group(0)
    is_class = matched.lstrip().startswith("class")
    name = m.group(1)
    params = []
    if not is_class and len(m.groups()) >= 2:
        params = _py_parse_params(m.group(2) or "")

    # posizione in src (non in selection)
    anchor = re.search(re.escape(matched), src, re.M)
    if not anchor:
        return src  # fallback: non dovremmo arrivare qui

    # riga successiva alla firma
    insert_at = _line_start_after_index(src, anchor.start())
    # evita doppio docstring
    if _has_triple_quoted_doc_after(src, insert_at):
        return src

    # deduci indent dal corpo
    after_line = src[insert_at: insert_at + 200]
    indent = _leading_indent(after_line) or "    "
    ds = _py_make_docstring_for(matched, name, params, is_class, prompt)
    # indenta docstring rispetto al blocco
    indented_ds = indent + ds.replace("\n", "\n" + indent) + "\n"
    return _insert_at_line_start(src, insert_at, indented_ds)

def _py_make_docstring(orig: str, selection: str, prompt: str) -> str:
    return _py_insert_docstring(orig, selection, prompt)


# ---------------------------
# JAVASCRIPT / TYPESCRIPT / REACT / NODE
# ---------------------------

_TS_FUNC_PATTERNS = [
    r"^\s*(export\s+)?(async\s+)?function\s+([A-Za-z_]\w*)\s*\(([^)]*)\)",
    r"^\s*(export\s+)?const\s+([A-Za-z_]\w*)\s*=\s*(async\s*)?\(([^)]*)\)\s*=>",
]

def _js_params_list(param_str: str) -> List[str]:
    if not param_str.strip():
        return []
    parts = [p.strip() for p in param_str.split(",")]
    names = []
    for p in parts:
        name = p.split(":")[0].split("=")[0].strip()
        if name:
            names.append(name)
    return names

def _js_make_jsdoc(name: str, params: List[str], prompt: str) -> str:
    desc = prompt.strip() or f"{name}: describe what it does."
    lines = ["/**", f" * {desc}"]
    for p in params:
        lines.append(f" * @param {p} ...")
    lines.append(" * @returns ...")
    lines.append(" */")
    return "\n".join(lines)

def _ts_insert_jsdoc(orig: str, selection: str, prompt: str) -> str:
    src = orig
    m = _first_match(_TS_FUNC_PATTERNS, selection or src)
    if not m:
        # Doc di modulo (in cima)
        jsdoc = _js_make_jsdoc("module", [], prompt)
        return jsdoc + "\n" + src

    # normalizza gruppi per due pattern diversi
    if "function" in m.re.pattern:
        name = m.group(3)
        params = _js_params_list(m.group(4) or "")
    else:
        name = m.group(2)
        params = _js_params_list(m.group(4) or "")

    # posizione in src
    anchor = re.search(re.escape(m.group(0)), src, re.M)
    if not anchor:
        return src

    # evita duplicati (/** ... */ immediatamente sopra)
    start = anchor.start()
    prev_block = src[max(0, start - 300): start]
    if "/**" in prev_block and "*/" in prev_block:
        return src

    jsdoc = _js_make_jsdoc(name, params, prompt)
    return src[:start] + jsdoc + "\n" + src[start:]

def _ts_make_docstring(orig: str, selection: str, prompt: str) -> str:
    return _ts_insert_jsdoc(orig, selection, prompt)


# ---------------------------
# JAVA
# ---------------------------

_JAVA_ANCHORS = [
    r"^\s*(public|protected|private)?\s*(static\s+)?(final\s+)?class\s+([A-Za-z_]\w*)\b",
    r"^\s*(public|protected|private)?\s*(static\s+)?[A-Za-z_<>\[\]]+\s+[A-Za-z_]\w*\s*\([^)]*\)\s*\{?",
]

def _java_make_javadoc(name: str | None, prompt: str) -> str:
    desc = prompt.strip() or (f"{name}: describe what it does." if name else "Autogenerated Javadoc.")
    lines = ["/**", f" * {desc}", " */"]
    return "\n".join(lines)

def _java_insert_javadoc(orig: str, selection: str, prompt: str) -> str:
    src = orig
    m = _first_match(_JAVA_ANCHORS, selection or src)
    if not m:
        # javadoc di file
        return _java_make_javadoc(None, prompt) + "\n" + src

    anchor = re.search(re.escape(m.group(0)), src, re.M)
    if not anchor:
        return src
    start = anchor.start()
    # evita duplicati
    if _has_block_comment_before(src, start):
        return src

    # tenta di estrarre il nome classe/metodo
    name = None
    mm = re.search(r"class\s+([A-Za-z_]\w*)", m.group(0))
    if mm:
        name = mm.group(1)
    else:
        mm = re.search(r"([A-Za-z_]\w*)\s*\(", m.group(0))
        if mm:
            name = mm.group(1)

    jdoc = _java_make_javadoc(name, prompt)
    return src[:start] + jdoc + "\n" + src[start:]

def _java_make_docstring(orig: str, selection: str, prompt: str) -> str:
    return _java_insert_javadoc(orig, selection, prompt)


# ---------------------------
# GO
# ---------------------------

_GO_FUNC_PATTERNS = [
    r'^\s*func\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:[A-Za-z_<>\*\[\]\{\}\(\) ]+)?\s*\{?',
    r'^\s*func\s*\(\s*[^)]*\)\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:[A-Za-z_<>\*\[\]\{\}\(\) ]+)?\s*\{?',
]

def _go_make_comment(name: str | None, prompt: str) -> str:
    desc = prompt.strip() or (f"{name}: describe what it does." if name else "Autogenerated Go doc.")
    return f"// {desc}"

def _go_insert_comment(orig: str, selection: str, prompt: str) -> str:
    src = orig
    m = _first_match(_GO_FUNC_PATTERNS, selection or src)
    if not m:
        # commento file
        return _go_make_comment(None, prompt) + "\n" + src

    anchor = re.search(re.escape(m.group(0)), src, re.M)
    if not anchor:
        return src
    start = anchor.start()

    # evita duplicati: controlla la riga precedente
    prev_nl = src.rfind("\n", 0, start)
    prev_line_start = src.rfind("\n", 0, prev_nl) + 1 if prev_nl != -1 else 0
    prev_line = src[prev_line_start:prev_nl] if prev_nl != -1 else ""
    if prev_line.strip().startswith("//"):
        return src

    name = m.group(1) if m.groups() else None
    comment = _go_make_comment(name, prompt)
    return src[:start] + comment + "\n" + src[start:]

def _go_make_docstring(orig: str, selection: str, prompt: str) -> str:
    return _go_insert_comment(orig, selection, prompt)


# ---------------------------
# MENDIX (placeholder comment)
# ---------------------------

def _mendix_insert_comment(orig: str, selection: str, prompt: str) -> str:
    comment = "// Mendix: " + (prompt.strip() or "autogenerated doc.")
    # metti in cima al file
    return comment + "\n" + orig

def _mendix_make_docstring(orig: str, selection: str, prompt: str) -> str:
    return _mendix_insert_comment(orig, selection, prompt)


# ---------------------------
# API pubbliche
# ---------------------------
import re

def insert_docstring(lang: str, orig: str, selection: str, docstring: str):
    """
    Inserisce in modo conservativo una docstring nel testo `orig`.

    Comportamento:
      - Normalizza/igienizza `docstring` (toglie code fences, "Here is..." ecc.,
        autowrap con triple quotes se mancano).
      - Se `selection` non è vuota:
          * inserisce SOLO la docstring immediatamente sopra la prima occorrenza
            di `selection`, separata da UNA sola newline (niente duplicazioni).
      - Se `selection` è vuota:
          * aggiunge una module-level docstring all’inizio del file,
            senza riga vuota extra tra docstring e primo codice.
      - Se il file inizia già con una module docstring, non duplica.

    Ritorna: (new_content: str, inserted: bool)
    """
    sel = selection or ""
    ds_raw = (docstring or "").strip()
    if not ds_raw:
        return orig, False  # niente da inserire

    # Mantieni stile newline del file
    nl = "\r\n" if ("\r\n" in orig and "\n" not in orig.replace("\r\n", "")) else "\n"

    # --- Helpers ------------------------------------------------------------
    def _strip_code_fences(s: str) -> str:
        # Rimuove blocchi ```...``` e linee "Here is the updated code:" ecc.
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s.strip())
        s = re.sub(r"\s*```$", "", s.strip())
        # Preamboli comuni restituiti dai modelli
        s = re.sub(r"(?i)^here\s+is\s+the\s+updated\s+code\s*:?\s*", "", s.strip())
        s = re.sub(r"(?i)^updated\s+code\s*:?\s*", "", s.strip())
        s = re.sub(r"(?i)^here\s+is\s+the\s+docstring\s*:?\s*", "", s.strip())
        return s.strip()

    def _autowrap_triple_quotes(s: str) -> str:
        s = s.strip()
        if s.startswith(('"""', "'''")) and s.endswith(('"""', "'''")):
            return s
        # Evita triple quotes dentro al body (best effort)
        inner = s.replace('"""', '"').replace("'''", "'")
        return f'"""{inner}"""'

    def _remove_selection_if_leaked(s: str, sel_text: str) -> str:
        if not sel_text or not s:
            return s
        # Se la selezione è finita *dentro* la docstring (AI leakage), eliminala
        return s.replace(sel_text, "").strip()

    # --- Igienizza la docstring generata -----------------------------------
    ds = _strip_code_fences(ds_raw)
    ds = _remove_selection_if_leaked(ds, sel)
    ds = _autowrap_triple_quotes(ds)

    # --- Selezione presente: inserisci sopra alla prima occorrenza ----------
    if sel.strip():
        idx = orig.find(sel)
        if idx != -1:
            before = orig[:idx]
            after = orig[idx:]  # NON consumare la selezione: la lasciamo intatta
            # UNA sola newline tra docstring e selection (niente riga vuota extra)
            block = f"{ds}{nl}{sel}"
            return f"{before}{block}{after[len(sel):]}", True
        # Se non troviamo la selezione, passeremo al module-level fallback

    # --- Module-level docstring ---------------------------------------------
    stripped = orig.lstrip()
    leading = orig[:len(orig) - len(stripped)]  # spazi/righe iniziali

    # Se già inizia con una docstring modulo, non duplicare
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return orig, False

    # Nessuna riga vuota extra: docstring + newline + codice
    block = f"{ds}{nl}"
    return f"{leading}{block}{stripped}", True



def make_docstring(lang: str, text: str, selection: str, prompt: str) -> str:
    """
    Fallback embedded (senza LLM), formattato per linguaggio.
    Ritorna il contenuto del file aggiornato con il doc inserito.
    """
    lang = (lang or "").lower()

    if lang == "python":
        return _py_make_docstring(text, selection, prompt)

    if lang in ("javascript", "typescript", "react", "node"):
        return _ts_make_docstring(text, selection, prompt)

    if lang == "java":
        return _java_make_docstring(text, selection, prompt)

    if lang == "go":
        return _go_make_docstring(text, selection, prompt)

    if lang == "mendix":
        return _mendix_make_docstring(text, selection, prompt)

    # default “neutro”
    desc = prompt.strip() or "Autogenerated documentation."
    comment = "// " + desc
    return comment + "\n" + selection
