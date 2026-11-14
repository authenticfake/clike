"""Lockfiles a local agent cannot resolve in its own sandbox (no network), resolved in the eval sandbox.

A coding agent writing a KIT often has no registry access: `uv lock` or `npm install --package-lock-only`
fail there, and the agent spent its eval-sandbox runs smuggling a lockfile out of a check's output
(lead-generation REQ-001: four of six runs). CLike resolves it instead: the manifest's folder is copied
to a scratch directory in the eval sandbox (which has registry egress), the package manager's own
lock command runs there with no install scripts, and the lockfile text goes back to the agent.

The request names only a manifest inside the REQ's KIT; the command is fixed by the manifest type,
never taken from the request.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from utils.safe_paths import UnsafePathError, resolve_within

# manifest file name → (lockfile name, command)
LOCK_COMMANDS: Dict[str, Any] = {
    "pyproject.toml": ("uv.lock", ["uv", "lock"]),
    "package.json": ("package-lock.json", ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"]),
}
_KIT_PATH_RE = re.compile(r"^runs/kit/REQ-[A-Za-z0-9._-]+/")
_COPY_IGNORE = shutil.ignore_patterns("node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "build", ".next", ".git")
TIMEOUT_S = 300
MAX_LOCK_BYTES = 5_000_000
LOG_TAIL = 4000


def _fail(manifest: str, message: str, log: str = "") -> Dict[str, Any]:
    return {"status": "FAIL", "manifest": manifest, "error": message, "log": log[-LOG_TAIL:]}


def resolve_lock(project_root: Path, manifest: str, *, timeout_s: int = TIMEOUT_S) -> Dict[str, Any]:
    """Resolve the lockfile of `manifest` (a pyproject.toml or package.json inside runs/kit/<REQ>/).

    Returns {status: OK, manifest, lockfile, content} or {status: FAIL, manifest, error, log}.
    """
    rel = str(manifest or "").replace("\\", "/").lstrip("./")
    name = rel.rsplit("/", 1)[-1]
    if name not in LOCK_COMMANDS:
        return _fail(rel, f"unsupported manifest {name or '(none)'}: one of {', '.join(sorted(LOCK_COMMANDS))}")
    if not _KIT_PATH_RE.match(rel):
        return _fail(rel, "the manifest must be inside the REQ's KIT (runs/kit/<REQ-ID>/...)")
    if ".." in rel.split("/"):
        return _fail(rel, "unsafe manifest path: '..' is not allowed")
    try:
        source = resolve_within(project_root, rel)
    except UnsafePathError as exc:
        return _fail(rel, f"unsafe manifest path: {exc}")
    # the resolved file (symlinks followed) is still inside the REQ's KIT
    try:
        resolved_rel = source.resolve().relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return _fail(rel, "unsafe manifest path: outside the project")
    if not _KIT_PATH_RE.match(resolved_rel):
        return _fail(rel, "unsafe manifest path: outside the REQ's KIT")
    if not source.is_file():
        return _fail(rel, "manifest not found")
    lock_name, command = LOCK_COMMANDS[name]
    if shutil.which(command[0]) is None:
        return _fail(rel, f"{command[0]} is not available in the eval sandbox")
    base = Path(os.getenv("CLIKE_EVAL_BASE_DIR") or tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clike-lock-", dir=str(base)) as tmp:
        work = Path(tmp) / "project"
        # the manifest's folder (path dependencies and workspace members resolve as in the KIT)
        shutil.copytree(source.parent, work, ignore=_COPY_IGNORE, symlinks=False)
        from eval_runner import scrubbed_process_env  # no credentials reach the package manager

        env = scrubbed_process_env()
        env.setdefault("UV_CACHE_DIR", str(Path(tmp) / "uv-cache"))
        env.setdefault("npm_config_cache", str(Path(tmp) / "npm-cache"))
        try:
            proc = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return _fail(rel, f"{' '.join(command)} timed out after {timeout_s} s")
        log = f"{proc.stdout}\n{proc.stderr}".strip()
        lock = work / lock_name
        if proc.returncode != 0 or not lock.is_file():
            return _fail(rel, f"{' '.join(command)} exited {proc.returncode}", log)
        data = lock.read_bytes()
        if len(data) > MAX_LOCK_BYTES:
            return _fail(rel, f"{lock_name} is larger than {MAX_LOCK_BYTES} bytes")
        lock_rel = f"{rel.rsplit('/', 1)[0]}/{lock_name}"
        return {"status": "OK", "manifest": rel, "lockfile": lock_rel, "content": data.decode("utf-8"), "log": log[-LOG_TAIL:]}


def supported_manifests() -> List[str]:
    return sorted(LOCK_COMMANDS)
