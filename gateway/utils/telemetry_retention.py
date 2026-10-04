"""Telemetry retention (WP7, moved from WP1.4).

Telemetry holds full prompts, raw provider responses and rejected artifacts, so it grows without
bound. ``CLIKE_TELEMETRY_RETENTION_DAYS`` (unset or 0 = keep everything, the default) deletes files
older than that many days. Pruning runs at most once per ``CLIKE_TELEMETRY_PRUNE_INTERVAL_S``
(default 1h), never follows symlinks and never leaves the telemetry directory.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger("gateway.telemetry_retention")

_lock = threading.Lock()
_last_run = 0.0


def retention_days() -> float:
    try:
        return max(0.0, float(os.getenv("CLIKE_TELEMETRY_RETENTION_DAYS") or 0))
    except ValueError:
        log.warning("invalid CLIKE_TELEMETRY_RETENTION_DAYS; retention disabled")
        return 0.0


def prune(root: str | Path, *, max_age_days: float, now: float | None = None) -> int:
    """Delete regular files under ``root`` older than ``max_age_days``; return how many."""
    if max_age_days <= 0:
        return 0
    base = Path(root)
    if not base.is_dir() or base.is_symlink():
        return 0
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400
    removed = 0
    for dirpath, dirnames, filenames in os.walk(base, topdown=False, followlinks=False):
        current = Path(dirpath)
        for name in filenames:
            path = current / name
            try:
                st = path.lstat()
                if path.is_symlink() or not path.is_file():
                    continue
                if st.st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError as exc:
                log.debug("telemetry prune skipped %s: %s", path, exc)
        if current != base:
            try:
                current.rmdir()  # only succeeds when empty
            except OSError:
                pass
    return removed


def maybe_prune(root: str | Path) -> int:
    """Throttled ``prune`` driven by the environment; safe to call on every telemetry write."""
    global _last_run
    days = retention_days()
    if days <= 0:
        return 0
    interval = float(os.getenv("CLIKE_TELEMETRY_PRUNE_INTERVAL_S") or 3600)
    with _lock:
        if time.time() - _last_run < interval:
            return 0
        _last_run = time.time()
    removed = prune(root, max_age_days=days)
    if removed:
        log.info("telemetry retention: removed %d files older than %s days", removed, days)
    return removed
