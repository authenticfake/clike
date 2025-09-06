# services/embedded_ops.py
# ---------------------------------------------------
# Clike – Embedded (no-AI) implementations + optional external tools
#   - deterministic_refactor(lang, orig, selection, prompt) -> str
#   - make_test_stub(lang, path, code) -> (test_content, test_path)
#   - mechanical_fixes(lang, orig) -> str
#   - apply_selection_or_file(orig, selection, replacement) -> str
#
# Supported langs: python, javascript, typescript, react, node, java, go, mendix
# External tools (optional): black, isort, ruff, prettier, eslint, google-java-format, gofmt, goimports
# Toggle via env (default: enabled if present), e.g.:
#   CLIKE_TOOLS_PY_BLACK=true|false
#   CLIKE_TOOLS_PY_ISORT=true|false
#   CLIKE_TOOLS_PY_RUFF=true|false
#   CLIKE_TOOLS_TS_PRETTIER=true|false
#   CLIKE_TOOLS_TS_ESLINT=true|false
#   CLIKE_TOOLS_JAVA_GJF=true|false
#   CLIKE_TOOLS_GO_FMT=true|false
#   CLIKE_TOOLS_GO_IMPORTS=true|false
# ---------------------------------------------------

from __future__ import annotations
import os
import re
import shutil
import tempfile
import subprocess
from typing import Tuple, Optional

# ---------------------------
# Generic helpers
# ---------------------------

def _nl_normalize(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff")
    return s

def _strip_trailing_spaces(s: str) -> str:
    return re.sub(r"[ \t]+(?=\n)", "", s)

def _ensure_trailing_nl(s: str) -> str:
    return s if s.endswith("\n") else s + "\n"

def apply_selection_or_file(orig: str, selection: str, replacement: str) -> str:
    """Replace only selection if it appears once; otherwise replace whole file."""
    if selection:
        occ = orig.count(selection)
        if occ == 1:
            return orig.replace(selection, replacement, 1)
    return replacement

def _extract_basename_no_ext(path: str) -> str:
    base = os.path.basename(path)
    if "." in base:
        return ".".join(base.split(".")[:-1]) or base
    return base

def _bool_env(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")

def _has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _run_cmd(argv, cwd=None, input_str: Optional[str] = None, timeout: int = 60) -> Tuple[int, str, str]:
    p = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE if input_str is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = p.communicate(input=input_str, timeout=timeout)
    return p.returncode, out or "", err or ""

def _run_on_tempfile(content: str, suffix: str, argv_builder, read_path: bool = True) -> Optional[str]:
    """
    Scrive content su temp file, esegue il tool (argv_builder(temp_path) -> argv),
    poi rilegge temp_path (se read_path True) e ritorna il contenuto. Ritorna None se fallisce.
    """
    tmpdir = tempfile.mkdtemp(prefix="clike_")
    try:
        tmp_path = os.path.join(tmpdir, f"file{suffix}")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        argv = argv_builder(tmp_path)
        rc, out, err = _run_cmd(argv, cwd=tmpdir)
        if rc != 0:
            return None
        if read_path:
            with open(tmp_path, "r", encoding="utf-8") as f:
                return f.read()
        return out
    except Exception:
        return None
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

# ---------------------------
# Refactor (deterministic + tools)
# ---------------------------

def _sort_import_blocks_python(src: str) -> str:
    lines = src.split("\n")
    import_idxs = [i for i, ln in enumerate(lines) if re.match(r"^\s*(import\s+\w|from\s+\w)", ln)]
    if not import_idxs:
        return src
    start = min(import_idxs)
    end = start
    while end < len(lines) and re.match(r"^\s*(import|from)\s+", lines[end]):
        end += 1
    block = lines[start:end]
    direct = [l for l in block if re.match(r"^\s*import\s+", l)]
    froms = [l for l in block if re.match(r"^\s*from\s+", l)]
    direct_sorted = sorted(set(direct), key=str.lower)
    froms_sorted  = sorted(set(froms),  key=str.lower)
    new_block = direct_sorted + froms_sorted
    return "\n".join(lines[:start] + new_block + lines[end:])

def _sort_import_blocks_ts_js(src: str) -> str:
    lines = src.split("\n")
    import_lines = []
    i = 0
    while i < len(lines) and (lines[i].strip().startswith(("import ", "//", "/*")) or lines[i].strip() == ""):
        if lines[i].strip().startswith("import "):
            import_lines.append(lines[i])
        i += 1
    if not import_lines:
        return src
    sorted_imports = sorted(set(import_lines), key=str.lower)
    # replace first contiguous import region with sorted
    out, consumed = [], 0
    for ln in lines:
        if consumed < len(import_lines) and ln in import_lines:
            if consumed == 0:
                out.extend(sorted_imports)
            consumed += 1
            continue
        out.append(ln)
    return "\n".join(out)

def _java_add_file_header(src: str, prompt: str) -> str:
    if "/**" in src[:200]:
        return src
    header = "/**\n * " + (prompt.strip() or "Refactor: cleanup imports/whitespace. Keep behavior.") + "\n */\n"
    return header + src

def _maybe_python_tools(src: str) -> str:
    # isort (stdin ok) – preferiamo temp-file per compat massima
    if _bool_env("CLIKE_TOOLS_PY_ISORT", True) and _has_cmd("isort"):
        res = _run_on_tempfile(src, ".py", lambda p: ["isort", p])
        if res is not None:
            src = res

    # black – usa temp-file (scrive in place)
    if _bool_env("CLIKE_TOOLS_PY_BLACK", True) and _has_cmd("black"):
        res = _run_on_tempfile(src, ".py", lambda p: ["black", "-q", p])
        if res is not None:
            # black non restituisce contenuto su stdout; rileggiamo dal path
            src = res

    return src

def _maybe_ts_js_tools(src: str, is_ts: bool) -> str:
    # prettier – stdin ok, ma usiamo temp-file per infer parser da estensione
    if _bool_env("CLIKE_TOOLS_TS_PRETTIER", True) and _has_cmd("prettier"):
        res = _run_on_tempfile(src, ".ts" if is_ts else ".js",
                               lambda p: ["prettier", "--write", p, "--loglevel", "silent"])
        if res is not None:
            src = res

    # eslint --fix – richiede spesso config; usiamo temp-file e --fix
    if _bool_env("CLIKE_TOOLS_TS_ESLINT", False) and _has_cmd("eslint"):
        res = _run_on_tempfile(src, ".ts" if is_ts else ".js",
                               lambda p: ["eslint", "--fix", p])
        if res is not None and res.strip():
            # molti setup eslint non stampano il contenuto; rileggiamo file già fatto da _run_on_tempfile
            src = res
    return src

def _maybe_java_tools(src: str) -> str:
    # google-java-format via jar; richiede 'java'
    if _bool_env("CLIKE_TOOLS_JAVA_GJF", True) and _has_cmd("java"):
        gjf = "/usr/local/bin/google-java-format.jar"
        if os.path.exists(gjf):
            # legge da stdin / scrive su stdout
            rc, out, err = _run_cmd(["java", "-jar", gjf, "--aosp", "-"], input_str=src)
            if rc == 0 and out.strip():
                return out
    return src

def _maybe_go_tools(src: str) -> str:
    # gofmt
    if _bool_env("CLIKE_TOOLS_GO_FMT", True) and _has_cmd("gofmt"):
        rc, out, err = _run_cmd(["gofmt"], input_str=src)
        if rc == 0 and out.strip():
            src = out
    # goimports
    if _bool_env("CLIKE_TOOLS_GO_IMPORTS", True) and _has_cmd("goimports"):
        rc, out, err = _run_cmd(["goimports"], input_str=src)
        if rc == 0 and out.strip():
            src = out
    return src

def deterministic_refactor(lang: str, orig: str, selection: str, prompt: str) -> str:
    """
    Safe, deterministic refactors:
      - normalize EOL, strip trailing spaces, ensure trailing NL
      - sort imports (python, ts/js)
      - optional external tools if present
      - minimal header (java)
    """
    lang = (lang or "").lower()
    src = _ensure_trailing_nl(_strip_trailing_spaces(_nl_normalize(orig)))

    if lang == "python":
        src = _maybe_python_tools(src)
        # fallback import sort (non distruttivo)
        src = _sort_import_blocks_python(src)

    elif lang in ("javascript", "typescript", "react", "node"):
        is_ts = (lang == "typescript")
        src = _maybe_ts_js_tools(src, is_ts=is_ts)
        src = _sort_import_blocks_ts_js(src)

    elif lang == "java":
        src = _maybe_java_tools(src)
        src = _java_add_file_header(src, prompt)

    elif lang == "go":
        src = _maybe_go_tools(src)

    elif lang == "mendix":
        # Mendix: non codificato; lasciamo housekeeping base
        pass

    return src

# ---------------------------
# Tests (stubs)
# ---------------------------

def _guess_primary_symbol_python(code: str) -> str | None:
    m = re.search(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", code, re.M)
    if m: return m.group(1)
    m = re.search(r"^\s*class\s+([A-Za-z_]\w*)\b", code, re.M)
    if m: return m.group(1)
    return None

def _python_test_stub(path: str, code: str) -> Tuple[str, str]:
    base = _extract_basename_no_ext(path)
    sym = _guess_primary_symbol_python(code) or "subject"
    test_path = os.path.join(os.path.dirname(path) or ".", f"test_{base}.py")
    content = f"""import pytest

def test_{sym}_basic():
    # Arrange
    # Act
    # Assert
    assert True
"""
    return content, test_path

def _ts_js_test_stub(path: str, code: str, ts: bool) -> Tuple[str, str]:
    base = _extract_basename_no_ext(path)
    ext = "test.ts" if ts else "test.js"
    test_path = os.path.join(os.path.dirname(path) or ".", f"{base}.{ext}")
    
    
    content = f"""{"// @ts-nocheck" if ts else ""}
import {{ /*target*/ }} from './{base}';

test('basic', () => {{
  expect(1).toBe(1);
}});"""
#     content = f"""{"// @ts-nocheck\n" if ts else ""}import {{ /*target*/ }} from './{base}';

# test('basic', () => {{
#   expect(1).toBe(1);
# }});
# """
    return content, test_path

def _java_test_stub(path: str, code: str) -> Tuple[str, str]:
    m = re.search(r"class\s+([A-Za-z_]\w*)", code)
    cls = m.group(1) if m else "Subject"
    dirn = os.path.dirname(path) or "."
    test_path = os.path.join(dirn, f"{cls}Test.java")
    content = f"""import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class {cls}Test {{
    @Test
    void basic() {{
        assertEquals(1, 1);
    }}
}}
"""
    return content, test_path

def _go_test_stub(path: str, code: str) -> Tuple[str, str]:
    base = _extract_basename_no_ext(path)
    dirn = os.path.dirname(path) or "."
    test_path = os.path.join(dirn, f"{base}_test.go")
    content = f"""package main

import "testing"

func TestBasic(t *testing.T) {{
    if 1 != 1 {{
        t.Fatal("expected 1")
    }}
}}
"""
    return content, test_path

def _mendix_test_stub(path: str, code: str) -> Tuple[str, str]:
    dirn = os.path.dirname(path) or "."
    test_path = os.path.join(dirn, "TESTS_MENDIX.md")
    content = "# Mendix Tests\n\n- [ ] Describe microflow and expected behavior.\n"
    return content, test_path

def make_test_stub(lang: str, path: str, code: str) -> Tuple[str, str]:
    lang = (lang or "").lower()
    code = _nl_normalize(code)

    if lang == "python":
        return _python_test_stub(path, code)
    if lang in ("typescript",):
        return _ts_js_test_stub(path, code, ts=True)
    if lang in ("javascript", "react", "node"):
        return _ts_js_test_stub(path, code, ts=False)
    if lang == "java":
        return _java_test_stub(path, code)
    if lang == "go":
        return _go_test_stub(path, code)
    if lang == "mendix":
        return _mendix_test_stub(path, code)

    dirn = os.path.dirname(path) or "."
    test_path = os.path.join(dirn, "TESTS.md")
    content = "# Tests\n\n- [ ] Add test cases.\n"
    return content, test_path

# ---------------------------
# Fix errors (mechanical + tools)
# ---------------------------

def mechanical_fixes(lang: str, orig: str) -> str:
    """
    Extremely safe, mechanical fixes + optional external tools:
      - normalize EOLs, strip trailing spaces
      - remove ';;'
      - remove trailing commas before )/]/}
      - optional: ruff/eslint/golangci (solo se configurati) → usiamo tmpfile
    """
    lang = (lang or "").lower()
    s = _nl_normalize(orig)
    s = _strip_trailing_spaces(s)

    # Optional external “auto-fix” per linguaggio
    if lang == "python" and _bool_env("CLIKE_TOOLS_PY_RUFF", True) and _has_cmd("ruff"):
        # ruff lavora meglio su file; tmpfile + --fix
        res = _run_on_tempfile(s, ".py", lambda p: ["ruff", "--fix", p])
        if res is not None:
            s = res

    elif lang in ("javascript", "typescript", "react", "node") and _bool_env("CLIKE_TOOLS_TS_ESLINT", False) and _has_cmd("eslint"):
        res = _run_on_tempfile(s, ".ts" if lang == "typescript" else ".js",
                               lambda p: ["eslint", "--fix", p])
        if res is not None:
            s = res

    elif lang == "go" and _bool_env("CLIKE_TOOLS_GO_FMT", True) and _has_cmd("gofmt"):
        rc, out, err = _run_cmd(["gofmt"], input_str=s)
        if rc == 0 and out.strip():
            s = out

    # Fallback neutrali e sicuri
    s = s.replace(";;", ";")
    s = re.sub(r",\s*([\)\]\}])", r"\1", s)
    return _ensure_trailing_nl(s)
