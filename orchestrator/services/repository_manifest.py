from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json



EXCLUDED_TOP_LEVEL = {
    ".git",
    ".clike",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    "runs",
    "promoted",
    "__MACOSX",
}

MARKER_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "tsconfig.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "go.mod",
    "go.work",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
]

CANONICAL_SOURCE_ROOT_CANDIDATES = [
    "src",
]

CANONICAL_TEST_ROOT_CANDIDATES = [
    "tests",
    "test",
]

def build_repo_access_manifest(repository_context: Optional[Dict[str, Any]]) -> Optional[str]:
    repo_ctx = dict(repository_context or {})
    repo_root_raw = _safe_str(repo_ctx.get("repo_root")) or _safe_str(repo_ctx.get("workspace_folder"))
    if not repo_root_raw:
        return None

    repo_root = Path(repo_root_raw).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        return None

    repo_url = _safe_str(repo_ctx.get("repo_url"))
    branch = _safe_str(repo_ctx.get("branch")) or "unknown"

    github_verified = False
    local_snapshot_verified = True

    lines: List[str] = [
        "# Repository Access Manifest",
        "",
        "## Verification Status",
        f"- Local snapshot verified: `{str(local_snapshot_verified).lower()}`",
        f"- GitHub remote verified in this run: `{str(github_verified).lower()}`",
        f"- Repository root analyzed: `{repo_root}`",
        f"- Branch hint: `{branch}`",
        f"- Repository URL hint: `{repo_url}`" if repo_url else "- Repository URL hint: `unknown`",
        "",
        "## Truthfulness Rules",
        "- You MAY say that a local repository snapshot was analyzed if you use this manifest.",
        "- You MUST NOT claim that the GitHub repository was analyzed unless `GitHub remote verified in this run` is `true`.",
        "- README and HOWTO must describe only repository evidence actually available in this run.",
        "",
        "## Documentation Wording Policy",
        "- Allowed wording: `Implementation decisions were informed by the local source snapshot and project artifacts provided for this run.`",
        "- Forbidden wording unless GitHub is verified: `The GitHub repository was analyzed.`",
    ]
    return "\n".join(lines).strip() + "\n"


def build_repo_structure_evidence(repository_context: Optional[Dict[str, Any]]) -> Optional[str]:
    repo_ctx = dict(repository_context or {})
    repo_root_raw = _safe_str(repo_ctx.get("repo_root")) or _safe_str(repo_ctx.get("workspace_folder"))
    if not repo_root_raw:
        return None

    repo_root = Path(repo_root_raw).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        return None

    top_level_dirs = _list_top_level_directories(repo_root)
    top_level_files = _list_top_level_files(repo_root)
    marker_files = _find_marker_files(top_level_files)

    payload = {
        "repo_root": str(repo_root),
        "top_level_dirs": top_level_dirs,
        "top_level_files": top_level_files,
        "marker_files": marker_files,
        "canonical_source_roots": _resolve_canonical_source_roots(top_level_dirs),
        "canonical_test_roots": _resolve_canonical_test_roots(top_level_dirs),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)

def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _list_top_level_directories(repo_root: Path) -> List[str]:
    out: List[str] = []
    for child in sorted(repo_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if child.name in EXCLUDED_TOP_LEVEL:
            continue
        out.append(child.name)
    return out


def _list_top_level_files(repo_root: Path) -> List[str]:
    out: List[str] = []
    for child in sorted(repo_root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file():
            out.append(child.name)
    return out


def _find_marker_files(top_level_files: List[str]) -> List[str]:
    return [name for name in MARKER_FILES if name in top_level_files]


def _resolve_canonical_source_roots(top_level_dirs: List[str]) -> List[str]:
    roots = [name for name in CANONICAL_SOURCE_ROOT_CANDIDATES if name in top_level_dirs]
    return roots or ["src"]


def _resolve_canonical_test_roots(top_level_dirs: List[str]) -> List[str]:
    roots = [name for name in CANONICAL_TEST_ROOT_CANDIDATES if name in top_level_dirs]
    return roots or ["tests"]


def build_req_promotion_manifest(
    repository_context: Optional[Dict[str, Any]],
    req_id: str,
) -> Optional[str]:
    repo_ctx = dict(repository_context or {})
    repo_root_raw = _safe_str(repo_ctx.get("repo_root")) or _safe_str(repo_ctx.get("workspace_folder"))
    if not repo_root_raw:
        return None

    repo_root = Path(repo_root_raw).expanduser().resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        return None

    branch = _safe_str(repo_ctx.get("branch")) or "unknown"
    workspace_folder = _safe_str(repo_ctx.get("workspace_folder")) or str(repo_root)
    repo_url = _safe_str(repo_ctx.get("repo_url"))

    top_level_dirs = _list_top_level_directories(repo_root)
    top_level_files = _list_top_level_files(repo_root)
    marker_files = _find_marker_files(top_level_files)
    source_roots = _resolve_canonical_source_roots(top_level_dirs)
    test_roots = _resolve_canonical_test_roots(top_level_dirs)

    lines: List[str] = [
        f"# REQ Promotion Manifest — {req_id}",
        "",
        "## Repository Context",
        f"- Repo root: `{repo_root}`",
        f"- Workspace folder: `{workspace_folder}`",
        f"- Branch: `{branch}`",
        f"- Repo URL: `{repo_url}`" if repo_url else "- Repo URL: `unknown`",
        "",
        "## Top-Level Directories",
    ]
    lines.extend([f"- `{name}`" for name in top_level_dirs] or ["- none detected"])

    lines.extend([
        "",
        "## Marker Files",
    ])
    lines.extend([f"- `{name}`" for name in marker_files] or ["- none detected"])

    lines.extend([
        "",
        "## Canonical Promotion Targets",
        "These are the architectural destinations that matter after promotion.",
        "",
        "### Source Targets",
    ])
    lines.extend([f"- `{name}/`" for name in source_roots])

    lines.extend([
        "",
        "### Test Targets",
    ])
    lines.extend([f"- `{name}/`" for name in test_roots])

    lines.extend([
        "",
        "## Staging Output Paths",
        "These are temporary staging paths only. They are not the final architecture.",
        f"- `runs/kit/{req_id}/src/...`",
        f"- `runs/kit/{req_id}/test/...`",
        f"- `runs/kit/{req_id}/docs/...`",
        f"- `runs/kit/{req_id}/ci/...`",
        "",
        "## Promotion Rules",
        "- Design emitted files as if they will be promoted into the canonical repository targets.",
        "- Do not treat `runs/` as an architectural example or as a valid module root.",
        "- Preserve the repository's canonical top-level module families.",
        "- Do not invent new top-level source roots if canonical promotion targets already exist.",
        "- Do not invent new top-level test roots if canonical promotion targets already exist.",
        "- Keep the implementation localized and reviewable so promotion from staging to canonical paths is low-risk.",
        "",
        "## Forbidden Path Families",
    ])
    lines.extend([f"- `{name}`" for name in sorted(EXCLUDED_TOP_LEVEL)])

    return "\n".join(lines).strip() + "\n"