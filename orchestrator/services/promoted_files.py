"""A KIT extends the promoted shared files it ships (entrypoint, manifests, shared modules): it never
replaces one with a much shorter version or one without the promoted dependencies.

Cloud pilot 2026-11-08: one generation call rewrote the promoted src/leadintel/app.py (196 → 34
lines) and src/pyproject.toml (no dependencies); the regression of every promoted REQ failed.
Language-agnostic line comparison, plus dependency/script names for the common manifests.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Set

SKIP_DIRS = frozenset({"node_modules", "__pycache__", ".venv", "dist", "build", ".next", "coverage", "reports"})
_COMMENT_LINE = re.compile(r"^\s*(#|//|/\*|\*|--|<!--)")
_MIN_LINES = 20


def significant_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not _COMMENT_LINE.match(line)]


def content_loss(before: str, after: str) -> str:
    """'keeps K of its N lines' when a promoted file of 20+ lines keeps less than a third of them (an
    evolution keeps more: over the B2B history the deepest legitimate rewrite kept 37%)."""
    old = significant_lines(before)
    if len(old) < _MIN_LINES:
        return ""
    new = set(significant_lines(after))
    kept = sum(1 for line in old if line in new)
    if kept * 3 >= len(old):
        return ""
    return f"keeps {kept} of its {len(old)} lines"


def _norm(dep: str) -> str:
    return re.split(r"[<>=!~\[;\s@]", str(dep).strip(), maxsplit=1)[0].lower().replace("_", "-")


def dependency_names(name: str, text: str) -> Dict[str, Set[str]]:
    """{kind: names} of a manifest: dependencies and scripts (pyproject.toml, package.json, requirements*.txt)."""
    out: Dict[str, Set[str]] = {}
    try:
        if name == "pyproject.toml":
            import tomllib

            project = tomllib.loads(text).get("project") or {}
            out["dependencies"] = {n for n in (_norm(d) for d in project.get("dependencies") or []) if n}
            for extra, deps in (project.get("optional-dependencies") or {}).items():
                out[f"optional {extra}"] = {n for n in (_norm(d) for d in deps) if n}
            out["scripts"] = set((project.get("scripts") or {}).keys())
        elif name == "package.json":
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "scripts"):
                out[key] = set((data.get(key) or {}).keys())
        elif re.fullmatch(r"requirements[^/]*\.txt", name):
            out["requirements"] = {
                n for n in (_norm(line) for line in text.splitlines() if line.strip() and not line.strip().startswith(("#", "-"))) if n
            }
    except Exception:
        return {}
    return out


def manifest_loss(name: str, before: str, after: str) -> str:
    """'drops promoted dependencies: x, y' when a manifest loses promoted dependencies or scripts."""
    old, new = dependency_names(name, before), dependency_names(name, after)
    if not old or not new:
        return ""
    lost = {kind: sorted(names - new.get(kind, set())) for kind, names in old.items() if names - new.get(kind, set())}
    if not lost:
        return ""
    return "drops promoted " + "; ".join(f"{kind}: {', '.join(names[:12])}" for kind, names in lost.items())


def loss(name: str, before: str, after: str) -> str:
    return manifest_loss(name, before, after) or content_loss(before, after)
