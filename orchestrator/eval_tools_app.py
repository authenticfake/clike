"""Eval tools service: installs native tools into the volume the eval sandbox mounts read-only.

Only the orchestrator reaches it (its own network, not the sandbox's): a check cannot install
anything. It holds no credentials, installs conda-forge packages only (no scripts, no URLs) with
micromamba into ``/opt/clike-tools/env`` and exposes the requested programs as small wrappers in
``/opt/clike-tools/bin`` (the sandbox appends that directory to the PATH of the checks, so a tool
never shadows the image's own Python or Node). What is installed, with versions, is recorded in
``/opt/clike-tools/installed.json``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import eval_tools
from eval_runner import _SECRET_ENV_NAME_RE

logging.basicConfig(level=logging.INFO, format="[eval-tools] | %(levelname)-8s %(message)s", force=True)
log = logging.getLogger("eval-tools")

_leaked = sorted(k for k in os.environ if _SECRET_ENV_NAME_RE.search(k))
if _leaked:
    raise RuntimeError(f"eval tools service refuses to start with credentials in its environment: {_leaked}")

ROOT = Path(os.getenv("CLIKE_EVAL_TOOLS_ROOT", "/opt/clike-tools"))
ENV = ROOT / "env"
BIN = ROOT / "bin"
STATE = ROOT / "installed.json"
CHANNEL = "conda-forge"
TIMEOUT_S = int(os.getenv("CLIKE_EVAL_TOOLS_TIMEOUT_S", "1500") or 1500)

app = FastAPI(title="CLike eval tools", docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()


class InstallRequest(BaseModel):
    packages: List[str]
    binaries: List[str]
    tools: List[str] = []


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tools": {}, "packages": {}}


def _versions() -> dict:
    """Installed conda packages and their versions (micromamba list)."""
    proc = subprocess.run(
        ["micromamba", "list", "-p", str(ENV), "--json"], capture_output=True, text=True, timeout=120, check=False
    )
    try:
        data = json.loads(proc.stdout or "[]")
        items = data.get("packages", []) if isinstance(data, dict) else data  # micromamba 2: {"packages": [...]}
        return {p["name"]: p["version"] for p in items}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}


def _write_wrapper(binary: str) -> bool:
    target = ENV / "bin" / binary
    if not target.is_file():
        return False
    BIN.mkdir(parents=True, exist_ok=True)
    wrapper = BIN / binary
    tmp = wrapper.with_suffix(".tmp")
    tmp.write_text(f'#!/bin/sh\nexec "{target}" "$@"\n', encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(wrapper)
    return True


@app.get("/health")
def health():
    return {"status": "ok", "service": "eval-tools", "installed": sorted((_state().get("tools") or {}).keys())}


@app.get("/installed")
def installed():
    return _state()


@app.post("/install")
def install(req: InstallRequest):
    packages = [p for p in req.packages if eval_tools.package_spec_ok(p)]
    if not packages or len(packages) != len(req.packages) or len(packages) > 20:
        raise HTTPException(status_code=400, detail="invalid package list")
    binaries = [b for b in req.binaries if eval_tools._TOOL_NAME.match(b) and "@" not in b][:60]
    with _lock:
        started = time.monotonic()
        action = "install" if (ENV / "conda-meta").is_dir() else "create"
        cmd = [
            "micromamba", action, "-y", "-p", str(ENV), "-r", str(ROOT / "mamba"),
            "-c", CHANNEL, "--override-channels", "--strict-channel-priority", *packages,
        ]
        log.info("%s %s", action, " ".join(packages))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail=f"installation took more than {TIMEOUT_S} s") from None
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-3000:]
            log.warning("install failed: %s", detail[-500:])
            raise HTTPException(status_code=422, detail=f"micromamba {action} failed: {detail}")
        exposed = [b for b in binaries if _write_wrapper(b)]
        versions = _versions()
        state = _state()
        now = time.time()
        for tool in req.tools or packages:
            state.setdefault("tools", {})[tool] = {"packages": packages, "binaries": exposed, "at": now}
        state["packages"] = {p.split("=")[0]: versions.get(p.split("=")[0]) for p in {*state.get("packages", {}), *packages}}
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(STATE)
        log.info("installed %s in %.0fs; exposed %s", " ".join(packages), time.monotonic() - started, " ".join(exposed))
        return {
            "installed": req.tools or packages,
            "binaries": exposed,
            "missing_binaries": [b for b in binaries if b not in exposed],
            "versions": {p.split("=")[0]: versions.get(p.split("=")[0]) for p in packages},
            "seconds": round(time.monotonic() - started),
        }
