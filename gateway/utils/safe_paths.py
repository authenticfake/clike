"""Path confinement helpers (WP4).

Kept byte-identical in orchestrator/utils/ and gateway/utils/ (checked by
tests) until both services share a package.

Every path built from request data, LLM output or identifiers must go
through these helpers before touching the filesystem.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Union

PathLike = Union[str, Path]

REQ_ID_RE = re.compile(r"^REQ-[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SEGMENT_BAD_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class UnsafePathError(ValueError):
    """Raised when a path would escape its allowed root or is malformed."""


def is_within(path: PathLike, root: PathLike) -> bool:
    """True if ``path`` resolves inside ``root`` (or is ``root``). Symlinks are resolved."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def is_within_any(path: PathLike, roots: Iterable[PathLike]) -> bool:
    return any(is_within(path, r) for r in roots)


def resolve_within(root: PathLike, relative: PathLike, *, allow_absolute_inside: bool = False) -> Path:
    """Resolve ``relative`` under ``root`` and refuse anything that escapes it.

    Rejects empty values, NUL bytes, Windows drive/UNC paths, and (unless
    ``allow_absolute_inside``) absolute paths. With ``allow_absolute_inside``
    an absolute path is accepted only if it already lies inside ``root``.
    """
    raw = str(relative if relative is not None else "")
    if not raw.strip():
        raise UnsafePathError("empty path")
    if "\x00" in raw:
        raise UnsafePathError("NUL byte in path")
    win = PureWindowsPath(raw)
    if win.drive or raw.startswith("\\\\"):
        raise UnsafePathError(f"drive or UNC path not allowed: {raw!r}")
    base = Path(root).resolve()
    candidate = Path(raw)
    if candidate.is_absolute():
        if not allow_absolute_inside:
            raise UnsafePathError(f"absolute path not allowed: {raw!r}")
        target = candidate.resolve()
    else:
        target = (base / PurePosixPath(raw.replace("\\", "/"))).resolve()
    if not target.is_relative_to(base):
        raise UnsafePathError(f"path escapes its root: {raw!r}")
    return target


def safe_segment(value: object, default: str = "default", max_len: int = 128) -> str:
    """Single safe filename segment: [A-Za-z0-9._-], no leading dots, never '.'/'..'."""
    cleaned = _SEGMENT_BAD_CHARS.sub("_", str(value if value is not None else "").strip())
    cleaned = cleaned.lstrip(".")[:max_len]
    return cleaned if cleaned and cleaned not in {".", ".."} else default


def validate_req_id(value: object) -> str:
    req_id = str(value or "").strip()
    if not REQ_ID_RE.match(req_id):
        raise UnsafePathError(f"invalid REQ id: {req_id!r}")
    return req_id
