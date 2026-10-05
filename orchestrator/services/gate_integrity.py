"""Gate integrity (WP6): acceptance-criteria lock, tamper detection, audited override.

The *acceptance surface* of a REQ is everything under ``runs/kit/<REQ>/test/`` and
``runs/kit/<REQ>/ci/`` (LTC profile, CI scripts, requirements, tests).

* A lock (sha256 per file) is recorded server-side the first time the REQ is
  evaluated after a KIT generation — before any local-agent eval pre-pass — in
  ``CLIKE_STATE_DIR``, which agents cannot write.
* Every eval/gate compares the current surface with the lock. Removed or
  modified files, LTC checks removed or made non-blocking, and newly added skip
  markers block the gate. Added files are reported but do not block.
* A new ``/kit`` for the REQ starts a new generation and invalidates the lock.
* A manual gate override requires a reason and is appended to an audit log
  together with a digest of the REQ artifacts.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import runs_dir
from utils.safe_paths import is_within_any, safe_segment, validate_req_id

LOCK_SCHEMA = "clike.acceptance_lock.v1"
_SURFACE_DIRS = ("test", "ci")
_MAX_FILES = 2000
_MAX_FILE_BYTES = 5 * 1024 * 1024

# Markers that disable or skip tests in common frameworks.
_SKIP_MARKER_RE = re.compile(
    r"(@pytest\.mark\.(skip|xfail)\b|pytest\.skip\(|unittest\.skip|@unittest\.skip"
    r"|\b(it|test|describe)\.(skip|todo)\s*\(|\bx(it|describe|test)\s*\("
    r"|@Disabled\b|@Ignore\b|\bt\.Skip(Now|f)?\s*\(|#\[ignore\])"
)


def allowed_eval_roots() -> List[Path]:
    """Roots eval/gate may operate on: DEV_FOLDER (host projects dir) + CLIKE_EVAL_ALLOWED_ROOTS."""
    roots: List[Path] = []
    dev = os.getenv("DEV_FOLDER", "").strip()
    if dev:
        roots.append(Path(dev))
    for raw in os.getenv("CLIKE_EVAL_ALLOWED_ROOTS", "").split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw.strip()))
    return roots


def is_eval_project(project_root: Path) -> bool:
    roots = allowed_eval_roots()
    return bool(roots) and Path(project_root).is_dir() and is_within_any(project_root, roots)


def state_dir() -> Path:
    raw = os.getenv("CLIKE_STATE_DIR") or str(runs_dir() / "state")
    path = Path(raw).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_key(project_root: Path) -> str:
    resolved = str(Path(project_root).resolve())
    return f"{safe_segment(Path(resolved).name, 'project')}-{hashlib.sha256(resolved.encode()).hexdigest()[:12]}"


def _req_state_path(project_root: Path, req_id: str, kind: str) -> Path:
    req = validate_req_id(req_id)
    path = state_dir() / "acceptance" / _project_key(project_root) / f"{req}.{kind}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kit_root(project_root: Path, req_id: str) -> Path:
    return Path(project_root).resolve() / "runs" / "kit" / validate_req_id(req_id)


def surface_manifest(project_root: Path, req_id: str) -> Dict[str, str]:
    """sha256 of every regular file of the acceptance surface (relative POSIX path -> digest)."""
    root = kit_root(project_root, req_id)
    files: Dict[str, str] = {}
    for sub in _SURFACE_DIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if len(files) >= _MAX_FILES:
                break
            if path.is_symlink() or not path.is_file():
                continue
            if any(part in {"node_modules", "__pycache__", ".pytest_cache", ".venv"} for part in path.parts):
                continue
            rel = path.relative_to(root).as_posix()
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    files[rel] = "oversize:" + str(path.stat().st_size)
                    continue
                files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
    return files


def _snapshot_texts(project_root: Path, req_id: str, rels: List[str]) -> Dict[str, str]:
    """Text of LTC/test files kept in the lock to explain later changes (bounded)."""
    root = kit_root(project_root, req_id)
    out: Dict[str, str] = {}
    budget = 2 * 1024 * 1024
    for rel in rels:
        path = root / rel
        if not path.suffix.lower() in {".json", ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".kt", ".cs"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > budget:
            break
        budget -= len(text)
        out[rel] = text
    return out


# --- KIT generations ---------------------------------------------------------

def record_kit_generation(project_root: Path, req_id: str) -> str:
    """A new KIT generation for the REQ: the next eval re-baselines the lock."""
    generation = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    _write_json(_req_state_path(project_root, req_id, "generation"), {"generation": generation, "at": time.time()})
    return generation


def _current_generation(project_root: Path, req_id: str) -> str:
    data = _read_json(_req_state_path(project_root, req_id, "generation")) or {}
    return str(data.get("generation") or "initial")


# --- lock ----------------------------------------------------------------------

def ensure_lock(project_root: Path, req_id: str) -> Dict[str, Any]:
    """Return the lock for the current KIT generation, creating it from disk if needed."""
    lock_path = _req_state_path(project_root, req_id, "lock")
    generation = _current_generation(project_root, req_id)
    lock = _read_json(lock_path)
    if lock and lock.get("schema") == LOCK_SCHEMA and lock.get("generation") == generation:
        return lock
    files = surface_manifest(project_root, req_id)
    lock = {
        "schema": LOCK_SCHEMA,
        "req_id": req_id,
        "generation": generation,
        "created_at": time.time(),
        "files": files,
        "texts": _snapshot_texts(project_root, req_id, list(files)),
        "digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    }
    _write_json(lock_path, lock)
    return lock


def _checks(ltc_text: str) -> Dict[str, Dict[str, Any]]:
    try:
        doc = json.loads(ltc_text)
    except ValueError:
        return {}
    items = doc.get("checks") or doc.get("cases") or []
    out: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(items if isinstance(items, list) else []):
        if isinstance(item, str):
            out[f"case::{index + 1}"] = {"run": item, "blocking": True}
        elif isinstance(item, dict):
            key = str(item.get("id") or item.get("name") or f"case::{index + 1}")
            required = item.get("required", True)
            out[key] = {
                "run": item.get("command") or item.get("run") or item.get("cmd"),
                "blocking": bool(item.get("blocking", required)),
            }
    return out


def _ltc_weakening(before: str, after: str) -> List[str]:
    old, new = _checks(before), _checks(after)
    issues = [f"check removed: {k}" for k in old if k not in new]
    issues += [f"check made non-blocking: {k}" for k in old if k in new and old[k]["blocking"] and not new[k]["blocking"]]
    issues += [f"check command changed: {k}" for k in old if k in new and old[k]["run"] != new[k]["run"]]
    return issues


def compare_with_lock(project_root: Path, req_id: str, lock: Dict[str, Any]) -> Dict[str, Any]:
    """Compare the current acceptance surface with the lock.

    Returns ``{"ok": bool, "anomalies": [...], "added": [...], "lock_digest": ...}``.
    """
    root = kit_root(project_root, req_id)
    locked: Dict[str, str] = lock.get("files") or {}
    texts: Dict[str, str] = lock.get("texts") or {}
    current = surface_manifest(project_root, req_id)
    anomalies: List[Dict[str, Any]] = []

    for rel, digest in sorted(locked.items()):
        if rel not in current:
            anomalies.append({"path": rel, "kind": "removed"})
            continue
        if current[rel] == digest:
            continue
        entry: Dict[str, Any] = {"path": rel, "kind": "modified"}
        try:
            new_text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            new_text = ""
        old_text = texts.get(rel)
        if rel.endswith("LTC.json") and old_text is not None:
            details = _ltc_weakening(old_text, new_text)
            if details:
                entry.update(kind="weakened", details=details)
        elif old_text is not None:
            added = len(_SKIP_MARKER_RE.findall(new_text)) - len(_SKIP_MARKER_RE.findall(old_text))
            if added > 0:
                entry.update(kind="skip_added", details=[f"{added} skip/disable marker(s) added"])
        anomalies.append(entry)

    added_files = sorted(set(current) - set(locked))
    return {
        "ok": not anomalies,
        "anomalies": anomalies,
        "added": added_files,
        "lock_digest": lock.get("digest"),
        "lock_generation": lock.get("generation"),
    }


# --- audited override --------------------------------------------------------------

def artifacts_digest(project_root: Path, req_id: str) -> Dict[str, Any]:
    root = kit_root(project_root, req_id)
    files: Dict[str, str] = {}
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if len(files) >= _MAX_FILES:
                break
            if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
                continue
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "files": len(files),
        "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    }


def record_override(project_root: Path, req_id: str, *, reason: str, author: str) -> Dict[str, Any]:
    req = validate_req_id(req_id)
    entry = {
        "audit_id": uuid.uuid4().hex,
        "at": time.time(),
        "type": "gate_override",
        "project_root": str(Path(project_root).resolve()),
        "req_id": req,
        "reason": reason,
        "author": author,
        "artifacts": artifacts_digest(project_root, req),
    }
    audit = state_dir() / "audit" / "gate_overrides.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


# --- auto-eval repair amendments -----------------------------------------------------

_LOCKED_TEST_ISSUE = "tests are locked: a repair must make the code pass them, not change them"


def _imports_and_body(source: str):
    tree = ast.parse(source)
    imports = set()
    body = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(("", alias.name, alias.asname) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.update((module, alias.name, alias.asname) for alias in node.names)
        else:
            body.append(node)
    return imports, ast.dump(ast.Module(body=body, type_ignores=[]))


def _test_change_issue(path: Path, locked_digest: Optional[str], content: str) -> Optional[str]:
    """None when a locked test change only removes module-level imports (e.g. an unused import
    that fails lint); otherwise why it is rejected."""
    if path.suffix != ".py" or not locked_digest or not path.is_file():
        return _LOCKED_TEST_ISSUE
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != locked_digest:
        return _LOCKED_TEST_ISSUE
    before = raw.decode("utf-8", errors="replace")
    try:
        old_imports, old_body = _imports_and_body(before)
        new_imports, new_body = _imports_and_body(content)
    except SyntaxError:
        return _LOCKED_TEST_ISSUE
    if new_body != old_body or not new_imports <= old_imports:
        return _LOCKED_TEST_ISSUE + " (only removing unused imports is allowed)"
    return None


def amend_acceptance_surface(
    project_root: Path,
    req_id: str,
    changes: Dict[str, str],
    *,
    reason: str,
    author: str = "auto-eval",
) -> Dict[str, Any]:
    """Accept non-weakening repairs of the locked acceptance surface (auto-eval).

    ``changes`` maps KIT-relative paths (``ci/LTC.json``, ``test/...``) to new content.

    * ``test/**`` is never amended (a repair must make the code pass the locked tests), except a
      Python test that only drops unused imports (lint): same code once imports are removed and
      no import added.
    * ``ci/LTC.json`` may change only the commands of existing checks (e.g. a path that does not
      exist in the sandbox): no check removed, none made non-blocking.
    * other ``ci/**`` files (requirements, manifests) may change, e.g. to upgrade a vulnerable
      dependency.

    Accepted changes update the lock so the following eval does not report them as tampering, and
    every amendment is appended to the audit log.
    """
    req = validate_req_id(req_id)
    lock = ensure_lock(project_root, req)
    root = kit_root(project_root, req)
    files: Dict[str, str] = dict(lock.get("files") or {})
    texts: Dict[str, str] = dict(lock.get("texts") or {})
    accepted: List[str] = []
    rejected: Dict[str, List[str]] = {}
    for raw_rel, content in (changes or {}).items():
        rel = str(raw_rel or "").replace("\\", "/").lstrip("/")
        if rel.startswith("test/"):
            issue = _test_change_issue(root / rel, files.get(rel), content)
            if issue:
                rejected[rel] = [issue]
                continue
            files[rel] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            accepted.append(rel)
            continue
        if not rel.startswith("ci/"):
            continue
        if rel.endswith("LTC.json"):
            before = texts.get(rel)
            if before is None and (root / rel).is_file():
                before = (root / rel).read_text(encoding="utf-8", errors="replace")
            issues = [i for i in _ltc_weakening(before or "{}", content) if not i.startswith("check command changed")]
            if issues:
                rejected[rel] = issues
                continue
            texts[rel] = content
        files[rel] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        accepted.append(rel)
    entry: Dict[str, Any] = {}
    if accepted:
        entry = {
            "audit_id": uuid.uuid4().hex,
            "at": time.time(),
            "type": "acceptance_amendment",
            "project_root": str(Path(project_root).resolve()),
            "req_id": req,
            "files": sorted(accepted),
            "reason": reason,
            "author": author,
        }
        lock.update({
            "files": files,
            "texts": texts,
            "digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            "amendments": [*(lock.get("amendments") or []), entry],
        })
        _write_json(_req_state_path(project_root, req, "lock"), lock)
        audit = state_dir() / "audit" / "acceptance_amendments.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return {"accepted": sorted(accepted), "rejected": rejected, "audit_id": entry.get("audit_id")}
