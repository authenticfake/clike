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
# Also deliverable (B2B REQ-037/038 staged them under ci/shared/, never promoted): the example of each
# private env file, the ignore files, the solution eval profile, project docs outside Harper/inputs.
ENV_EXAMPLE_RE = re.compile(r"^\.env(\.[\w-]+)?\.example$")
EXTRA_ROOT_FILES = (".gitignore", ".dockerignore")
SOLUTION_FILES = ("ci/SOLUTION_LTC.json",)
DOCS_DENIED = frozenset({"harper", "inputs", "reference"})


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
    if any(s in ("", ".", "..") for s in parts):
        return False
    name = parts[-1]
    if _DENIED_NAME_RE.search(name) and not ENV_EXAMPLE_RE.match(name):
        return False
    if p in SOLUTION_FILES:
        return True
    if parts[0] == "docs":
        return parts[1] not in DOCS_DENIED if len(parts) > 2 else len(parts) == 2
    if parts[0] in DENIED_FIRST_SEGMENTS:
        return False
    if len(parts) == 1:
        return name in policy["files"] or bool(ENV_EXAMPLE_RE.match(name)) or name in EXTRA_ROOT_FILES
    return parts[0] in policy["folders"]


def extra_root_files(layer: Path, policy: Dict[str, List[str]]) -> List[str]:
    """Deliverables of a KIT root/ outside the policy's folders and files: env examples, ignore files,
    the solution eval profile, project docs (relative paths, sorted)."""
    out: List[str] = []
    if not layer.is_dir():
        return out
    for path in layer.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(layer).as_posix()
        top = rel.split("/", 1)[0]
        if top in policy["folders"] or rel in policy["files"]:
            continue
        if is_allowed_root_path(rel, policy):
            out.append(rel)
    return sorted(out)


def root_entries(project_root: Optional[Path], policy: Dict[str, List[str]]) -> List[str]:
    """Top-level repository names the policy covers (folders and files)."""
    return [*policy["folders"], *policy["files"]]


def staged_root_deliverables(project_root: Optional[Path]) -> List[Dict[str, str]]:
    """Repository-root deliverables the KITs left in a staging folder (runs/kit/<REQ>/ci/<staging>/
    <repository path>) that the gate never promoted, and that the repository does not hold as they
    are: ``[{"req", "kit_path", "repository_path", "state": "missing" | "differs"}]``, the newest REQ
    last. /finalize brings them to the root (B2B v3: --oidc and --live existed only in ci/shared/)."""
    if project_root is None:
        return []
    root = Path(project_root)
    kits = root / "runs" / "kit"
    policy = root_policy(root)
    out: Dict[str, Dict[str, str]] = {}
    for kit in sorted((p for p in kits.iterdir() if p.is_dir()), key=lambda p: p.name) if kits.is_dir() else []:
        ci = kit / "ci"
        if not ci.is_dir():
            continue
        # a staging map of the KIT may name other files too (its runbooks under docs/)
        try:
            mapped = json.loads((ci / "STAGING_MAP.json").read_text(encoding="utf-8")).get("shared") or {}
        except Exception:
            mapped = {}
        for src_rel, dst_rel in (mapped.items() if isinstance(mapped, dict) else []):
            src, dst = kit / str(src_rel), str(dst_rel).strip("/")
            if src.is_file() and str(src_rel).startswith("docs/") and is_allowed_root_path(dst, policy):
                target = root / dst
                if not (target.is_file() and target.read_bytes() == src.read_bytes()):
                    out[dst] = {"req": kit.name, "kit_path": src.relative_to(root).as_posix(), "repository_path": dst,
                                "state": "differs" if target.exists() else "missing"}
        for path in sorted(ci.rglob("*")):
            parts = path.relative_to(ci).parts
            if not path.is_file() or len(parts) < 2 or parts[0] in {"reports", "local-eval-workspaces", "regression"}:
                continue
            if any(p in {"node_modules", ".venv", "__pycache__"} for p in parts):
                continue
            rel = "/".join(parts[1:])
            if not is_allowed_root_path(rel, policy):
                continue
            target = root / rel
            try:
                same = target.is_file() and target.read_bytes() == path.read_bytes()
            except OSError:
                same = False
            if same:
                out.pop(rel, None)
                continue
            out[rel] = {"req": kit.name, "kit_path": path.relative_to(root).as_posix(), "repository_path": rel,
                        "state": "differs" if target.exists() else "missing"}
    return list(out.values())
