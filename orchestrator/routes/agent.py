# routes/agent.py
import re
import json
import logging
from typing import Any, Dict, Tuple, List
from fastapi import APIRouter, Request, HTTPException

from routes.v1 import _extract_json
from services.utils import read_file, to_diff, detect_lang
from services.docstrings import (
    insert_docstring as _insert_docstring,
)
from config import settings

from services.rationale import rationale
from services.llm_client import call_gateway_chat  # compat handled below

router = APIRouter()
gateway_url = str(settings.GATEWAY_URL)
# --- JSON schema guard for model responses (reusable) ---
MODEL_OUTPUT_SCHEMA = """
Devi rispondere in **solo JSON**, senza testo extra né blocchi di codice.
Schema consentito (uno dei due):

1) {"files":[{"path":"<relative/path/with/extension>", "content":"<full file content>"} , ...]}
   - 'path' deve essere relativo al workspace, con estensione corretta (.py, .go, .java, .ts, .js, .css, .html, etc.).
   - 'content' è il contenuto completo del file (non un diff).

OPPURE

2) {"replace_selection":"<nuovo testo da sostituire alla selezione originale>"}
   - Usalo quando vuoi **riscrivere** direttamente la selezione nel file originale.

NON usare altri campi. NON restituire testo fuori dal JSON.
"""

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
        # take the first non-empty string element, otherwise concatenate the string pieces
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
    # if it is accidentally a tuple like (text, flag), take the first string piece
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

    # no selection -> no dedup
    if not selection or len(selection.strip()) < 4:
        return text

    # if the selection does not appear at least twice, there is no duplication to remove
    matches = list(re.finditer(re.escape(selection), text))
    if len(matches) <= 1:
        return text

    # Keep the first one, remove the following ones
    first = matches[0]
    start_keep, end_keep = first.start(), first.end()

    before = text[:start_keep]
    keep = text[start_keep:end_keep]
    after = text[end_keep:]

    # clean up selection duplicates in the after part
    after = re.sub(re.escape(selection), "", after)

    return before + keep + after


_DOCSTRING_START_RE = re.compile(r'^\s*(?P<q>"""|\'\'\')', re.DOTALL)
_DOCSTRING_FULL_RE = re.compile(r'^\s*(?P<q>"""|\'\'\')(?P<body>[\s\S]*?)(?P=q)', re.DOTALL)

def _squeeze_blank_lines(s: str) -> str:
    """Riduce sequenze di >2 righe vuote a massimo 2, e rimuove spazi inutili in testa/coda."""
    # at most 2 consecutive newlines
    s = re.sub(r'\n{3,}', '\n\n', s)
    # strip leading/trailing whitespace of the file
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
    # remove leading blank lines in the rest
    rest = re.sub(r'^\s*\n', '', rest, count=1)
    # force exactly 1 newline between docstring and code
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
        return json.loads(raw)  # last attempt
    except Exception:
        logging.info("[agent] body (non-json)=%r", raw[:300])
        raise HTTPException(400, "invalid JSON body")


# ---------------------------
# AI output cleanup
# ---------------------------
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*([\s\S]*?)\s*```$", re.MULTILINE)

def _strip_md_fences(s: str) -> str:
    s = s.strip()
    m = _FENCE_RE.search(s)
    if m:
        return m.group(1).strip()
    return s

def _strip_leading_preamble(s: str) -> str:
    # Remove intros like "Here is the updated code:" or "Updated code:"
    return re.sub(r"^\s*(Here\s+is\s+the\s+updated\s+code:|Updated\s+code:|Here\s+is\s+the\s+code:)\s*\n+", "", s, flags=re.IGNORECASE)

def _extract_code_from_ai(s: str) -> str:
    return _strip_md_fences(_strip_leading_preamble(s))

def _extract_docstring_from_ai(s: str, lang: str) -> str:
    raw = _strip_md_fences(s).strip()

    if lang.startswith("py"):
        # take only the first triple-quoted block if present
        m = re.search(r'("""|\'\'\')([\s\S]*?)(\1)', raw)
        if m:
            return f'{m.group(1)}{m.group(2).strip()}{m.group(1)}'
        # otherwise normalize to triple double quotes
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
        # Go doc: // comments above the declaration
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        return "\n".join("// " + l for l in lines) or "// TODO: doc"
    # fallback
    return raw


# ---------------------------
# LLM wrapper compat
#   New signature: call_gateway_chat(model=..., messages=..., base_url=..., ...)
#   Old signature: call_gateway_chat(base_url, payload_dict)
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

    temperature = b.get("temperature", 0.1)
    max_tokens = b.get("max_tokens", 1024)
    
    use_ai_doc = True
    use_ai_ref = True
    use_ai_tst = True
    use_ai_fix = True
    fallback_allowed = False
    model = b.get("model") or "auto"

    logging.info(
        "[agent] intent=%s path=%s use_ai.doc=%s use_ai.ref=%s use_ai.tests=%s use_ai.fix=%s text_len=%s",
        intent, path, use_ai_doc, use_ai_ref, use_ai_tst, use_ai_fix, len(orig),
    )

    try:
        # ---------------- DOCSTRING ----------------
        if intent == "docstring":
            source = "ai"
            doc = None

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
                # Handle a possible OpenAI-like JSON
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
               raise HTTPException(502, f"docstring via AI failed: {type(e).__name__}: {e}")
                

            # Insert the docstring and then dedup the selection if it was duplicated
            new_content = _insert_docstring_compat(lang, orig, selection, doc or "")
            new_content = _ensure_str(new_content)
            new_content = _dedupe_selection_in_text(new_content, selection)

            new_content = _normalize_module_doc_spacing(lang, new_content)
            new_content = _squeeze_blank_lines(new_content)

            diff = to_diff(path, orig, new_content)
            rat = await rationale("docstring", lang, path, orig, prompt)
            apply_type = "replace_selection" if selection else "replace_whole"
    
            return {
                "status": "ok",
                "message": "Docstring applied successfully",
                "new_content": new_content,
                "rationale": rat,
                "apply": {"type": apply_type, "path": path},
                "source": "ai",
            }
        # ---------------- REFACTOR ----------------
        if intent == "refactor":
            source = "ai"
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
               raise HTTPException(502, f"refactor via AI failed: {type(e).__name__}: {e}")
            
            apply_type = "replace_selection" if selection else "replace_whole"
            diff = to_diff(path, orig, new)
            rat = await rationale("refactor", lang, path, orig, prompt)
            return {
                "diff": diff, 
                "new_content": new, 
                "rationale": rat, 
                "apply": {"type":apply_type, "path": path}, 
                "source": source}
        # ---------------- TESTS ----------------
        # INPUT from the payload
            lang = (body.get("language") or "").strip().lower()
            path = (body.get("path") or "").strip()  # file active in the editor (optional but recommended)
            selection = body.get("selection") or ""
            orig = body.get("content") or ""         # full content of the current file
        # ---------------- TEST ----------------
        if intent == "tests":
            # INPUT from the payload
            
            if not selection and not orig:
                raise HTTPException(400, "tests: serve almeno 'selection' o 'content'")

            # --- Messages for the model: minimal & schema-locked ---
            sys = (
                "You are a code generation assistant that writes **tests** only.\n"
                "Given a snippet (selection) or a full file (content), you will generate test code.\n"
                "Prefer creating test files, but if the user context implies a tiny inline adaptation, you can return replace_selection.\n"
                "Language: " + (lang or "unknown") + "\n\n" + MODEL_OUTPUT_SCHEMA
            )

            user_parts = []
            if path:
                user_parts.append(f"Current file path: {path}")
            if selection:
                user_parts.append("Selection (test this unit):\n```\n" + selection + "\n```")
            elif orig:
                user_parts.append("File content (derive test units from it):\n```\n" + orig + "\n```")

            # Optionally include a user request (extra prompt) if the extension sends one
            user_hint = prompt
            if user_hint:
                user_parts.append(f"User request:\n{user_hint}")

            messages = [
                {"role": "system", "content": sys},
                {"role": "user", "content": "\n\n".join(user_parts)}
            ]

            # --- Call LLM via gateway (as already done for the other intents) ---
            try:
                raw = await llm_client.call_gateway_chat(
                    model,
                    messages,
                    base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
                    timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

            # --- Robust parse: files[] or replace_selection ---
            # NB: No path heuristics: let the model decide and only normalize
            try:
                pj = _extract_json(raw)
            except Exception as e:
                raise HTTPException(502, f"model did not return JSON: {type(e).__name__}: {e}")

            files_out: list[dict] = []
            diffs: list[dict] = []

            if isinstance(pj, dict) and "replace_selection" in pj:
                if not path or not orig or not selection:
                    raise HTTPException(422, "replace_selection richiede path, content e selection nel payload")
                repl = str(pj["replace_selection"])
                # single-occurrence replacement of the selection
                new_text = orig.replace(selection, repl, 1)
                files_out = [{"path": path, "content": new_text}]

            elif isinstance(pj, dict) and isinstance(pj.get("files"), list) and pj["files"]:
                # Keep the paths provided by the model; only minimal normalization (slashes)
                for f in pj["files"]:
                    p = (f.get("path") or "").replace("\\", "/")
                    c = f.get("content") or ""
                    if not p:
                        raise HTTPException(422, "each file in files[] must have a non-empty 'path'")
                    files_out.append({"path": p, "content": c})

            else:
                raise HTTPException(422, "tests: empty or invalid model output (expect files[] or replace_selection)")

            # --- Diff computation as in the rest of the flow (no name heuristics) ---
            for fobj in files_out:
                p = fobj["path"]
                c = fobj["content"]
                prev = su.read_file(p) or ""
                patch = su.to_diff(prev, c, p)
                diffs.append({"path": p, "diff": patch})

            resp = {
                "version": "1.0",
                "files": files_out,
                "diffs": diffs,
                "eval_report": {"status": "skipped"},
            }
            return resp


        # ---------------- FIX_ERRORS ----------------
        if intent == "fix_errors":
            source = "ai"
            sys = {"role": "system", "content": "Fix syntax and all issues. Return only fixed code."}
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
                raise HTTPException(502, f"fix_errors via AI failed: {type(e).__name__}: {e}")

            apply_type = "replace_selection" if selection else "replace_whole"
            diff = to_diff(path, orig, new)
            rat = await rationale("fix_errors", lang, path, orig, prompt)
            return {
                "diff": diff, 
                "new_content": new,
                "rationale": rat, 
                "apply": {"type": apply_type, "path": path}, 
                "source": source
                }

        # ---------------- generic fallback ----------------
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
