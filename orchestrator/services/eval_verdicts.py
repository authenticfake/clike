"""Verdicts of full evals, reusable by the gate when nothing changed since.

/v1/eval/run records each full verdict with a digest of everything it depends on, computed here,
server-side, from the project tree (never from a client report); /v1/gate/check reuses a passing
verdict whose digest still matches instead of running the whole profile again. Same inputs, same
CLike version and eval engine code, same regression set: the same checks would give the same result. Anything changed
(a file of the REQ or of the canonical tree, an LTC, a REQ status in plan.json) runs it again.
Records live in CLIKE_STATE_DIR, which agents cannot write.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from services.gate_integrity import _project_key, state_dir
from services.root_files import KIT_ROOT_DIR, root_policy

MAX_AGE_S = 24 * 3600
_SKIP_DIRS = frozenset({
    "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".next", ".turbo", ".cache", ".tmp", "reports", "local-eval-workspaces", "coverage", "dist",
})


# The code that decides an eval or gate verdict: a change to any of them (a fix between two releases,
# same version number) must not reuse a verdict or a baseline computed by the code before it.
_EVAL_ENGINE_FILES = (
    "eval_runner.py", "eval_failures.py", "eval_environment.py", "eval_tools.py", "eval_tools_catalog.yaml",
    "sandbox_resources.py", "services/gate_integrity.py", "services/eval_verdicts.py", "services/root_files.py",
)
_ENGINE_DIGEST: Optional[str] = None


def _clike_version() -> str:
    """CLike's version and a digest of its eval engine code (computed once per process)."""
    global _ENGINE_DIGEST
    base = Path(__file__).resolve().parents[1]
    try:
        import tomllib

        version = tomllib.loads((base / "pyproject.toml").read_text())["project"]["version"]
    except Exception:
        version = "unknown"
    if _ENGINE_DIGEST is None:
        h = hashlib.sha256()
        for rel in _EVAL_ENGINE_FILES:
            try:
                h.update(rel.encode() + b"\0" + (base / rel).read_bytes() + b"\0")
            except OSError:
                h.update(rel.encode() + b"\0missing\0")
        _ENGINE_DIGEST = h.hexdigest()[:12]
    return f"{version}+{_ENGINE_DIGEST}"


def inputs_digest(project_root: Path, req_id: str, regression: bool) -> str:
    root = Path(project_root).resolve()
    h = hashlib.sha256()
    h.update(f"clike={_clike_version()}\0regression={bool(regression)}\0req={req_id}\0".encode())

    def add_file(path: Path) -> None:
        try:
            h.update(f"{path.relative_to(root).as_posix()}\0".encode())
            h.update(path.read_bytes())
            h.update(b"\0")
        except OSError:
            pass

    def add_tree(path: Path) -> None:
        if path.is_file():
            add_file(path)
            return
        if not path.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info"))
            for name in sorted(filenames):
                if name.endswith((".pyc", ".log")) or name == ".DS_Store":
                    continue
                add_file(Path(dirpath) / name)

    policy = root_policy(root)
    for name in ("src", "test", "tests", *policy["folders"], *policy["files"]):
        add_tree(root / name)
    kit = root / "runs" / "kit" / req_id
    for name in ("src", "test", "tests", "ci", KIT_ROOT_DIR):
        add_tree(kit / name)
    add_tree(root / "docs" / "harper" / "plan.json")  # statuses decide the regression set
    for ltc in sorted((root / "runs" / "kit").glob("*/ci/LTC.json")):
        add_file(ltc)
    return h.hexdigest()


def _record_path(project_root: Path, req_id: str) -> Path:
    return state_dir() / "eval_verdicts" / _project_key(Path(project_root)) / f"{req_id}.json"


def record(project_root: Path, req_id: str, regression: bool, report: Dict[str, Any]) -> None:
    path = _record_path(project_root, req_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "req_id": req_id, "regression": bool(regression), "at": time.time(),
        "digest": inputs_digest(project_root, req_id, regression), "report": report,
    }), encoding="utf-8")


def reusable(project_root: Path, req_id: str, regression: bool) -> Optional[Dict[str, Any]]:
    """The recorded passing report when its inputs are still the same, else None."""
    try:
        data = json.loads(_record_path(project_root, req_id).read_text(encoding="utf-8"))
    except Exception:
        return None
    report = data.get("report") or {}
    if (data.get("regression") != bool(regression) or time.time() - float(data.get("at") or 0) > MAX_AGE_S
            or str(report.get("status")) not in {"PASS", "PASS_WITH_WARNINGS"}):
        return None
    if data.get("digest") != inputs_digest(project_root, req_id, regression):
        return None
    return {"report": report, "at": data.get("at")}
