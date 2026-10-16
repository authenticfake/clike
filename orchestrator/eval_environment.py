"""Eval environment provisioning: the values the LTC checks need, created by CLike in the sandbox.

The KIT declares in ``ci/LTC.json``:

    "environment": {
      "required_variables": [
        {"name": "APP_TEST_DATABASE_URL", "provision": "postgres_database", "scheme": "postgresql+psycopg"},
        {"name": "APP_TEST_SESSION", "provision": "token"},
        {"name": "APP_TEST_CLIENT_ID", "provision": "uuid"},
        {"name": "APP_SESSION_EXPIRES_AT", "provision": "timestamp", "offset_s": 3600},
        {"name": "APP_LOCAL_SESSION", "provision": "template", "value": "${APP_TEST_SESSION}"},
        {"name": "APP_TEST_API_URL", "provision": "service", "service": "req001-api"},
        {"name": "PROVIDER_API_URL", "provision": "external", "purpose": "..."}
      ]
    },
    "services": [{
      "name": "req001-api", "req": "REQ-001", "cwd": "src",
      "setup": ["python -m alembic -c alembic.ini upgrade head"],
      "start": "python -m backend.main",
      "env": {"APP_DATABASE_URL": "${APP_TEST_DATABASE_URL}", "APP_PORT": "${PORT}"},
      "ready": {"http_path": "/health"},
      "exports": {"APP_TEST_API_URL": "http://127.0.0.1:${PORT}"}
    }]

* token / uuid / timestamp / template: generated per eval run.
* postgres_database: a disposable database per REQ (dropped and created again at every run) on the
  server of ``CLIKE_EVAL_POSTGRES_URL`` (docker/eval.env, an admin URL from the sandbox).
* service: started from the composed source and environment of another REQ (or of the candidate,
  without ``req``) before the checks, on a free loopback port, and stopped after them.
* external: only the developer can give it (docker/eval.env); a missing one blocks the eval.

A value already in the environment (docker/eval.env) always wins over provisioning. KITs written
before this contract (free-form ``environment: {NAME: "Required ..."}``) are understood too; a
``*DATABASE_URL`` described as PostgreSQL is provisioned like ``postgres_database``.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

ADMIN_URL_VAR = "CLIKE_EVAL_POSTGRES_URL"
GENERATED = {"token", "uuid", "timestamp", "template"}
PROVISIONS = GENERATED | {"postgres_database", "service", "external"}

_ENV_VAR_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
_REQUIRED_WORD_RE = re.compile(r"\b(required|requires|must|needed|mandatory)\b", re.IGNORECASE)
_OPTIONAL_WORD_RE = re.compile(r"\boptional\b", re.IGNORECASE)
_TEMPLATE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DEFAULT_SERVICE_TIMEOUT_S = 90
_LOG_TAIL = 3000


@dataclass
class VariableSpec:
    name: str
    purpose: str = ""
    example: str = ""
    provision: str = ""  # "" = not declared (external unless inferred)
    options: Dict[str, Any] = field(default_factory=dict)

    def effective_provision(self) -> str:
        if self.provision in PROVISIONS:
            return self.provision
        if self.provision.startswith("service"):
            return "service"
        hint = f"{self.purpose} {self.example}".lower()
        if self.name.endswith("DATABASE_URL") and ("postgres" in hint or not hint.strip()):
            return "postgres_database"
        return "external"


class ProvisionError(Exception):
    pass


# --- declaration --------------------------------------------------------------------------------

def _ltc_set_names(ltc: Dict[str, Any]) -> set:
    """Names the LTC itself sets (top-level env and per-check env)."""
    names = set(ltc.get("env") or {}) if isinstance(ltc.get("env"), dict) else set()
    for key in ("checks", "cases", "commands", "steps"):
        for item in ltc.get(key) or []:
            if isinstance(item, dict) and isinstance(item.get("env"), dict):
                names.update(item["env"])
    return names


def variable_specs(ltc: Dict[str, Any]) -> List[VariableSpec]:
    """Variables the LTC declares the checks need from the environment (CLike's own CLIKE_*
    variables, values the LTC sets itself and entries marked optional excluded)."""
    env = ltc.get("environment") if isinstance(ltc, dict) else None
    found: Dict[str, VariableSpec] = {}

    def add(item: Any, optional: bool = False, **defaults: Any) -> None:
        if isinstance(item, dict):
            name = str(item.get("name") or defaults.get("name") or "").strip()
            optional = optional or bool(item.get("optional")) or item.get("required") is False
            options = {k: v for k, v in item.items() if k not in {"name", "purpose", "description", "example", "provision"}}
            spec = VariableSpec(
                name=name,
                purpose=str(item.get("purpose") or item.get("description") or defaults.get("purpose") or "").strip(),
                example=str(item.get("example") or "").strip(),
                provision=str(item.get("provision") or "").strip().lower(),
                options=options,
            )
        else:
            spec = VariableSpec(name=str(item or "").strip(), purpose=str(defaults.get("purpose") or ""))
        if not _ENV_VAR_NAME_RE.match(spec.name) or spec.name.startswith("CLIKE_") or optional:
            return
        found.setdefault(spec.name, spec)

    if isinstance(env, dict):
        for item in env.get("required_variables") or []:
            add(item)
        for name, value in env.items():
            if name == "required_variables":
                continue
            if isinstance(value, dict):
                add({"name": name, **value})
            elif isinstance(value, str) and _REQUIRED_WORD_RE.search(value) and not _OPTIONAL_WORD_RE.search(value):
                add(name, purpose=value)
    elif isinstance(env, list):
        for item in env:
            add(item)
    provided = _ltc_set_names(ltc)
    return [spec for name, spec in found.items() if name not in provided]


def service_specs(ltc: Dict[str, Any]) -> List[Dict[str, Any]]:
    services = ltc.get("services") if isinstance(ltc, dict) else None
    return [s for s in (services or []) if isinstance(s, dict) and str(s.get("name") or "").strip() and s.get("start")]


def service_exports(ltc: Dict[str, Any]) -> set:
    return {name for svc in service_specs(ltc) for name in (svc.get("exports") or {})}


# --- pre-check ----------------------------------------------------------------------------------

def missing_variables(ltc: Dict[str, Any], environ: Dict[str, str]) -> List[Tuple[VariableSpec, str]]:
    """(spec, how to provide it) of every required variable CLike can neither find nor create."""
    exports = service_exports(ltc)
    missing = []
    for spec in variable_specs(ltc):
        if str(environ.get(spec.name, "")).strip():
            continue
        provision = spec.effective_provision()
        if provision in GENERATED:
            continue
        if provision == "postgres_database":
            if str(environ.get(ADMIN_URL_VAR, "")).strip():
                continue
            missing.append((spec, (
                f"set {ADMIN_URL_VAR}=postgresql://<user>@host.containers.internal:5432/postgres in "
                "docker/eval.env once: CLike then creates a disposable database per REQ"
            )))
            continue
        if provision == "service" and spec.name in exports:
            continue
        if provision == "service":
            missing.append((spec, "no service in ci/LTC.json `services` exports it"))
            continue
        missing.append((spec, "external value: add it to docker/eval.env"))
    return missing


def repairable(missing: List[Tuple[VariableSpec, str]]) -> bool:
    """A KIT repair can fix it (declare how CLike provisions the variable) unless every missing
    variable is explicitly external or only the developer's database server is missing."""
    return any(
        spec.provision != "external" and spec.effective_provision() not in {"postgres_database"}
        for spec, _ in missing
    )


# --- provisioning -------------------------------------------------------------------------------

def render(template: Any, values: Dict[str, str]) -> str:
    def sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise ProvisionError(f"unknown variable ${{{name}}}")
        return values[name]

    return _TEMPLATE_RE.sub(sub, str(template))


def _database_name(project_key: str, req_id: str, var: str) -> str:
    digest = hashlib.sha1(var.encode()).hexdigest()[:6]
    base = re.sub(r"[^a-z0-9_]+", "_", f"clike_{project_key}_{req_id}".lower())[:50]
    return f"{base}_{digest}"


def _scheme_for(spec: VariableSpec, admin_scheme: str) -> str:
    scheme = str(spec.options.get("scheme") or "").strip()
    if not scheme and "://" in spec.example:
        scheme = spec.example.split("://", 1)[0]
    if not scheme and "://" in spec.purpose:
        scheme = spec.purpose.split("://", 1)[0].split()[-1]
    return scheme or admin_scheme or "postgresql"


def create_postgres_database(admin_url: str, database: str) -> None:
    import psycopg

    parts = urlsplit(admin_url)
    dsn = urlunsplit(("postgresql", parts.netloc, parts.path or "/postgres", parts.query, ""))
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{database}"')


def provision_postgres(spec: VariableSpec, admin_url: str, project_key: str, req_id: str,
                       create: Callable[[str, str], None] = create_postgres_database) -> str:
    database = str(spec.options.get("database") or _database_name(project_key, req_id, spec.name))
    create(admin_url, database)
    parts = urlsplit(admin_url)
    return urlunsplit((_scheme_for(spec, parts.scheme.split("+")[0]), parts.netloc, f"/{database}", parts.query, ""))


def generate(spec: VariableSpec, values: Dict[str, str]) -> Optional[str]:
    provision = spec.effective_provision()
    if provision == "token":
        return secrets.token_urlsafe(int(spec.options.get("bytes") or 32))
    if provision == "uuid":
        return str(uuid.uuid4())
    if provision == "timestamp":
        moment = datetime.now(timezone.utc) + timedelta(seconds=float(spec.options.get("offset_s") or 0))
        return moment.isoformat()
    if provision == "template":
        return render(spec.options.get("value") or "", values)
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class RunningService:
    name: str
    proc: subprocess.Popen
    log_path: Path


def _tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-_LOG_TAIL:]
    except OSError:
        return ""


def wait_ready(svc: Dict[str, Any], port: int, proc: subprocess.Popen, timeout_s: float) -> Optional[str]:
    """None when the service answers, else why not."""
    ready = svc.get("ready") or {}
    path = str(ready.get("http_path") or ready.get("path") or "").strip() if isinstance(ready, dict) else ""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return f"exited with code {proc.returncode} before it was ready"
        try:
            if path:
                url = f"http://127.0.0.1:{port}/{path.lstrip('/')}"
                try:
                    with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 - loopback only
                        if resp.status < 500:
                            return None
                except urllib.error.HTTPError as exc:
                    if exc.code < 500:
                        return None
            else:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return None
        except OSError:
            pass
        time.sleep(0.5)
    return f"not ready after {timeout_s:.0f}s"


def start_service(svc: Dict[str, Any], *, workdir: Path, env: Dict[str, str], values: Dict[str, str],
                  log_dir: Path, run_setup: Callable[[str, str, Path, Dict[str, str]], Tuple[bool, str]]
                  ) -> Tuple[Optional[RunningService], Dict[str, str], str]:
    """Start one service: setup commands, then the start command on a free port.

    Returns (running service or None, exported values, report text)."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(svc["name"]))
    port = free_port()
    scope = {**values, "PORT": str(port), "HOST": "127.0.0.1"}
    svc_env = {**env, **{k: render(v, scope) for k, v in (svc.get("env") or {}).items()}, "PORT": str(port)}
    if svc.get("port_env"):
        svc_env[str(svc["port_env"])] = str(port)
    for i, cmd in enumerate(svc.get("setup") or [], start=1):
        ok, output = run_setup(f"{name}::setup::{i}", render(cmd, scope), workdir, svc_env)
        if not ok:
            return None, {}, f"setup `{cmd}` failed:\n{output[-_LOG_TAIL:]}"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(  # noqa: S602 - model-authored command, run in the eval sandbox like the checks
        render(svc["start"], scope), shell=True, cwd=str(workdir), env=svc_env,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    log.close()
    started = time.monotonic()
    why = wait_ready(svc, port, proc, float(svc.get("timeout_s") or _DEFAULT_SERVICE_TIMEOUT_S))
    if why:
        stop_process(proc)
        return None, {}, f"`{svc['start']}` {why}. Log:\n{_tail(log_path)}"
    exports = {k: render(v, scope) for k, v in (svc.get("exports") or {}).items()}
    names = ", ".join(sorted(exports)) or "nothing"
    return RunningService(name, proc, log_path), exports, (
        f"started on 127.0.0.1:{port} in {time.monotonic() - started:.1f}s; exports {names}; log {log_path}"
    )


def stop_process(proc: subprocess.Popen) -> None:
    import os
    import signal

    # The group, even when its leader exited: `npm start` may have left the server it launched.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # what ignored SIGTERM
    except Exception:
        pass
