# routes/agent.py
import re
import json
import logging
from typing import Any, Dict, Tuple, List, Optional
from fastapi import APIRouter, Request, HTTPException

from services.utils import read_file, write_file, to_diff, detect_lang
from services.docstrings import (
    make_docstring as _make_docstring,
    insert_docstring as _insert_docstring,
)
from config import settings

from services.embedded_ops import deterministic_refactor, mechanical_fixes, make_test_stub
from services.rationale import rationale
from services.llm_client import call_gateway_chat  # compat gestita sotto

router = APIRouter()
gateway_url = str(settings.GATEWAY_URL)

def _normalize_selection(sel: Any) -> str:
    """Rende sempre 'sel' una stringa utilizzabile per la dedup.
    - tuple/list -> prende il primo pezzo non vuoto, altrimenti concatena
    - dict       -> prova 'text' | 'selection' | 'value'
    - None       -> ''
    - altro      -> str(sel)
    """
    if sel is None:
        return ""
    if isinstance(sel, str):
        return sel
    if isinstance(sel, (list, tuple)):
        # prendi il primo elemento stringa non vuoto, altrimenti concatena i pezzi stringa
        for x in sel:
            if isinstance(x, str) and x.strip():
                return x
        return "".join([x for x in sel if isinstance(x, str)])
    if isinstance(sel, dict):
        for k in ("text", "selection", "value"):
            v = sel.get(k)
            if isinstance(v, str) and v.strip():
                return v
    # fallback
    try:
        return str(sel)
    except Exception:
        return ""

def _ensure_str(x: Any) -> str:
    """Garantisce che x sia una stringa."""
    if isinstance(x, str):
        return x
    # se accidentalmente è una tuple tipo (text, flag), prendi il primo pezzo stringa
    if isinstance(x, (list, tuple)):
        for p in x:
            if isinstance(p, str):
                return p
        return "".join([str(p) for p in x])
    if x is None:
        return ""
    return str(x)

def _dedupe_selection_in_text(text: str, selection: str) -> str:
    """Rimuove dai contenuti finali una eventuale ripetizione *aggiuntiva* del blocco selezionato.
    Non tocca la prima occorrenza (quella “giusta”), ma toglie eventuali duplicati introdotti
    dal processo di inserimento docstring/refactor.
    """
    text = _ensure_str(text)
    selection = _normalize_selection(selection)

    # niente selezione -> niente dedup
    if not selection or len(selection.strip()) < 4:
        return text

    # se la selezione non appare almeno 2 volte, non c'è duplicazione da rimuovere
    matches = list(re.finditer(re.escape(selection), text))
    if len(matches) <= 1:
        return text

    # Mantieni la prima, rimuovi le successive
    first = matches[0]
    start_keep, end_keep = first.start(), first.end()

    before = text[:start_keep]
    keep = text[start_keep:end_keep]
    after = text[end_keep:]

    # ripulisci duplicazioni della selezione nell'after
    after = re.sub(re.escape(selection), "", after)

    return before + keep + after


_DOCSTRING_START_RE = re.compile(r'^\s*(?P<q>"""|\'\'\')', re.DOTALL)
_DOCSTRING_FULL_RE = re.compile(r'^\s*(?P<q>"""|\'\'\')(?P<body>[\s\S]*?)(?P=q)', re.DOTALL)

def _squeeze_blank_lines(s: str) -> str:
    """Riduce sequenze di >2 righe vuote a massimo 2, e rimuove spazi inutili in testa/coda."""
    # massimo 2 newline consecutivi
    s = re.sub(r'\n{3,}', '\n\n', s)
    # rimuovi spazi in testa/coda del file
    return s.strip() + "\n"

def _normalize_module_doc_spacing(lang: str, s: str) -> str:
    """
    Se il file inizia con una docstring di modulo (Python), forza ESATTAMENTE
    una riga vuota tra la docstring e il primo statement.
    """
    if not lang.startswith("py"):
        return s

    m = _DOCSTRING_FULL_RE.match(s)
    if not m:
        return s

    q = m.group('q')
    body = m.group('body').strip()
    doc = f'{q}{body}{q}'

    rest = s[m.end():]
    # rimuovi righe vuote iniziali nel resto
    rest = re.sub(r'^\s*\n', '', rest, count=1)
    # forza esattamente 1 newline tra docstring e codice
    return (doc + "\n\n" + rest.lstrip())


# ---------------------------
# util: logging & body parsing
# ---------------------------
async def _read_json_safely(req: Request) -> Dict[str, Any]:
    raw = await req.body()
    ct = (req.headers.get("content-type") or "").lower()
    try:
        if ct.startswith("application/json"):
            return json.loads(raw)
        return json.loads(raw)  # ultimo tentativo
    except Exception:
        logging.info("[agent] body (non-json)=%r", raw[:300])
        raise HTTPException(400, "invalid JSON body")


# ---------------------------
# util: flag reader (dotted / nested)
# ---------------------------
def _flag(d: Dict[str, Any], dotted_key: str, nested_root: str, nested_leaf: str, default: bool = False) -> bool:
    if dotted_key in d:
        return bool(d[dotted_key])
    nest = d.get(nested_root)
    if isinstance(nest, dict) and nested_leaf in nest:
        return bool(nest[nested_leaf])
    return default


# ---------------------------
# pulizia output AI
# ---------------------------
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*([\s\S]*?)\s*```$", re.MULTILINE)

def _strip_md_fences(s: str) -> str:
    s = s.strip()
    m = _FENCE_RE.search(s)
    if m:
        return m.group(1).strip()
    return s

def _strip_leading_preamble(s: str) -> str:
    # Rimuove intro tipo "Here is the updated code:" o "Updated code:"
    return re.sub(r"^\s*(Here\s+is\s+the\s+updated\s+code:|Updated\s+code:|Here\s+is\s+the\s+code:)\s*\n+", "", s, flags=re.IGNORECASE)

def _extract_code_from_ai(s: str) -> str:
    return _strip_md_fences(_strip_leading_preamble(s))

def _extract_docstring_from_ai(s: str, lang: str) -> str:
    raw = _strip_md_fences(s).strip()

    if lang.startswith("py"):
        # prendi solo il primo blocco tripla-virgolette se presente
        m = re.search(r'("""|\'\'\')([\s\S]*?)(\1)', raw)
        if m:
            return f'{m.group(1)}{m.group(2).strip()}{m.group(1)}'
        # altrimenti normalizza a triple double quotes
        body = raw.strip().strip('"').strip("'").strip()
        return f'""" {body} """'.replace("  ", " ").strip()
    if lang.startswith("ts") or lang.startswith("js") or "react" in lang:
        m = re.search(r"/\*\*([\s\S]*?)\*/", raw)
        if m:
            return "/**" + m.group(1).rstrip() + "*/"
        body = raw.strip().strip("/*").strip("*/").strip()
        return "/** " + body + " */"
    if lang.startswith("java"):
        m = re.search(r"/\*\*([\s\S]*?)\*/", raw)
        if m:
            return "/**" + m.group(1).rstrip() + "*/"
        body = raw.strip().strip("/*").strip("*/").strip()
        return "/** " + body + " */"
    if lang.startswith("go"):
        # Go doc: commenti // sopra la dichiarazione
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        return "\n".join("// " + l for l in lines) or "// TODO: doc"
    # fallback
    return raw


# ---------------------------
# LLM wrapper compat
#   Nuova firma: call_gateway_chat(model=..., messages=..., base_url=..., ...)
#   Vecchia firma: call_gateway_chat(base_url, payload_dict)
# ---------------------------
async def _call_gateway_chat_compat(
    *,
    model: str,
    messages: List[Dict[str, str]],
    gateway: str,
    temperature: float = 0.2,
    max_tokens: int = 512,
    timeout_s: float = 45.0,
) -> str:
    try:
        return await call_gateway_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=gateway,
            timeout=timeout_s,
        )
    except TypeError:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return await call_gateway_chat(gateway, payload)


# ---------------------------
# docstring shims (compat vecchie firme)
# ---------------------------
def _make_docstring_compat(lang: str, text: str, selection: str, prompt: str) -> str:
    try:
        return _make_docstring(lang, text=text, selection=selection, prompt=prompt)
    except TypeError:
        try:
            return _make_docstring(lang, text, selection, prompt)
        except TypeError:
            # alcune versioni usano code=
            return _make_docstring(lang, code=text, selection=selection, prompt=prompt)

def _insert_docstring_compat(lang: str, orig: str, selection: str, doc: str) -> Tuple[str, bool]:
    res = _insert_docstring(lang, orig, "", doc)
    if isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], str) and isinstance(res[1], bool):
        return res
    if isinstance(res, str):
        return res, res != orig
    s = str(res)
    return s, s != orig


# ---------------------------
# endpoint
# ---------------------------
@router.post("/agent/code")
async def agent_code(req: Request):
    b = await _read_json_safely(req)

    intent = (b.get("intent") or "").strip().lower()
    if not intent:
        raise HTTPException(400, "no inent specified. Intent required")

    path = b.get("path")
    if not path:
        raise HTTPException(400, "path required")

    orig = b.get("text")
    if orig is None:
        orig = read_file(path) or ""
    selection = _normalize_selection(b.get("selection"))

    prompt = b.get("prompt", "") or ""
    lang = (b.get("language") or detect_lang(path) or "text").lower()

    use_ai_doc = _flag(b, "use.ai.docstring", "use_ai", "docstring", False)
    use_ai_ref = _flag(b, "use.ai.refactor", "use_ai", "refactor", False)
    use_ai_tst = _flag(b, "use.ai.tests", "use_ai", "tests", False)
    use_ai_fix = _flag(b, "use.ai.fix_errors", "use_ai", "fix_errors", False)
    fallback_allowed = bool(b.get("fallback", False))
    model = b.get("model") or "auto"

    logging.info(
        "[agent] intent=%s path=%s use_ai.doc=%s use_ai.ref=%s use_ai.tests=%s use_ai.fix=%s text_len=%s",
        intent, path, use_ai_doc, use_ai_ref, use_ai_tst, use_ai_fix, len(orig),
    )

    try:
        # ---------------- DOCSTRING ----------------
        if intent == "docstring":
            source = "embedded"
            doc = None

            if use_ai_doc:
                sys = {
                    "role": "system",
                    "content": (
                        "You generate concise, idiomatic docstrings only. "
                        "Do not rewrite code. Output just the docstring text."
                    ),
                }
                usr = {
                    "role": "user",
                    "content": (
                        f"Language: {lang}\nSelection (if any):\n{selection or orig}\nPrompt: {prompt}"
                    ),
                }
                try:
                    ai_text = await _call_gateway_chat_compat(
                        model=model,
                        messages=[sys, usr],
                        gateway=gateway_url,
                        temperature=0.1,
                        max_tokens=256,
                        timeout_s=float(settings.REQUEST_TIMEOUT_S),
                    )
                    # Gestione eventuale JSON OpenAI-like
                    if isinstance(ai_text, str) and ai_text.strip().startswith("{"):
                        try:
                            jr = json.loads(ai_text)
                            ai_text = (jr["choices"][0]["message"]["content"] or "").strip()
                        except Exception:
                            pass
                    ai_text = ai_text or ""
                    doc = _extract_docstring_from_ai(ai_text, lang)
                    source = "ai"
                except Exception as e:
                    logging.error("[agent] docstring AI failed: %s", e)
                    if not fallback_allowed:
                        raise HTTPException(502, f"docstring via AI failed: {type(e).__name__}: {e}")
                    doc = _make_docstring_compat(lang, orig, selection, prompt)
                    source = "embedded_fallback"
            else:
                doc = _make_docstring_compat(lang, orig, selection, prompt)

            # Inserisce la docstring e poi deduplica la selection se è stata duplicata
            new_content = _insert_docstring_compat(lang, orig, selection, doc or "")
            new_content = _ensure_str(new_content)
            new_content = _dedupe_selection_in_text(new_content, selection)

            new_content = _normalize_module_doc_spacing(lang, new_content)
            new_content = _squeeze_blank_lines(new_content)


            diff = to_diff(path, orig, new_content)
            rat = f"Inserted/updated Python docstring for `{'selection' if selection else 'module'}` in `{path}`."
            try:
                rat_ai = await rationale("docstring", lang, path, orig, prompt)
                if rat_ai:
                    rat = rat_ai
            except Exception:
                pass

            return {
                "status": "ok",
                "message": "Docstring applicata",
                "diff": diff,
                "new_content": new_content,
                "rationale": rat,
                "apply": {"type": "unified_diff", "path": path},
                "source": source,
            }

    
        # ---------------- REFACTOR ----------------
        if intent == "refactor":
            source = "embedded"
            if use_ai_ref:
                sys = {"role": "system", "content": "You are a senior software engineer and an expert developer. Return only the updated code."}
                usr = {"role": "user", "content": json.dumps({"language": lang, "prompt": prompt, "code": orig}, ensure_ascii=False)}
                try:
                    ai_code = await _call_gateway_chat_compat(
                        model=model, messages=[sys, usr], gateway=gateway_url, temperature=0.2, max_tokens=2048
                    )
                    if isinstance(ai_code, str) and ai_code.strip().startswith("{"):
                        try:
                            jr = json.loads(ai_code)
                            ai_code = (jr["choices"][0]["message"]["content"] or "")
                        except Exception:
                            pass
                    new = _extract_code_from_ai(ai_code or "")
                    source = "ai"
                except Exception as e:
                    if not fallback_allowed:
                        raise HTTPException(502, f"refactor via AI failed: {type(e).__name__}: {e}")
                    new = deterministic_refactor(lang, orig, selection or "", prompt or "")
                    source = "embedded_fallback"
            else:
                new = deterministic_refactor(lang, orig, selection or "", prompt or "")

            diff = to_diff(path, orig, new)
            rat = await rationale("refactor", lang, path, orig, prompt)
            return {"diff": diff, "new_content": new, "rationale": rat, "apply": {"type": "unified_diff", "path": path}, "source": source}

        # ---------------- TESTS ----------------
        if intent == "tests":
            source = "embedded"
            if use_ai_tst:
                sys = {"role": "system", "content": "Generate  unit tests. Return only test code."}
                usr = {"role": "user", "content": json.dumps({"language": lang, "prompt": prompt, "code": orig}, ensure_ascii=False)}
                try:
                    ai_test = await _call_gateway_chat_compat(
                        model=model, messages=[sys, usr], gateway=gateway_url, temperature=0.2, max_tokens=1024
                    )
                    if isinstance(ai_test, str) and ai_test.strip().startswith("{"):
                        try:
                            jr = json.loads(ai_test)
                            ai_test = (jr["choices"][0]["message"]["content"] or "")
                        except Exception:
                            pass
                    tcontent = _strip_md_fences(_strip_leading_preamble(ai_test or ""))
                    source = "ai"
                except Exception as e:
                    if not fallback_allowed:
                        raise HTTPException(502, f"tests via AI failed: {type(e).__name__}: {e}")
                    tcontent = make_test_stub(lang, path, orig)
                    source = "embedded_fallback"
            else:
                tcontent = make_test_stub(lang, path, orig)

            # calcolo test_path
            if lang.startswith("ts"):
                test_path = path.replace(".ts", ".test.ts")
            elif lang.startswith("py"):
                import os as _os
                base = _os.path.basename(path).replace(".py", "")
                test_path = _os.path.join(_os.path.dirname(path) or ".", f"test_{base}.py")
            else:
                test_path = path + ".test"

            before = read_file(test_path) or ""
            diff = to_diff(test_path, before, tcontent or "")
            rat = await rationale("tests", lang, test_path, before, prompt or "tests")
            return {"diff": diff, "new_content": tcontent, "rationale": rat, "apply": {"type": "unified_diff", "path": test_path}, "source": source}

        # ---------------- FIX_ERRORS ----------------
        if intent == "fix_errors":
            source = "embedded"
            if use_ai_fix:
                sys = {"role": "system", "content": "Fix syntax and simple issues. Return only fixed code."}
                usr = {"role": "user", "content": json.dumps({"language": lang, "prompt": prompt, "code": orig}, ensure_ascii=False)}
                try:
                    ai_code = await _call_gateway_chat_compat(
                        model=model, messages=[sys, usr], gateway=gateway_url, temperature=0.0, max_tokens=2048
                    )
                    if isinstance(ai_code, str) and ai_code.strip().startswith("{"):
                        try:
                            jr = json.loads(ai_code)
                            ai_code = (jr["choices"][0]["message"]["content"] or "")
                        except Exception:
                            pass
                    new = _extract_code_from_ai(ai_code or "")
                    source = "ai"
                except Exception as e:
                    if not fallback_allowed:
                        raise HTTPException(502, f"fix_errors via AI failed: {type(e).__name__}: {e}")
                    new = mechanical_fixes(lang, orig)
                    source = "embedded_fallback"
            else:
                new = mechanical_fixes(lang, orig)

            diff = to_diff(path, orig, new)
            rat = await rationale("fix_errors", lang, path, orig, prompt)
            return {"diff": diff, "new_content": new, "rationale": rat, "apply": {"type": "unified_diff", "path": path}, "source": source}

        # ---------------- fallback generico ----------------
        rat = await rationale(intent, lang, path, orig, prompt)
        return {
            "diff": to_diff(path, orig, orig),
            "new_content": orig,
            "rationale": rat,
            "apply": {"type": "unified_diff", "path": path},
            "source": "noop",
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("[agent] error: %s", e)
        raise HTTPException(500, f"agent_code failed: {type(e).__name__}: {e}")
