"""Language runtimes a check needs beyond the sandbox image (G2): an LTC declares them in
``"environment": {"python": "3.14", "node": ">=24"}`` (B2B/foundation pilot: Python 3.14 with uv,
a portal on Node 24, an image with 3.12 and 22). CLike installs the versioned runtime from the tools
catalog (``python3.14``, ``nodejs24``) and gives it to that REQ's checks only:

- Python: the eval venv is created with it, and ``uv`` uses it (``UV_PYTHON``), never downloading one;
- Node: its ``node`` / ``npm`` / ``npx`` come first on that REQ's PATH;
- ``uv`` always gets a writable project environment of the REQ (the image's ``UV_PROJECT_ENVIRONMENT``
  is CLike's own read-only venv, so a project's ``uv sync`` / ``uv run`` failed there).

A runtime the image already satisfies is not installed. Nothing changes for an LTC that declares none.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_VERSION = re.compile(r"(\d+)(?:\.(\d+))?")


def _wanted(spec: Any) -> Optional[Tuple[int, Optional[int]]]:
    """(major, minor) asked by "3.14", ">=3.14", "~=3.14.1", "24", ">=24.11" — the lowest version it allows."""
    if spec is None:
        return None
    m = _VERSION.search(str(spec))
    if not m:
        return None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) is not None else None)


def declared_runtimes(ltc: Dict[str, Any]) -> Dict[str, Tuple[int, Optional[int]]]:
    env = ltc.get("environment") if isinstance(ltc.get("environment"), dict) else {}
    out: Dict[str, Tuple[int, Optional[int]]] = {}
    for key in ("python", "node"):
        wanted = _wanted(env.get(key))
        if wanted:
            out[key] = wanted
    return out


def image_node_major() -> Optional[int]:
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    m = _VERSION.search(out or "")
    return int(m.group(1)) if m else None


def runtime_tools(ltc: Dict[str, Any], *, python: Tuple[int, int] = sys.version_info[:2],
                  node: Optional[int] = None) -> List[str]:
    """Catalog tools for the runtimes the LTC declares and the image does not satisfy."""
    decl = declared_runtimes(ltc)
    tools: List[str] = []
    if "python" in decl:
        major, minor = decl["python"]
        if minor is not None and (major, minor) > tuple(python):
            tools.append(f"python{major}.{minor}")
    if "node" in decl:
        have = node if node is not None else image_node_major()
        if have is None or decl["node"][0] > have:
            tools.append(f"nodejs{decl['node'][0]}")
    return tools


def tools_envs_dir() -> Optional[Path]:
    raw = os.getenv("CLIKE_EVAL_TOOLS_BIN", "").strip()
    return Path(raw).parent / "envs" if raw else None


def runtime_env(env: Dict[str, str], ltc: Dict[str, Any], uv_environment: Path,
                envs_dir: Optional[Path] = None) -> Tuple[Dict[str, str], Optional[str]]:
    """The env of the REQ's checks with its runtimes; returns (env, python interpreter for its venv or None)."""
    out = dict(env)
    # a writable project environment per REQ: never CLike's own read-only venv
    out["UV_PROJECT_ENVIRONMENT"] = str(uv_environment)
    out.setdefault("UV_PYTHON_DOWNLOADS", "never")
    python: Optional[str] = None
    envs = envs_dir if envs_dir is not None else tools_envs_dir()
    for tool in runtime_tools(ltc):
        bin_dir = envs / tool / "bin" if envs else None
        if not bin_dir or not bin_dir.is_dir():
            continue
        if tool.startswith("python"):
            candidate = bin_dir / tool
            if candidate.exists():
                python = str(candidate)
                out["UV_PYTHON"] = python
                # the declared Python is the REQ's python / python3 (a venv, when created, comes first)
                out["PATH"] = f"{bin_dir}{os.pathsep}{out.get('PATH', '')}"
        elif tool.startswith("nodejs"):
            out["PATH"] = f"{bin_dir}{os.pathsep}{out.get('PATH', '')}"
    return out, python
