"""Deterministic, behaviour-neutral fixes of generated KIT files before they are written and locked.

Models often emit code that a linter rejects only for mechanical reasons (import order, an
unused import, trailing whitespace); the eval then fails and an auto-eval cycle is spent on it.
FIXERS maps a file extension to a fixer that applies only such fixes, with the KIT's own lint
configuration, to sources and tests alike (the code does the same thing afterwards). An
ecosystem gets a fixer only when its fixes are safe whatever the project's configuration.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

log = logging.getLogger("service.kit_format")

# unused imports, trailing/blank-line whitespace, unused noqa comments. Not import order (I): it
# depends on which modules ruff sees as first-party, i.e. on the directory the KIT's lint runs
# from, so a fix here could contradict the eval's own lint.
SAFE_RUFF_RULES = "F401,W291,W292,W293,RUF100"
_CONFIG_NAMES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}
_TIMEOUT_S = 60


def _ruff() -> List[str]:
    exe = shutil.which("ruff")
    if exe:
        return [exe]
    try:
        subprocess.run(["python3", "-m", "ruff", "--version"], capture_output=True, check=True, timeout=10)
        return ["python3", "-m", "ruff"]
    except (OSError, subprocess.SubprocessError):
        return []


def _python_fixer(files: List[Dict[str, Any]], req_id: str) -> Dict[str, str]:
    """ruff with the context-independent safe rules only."""
    prefix = f"runs/kit/{req_id}/"
    python = [
        f for f in files or []
        if str(f.get("path") or "").startswith(prefix)
        and str(f.get("path") or "").endswith(".py")
        and str(f.get("path") or "")[len(prefix):].split("/", 1)[0] in {"src", "test", "tests"}
    ]
    ruff = _ruff() if python else []
    if not ruff:
        return {}
    changed: Dict[str, str] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="clike-kit-format-") as tmp:
            root = Path(tmp)
            for f in files:
                path = str(f.get("path") or "")
                if path.startswith(prefix) and (path.endswith(".py") or Path(path).name in _CONFIG_NAMES):
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(f.get("content") or ""), encoding="utf-8")
            cmd = [
                *ruff, "check", "--fix", "--exit-zero", "--no-cache", "--quiet",
                "--select", SAFE_RUFF_RULES,
                *[str(f["path"]) for f in python],
            ]
            subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=_TIMEOUT_S)
            for f in python:
                fixed = (root / f["path"]).read_text(encoding="utf-8")
                if fixed != f.get("content"):
                    changed[f["path"]] = fixed
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        log.warning("python autofix skipped: %s", type(exc).__name__)
        return {}
    return changed


FIXERS = {".py": _python_fixer}


def autofix_kit_files(files: List[Dict[str, Any]], req_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return the files with the safe fixes of every applicable fixer, and the paths that changed.
    Best effort: a missing tool or an error leaves the files unchanged."""
    changed: Dict[str, str] = {}
    extensions = {Path(str(f.get("path") or "")).suffix for f in files or []}
    for extension, fixer in FIXERS.items():
        if extension in extensions:
            changed.update(fixer(files, req_id))
    if not changed:
        return files, []
    return [{**f, "content": changed[f["path"]]} if f.get("path") in changed else f for f in files], sorted(changed)
