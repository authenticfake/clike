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

# A check that needs a container runtime: the sandbox has none (no docker/podman, no privileges).
_NO_CONTAINER_RUNTIME = re.compile(
    r"((?:docker|podman)(?:[- ]compose)?(?: v\d)?[^\n]{0,120}\b(?:is |are )?(?:required|not found|not installed|"
    r"unavailable|not available|is not running)\b|Cannot connect to the Docker daemon|"
    r"(?:docker|podman)(?:-compose)?: (?:command )?not found)",
    re.IGNORECASE,
)

CONTAINER_RUNTIME_NOTE = (
    "The CLike eval sandbox has no container runtime (docker, podman, compose): this check cannot run "
    "there. Not a defect of the code: make it non-blocking (\"blocking\": false) in ci/LTC.json, keep it "
    "runnable on the developer's machine (ci/HOWTO.md)."
)


def container_runtime_missing(text: str) -> bool:
    return bool(_NO_CONTAINER_RUNTIME.search(text or ""))


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


# Memory: the kernel slows the processes down at the limit and kills some (OOM) without any
# "ENOMEM" in their output; checks then time out (B2B REQ-026: 9 million hits of a 3 GB limit, two
# OOM kills, every failure a timeout the repair could not fix). Read from the cgroup counters.
MEMORY_HINT = (
    "Give the eval sandbox more memory: CLIKE_EVAL_SANDBOX_MEM_LIMIT in docker/.env (and the Podman or "
    "Docker machine memory, e.g. `podman machine set --memory 16384`), or fewer regressions side by side "
    "(CLIKE_EVAL_REGRESSION_WORKERS=1); then restart the services and run again."
)
MEMORY_LIMIT_HITS = int(os.getenv("CLIKE_EVAL_MEMORY_LIMIT_HITS", "1000") or 1000)


def memory_events(cgroup_root: Path = Path("/sys/fs/cgroup")) -> Dict[str, int]:
    """The cgroup v2 memory counters (oom_kill, max: times the limit was hit); {} when unknown."""
    try:
        lines = (cgroup_root / "memory.events").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    events: Dict[str, int] = {}
    for line in lines:
        name, _, value = line.partition(" ")
        if value.strip().isdigit():
            events[name] = int(value)
    return events


def memory_exhaustion(before: Dict[str, int], after: Dict[str, int]) -> Optional[str]:
    """Why memory, not the code, explains a check that failed between the two readings, or None."""
    if not before or not after:
        return None
    killed = after.get("oom_kill", 0) - before.get("oom_kill", 0)
    hits = after.get("max", 0) - before.get("max", 0)
    if killed > 0:
        return f"{killed} process(es) killed by the kernel for lack of memory during this check"
    if hits >= MEMORY_LIMIT_HITS:
        return f"the sandbox hit its memory limit {hits} times during this check (processes slowed to time-outs)"
    return None


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


# --- eval disk: the eval directories are caches (composed workspaces, node_modules, venvs) ------

_REQ_DIR = re.compile(r"^REQ-[\w-]+$")
KEEP_REQ_DIRS = int(os.getenv("CLIKE_EVAL_KEEP_REQS", "3") or 3)
MIN_FREE_GB = float(os.getenv("CLIKE_EVAL_MIN_FREE_GB", "10") or 10)


def _free_bytes(path: Path) -> int:
    try:
        stat = os.statvfs(path)
    except (OSError, AttributeError):
        return -1
    return stat.f_bavail * stat.f_frsize


def _last_used(path: Path) -> float:
    """When an eval directory was last used: its newest direct entry (cheap, no full walk)."""
    times = [path.stat().st_mtime]
    try:
        times += [child.stat().st_mtime for child in path.iterdir()]
    except OSError:
        pass
    return max(times)


def prune_eval_dirs(
    project_dir: Path, current_req: Optional[str], *, keep: int = KEEP_REQ_DIRS, min_free_gb: float = MIN_FREE_GB,
    remove=None,
) -> list:
    """Free the eval volume before an eval; returns the directories removed.

    Each REQ eval directory holds a composed workspace per regression REQ and per service, each
    with its own installs (1 GB with node_modules): kept for every REQ they grew with the square
    of the REQs (48 GB for 13 REQs). They are rebuilt when needed, so CLike keeps the ``keep`` REQ
    directories of this project used last (and the current one), and when the volume has less
    than ``min_free_gb`` free, removes the least recently used ones of any project.
    Only under CLIKE_EVAL_BASE_DIR (the sandbox volume), never a project's runs/.
    """
    import shutil

    base = os.getenv("CLIKE_EVAL_BASE_DIR", "").strip()
    try:
        root = Path(base).resolve() if base else None
        project_dir = project_dir.resolve()
    except OSError:
        return []
    if root is None or project_dir.parent != root:
        return []
    remove = remove or (lambda p: shutil.rmtree(p, ignore_errors=True))

    def req_dirs(project: Path) -> list:
        try:
            dirs = [d for d in project.iterdir() if d.is_dir() and _REQ_DIR.match(d.name) and d.name != current_req]
        except OSError:
            return []
        return sorted(dirs, key=_last_used, reverse=True)  # most recent first

    removed = []
    for stale in req_dirs(project_dir)[max(0, keep - (1 if current_req else 0)):]:
        remove(stale)
        removed.append(str(stale))
    min_free = int(min_free_gb * 1024 ** 3)
    if 0 <= _free_bytes(root) < min_free:
        others = []
        for project in (p for p in root.iterdir() if p.is_dir()):
            others += req_dirs(project)
        for stale in sorted(others, key=_last_used):  # least recent first
            if _free_bytes(root) >= min_free:
                break
            remove(stale)
            removed.append(str(stale))
    return removed


def disk_preflight(path: Path, min_free_gb: float = 2.0) -> Optional[str]:
    """Why the eval volume cannot hold an eval now (even after pruning), or None."""
    free = _free_bytes(path)
    if free < 0 or free >= min_free_gb * 1024 ** 3:
        return None
    return (
        f"The eval volume has only {free / 1024 ** 3:.1f} GB free: installs and builds would fail with ENOSPC. "
        "This is not a defect of the REQ. Free the Podman machine disk (`podman image prune -a`, `podman system df`) "
        "and run again."
    )
