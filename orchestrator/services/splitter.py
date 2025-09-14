# orchestrator/services/splitter.py
from __future__ import annotations
import ast
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# TS parsing via tree-sitter
try:
    from tree_sitter import Language, Parser  # type: ignore
    from tree_sitter_languages import get_language  # type: ignore
    _TS_LANG = get_language("typescript")
except Exception:
    _TS_LANG = None
    Parser = None  # type: ignore

@dataclass
class Symbol:
    name: str
    kind: str  # "class" | "function" | "unknown"
    content: str

_snake_re = re.compile(r"(?<!^)(?=[A-Z])")

def _snake_case(name: str) -> str:
    return _snake_re.sub("_", name).lower()

def infer_language(hint_text: Optional[str] = None, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit.lower()
    if not hint_text:
        return None
    t = hint_text.lower()
    if "def " in t or "class " in t and ".py" in t or "pytest" in t:
        return "python"
    if "export class" in t or "export function" in t or ".ts" in t or "typescript" in t:
        return "typescript"
    return None

# -------- Python: AST top-level classes & functions ----------
def split_python_per_symbol(code: str) -> List[Symbol]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Se non parsabile, restituisci blob unico
        return [Symbol(name="generated", kind="unknown", content=code)]
    out: List[Symbol] = []
    lines = code.splitlines()
    def _block(start: int, end: int) -> str:
        return "\n".join(lines[start-1:end])
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, 'end_lineno', node.lineno)
            out.append(Symbol(name=node.name, kind="class", content=_block(node.lineno, end)))
        elif isinstance(node, ast.FunctionDef):
            end = getattr(node, 'end_lineno', node.lineno)
            out.append(Symbol(name=node.name, kind="function", content=_block(node.lineno, end)))
    if not out:
        # Nessun simbolo top-level trovato -> blob unico
        return [Symbol(name="generated", kind="unknown", content=code)]
    return out

# -------- TypeScript: tree-sitter (class/function top-level) ----------
def split_ts_per_symbol(code: str) -> List[Symbol]:
    if _TS_LANG is None or Parser is None:
        # Senza parser -> blob unico (fallback)
        return [Symbol(name="generated", kind="unknown", content=code)]
    parser = Parser()
    parser.set_language(_TS_LANG)
    tree = parser.parse(bytes(code, "utf8"))
    root = tree.root_node
    out: List[Symbol] = []
    src = code

    def text(node) -> str:
        return src[node.start_byte:node.end_byte]

    for node in root.children:
        # consideriamo top-level: class declaration / function declaration
        if node.type in ("class_declaration", "function_declaration"):
            # name
            name_node = None
            for ch in node.children:
                if ch.type == "identifier":
                    name_node = ch
                    break
            name = text(name_node) if name_node else "generated"
            kind = "class" if node.type == "class_declaration" else "function"
            out.append(Symbol(name=name, kind=kind, content=text(node)))

    if not out:
        return [Symbol(name="generated", kind="unknown", content=code)]
    return out

# -------- Mapping: simbolo -> path in repo ----------
def map_symbol_to_path(sym: Symbol, language: str, settings: Any, hints: Optional[Dict[str, Any]] = None) -> str:
    code_root = getattr(settings, "CODE_ROOT", "src").rstrip("/")

    if language == "python":
        base = _snake_case(sym.name)
        fname = f"{base}.py"
        return f"{code_root}/{fname}"
    if language == "typescript":
        # preserva CamelCase per classi
        ext = ".ts"
        fname = f"{sym.name}{ext}" if sym.kind == "class" else f"{sym.name}{ext}"
        return f"{code_root}/{fname}"
    # default: un unico file testo
    return f"{code_root}/generated.txt"

# -------- Strategia di split ----------
def apply_strategy(symbols: List[Symbol], strategy: str, language: str, settings: Any) -> List[Dict[str, str]]:
    strategy = (strategy or "per_symbol").lower()
    if strategy == "none":
        blob = "\n\n".join(s.content for s in symbols)
        return [{"path": map_symbol_to_path(Symbol("generated", "unknown", blob), language, settings), "content": blob}]
    # "per_symbol" (default) o "per_filehint"
    files: List[Dict[str, str]] = []
    for s in symbols:
        files.append({"path": map_symbol_to_path(s, language, settings), "content": s.content})
    return files
