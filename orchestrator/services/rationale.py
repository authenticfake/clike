# services/rationale.py
import re, os
from typing import Optional
from .llm_client import call_gateway_chat  # tua funzione già esistente

def _diff_stats(diff_text: Optional[str]) -> str:
    if not diff_text:
        return ""
    adds = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    dels = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    return f"Δ +{adds}/-{dels}"

def _first_py_def_name(src: str) -> Optional[str]:
    m = re.search(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", src or "", re.M)
    return m.group(1) if m else None

def _local_rationale(intent: str, lang: str, path: str, orig: str, prompt: str, diff_text: Optional[str]) -> str:
    delta = _diff_stats(diff_text)
    lang = (lang or "").lower()
    if intent == "docstring" and lang == "python":
        fn = _first_py_def_name(orig) or "function"
        return f"Inserted/updated Python docstring for `{fn}` in `{path}`. {delta}".strip()
    if intent == "docstring":
        return f"Inserted/updated {lang or 'code'} docstring in `{path}`. {delta}".strip()
    if intent == "refactor":
        return f"Applied deterministic refactor (imports/format/whitespace) in `{path}`. {delta}".strip()
    if intent == "tests":
        return f"Generated test stub for `{path}`. {delta}".strip()
    if intent == "fix_errors":
        return f"Applied mechanical fixes (safe auto-fixes) in `{path}`. {delta}".strip()
    return f"Performed `{intent}` on `{path}`. {delta}".strip()

async def rationale(
    intent: str,
    lang: str,
    path: str,
    orig: str,
    prompt: str,
    *,
    use_ai: bool = False,
    model: Optional[str] = None,
    gateway_url: Optional[str] = None,
    diff_text: Optional[str] = None,
) -> str:
    # Produciamo SEMPRE una rationale; AI solo se richiesto.
    if not use_ai:
        return _local_rationale(intent, lang, path, orig, prompt, diff_text)

    # Modalità AI (con fallback locale in caso di errore)
    try:
        system = "You are a code change explainer. Summarize what changed succinctly."
        user = (
            f"Intent: {intent}\nLanguage: {lang}\nPath: {path}\nPrompt: {prompt}\n"
            f"Diff:\n{diff_text or '(no diff)'}\n"
        )
        msg = await call_gateway_chat(
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            model=model or "auto",
            gateway_url=gateway_url or os.getenv("GATEWAY_URL","http://gateway:8000"),
            temperature=0.0,
            max_tokens=200,
        )
        return (msg or "").strip() or _local_rationale(intent, lang, path, orig, prompt, diff_text)
    except Exception as e:
        return _local_rationale(intent, lang, path, orig, prompt, diff_text) + f" (AI rationale fallback: {type(e).__name__})"
