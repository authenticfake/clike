"""Resources of the eval sandbox: processes, threads, memory, disk.

A sandbox that ran out of them fails every check with errors that look like code defects
(``spawn node EAGAIN``, ``pthread_create: Resource temporarily unavailable``, a browser that
closes, a web server that "exited early"). They are not: no change to the REQ can fix them, and a
repair loop that sends them to the model makes it change correct code. ``exhaustion`` recognises
them in a check's output; ``preflight`` refuses to start an eval in a sandbox that is already
near its process limit (e.g. zombies piling up when the container runs without an init).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

SANDBOX_EXHAUSTED_REASON = "EVAL_SANDBOX_EXHAUSTED"

# The OS refused a process, a thread, memory, a file descriptor or disk space.
_EXHAUSTION = re.compile(
    r"(\bspawn(?:Sync)?\b[^\n]{0,200}\bEAGAIN\b|\bEAGAIN\b[^\n]{0,80}\bspawn|"
    r"pthread_create[^\n]{0,80}(?:Resource temporarily unavailable|\(11\))|"
    r"fork: (?:retry|Resource temporarily unavailable|Cannot allocate memory)|"
    r"\bcan't fork\b|Cannot allocate memory|\bENOMEM\b|"
    r"No space left on device|\bENOSPC\b|Too many open files|\bEMFILE\b)",
    re.IGNORECASE,
)

# Fraction of pids.max at which a new eval is refused: a REQ eval with services, a build and a
# browser starts hundreds of processes and threads.
PIDS_PREFLIGHT_RATIO = 0.6

RESTART_HINT = (
    "Restart the eval sandbox (`podman restart docker_eval-sandbox_1`, or docker/rebuild.sh) and run again."
)


def exhaustion(text: str) -> Optional[str]:
    """The line of the output where the OS refused a resource, or None."""
    match = _EXHAUSTION.search(text or "")
    if not match:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return text[start:end if end >= 0 else len(text)].strip()[:300]


def _read_int(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None


def _cgroup_pids(cgroup_root: Path) -> tuple[Optional[int], Optional[int]]:
    for base in (cgroup_root, cgroup_root / "pids"):  # cgroup v2, then v1
        current = _read_int(base / "pids.current")
        if current is not None:
            return current, _read_int(base / "pids.max")  # "max" (unlimited) reads as None
    return None, None


def _zombies(proc_root: Path) -> int:
    count = 0
    try:
        entries = [p for p in proc_root.iterdir() if p.name.isdigit()]
    except OSError:
        return 0
    for entry in entries:
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # "<pid> (<comm>) <state> …": comm may hold spaces and parentheses
        if stat[stat.rfind(")") + 1:].split()[:1] == ["Z"]:
            count += 1
    return count


def snapshot(cgroup_root: Path = Path("/sys/fs/cgroup"), proc_root: Path = Path("/proc")) -> Dict[str, Any]:
    """Processes in use against the limit, zombies, whether PID 1 is an init that reaps them."""
    current, limit = _cgroup_pids(cgroup_root)
    try:
        pid1 = (proc_root / "1" / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        pid1 = ""
    return {"pids": current, "pids_max": limit, "zombies": _zombies(proc_root) if proc_root.is_dir() else 0, "pid1": pid1}


def preflight(cgroup_root: Path = Path("/sys/fs/cgroup"), proc_root: Path = Path("/proc")) -> Optional[str]:
    """Why the sandbox cannot run an eval now, or None (no limit known: no opinion)."""
    if os.name == "nt":
        return None
    snap = snapshot(cgroup_root, proc_root)
    current, limit = snap["pids"], snap["pids_max"]
    if not current or not limit or current < limit * PIDS_PREFLIGHT_RATIO:
        return None
    return (
        f"The eval sandbox already uses {current} of its {limit} processes ({snap['zombies']} zombies left by earlier "
        f"evals; PID 1 is {snap['pid1'] or 'unknown'}): checks would fail to start processes and threads. "
        "This is not a defect of the REQ. " + RESTART_HINT
    )
