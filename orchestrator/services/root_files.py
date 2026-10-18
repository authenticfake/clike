"""Repository-root deliverables of a KIT (scripts/, deploy/, infra/, root manifests, .env.example).

A KIT writes them under runs/kit/<REQ>/root/<repository path>; the gate promotes them to
<repository path> and the eval overlays them on the workspace like src/ and test/. Mirror of
extensions/vscode/root-files-policy.js (same defaults, same denylist). `.clike/project.json` may
add `root_folders` and `root_files`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

KIT_ROOT_DIR = "root"
DEFAULT_ROOT_FOLDERS = ["scripts", "deploy", "infra", "ops", "config", "configs", "migrations", "db"]
DEFAULT_ROOT_FILES = [
    ".env.example", "compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml",
    "Dockerfile", "Makefile", "Procfile",
]
DENIED_FIRST_SEGMENTS = frozenset({
    ".git", ".clike", "runs", "docs", "src", "test", "tests", "ci", "node_modules", ".venv", "venv",
    "__pycache__", ".cache", ".next", "dist", "build", "coverage",
})
_DENIED_NAME_RE = re.compile(r"^\.env(\..+)?$|\.(pem|key|p12|pfx)$|^id_(rsa|ed25519)", re.IGNORECASE)


def root_policy(project_root: Optional[Path]) -> Dict[str, List[str]]:
    meta: dict = {}
    if project_root is not None:
        try:
            meta = json.loads((Path(project_root) / ".clike" / "project.json").read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}

    def _list(value) -> List[str]:
        return [str(v or "").strip().strip("/").removeprefix("./") for v in value] if isinstance(value, list) else []

    folders = [f for f in dict.fromkeys(DEFAULT_ROOT_FOLDERS + _list(meta.get("root_folders")))
               if f and "/" not in f and f not in DENIED_FIRST_SEGMENTS]
    files = [f for f in dict.fromkeys(DEFAULT_ROOT_FILES + _list(meta.get("root_files"))) if f and "/" not in f]
    return {"folders": folders, "files": files}


def is_allowed_root_path(rel: str, policy: Dict[str, List[str]]) -> bool:
    p = str(rel or "").replace("\\", "/").removeprefix("./")
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return False
    parts = p.split("/")
    if any(s in ("", ".", "..") for s in parts) or parts[0] in DENIED_FIRST_SEGMENTS:
        return False
    name = parts[-1]
    if _DENIED_NAME_RE.search(name) and name != ".env.example":
        return False
    return name in policy["files"] if len(parts) == 1 else parts[0] in policy["folders"]


def root_entries(project_root: Optional[Path], policy: Dict[str, List[str]]) -> List[str]:
    """Top-level repository names the policy covers (folders and files)."""
    return [*policy["folders"], *policy["files"]]
