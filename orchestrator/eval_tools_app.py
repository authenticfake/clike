"""Eval tools service: installs native tools into the volume the eval sandbox mounts read-only.

Only the orchestrator reaches it (its own network, not the sandbox's): a check cannot install
anything. It holds no credentials and installs, per tool, into its own environment
``/opt/clike-tools/envs/<tool>`` (two tools never change each other's versions; micromamba's
package cache keeps them small):

* conda-forge packages (micromamba, no scripts, no URLs);
* plus PyPI packages for CLIs distributed there (``pip``: azure-cli, cfn-lint…), in that env's Python;
* or a vendor archive (``download``: an https URL per platform with its sha256, verified before it
  is unpacked, never executed by CLike).

The requested programs are exposed as small wrappers in ``/opt/clike-tools/bin``, which the sandbox
appends to the PATH of the checks (never before the image's own programs). ``installed.json``
records, per tool, the top-level versions and an exact lock (micromamba explicit spec, pip freeze,
archive digest): ``/restore`` rebuilds the same environments on a new volume, ``/update`` rebuilds
them at the latest versions and reports what changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

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
ENVS = ROOT / "envs"
BIN = ROOT / "bin"
STATE = ROOT / "installed.json"
CHANNEL = "conda-forge"
TIMEOUT_S = int(os.getenv("CLIKE_EVAL_TOOLS_TIMEOUT_S", "1500") or 1500)
MAX_DOWNLOAD_BYTES = int(os.getenv("CLIKE_EVAL_TOOLS_MAX_DOWNLOAD_MB", "1500") or 1500) * 1024 * 1024
_PIP_SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-\[\],]{0,80}(?:(?:==|>=|<=|~=|!=|<|>)[A-Za-z0-9_.*+!-]{1,40})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

app = FastAPI(title="CLike eval tools", docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()


class ToolSpec(BaseModel):
    name: str
    packages: List[str] = []
    pip: List[str] = []
    download: Dict[str, Dict[str, str]] = {}
    binaries: List[str] = []


class InstallRequest(BaseModel):
    tools: List[ToolSpec]


class UpdateRequest(BaseModel):
    tools: List[str] = []  # empty: every installed tool


class RestoreRequest(BaseModel):
    lock: Dict[str, Any] = {}


# --- state -------------------------------------------------------------------------------

def _state() -> Dict[str, Any]:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tools": {}}
    return data if isinstance(data, dict) and isinstance(data.get("tools"), dict) else {"tools": {}}


def _save(state: Dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def _env_dir(name: str) -> Path:
    return ENVS / re.sub(r"[^A-Za-z0-9_.+-]", "-", name)


def _platform() -> str:
    return "linux-aarch64" if platform.machine().lower() in {"aarch64", "arm64"} else "linux-64"


def _run(cmd: List[str], timeout: int = TIMEOUT_S) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"{cmd[0]} took more than {timeout} s") from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[-3000:]
        log.warning("%s failed: %s", " ".join(cmd[:3]), detail[-400:])
        raise HTTPException(status_code=422, detail=f"{' '.join(cmd[:2])} failed: {detail}")
    return proc


# --- building one tool environment ----------------------------------------------------------

def _validate(spec: ToolSpec) -> None:
    if not eval_tools._TOOL_NAME.match(spec.name):
        raise HTTPException(status_code=400, detail=f"invalid tool name: {spec.name}")
    if not spec.packages and not spec.download:
        raise HTTPException(status_code=400, detail=f"{spec.name}: no packages and no download")
    if not all(eval_tools.package_spec_ok(p) for p in spec.packages) or len(spec.packages) > 20:
        raise HTTPException(status_code=400, detail=f"{spec.name}: invalid conda package list")
    if not all(_PIP_SPEC.match(p) for p in spec.pip) or len(spec.pip) > 20:
        raise HTTPException(status_code=400, detail=f"{spec.name}: invalid pip package list")
    for plat, item in spec.download.items():
        if not str(item.get("url", "")).startswith("https://") or not _SHA256.match(str(item.get("sha256", "")).lower()):
            raise HTTPException(status_code=400, detail=f"{spec.name}: download {plat} needs an https url and a sha256")


def _fetch(url: str, sha256: str, dest: Path) -> None:
    """Download over https into dest, refusing more than MAX_DOWNLOAD_BYTES and a wrong digest."""
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=120) as response, dest.open("wb") as out:  # noqa: S310 - https only, validated
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"download larger than {MAX_DOWNLOAD_BYTES // 2**20} MB")
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != sha256.lower():
        raise HTTPException(status_code=422, detail=f"sha256 mismatch for {url}: the archive is refused")


def _unpack(archive: Path, target: Path, binaries: List[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter="data")  # no absolute paths, links out of target or devices
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                path = (target / member.filename).resolve()
                if not str(path).startswith(str(root) + os.sep) and path != root:
                    raise HTTPException(status_code=422, detail=f"unsafe path in archive: {member.filename}")
                zf.extract(member, target)
                mode = (member.external_attr >> 16) & 0o777
                if mode and path.is_file():
                    path.chmod(mode)
    else:  # a single executable
        (target / "bin").mkdir(exist_ok=True)
        shutil.copy2(archive, target / "bin" / (binaries[0] if binaries else archive.name))
        (target / "bin" / (binaries[0] if binaries else archive.name)).chmod(0o755)


def _find_binary(env: Path, binary: str) -> Optional[Path]:
    direct = env / "bin" / binary
    if direct.is_file():
        return direct
    found = sorted(env.rglob(binary), key=lambda p: ("/bin/" not in str(p), len(p.parts)))
    return next((p for p in found if p.is_file()), None)


def _versions(env: Path) -> Dict[str, str]:
    proc = subprocess.run(["micromamba", "list", "-p", str(env), "--json"], capture_output=True, text=True, timeout=120, check=False)
    try:
        data = json.loads(proc.stdout or "[]")
        items = data.get("packages", []) if isinstance(data, dict) else data  # micromamba 2: {"packages": [...]}
        return {p["name"]: p["version"] for p in items}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}


def _build(spec: ToolSpec, env: Path, lock: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the tool's environment at `env` (from the exact lock when given); returns its record."""
    record: Dict[str, Any] = {"packages": spec.packages, "pip": spec.pip, "download": spec.download, "binaries": spec.binaries}
    if spec.download:
        item = spec.download.get(_platform())
        if not item:
            raise HTTPException(status_code=422, detail=f"{spec.name}: no download for {_platform()}")
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            archive = Path(tmp) / "archive"
            _fetch(item["url"], item["sha256"], archive)
            _unpack(archive, env, spec.binaries)
        record["versions"] = {spec.name: item.get("version", "")}
        record["lock"] = {"download": {_platform(): item}}
        return record
    conda_lock = (lock or {}).get("explicit")
    if conda_lock:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=ROOT, delete=False) as f:
            f.write(conda_lock)
        try:
            _run(["micromamba", "create", "-y", "-p", str(env), "-r", str(ROOT / "mamba"), "--file", f.name])
        finally:
            Path(f.name).unlink(missing_ok=True)
    else:
        packages = [*spec.packages, *(["python=3.12", "pip"] if spec.pip and not any(p.startswith("python") for p in spec.packages) else [])]
        _run(["micromamba", "create", "-y", "-p", str(env), "-r", str(ROOT / "mamba"), "-c", CHANNEL,
              "--override-channels", "--strict-channel-priority", *packages])
    if spec.pip:
        pip_lock = (lock or {}).get("pip")
        pip_args = pip_lock if pip_lock else spec.pip
        _run([str(env / "bin" / "python"), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", *pip_args])
    versions = _versions(env)
    explicit = subprocess.run(["micromamba", "env", "export", "-p", str(env), "--explicit", "--md5"],
                              capture_output=True, text=True, timeout=120, check=False).stdout
    pip_freeze = []
    if spec.pip:
        frozen = subprocess.run([str(env / "bin" / "python"), "-m", "pip", "freeze", "--disable-pip-version-check"],
                                capture_output=True, text=True, timeout=120, check=False).stdout
        pip_freeze = [line for line in frozen.splitlines() if "==" in line]
        versions.update({line.split("==")[0].lower(): line.split("==")[1] for line in pip_freeze})
    top = [re.split(r"[=<>!~]", p, 1)[0].lower() for p in [*spec.packages, *spec.pip]]
    record["versions"] = {name: versions.get(name) for name in top if versions.get(name)}
    record["lock"] = {"explicit": explicit, "pip": pip_freeze, "platform": _platform()}
    return record


def _expose(name: str, env: Path, binaries: List[str]) -> List[str]:
    exposed = []
    BIN.mkdir(parents=True, exist_ok=True)
    for binary in binaries:
        target = _find_binary(env, binary)
        if not target:
            continue
        if not os.access(target, os.X_OK):
            target.chmod(target.stat().st_mode | 0o755)
        wrapper = BIN / binary
        tmp = wrapper.with_suffix(".tmp")
        tmp.write_text(f'#!/bin/sh\nexec "{target}" "$@"\n', encoding="utf-8")
        tmp.chmod(0o755)
        tmp.replace(wrapper)
        exposed.append(binary)
    return exposed


def _install_one(spec: ToolSpec, lock: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the tool at its final path (conda environments hold their prefix, so they are never
    moved); the previous environment is set aside and put back if the build fails."""
    env = _env_dir(spec.name)
    ENVS.mkdir(parents=True, exist_ok=True)
    old = env.with_name(env.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if env.exists():
        env.rename(old)
    try:
        record = _build(spec, env, lock)
    except Exception:
        shutil.rmtree(env, ignore_errors=True)
        if old.exists():
            old.rename(env)
        raise
    shutil.rmtree(old, ignore_errors=True)
    record["exposed"] = _expose(spec.name, env, spec.binaries)
    record["at"] = time.time()
    _drop_legacy_env()
    return record


def _drop_legacy_env() -> None:
    """The first tools layout had one shared environment (/opt/clike-tools/env): removed once no
    wrapper uses it any more (every tool rebuilt in its own environment by /update)."""
    legacy = ROOT / "env"
    if not legacy.is_dir():
        return
    needle = str(legacy) + "/"
    for wrapper in BIN.glob("*"):
        try:
            if needle in wrapper.read_text(encoding="utf-8", errors="ignore"):
                return
        except OSError:
            continue
    shutil.rmtree(legacy, ignore_errors=True)
    log.info("removed the legacy shared tools environment")


# --- API -------------------------------------------------------------------------------------

@app.get("/health")
def health():
    state = _state()
    return {"status": "ok", "service": "eval-tools", "installed": sorted(state["tools"]), "updated_at": state.get("updated_at")}


@app.get("/installed")
def installed():
    state = _state()
    return {**state, "tools": {name: {k: v for k, v in rec.items() if k != "lock"} for name, rec in state["tools"].items()}}


@app.get("/lock")
def lock():
    """What /restore needs to rebuild the same environments (the orchestrator keeps a copy)."""
    return {name: {"spec": {k: rec.get(k) for k in ("packages", "pip", "download", "binaries")}, "lock": rec.get("lock")}
            for name, rec in _state()["tools"].items()}


@app.post("/install")
def install(req: InstallRequest):
    if not req.tools or len(req.tools) > 20:
        raise HTTPException(status_code=400, detail="1 to 20 tools")
    for spec in req.tools:
        _validate(spec)
    with _lock:
        started = time.monotonic()
        state = _state()
        results = {}
        for spec in req.tools:
            log.info("install %s", spec.name)
            state["tools"][spec.name] = _install_one(spec)
            results[spec.name] = state["tools"][spec.name]
            _save(state)
        return {
            "installed": list(results),
            "binaries": sorted({b for r in results.values() for b in r["exposed"]}),
            "missing_binaries": sorted({b for s in req.tools for b in s.binaries} - {b for r in results.values() for b in r["exposed"]}),
            "versions": {n: r.get("versions", {}) for n, r in results.items()},
            "seconds": round(time.monotonic() - started),
        }


@app.post("/update")
def update(req: UpdateRequest):
    """Rebuild tools at the latest versions their specs allow; report what changed."""
    with _lock:
        state = _state()
        names = req.tools or sorted(state["tools"])
        changes: Dict[str, Any] = {}
        failed: Dict[str, str] = {}
        for name in names:
            rec = state["tools"].get(name)
            if not rec:
                failed[name] = "not installed"
                continue
            before = dict(rec.get("versions") or {})
            spec = ToolSpec(name=name, **{k: rec.get(k) or ([] if k != "download" else {}) for k in ("packages", "pip", "download", "binaries")})
            try:
                state["tools"][name] = _install_one(spec)
            except HTTPException as exc:
                failed[name] = str(exc.detail)[:500]
                continue
            after = state["tools"][name].get("versions") or {}
            diff = {pkg: [before.get(pkg), ver] for pkg, ver in after.items() if before.get(pkg) != ver}
            if diff:
                changes[name] = diff
            _save(state)
        state["updated_at"] = time.time()
        _save(state)
        return {"updated": [n for n in names if n not in failed], "changes": changes, "failed": failed, "updated_at": state["updated_at"]}


@app.post("/restore")
def restore(req: RestoreRequest):
    """Rebuild, from a lock, the tools this volume does not have (a new machine, a new volume)."""
    with _lock:
        state = _state()
        restored, failed = [], {}
        for name, item in (req.lock or {}).items():
            if name in state["tools"] or not isinstance(item, dict):
                continue
            try:
                spec = ToolSpec(name=name, **{k: v for k, v in (item.get("spec") or {}).items() if v is not None})
                _validate(spec)
                lock_data = item.get("lock") or {}
                if lock_data.get("platform") and lock_data.get("platform") != _platform():
                    lock_data = {}  # another architecture: resolve again from the spec
                state["tools"][name] = _install_one(spec, lock_data)
                restored.append(name)
                _save(state)
            except HTTPException as exc:
                failed[name] = str(exc.detail)[:500]
        return {"restored": restored, "failed": failed}
