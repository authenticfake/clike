from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ALLOWED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}
IGNORED_DIR_NAMES = {".git", "node_modules", "__pycache__"}


@dataclass(frozen=True)
class CompanionArtifact:
    path: str
    size_bytes: int
    sha256: str
    truncated: bool
    snippet: str
    source_group: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "truncated": self.truncated,
            "snippet": self.snippet,
            "source_group": self.source_group,
        }


class CompanionArtifactCollector:
    """Collect bounded BMAD/UX companion artifacts from server-derived roots."""

    def __init__(
        self,
        *,
        workspace_root: Path | str,
        doc_root: Path | str,
        phase: str,
        methodology_context: Optional[Dict[str, Any]],
        req_id: Optional[str] = None,
        max_file_count: int = 40,
        max_bytes_per_file: int = 64 * 1024,
        max_total_snippet_chars: int = 40_000,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        raw_doc_root = Path(doc_root).expanduser()
        resolved_doc_root = (
            raw_doc_root
            if raw_doc_root.is_absolute()
            else self.workspace_root / raw_doc_root
        ).resolve()
        default_doc_root = (self.workspace_root / "docs" / "harper").resolve()
        try:
            doc_root_key = resolved_doc_root.relative_to(self.workspace_root).as_posix().strip("/")
        except ValueError:
            doc_root_key = ""
        self.doc_root = resolved_doc_root if doc_root_key == "docs/harper" else default_doc_root
        self.phase = str(phase or "").strip().lower()
        self.methodology_context = methodology_context if isinstance(methodology_context, dict) else None
        self.req_id = str(req_id or "").strip().upper() or None
        self.max_file_count = max(0, int(max_file_count))
        self.max_bytes_per_file = max(0, int(max_bytes_per_file))
        self.max_total_snippet_chars = max(0, int(max_total_snippet_chars))

    def collect(self) -> List[Dict[str, Any]]:
        if not self.methodology_context or self.methodology_context.get("methodology") != "bmad":
            return []
        if not self._is_within_workspace(self.doc_root):
            return []

        artifacts: List[CompanionArtifact] = []
        total_chars = 0
        for root, group in self._allowed_roots():
            if len(artifacts) >= self.max_file_count:
                break
            if not root.exists() or not root.is_dir():
                continue
            for path in self._iter_files(root):
                if len(artifacts) >= self.max_file_count:
                    break
                artifact = self._read_artifact(path, group, total_chars)
                if artifact is None:
                    continue
                artifacts.append(artifact)
                total_chars += len(artifact.snippet)

        return [artifact.as_dict() for artifact in artifacts]

    def _allowed_roots(self) -> List[tuple[Path, str]]:
        roots = [
            (self.doc_root / "bmad", "bmad_project"),
            (self.doc_root / "ux", "ux"),
        ]
        if self.req_id:
            roots.append((self.workspace_root / "runs" / "kit" / self.req_id / "docs", "req_docs"))
        return [(root.resolve(), group) for root, group in roots if self._is_within_workspace(root.resolve())]

    def _iter_files(self, root: Path) -> Iterable[Path]:
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                children = sorted(current.iterdir(), key=lambda p: p.as_posix())
            except OSError:
                continue

            for child in children:
                name = child.name
                if name.startswith("."):
                    continue
                if child.is_symlink():
                    if not self._symlink_target_is_safe(child):
                        continue
                try:
                    if child.is_dir():
                        if name in IGNORED_DIR_NAMES:
                            continue
                        stack.append(child)
                        continue
                    if not child.is_file():
                        continue
                except OSError:
                    continue
                if child.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                resolved = child.resolve()
                if not self._is_within_workspace(resolved):
                    continue
                yield resolved

    def _read_artifact(self, path: Path, source_group: str, total_chars: int) -> Optional[CompanionArtifact]:
        try:
            size_bytes = path.stat().st_size
        except OSError:
            return None

        available = max(0, self.max_total_snippet_chars - total_chars)
        limit = min(self.max_bytes_per_file, available)

        digest = hashlib.sha256()
        snippet_parts: List[bytes] = []
        remaining_snippet_bytes = limit
        first_chunk = True
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(8192)
                    if not chunk:
                        break
                    if first_chunk:
                        if self._looks_binary(chunk):
                            return None
                        first_chunk = False
                    digest.update(chunk)
                    if remaining_snippet_bytes > 0:
                        snippet_parts.append(chunk[:remaining_snippet_bytes])
                        remaining_snippet_bytes -= len(snippet_parts[-1])
        except OSError:
            return None

        snippet_bytes = b"".join(snippet_parts)
        truncated = size_bytes > len(snippet_bytes)
        try:
            snippet = snippet_bytes.decode("utf-8")
        except UnicodeDecodeError:
            snippet = snippet_bytes.decode("utf-8", errors="replace")

        try:
            rel_path = path.relative_to(self.workspace_root).as_posix()
        except ValueError:
            return None

        return CompanionArtifact(
            path=rel_path,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            truncated=truncated,
            snippet=snippet,
            source_group=source_group,
        )

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def _symlink_target_is_safe(self, path: Path) -> bool:
        try:
            return self._is_within_workspace(path.resolve())
        except OSError:
            return False

    @staticmethod
    def _looks_binary(data: bytes) -> bool:
        return b"\x00" in data[:4096]


def companion_core_blob_key(path: str) -> str:
    return f"companion::{str(path or '').strip().lstrip('/')}"
