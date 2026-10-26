from __future__ import annotations
import hashlib
import json
import logging
import os
import posixpath
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

import eval_environment
import eval_failures
from services.gate_integrity import _DEFINES_TESTS_RE
from services.root_files import KIT_ROOT_DIR, extra_root_files, is_allowed_root_path, root_policy
import eval_tools
import sandbox_resources
from utils.safe_paths import validate_req_id

log = logging.getLogger("eval_runner")


# a check result taken from the run on the same inputs instead of running the check again
_REUSED_NOTE = "[CLike EvalRunner] Reused: same inputs as the targeted re-eval that just ran; not run again."


@dataclass
class EvalCase:
    name: str
    passed: bool
    code: int
    stdout: str
    stderr: str
    cmd: Optional[str] = None
    cwd: Optional[str] = None
    expect: Optional[int] = None
    blocked: bool = False
    blocking: bool = True
    # A failed check: its error blocks from the whole output (eval_failures.excerpt) and their id.
    excerpt: Optional[str] = None
    fingerprint: Optional[str] = None
    # seconds the check took (CLike's own steps have none)
    duration_s: Optional[float] = None


@dataclass
class EvalReport:
    profile: str
    req_id: Optional[str]
    mode: str
    passed: int
    failed: int
    cases: List[EvalCase]
    blocked: int = 0
    warnings: int = 0
    status: str = "FAIL"
    junit_path: Optional[str] = None
    json_path: Optional[str] = None
    reason_code: Optional[str] = None
    # EVAL_ENVIRONMENT_MISSING: a KIT repair can declare how CLike provisions the variables
    environment_repairable: Optional[bool] = None
    # programs of CLike's tools catalog a check reported missing (installed on confirmation)
    missing_tools: Optional[List[str]] = None
    # versions of the tools installed in the sandbox's tools volume when the eval ran
    tools: Optional[Dict[str, Dict[str, str]]] = None


def report_to_dict(rep: "EvalReport") -> Dict[str, Any]:
    """JSON-safe form of a report (used across the eval sandbox boundary)."""
    from dataclasses import asdict

    return asdict(rep)


def report_from_dict(data: Dict[str, Any]) -> "EvalReport":
    fields = dict(data)
    fields["cases"] = [EvalCase(**case) for case in (data.get("cases") or [])]
    return EvalReport(**fields)


# Environment variables that must never reach LTC commands (WP4): provider keys,
# the CLike service token and any other credential-looking variable.
_SECRET_ENV_NAME_RE = re.compile(
    r"(API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY|ACCESS_KEY)", re.IGNORECASE
)


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _head_tail(text: str, limit: int) -> str:
    """Keep the start (a stack dump starts with the innermost frame) and the end of long output."""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    return text[:head] + "\n[...]\n" + text[-(limit - head):]


def _with_pytest_hang_dump(env: Dict[str, str], timeout: Optional[int]) -> Dict[str, str]:
    """Make pytest dump the stack of a test that runs longer than part of the check timeout and
    print each test id before running it and show full assertion diffs (-vvv on top of a command's
    -q gives -vv), so a
    hanging test, also an async one whose coroutine is not on the dumped stack, is named in the
    report instead of being lost when the check is stopped."""
    try:
        seconds = max(5, int(float(timeout) * 0.6)) if timeout else 60
    except (TypeError, ValueError):
        seconds = 60
    current = env.get("PYTEST_ADDOPTS", "")
    if "faulthandler_timeout" in current:
        return env
    return {**env, "PYTEST_ADDOPTS": f"{current} -vvv -o faulthandler_timeout={seconds}".strip()}


class EvalCancelled(RuntimeError):
    """The caller went away (client disconnected): the running check was stopped."""


def _stop_group(proc: subprocess.Popen) -> None:
    if os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    elif proc.poll() is None:
        proc.kill()


def _run_process_group(
    cmd: str,
    *,
    cwd: Path,
    env: Dict[str, str],
    timeout: Optional[int],
    cancel: Optional[threading.Event] = None,
) -> subprocess.CompletedProcess:
    """subprocess.run(shell=True) that stops the whole process group on timeout or cancellation
    (the shell's children, e.g. pytest or a server, would otherwise keep running in the sandbox)."""
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name != "nt"),
    )
    deadline = time.monotonic() + float(timeout) if timeout else None
    while True:
        # short waits so a cancellation is seen within a second (retrying communicate loses no output)
        step = 1.0 if deadline is None else max(0.0, min(1.0, deadline - time.monotonic()))
        try:
            stdout, stderr = proc.communicate(timeout=step)
            # What the check left running in its group (a server, a browser) is stopped too: an
            # orphan per check exhausted the sandbox's process limit within a day of evals.
            _stop_group(proc)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                _stop_group(proc)
                proc.communicate()
                raise EvalCancelled(cmd)
            if deadline is not None and time.monotonic() >= deadline:
                _stop_group(proc)
                stdout, stderr = proc.communicate()
                raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)


_SANDBOX_EXHAUSTED_NOTE = "[CLike EvalRunner] Sandbox resources exhausted"
_MISSING_TOOLS_NOTE = "[CLike EvalRunner] Missing in the eval sandbox"
_NONDETERMINISTIC_NOTE = "[CLike EvalRunner] Nondeterministic"
# a failure of a promoted REQ that does not depend on the candidate (it fails on the promoted tree alone)
_PREEXISTING_NOTE = "[CLike EvalRunner] Already failing without this candidate"
_NEW_ERRORS_NOTE = "[CLike EvalRunner] New errors from this candidate"
_SUPERSEDED_TESTS_NOTE = "[CLike EvalRunner] Superseded tests"
_CONTENTION_NOTE = "[CLike EvalRunner] Timeout under parallel load"
_DECLARE_NOTE = "[CLike EvalRunner] A delivered test of an amended REQ"
_ACCEPTANCE_NOTE = "[CLike EvalRunner] Acceptance coverage"
# A failure where the new value extends the old one (pytest, jest/vitest, JUnit/AssertJ, Go/testify…)
_ADDITIVE_DIFF_RE = re.compile(
    r"Extra items in the (?:left|right) (?:set|list|dict)|(?:Left|Right) contains \d+ more items?|"
    r"Unexpected (?:key|element|item)s?|but has extra (?:key|element|item)s?|"
    r"expected .{0,40}to have (?:length|size) \d+ but got \d+|"
    r"unexpected (?:element|item)s? in|Extra elements:|elements not expected:",
    re.IGNORECASE,
)
# acceptance saying the delivered tests keep holding ("existing … tests still hold", "unchanged")
_KEEPS_TESTS_RE = re.compile(r"(?:existing|delivered|earlier)[^.;]{0,80}tests? (?:still|continue to) (?:hold|pass)", re.IGNORECASE)
# A KIT's self review saying it is not complete (the agent's own words, any phrasing seen so far)
_SELF_INCOMPLETE_RE = re.compile(
    r"not (?:be )?(?:treated as )?(?:complete|promotable)|must not be promoted|"
    r"remains? (?:unimplemented|not implemented|absent|incomplete|missing)|"
    r"(?:is|are) not (?:yet )?(?:implemented|wired)|implementation gaps? remain",
    re.IGNORECASE,
)
_SHARED_FILES_NOTE = "[CLike EvalRunner] Shared files changed"
_SERVICE_BROKEN_NOTE = "[CLike EvalRunner] Service broken by the candidate"
# A test file by name in Python, JS/TS, Java/Kotlin, Go, C# (test_x.py, x_test.go, x.test.ts, x.spec.js, XTest.java, XTests.cs).
_TEST_FILE_NAME_RE = re.compile(r"^test_|_test\.\w+$|\.(test|spec)\.\w+$|Tests?\.\w+$")
# The test root's conftest is shared by every REQ and merged at promotion (a REQ's fixtures may move
# to a subdirectory): its canonical copy is not a promoted version of one REQ's conftest.
_SHARED_ROOT_TEST_FILES = frozenset({"conftest.py"})
# new support files a reconciled test gets when they sit beside it (package marker, fixtures)
_BESIDE_SUPPORT_NAMES = {"__init__.py", "conftest.py"}
_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+(\.*)([\w.]*)\s+import\s+([\w., ()]+)|import\s+([\w., ]+))", re.M)


_JS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# Public names of a test-support file, per language family (the shared-support check compares them).
_JS_EXPORT_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function\*?|class|const|let|var|type|interface|enum)\s+([A-Za-z_$][\w$]*)"
)
_JS_EXPORT_LIST_RE = re.compile(r"\bexport\s+(?:type\s+)?\{([^}]*)\}")
_JVM_PUBLIC_RE = re.compile(r"\bpublic\s+(?:[\w<>\[\],.?]+\s+)*?([A-Za-z_]\w*)\s*[({<]")
_KOTLIN_DECL_RE = re.compile(r"^(?!\s*(?:private|internal|protected)\b)\s*(?:[\w]+\s+)*?(?:fun|class|object|val|var)\s+(?:<[^>]*>\s*)?([A-Za-z_]\w*)", re.M)
_GO_EXPORTED_RE = re.compile(r"^(?:func\s+(?:\([^)]*\)\s*)?|type\s+|var\s+|const\s+)([A-Z]\w*)", re.M)


def _public_names(path: Path, text: str) -> Optional[set]:
    """The names other tests can use from a support file, or None for a language CLike does not
    read (the regression still covers it)."""
    suffix = path.suffix
    if suffix == ".py":
        import ast

        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return None
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        return {n for n in names if not n.startswith("_")}
    if suffix in _JS_SUFFIXES:
        names = set(_JS_EXPORT_RE.findall(text))
        for group in _JS_EXPORT_LIST_RE.findall(text):
            for item in group.split(","):
                item = item.strip()
                if item:
                    names.add(item.split(" as ")[-1].strip())
        return names
    if suffix in {".java", ".cs"}:
        return set(_JVM_PUBLIC_RE.findall(text))
    if suffix in {".kt", ".kts"}:
        return set(_KOTLIN_DECL_RE.findall(text))
    if suffix == ".go":
        return set(_GO_EXPORTED_RE.findall(text))
    return None
_JS_RELATIVE_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)(['"])(\.{1,2}/[^'"]+)\1""", re.M
)


def _js_imported_support(rel: str, path: Path, support: Dict[str, Path]) -> List[str]:
    """The candidate support files a JS/TS file imports by a relative specifier: the exact file, the
    file with a JS/TS extension (also replacing a .js one, as TypeScript allows) or the directory's
    index."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: List[str] = []
    here = PurePosixPath(rel).parent
    for _, spec in _JS_RELATIVE_IMPORT_RE.findall(text):
        target = posixpath.normpath(str(here / spec))
        stem = target[: -len(PurePosixPath(target).suffix)] if PurePosixPath(target).suffix in _JS_SUFFIXES else target
        options = [target] + [stem + ext for ext in _JS_SUFFIXES] + [f"{target}/index{ext}" for ext in _JS_SUFFIXES]
        for option in options:
            if option in support:
                found.append(option)
                break
    return found


def _imported_support(
    rel: str, path: Optional[Path], support: Dict[str, Path], source_root: Optional[Path] = None
) -> List[str]:
    """The candidate support files (relative paths in ``support``) that the Python file ``rel``
    imports: an absolute module that is not in ``source_root`` matches a support file whose path
    ends with it, anywhere in the test tree (the test runner puts several test directories on the
    path); a relative one resolves from the file's directory. JS/TS files: their relative imports
    (``import … from './x'``, ``export … from``, ``require('./x')``, ``import('./x')``)."""
    if path is not None and Path(rel).suffix in _JS_SUFFIXES:
        return _js_imported_support(rel, path, support)
    if path is None or not rel.endswith(".py"):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: List[str] = []

    def by_suffix(parts: List[str]) -> None:
        if source_root is not None and (
            (source_root / Path(*parts)).with_suffix(".py").is_file()
            or (source_root / Path(*parts) / "__init__.py").is_file()
        ):
            return  # the module is in the sources: a same-named file of the test tree is not it
        tails = ("/".join(parts) + ".py", "/".join(parts) + "/__init__.py")
        if len(parts) > 1 and parts[0] in ("test", "tests"):
            # `test.leadintel.x` imports the test tree itself as a package (support is relative to it)
            inner = "/".join(parts[1:])
            tails += (inner + ".py", inner + "/__init__.py")
        for candidate in support:
            if any(candidate == t or candidate.endswith("/" + t) for t in tails):
                found.append(candidate)

    here = Path(rel).parent
    for dots, module, names, plain in _PY_IMPORT_RE.findall(text):
        if plain:
            for name in plain.split(","):
                by_suffix(name.strip().split(" ")[0].split("."))
            continue
        parts = [p for p in module.split(".") if p]
        imported = [n.strip().split(" ")[0] for n in names.strip("() ").split(",") if n.strip()]
        if dots:
            base = here
            for _ in range(len(dots) - 1):
                base = base.parent
            prefix = [] if str(base) == "." else list(base.parts)
            for target in ([parts] if parts else []) + [parts + [n] for n in imported]:
                tail = "/".join(prefix + target)
                for t in (tail + ".py", tail + "/__init__.py"):
                    if t in support:
                        found.append(t)
            continue
        # the full module only: a parent package marker in the test tree would shadow the source one
        by_suffix(parts)
        for n in imported:
            by_suffix(parts + [n])
    return found


_SHARED_SCAN_SKIP = {
    "node_modules", "__pycache__", ".venv", ".next", "dist", ".tmp", ".cache", "reports", "target", ".gradle", "obj",
}


_TEST_FILE_NAME_RE = re.compile(
    r"^(test_.+|.+_test|.+\.(test|spec)|.+Tests?|.+_spec)\.[A-Za-z0-9]+$"
)


# Files whose presence in a test directory changes how its tests are collected or import: package
# markers, pytest / Jest / Vitest / Playwright / Mocha / Babel / TypeScript configs, Go / Maven /
# Gradle / .NET project files.
_TEST_LAYOUT_FILE = re.compile(
    r"^(__init__\.py|conftest\.py|pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml|package\.json|tsconfig(\..+)?\.json|"
    r"(jest|vitest|playwright|babel|vite)\.config\.[cm]?[jt]s|\.mocharc(\.[a-z]+)?|\.babelrc|go\.mod|pom\.xml|"
    r"build\.gradle(\.kts)?|.+\.csproj|Directory\.Build\.props)$"
)


def _is_test_file_name(name: str) -> bool:
    """A file named as a test in the usual conventions (test_x.py, x_test.go, x.test.ts, x.spec.js,
    XTest.java, XTests.cs, x_spec.rb): it holds tests, it does not configure how others run."""
    return bool(_TEST_FILE_NAME_RE.match(name))


def _same_but_layout(old: bytes, new: bytes) -> bool:
    """The same content once whitespace is ignored (a formatter wrapped a line, re-indented a
    continuation): such a change is no cause of a failing check. B2B REQ-026: a line wrap in
    worker.py was named on REQ-014's failure and sent the repair to the wrong file for two cycles."""
    try:
        a, b = old.decode("utf-8"), new.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def _shared_file_changes(project_root: Path, candidate_root: Path, other_kit: Path, limit: int = 8) -> List[str]:
    """Files the promoted REQ delivered (its KIT src/ and test/) that the candidate KIT replaces with
    different content, each with a short diff against the canonical copy (the state the promoted REQ
    passed with; its KIT copy when the file was never promoted). Empty when the candidate touches
    none of them, so the regression failure has another cause."""
    import difflib

    changes: List[str] = []
    test_dirs: set = set()  # the promoted REQ's test directories and their parents, KIT-relative
    for top in ("src", "test", "tests", KIT_ROOT_DIR):
        base = other_kit / top
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in _SHARED_SCAN_SKIP)
            if top in ("test", "tests") and filenames:
                rel_dir = Path(dirpath).relative_to(other_kit)
                test_dirs.update([rel_dir, *[p for p in rel_dir.parents if p != Path(".")]])
            for filename in sorted(filenames):
                rel = (Path(dirpath) / filename).relative_to(other_kit)
                candidate = candidate_root / rel
                if not candidate.is_file():
                    continue
                # root/<path> is delivered to <path> in the repository
                canon = rel.relative_to(KIT_ROOT_DIR) if top == KIT_ROOT_DIR else rel
                baseline = project_root / canon if (project_root / canon).is_file() else other_kit / rel
                try:
                    old, new = baseline.read_bytes(), candidate.read_bytes()
                except OSError:
                    continue
                if old == new or _same_but_layout(old, new):
                    continue  # identical, or only reformatted (line wraps, indentation): not a cause
                try:
                    diff = list(difflib.unified_diff(
                        old.decode("utf-8").splitlines(), new.decode("utf-8").splitlines(),
                        "canonical", "candidate", n=1, lineterm="",
                    ))[2:]
                except UnicodeDecodeError:
                    diff = ["(binary content differs)"]
                shown = diff[:24] + ([f"... {len(diff) - 24} more diff lines"] if len(diff) > 24 else [])
                changes.append(f"- {canon.as_posix()}\n" + "\n".join(f"    {line}" for line in shown))
                if len(changes) >= limit:
                    return changes
    # Files the candidate adds where the promoted REQ's tests live (a package marker, a conftest, a
    # runner config): after promotion they change how those tests are collected and import helpers.
    for rel_dir in sorted(test_dirs):
        folder = candidate_root / rel_dir
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            rel = rel_dir / path.name
            if not path.is_file() or (other_kit / rel).exists() or (project_root / rel).exists():
                continue
            if _is_test_file_name(path.name):
                continue  # a test of this REQ next to the promoted ones: collected on its own
            changes.append(f"- {rel.as_posix()} (added by this candidate in a test directory of the promoted REQ)")
            if len(changes) >= limit:
                return changes
    return changes


def _shared_files_note(other: str, changes: List[str]) -> str:
    return (
        f"{_SHARED_FILES_NOTE}: this candidate replaces files that {other} also delivers, and a check of "
        f"{other} fails with the candidate overlaid. A shared file keeps what {other} put there and adds this "
        "REQ's part: test runner selectors (match/include patterns, test directories, projects, suites) keep the "
        "existing entries and add new ones, never chosen by which test files exist (after promotion every REQ's "
        "tests are in the same tree); infrastructure, build and route files keep their entries. When "
        f"a check of {other} pins the file's content (an exact set of services or files), add this REQ's part "
        "in a separate file instead (a compose override, an extra test config or project). If this REQ changes "
        f"{other}'s behaviour on purpose, reconcile {other}'s test in the candidate test root. A file this "
        f"candidate adds in a test directory of {other} (a package marker such as __init__.py, a conftest, a "
        f"runner config) changes how {other}'s tests are collected and import their helpers after promotion: "
        "remove it and make this REQ's tests import their helpers the way the promoted tests already do (the "
        "check's import path, its own directories).\n"
        + "\n".join(changes)
    )


def _sandbox_exhausted_case(case: "EvalCase") -> bool:
    """A check that failed because the sandbox ran out of processes, threads, memory or disk."""
    return not case.passed and (
        case.name.endswith("env::sandbox-resources") or _SANDBOX_EXHAUSTED_NOTE in (case.stderr or "")
    )


# Never copied into an eval workspace: installs, caches and scratch a KIT may hold (a local agent
# kept an npm cache in ci/.tmp; npm removed files from it during the copy and the eval failed).
_KIT_COPY_IGNORE = shutil.ignore_patterns(
    "node_modules", ".npm-*", ".npm", ".npm-cache", ".venv", "__pycache__", "__MACOSX", ".DS_Store",
    "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache", "reports", ".tmp", ".cache",
    ".next", ".turbo", "local-eval-workspaces",
)


def _copy_if_present(src: str, dst: str) -> None:
    """shutil.copy2 that skips a file removed while the tree is being copied."""
    try:
        shutil.copy2(src, dst)
    except FileNotFoundError:
        pass


def scrubbed_process_env() -> Dict[str, str]:
    """Copy of os.environ without credentials, used as the base env of every eval command. The
    tools CLike installed (eval_tools) are on its PATH, after the image's own programs."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_NAME_RE.search(k)}
    env["PATH"] = eval_tools.search_path(env.get("PATH", ""))
    return env


# plan.json status of a promoted REQ (set by the extension after a passing gate).
PROMOTED_REQ_STATUSES = {"done"}


_COVERAGE_THRESHOLD_RE = re.compile(r"Required test coverage of .* not reached", re.IGNORECASE)
_NON_BEHAVIOURAL_CHECK_RE = re.compile(
    r"lint|format|style|ruff|flake8|eslint|prettier|type|mypy|pyright|tsc|security|secret|audit|bandit|"
    r"vuln|sast|build|compile|syntax|coverage",
    re.IGNORECASE,
)
# In the regression of a promoted REQ only what guards behaviour runs: its static/quality checks
# (lint, types, security scans, coverage, syntax) passed at its own gate, now measure the candidate's
# code too and never block there (see _is_regression_test_case), so they are not run at all.
# Installs and builds stay: the tests need them.
_STATIC_CHECK_TOKENS = frozenset({
    "lint", "linter", "format", "fmt", "style", "ruff", "flake8", "pylint", "eslint", "prettier", "typecheck",
    "types", "type", "typing", "mypy", "pyright", "tsc", "security", "sast", "secret", "secrets", "audit",
    "bandit", "vuln", "vulns", "coverage", "cov", "syntax", "sbom", "license", "licenses",
})
_TEST_CHECK_TOKENS = frozenset({
    "test", "tests", "unit", "integration", "e2e", "smoke", "pytest", "vitest", "jest", "playwright", "acceptance",
})


def _is_static_regression_check(name: str) -> bool:
    tokens = {t for t in re.split(r"[^a-z0-9]+", str(name or "").lower()) if t}
    return bool(tokens & _STATIC_CHECK_TOKENS) and not tokens & _TEST_CHECK_TOKENS


# A promoted REQ's own "regression" check (regression, test:backend-regression, …) re-runs tests of
# earlier REQs, often copies of them in its KIT: in its regression those REQs are regressed
# themselves, on their promoted tests, so it only repeats them (REQ-018's took 120 s of 25 min).
_KIT_REGRESSION_TOKENS = frozenset({"regression", "regressions"})


def _is_kit_regression_check(name: str) -> bool:
    return bool({t for t in re.split(r"[^a-z0-9]+", str(name or "").lower()) if t} & _KIT_REGRESSION_TOKENS)


_TEST_FAILURES_RE = re.compile(r"\b\d+ (?:failed|errors?)\b|^FAILED ", re.MULTILINE)
# CLike's own promotion leftovers next to canonical files (<name>.conflict-REQ-…, .incoming-REQ-…,
# .bak-<n>): never source, so never composed into an eval workspace (a format check walked into
# a .conflict-… file the developer had not deleted yet and failed the gate).
_PROMOTION_SCRATCH_RE = re.compile(r"\.(?:incoming|conflict)-REQ-|\.bak-\d")


ENVIRONMENT_MISSING_REASON = "EVAL_ENVIRONMENT_MISSING"


def required_environment_variables(ltc: Dict[str, Any]) -> List[Dict[str, str]]:
    """Variables the LTC declares the checks need (see eval_environment for the contract)."""
    return [
        {"name": spec.name, "purpose": spec.purpose, "example": spec.example, "provision": spec.effective_provision()}
        for spec in eval_environment.variable_specs(ltc)
    ]


def missing_environment_case(ltc: Dict[str, Any], environ: Optional[Dict[str, str]] = None) -> Optional["EvalCase"]:
    """A blocked case listing the required variables CLike can neither find nor create, or None."""
    environ = scrubbed_process_env() if environ is None else environ
    missing = eval_environment.missing_variables(ltc, environ)
    if not missing:
        return None
    example = missing[0][0]
    lines = [
        "The checks need variables that the eval environment does not provide and CLike cannot create:",
        *(f"  - {spec.name}" + (f": {spec.purpose}" if spec.purpose else "") + f" ({how})" for spec, how in missing),
        "CLike creates variables declared in ci/LTC.json environment.required_variables with a `provision`",
        "(token, uuid, timestamp, template, postgres_database, service; see docs/development.md).",
        "External values go to docker/eval.env (git-ignored; template docker/eval.env.example), one NAME=value",
        "per line; from the eval sandbox the host machine is host.containers.internal, e.g.",
        f"  {example.name}=" + (example.example or "postgresql+psycopg://me@host.containers.internal:5432/test_db"),
        "then recreate the stack (docker/rebuild.sh) and re-run /eval. See the REQ's ci/HOWTO.md.",
        "No check was run: the code is not at fault.",
    ]
    return EvalCase(
        name="env::required-variables",
        passed=False,
        code=78,
        stdout="",
        stderr="\n".join(lines),
        blocked=True,
        blocking=True,
    )


def _is_regression_test_case(case: "EvalCase") -> bool:
    """A regression check that guards behaviour: any check except static/quality ones (lint,
    types, security scans, build, syntax, coverage), and not when its only failure is the coverage
    threshold (coverage of the other REQ now includes the candidate's code)."""
    if _NON_BEHAVIOURAL_CHECK_RE.search(case.name):
        return False
    if case.passed:
        return True
    output = f"{case.stdout}\n{case.stderr}"
    return not (_COVERAGE_THRESHOLD_RE.search(output) and not _TEST_FAILURES_RE.search(output))


# Live progress of the evals in flight (GET /progress of the sandbox, /v1/eval/progress of the
# orchestrator): what the developer's chat shows while an eval runs. Only the top-level run of a
# REQ writes it; the nested runners of the regression report through it, per promoted REQ.
_PROGRESS: Dict[str, Dict[str, Any]] = {}
_PROGRESS_LOCK = threading.Lock()
_PROGRESS_TTL_S = 3600


def progress_key(project_root: Path, req_id: Optional[str]) -> str:
    return f"{Path(project_root).resolve()}::{str(req_id or '').strip().upper()}"


def eval_progress(project_root: Path, req_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The progress of the latest eval of the REQ in this process (a copy), or None."""
    with _PROGRESS_LOCK:
        entry = _PROGRESS.get(progress_key(project_root, req_id))
        if not entry:
            return None
        out = dict(entry)
        out["regression_current"] = list(entry.get("regression_current") or [])
    out["elapsed_s"] = round((out.get("ended_at") or time.time()) - out.get("started_at", time.time()), 1)
    return out


def regression_workers() -> int:
    """Promoted REQs regressed at the same time (``CLIKE_EVAL_REGRESSION_WORKERS``, default 2,
    1 = one after the other). Each one runs its own installs, tests and services: more workers need
    more sandbox memory (``CLIKE_EVAL_SANDBOX_MEM_LIMIT``)."""
    try:
        value = int(os.getenv("CLIKE_EVAL_REGRESSION_WORKERS", "").strip() or 2)
    except ValueError:
        value = 2
    return max(1, min(value, 8))


# Installs shared by parallel regressions (a REQ's venv is also used by the services other REQs
# start from it; one npm install store per manifest): created by one thread at a time.
_KEYED_LOCKS: Dict[str, threading.Lock] = {}
_KEYED_LOCKS_GUARD = threading.Lock()


def _keyed_lock(key: str) -> threading.Lock:
    with _KEYED_LOCKS_GUARD:
        return _KEYED_LOCKS.setdefault(key, threading.Lock())


# Process variables that change with the container or the shell, not with what a check sees.
_VOLATILE_ENV_NAMES = frozenset({"HOSTNAME", "PWD", "OLDPWD", "SHLVL", "_", "TERM", "COLUMNS", "LINES"})


class _BaselineCache:
    """Results (check name -> failed) of a promoted REQ's checks on the promoted tree alone, valid
    while the promoted state digest is the same and for at most a day (tools, network, time)."""

    MAX_AGE_S = 24 * 3600
    # How long a failure on an earlier promoted state is remembered (``failed_before``).
    HISTORY_AGE_S = 7 * 24 * 3600

    def __init__(self, path: Optional[Path], digest: str = "") -> None:
        self.path, self.digest = path, digest
        self.results: Dict[str, bool] = {}
        # check name -> when it last failed without any candidate, on any recent promoted state
        self.history: Dict[str, float] = {}
        # check name -> its normalized error lines on the promoted tree (eval_failures.error_keys)
        self.errors: Dict[str, List[str]] = {}
        # check name -> {"at", "errors"}: it failed with a candidate, then passed on a re-run of the
        # same code, in a recent eval (any promoted state): a known nondeterministic check
        self.flaky: Dict[str, Dict[str, Any]] = {}
        self.at = time.time()
        if path is None:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.flaky = {
            str(k): {"at": float(v.get("at") or 0), "errors": list(v.get("errors") or [])}
            for k, v in (data.get("flaky") or {}).items()
            if isinstance(v, dict) and time.time() - float(v.get("at") or 0) <= self.HISTORY_AGE_S
        }
        at = float(data.get("at") or 0)
        history = {str(k): float(v) for k, v in (data.get("history") or {}).items()}
        history.update({str(k): at for k, v in (data.get("results") or {}).items() if v})
        self.history = {k: v for k, v in history.items() if time.time() - v <= self.HISTORY_AGE_S}
        if data.get("digest") == digest and time.time() - at <= self.MAX_AGE_S:
            self.results = {str(k): bool(v) for k, v in (data.get("results") or {}).items()}
            self.errors = {str(k): list(v) for k, v in (data.get("errors") or {}).items()}
            self.at = at or self.at  # the age counts from the first result

    def failed_before(self, check: str) -> Optional[float]:
        """When ``check`` last failed without a candidate on an earlier promoted state (recent)."""
        return self.history.get(check)

    def result(self, check: str) -> Optional[bool]:
        """True: it fails without the candidate; False: it passes; None: not known yet."""
        return self.results.get(check)

    def failing(self) -> frozenset:
        return frozenset(name for name, failed in self.results.items() if failed)

    def new_errors(self, check: str, excerpt: Optional[str]) -> List[str]:
        """Error lines of ``excerpt`` that ``check`` did not show on the promoted tree: the candidate
        broke it in a new way. Empty when they are the same, or when the baseline kept none."""
        known = self.errors.get(check)
        if not known:
            return []
        return [key for key in eval_failures.error_keys(excerpt or "") if key not in set(known)]

    def record_flaky(self, check: str, excerpt: Optional[str]) -> None:
        """``check`` failed, then passed on a re-run of the same code: remember it and its errors."""
        known = self.flaky.get(check, {}).get("errors") or []
        self.flaky[check] = {"at": time.time(), "errors": sorted(set(known) | set(eval_failures.error_keys(excerpt or "")))}
        self.store({})

    def known_flaky(self, check: str, excerpt: Optional[str]) -> Optional[float]:
        """When ``check`` was last seen nondeterministic, if this failure shows only errors seen in
        its nondeterministic failures (a timeout, a missing UI element); None otherwise: an error
        it never showed is the candidate's."""
        seen = self.flaky.get(check)
        if not seen or not seen.get("errors"):
            return None
        known, keys = set(seen["errors"]), eval_failures.error_keys(excerpt or "")
        if not keys or any(key not in known for key in keys):
            return None  # no error to compare, or one it never showed: the candidate's
        return float(seen["at"])

    def store(self, results: Dict[str, bool], errors: Optional[Dict[str, List[str]]] = None) -> None:
        self.results.update(results)
        self.errors.update(errors or {})
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            history = {**self.history, **{k: self.at for k, v in self.results.items() if v}}
            tmp.write_text(
                json.dumps({"digest": self.digest, "at": self.at, "results": self.results, "history": history,
                            "errors": self.errors, "flaky": self.flaky}),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("regression baseline cache not written: %s", exc)


# `No module named 'x.y'` (Python), `Cannot find module 'x'` (Node): the module a check could not load.
_MISSING_MODULE_RE = re.compile(r"(no module named|cannot find module) ['\"]([\w./@-]+)['\"]", re.IGNORECASE)
_DEPENDENCY_DIRS = {"node_modules", ".venv", "venv", ".venvs", "site-packages", ".git", "__pycache__", ".tox", "dist", "build"}
_MODULE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")


def _project_modules(roots: List[Optional[Path]], names: List[str]) -> List[str]:
    """The names that are a module file (or a package directory of source files) of the project,
    outside dependency directories: `a.b` / `a/b` → `…/a/b.<ext>` or `…/a/b/`."""
    wanted = {}
    for name in names:
        rel = name.strip("./").replace(".", "/") if "/" not in name else name.strip("./")
        if rel:
            wanted[tuple(rel.split("/"))] = name
    found: List[str] = []
    seen_roots = set()
    for root in roots:
        if not root or not Path(root).is_dir() or Path(root).resolve() in seen_roots:
            continue
        seen_roots.add(Path(root).resolve())
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _DEPENDENCY_DIRS and not d.endswith(".egg-info")]
            parts = Path(dirpath).relative_to(root).parts
            stems = {f.rsplit(".", 1)[0] for f in filenames if f.endswith(_MODULE_SUFFIXES)}
            for key, name in list(wanted.items()):
                *head, last = key
                if (not head or tuple(parts[-len(head):]) == tuple(head)) and len(parts) >= len(head):
                    sub = Path(dirpath, last)
                    if last in stems or (sub.is_dir() and any(f.suffix in _MODULE_SUFFIXES for f in sub.iterdir() if f.is_file())):
                        found.append(name)
                        wanted.pop(key)
            if not wanted:
                return found
    return found


class EvalRunner:
    def __init__(
        self,
        project_root: Path,
        *,
        eval_key: Optional[str] = None,
        extra_src_roots: Optional[List[Path]] = None,
        cancel_event: Optional[threading.Event] = None,
        regression: bool = False,
        extra_root_roots: Optional[List[Path]] = None,
        extra_test_roots: Optional[List[Path]] = None,
    ):
        self.project_root = project_root.resolve()
        # set when the caller goes away: the running check is stopped and no further check starts
        self.cancel_event = cancel_event
        # Regression runs: own eval directory and the candidate's source overlaid last.
        self.eval_key = eval_key
        self.extra_src_roots = list(extra_src_roots or [])
        # Regression runs: the candidate's repository-root deliverables (its KIT root/) overlaid last.
        self.extra_root_roots = list(extra_root_roots or [])
        # Regression runs: the candidate KIT, whose copies of the regressed REQ's test files win (a
        # reconciled test of that REQ is what promotion delivers). Only files the REQ already has.
        self.extra_test_roots = list(extra_test_roots or [])
        self.reconciled_tests: List[str] = []
        # A regression run re-checks a promoted REQ: its own KIT source is already in the canonical
        # tree (merged with what later REQs changed), so the stale KIT copy is not overlaid.
        self.regression = regression
        # the key of the live progress: set by the top-level run of a REQ only
        self._progress_key: Optional[str] = None

    def _progress(self, **fields: Any) -> None:
        key = self._progress_key
        if not key:
            return
        with _PROGRESS_LOCK:
            entry = _PROGRESS.get(key)
            if entry is not None:
                entry.update(fields)
                entry["updated_at"] = time.time()

    def _progress_start(self, req_id: Optional[str], partial: bool) -> None:
        if self.eval_key or self.regression or not req_id:
            return
        self._progress_key = progress_key(self.project_root, req_id)
        now = time.time()
        with _PROGRESS_LOCK:
            for key in [k for k, v in _PROGRESS.items() if now - v.get("updated_at", now) > _PROGRESS_TTL_S]:
                _PROGRESS.pop(key, None)
            _PROGRESS[self._progress_key] = {
                "req_id": str(req_id).upper(), "state": "running", "phase": "setup", "partial": partial,
                "checks_total": 0, "checks_done": 0, "current": None, "passed": 0, "failed": 0,
                "regression_total": 0, "regression_done": 0, "regression_current": [],
                "started_at": now, "updated_at": now, "ended_at": None,
            }

    def _progress_regression(self, other: str, started: bool) -> None:
        key = self._progress_key
        if not key:
            return
        with _PROGRESS_LOCK:
            entry = _PROGRESS.get(key)
            if entry is None:
                return
            current = entry.setdefault("regression_current", [])
            if started:
                current.append(other)
            else:
                if other in current:
                    current.remove(other)
                entry["regression_done"] = entry.get("regression_done", 0) + 1
            entry["updated_at"] = time.time()

    def _merge_env(
        self,
        base: Optional[Dict[str, str]],
        extra: Optional[Dict[str, str]],
    ) -> Dict[str, str]:
        env = scrubbed_process_env()
        if base:
            env.update({str(k): str(v) for k, v in base.items()})
        if extra:
            env.update({str(k): str(v) for k, v in extra.items()})
        return env

    def _run(
        self,
        *,
        name: str,
        cmd: str,
        cwd: Path,
        expect: int = 0,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        blocking: bool = True,
        environment_requirements: Optional[List[str]] = None,
    ) -> EvalCase:
        if env is None:
            env = scrubbed_process_env()
        env = _with_pytest_hang_dump(env, timeout)
        try:
            memory_before = sandbox_resources.memory_events()
            proc = _run_process_group(cmd, cwd=cwd, env=env, timeout=timeout, cancel=self.cancel_event)
            stderr = eval_failures.strip_ansi(proc.stderr or "")
            stdout = eval_failures.strip_ansi(proc.stdout or "")
            ok = proc.returncode == expect
            blocked = False
            noted = False  # a specific note already explains the failure
            exhausted = None if ok else sandbox_resources.exhaustion(f"{stdout}\n{stderr}")
            memory = None if ok or exhausted else sandbox_resources.memory_exhaustion(
                memory_before, sandbox_resources.memory_events()
            )
            if memory:
                blocked = noted = True
                exhausted = memory
                stderr = (
                    stderr
                    + f"\n{_SANDBOX_EXHAUSTED_NOTE} ({memory}). Not a defect of the code. " + sandbox_resources.MEMORY_HINT
                )[-4000:]
            elif exhausted:
                blocked = noted = True
                stderr = (
                    stderr
                    + f"\n{_SANDBOX_EXHAUSTED_NOTE} ({exhausted}): the OS refused a process, "
                    "thread, memory or disk space. Not a defect of the code. " + sandbox_resources.RESTART_HINT
                )
            elif not ok and sandbox_resources.unreachable_reserved_host(f"{stdout}\n{stderr}"):
                # A test defect, not the environment: the repair fixes the test (assertions kept).
                host = sandbox_resources.unreachable_reserved_host(f"{stdout}\n{stderr}")
                noted = True
                stderr = stderr + "\n[CLike EvalRunner] " + sandbox_resources.UNREACHABLE_HOST_NOTE.format(host=host)
            elif not ok and sandbox_resources.needs_person(f"{stdout}\n{stderr}"):
                # Like a missing container runtime: blocking, the repair makes it non-blocking.
                blocked, noted = blocking, True
                stderr = stderr + "\n[CLike EvalRunner] " + sandbox_resources.MANUAL_CHECK_NOTE
            elif not ok and sandbox_resources.container_runtime_missing(f"{stdout}\n{stderr}"):
                # Blocking: no verdict without it, and the repair is told to make it non-blocking.
                # Non-blocking: a warning, it runs on the developer's machine.
                blocked, noted = blocking, True
                stderr = stderr + "\n[CLike EvalRunner] " + sandbox_resources.CONTAINER_RUNTIME_NOTE
            elif not ok and eval_tools.missing_from_failure(f"{stdout}\n{stderr}", self._tools_catalog()):
                missing = eval_tools.missing_from_failure(f"{stdout}\n{stderr}", self._tools_catalog())
                blocked, noted = True, True
                stderr = stderr + f"\n{_MISSING_TOOLS_NOTE}: {', '.join(missing)}. Not a defect of the code: CLike asks the developer to install them (its tools catalog) and runs the check again."
            elif not ok:
                blocked = self._is_environment_blocked(
                    code=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    environment_requirements=environment_requirements or [],
                    cwd=cwd,
                )

            if blocked and not ok and not noted:
                stderr = (
                    stderr
                    + "\n[CLike EvalRunner] Classified as environment-blocked: "
                    "missing tool, unavailable dependency, native binary mismatch, "
                    "network restriction, or sandbox/runtime incompatibility."
                )[-4000:]
            excerpt = None if ok else eval_failures.excerpt(stdout, stderr)
            if noted and excerpt is not None:
                excerpt = f"{excerpt.rstrip()}\n{stderr.rstrip().splitlines()[-1]}"  # CLike's note, always shown
            return EvalCase(
                name=name,
                passed=ok,
                code=proc.returncode,
                stdout=stdout[-4000:],
                stderr=stderr[-4000:],
                cmd=cmd,
                cwd=str(cwd),
                expect=expect,
                blocked=blocked and not ok,
                blocking=blocking,
                excerpt=excerpt,
                fingerprint=eval_failures.fingerprint(excerpt) if excerpt else None,
            )
        except EvalCancelled:
            return EvalCase(
                name=name,
                passed=False,
                code=997,
                stdout="",
                stderr="[CLike EvalRunner] cancelled: the caller disconnected, the check was stopped.",
                cmd=cmd,
                cwd=str(cwd),
                expect=expect,
                blocked=True,
                blocking=blocking,
            )
        except subprocess.TimeoutExpired as exc:
            return EvalCase(
                name=name,
                passed=False,
                code=998,
                stdout=_text(exc.stdout)[-4000:],
                stderr=_head_tail(
                    _text(exc.stderr)
                    + f"\n[CLike EvalRunner] timeout: the check was stopped after {timeout} s. A test or the code"
                    " under test hangs (e.g. a network call or a server without a timeout, a task never"
                    " cancelled). For pytest, the traceback dump above shows where it was blocked.",
                    4000,
                ),
                cmd=cmd,
                cwd=str(cwd),
                expect=expect,
                blocked=False,
                blocking=blocking,
            )
        except Exception as exc:
            return EvalCase(
                name=name,
                passed=False,
                code=999,
                stdout="",
                stderr=str(exc),
                cmd=cmd,
                cwd=str(cwd),
                expect=expect,
                blocked=False,
                blocking=blocking,
            )

    def _collect_eval_test_files(self, root: Path) -> List[Path]:
        """Collect concrete test files for runtimes that do not expand globs."""
        if not root.exists():
            return []

        patterns = (
            "*.test.mjs",
            "*.test.js",
            "*.spec.mjs",
            "*.spec.js",
            "*.spec.py",
            "*.test.py",
            "*.py",
        )

        files: List[Path] = []
        seen: set[str] = set()
        for pattern in patterns:
            for path in root.rglob(pattern):
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(path.resolve())

        return sorted(files, key=lambda item: str(item))

    _MISSING_BROWSER_RE = re.compile(r"Executable doesn't exist at [^\n]*ms-playwright|npx playwright install")

    def _playwright_version(self, *roots: Optional[Path]) -> Optional[str]:
        for root in roots:
            if not root or not root.exists():
                continue
            for manifest in root.rglob("node_modules/playwright-core/package.json"):
                try:
                    version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
                except Exception:
                    continue
                if version and re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", str(version)):
                    return str(version)
        return None

    def _recover_missing_browser(
        self,
        *,
        result: EvalCase,
        cmd: str,
        cwd: Path,
        env: Dict[str, str],
        work_kit_root: Optional[Path],
        timeout: Optional[int],
        blocking: bool,
        environment_requirements: Optional[List[str]] = None,
    ) -> EvalCase:
        """A Playwright check that fails because the browser is not downloaded: download Chromium
        in the version of the project's Playwright (the image carries only its system libraries)
        and run the check once more."""
        if result.passed or not self._MISSING_BROWSER_RE.search(f"{result.stdout}\n{result.stderr}"):
            return result
        version = self._playwright_version(cwd, work_kit_root)
        install_cmd = f"npx --yes playwright{'@' + version if version else ''} install chromium"
        install = self._run(name=f"{result.name}::browser-install", cmd=install_cmd, cwd=cwd, env=env, timeout=900)
        if not install.passed:
            result.stderr = (
                result.stderr
                + f"\n[CLike EvalRunner] browser download failed ({install_cmd}): "
                + (install.stderr or install.stdout)[-800:]
            )[-4000:]
            return result
        retry = self._run(
            name=result.name,
            cmd=cmd,
            cwd=cwd,
            expect=result.expect if result.expect is not None else 0,
            env=env,
            timeout=timeout,
            blocking=blocking,
            environment_requirements=environment_requirements,
        )
        retry.stderr = (f"[CLike EvalRunner] Chromium downloaded ({install_cmd}); check re-run.\n" + retry.stderr)[-4000:]
        return retry

    def _recover_node_test_glob_failure(
        self,
        *,
        result: EvalCase,
        cmd: str,
        cwd: Path,
        env: Dict[str, str],
        work_kit_root: Optional[Path],
        timeout: Optional[int],
        blocking: bool,
    ) -> EvalCase:
        """
        Recover generated Node test scripts that pass an unexpanded glob to node --test.

        Some generated CI scripts invoke node --test with a literal argument such
        as test/**/*.test.mjs. On runners where Node does not expand that glob,
        the test case fails even though concrete test files exist. EvalRunner can
        safely recover by running the same Node test runner against explicit files.
        """
        if result.passed or not work_kit_root:
            return result

        text = f"{result.stdout}\n{result.stderr}"
        if "Could not find" not in text or "**/*.test." not in text:
            return result

        if "run-tests" not in cmd and "node --test" not in cmd:
            return result

        test_files: List[Path] = []
        test_files.extend(self._collect_eval_test_files(work_kit_root / "test"))
        test_files.extend(self._collect_eval_test_files(work_kit_root / "tests"))

        if not test_files:
            return result

        fallback_cmd = "node --test " + " ".join(shlex.quote(str(path)) for path in test_files)

        recovered = self._run(
            name=result.name,
            cmd=fallback_cmd,
            cwd=work_kit_root,
            expect=result.expect if result.expect is not None else 0,
            env=env,
            timeout=timeout,
            blocking=blocking,
            environment_requirements=[],
        )

        if recovered.passed:
            recovered.cmd = f"{result.cmd}\n[CLike EvalRunner fallback] {fallback_cmd}"
            recovered.stdout = (
                (result.stdout or "")
                + "\n[CLike EvalRunner] Recovered Node test glob failure by executing concrete test files.\n"
                + (recovered.stdout or "")
            )[-4000:]
            recovered.stderr = (recovered.stderr or "")[-4000:]
            recovered.cwd = str(cwd)

        return recovered

    def _raw_secret_findings_are_dependency_only(self, stderr: str) -> bool:
        """
        Return True only when a generated raw-secret scanner failed exclusively
        because it scanned installed/generated dependency trees.

        This is intentionally narrow:
        - candidate-owned source/test/docs/ci findings remain blocking;
        - mixed findings remain blocking;
        - non raw-secret scanner failures remain blocking.
        """
        text = str(stderr or "")
        if "Potential raw secrets found:" not in text:
            return False

        finding_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("Potential raw secrets found:")
        ]

        if not finding_lines:
            return False

        excluded_markers = (
            "/node_modules/",
            "/.npm-cache/",
            "/local-eval-workspaces/",
            "/coverage/",
            "/dist/",
            "/build/",
            "/.cache/",
            "/.tmp/",
            "/__pycache__/",
            "/.venv/",
            "/.next/",
        )

        return all(any(marker in line for marker in excluded_markers) for line in finding_lines)

    def _normalize_raw_secret_scan_result(self, result: EvalCase) -> EvalCase:
        """
        Generated check-no-secrets scripts must not scan installed dependencies.

        If an already-generated KIT still scans dependency/generated folders and
        reports findings only there, treat it as a recovered scanner-scope issue.
        Do not suppress candidate-owned findings.
        """
        if result.passed:
            return result

        cmd = str(result.cmd or "")
        if "check-no-secrets" not in cmd:
            return result

        if not self._raw_secret_findings_are_dependency_only(result.stderr):
            return result

        return EvalCase(
            name=result.name,
            passed=True,
            code=0,
            stdout=(
                (result.stdout or "")
                + "\n[CLike EvalRunner] Recovered raw-secret scanner false positive: "
                "all findings were under dependency/generated/temp directories. "
                "Candidate-owned files remain subject to blocking secret scanning.\n"
            )[-4000:],
            stderr="",
            cmd=result.cmd,
            cwd=result.cwd,
            expect=result.expect,
            blocked=False,
            blocking=result.blocking,
        )

    def _is_environment_blocked(
        self,
        *,
        code: int,
        stdout: str,
        stderr: str,
        environment_requirements: List[str],
        cwd: Optional[Path] = None,
    ) -> bool:
        text = f"{stdout}\n{stderr}".lower()

        if code not in {126, 127} and self._looks_like_executed_diagnostic_failure(text):
            return False

        # A module of the candidate itself (relative, absolute in the workspace, or a path alias)
        # that cannot be resolved is a code defect (a missing file, a wrong import), not the sandbox.
        if re.search(
            r"(cannot find module|failed to resolve import|module not found: (error: )?can't resolve)"
            r" ['\"](\.{1,2}/|@/|~/|/(?![^'\"]*node_modules)[^'\"]*/(work|test|tests|src)/)",
            text,
        ):
            return False

        # A missing module that is a file of the project (a test helper, a package of the candidate)
        # is a wrong import or path, not a missing dependency: the repair fixes it.
        missing = _MISSING_MODULE_RE.findall(f"{stdout}\n{stderr}")
        if missing and _project_modules([cwd, self.project_root], [name for _, name in missing]):
            return False

        # A generated CI script that calls mkdtemp under a local eval workspace
        # without creating the parent directory is not an environment blockage.
        # It is a deterministic, repairable candidate CI defect.
        if "mkdtemp" in text and "enoent" in text and "local-eval-workspaces" in text:
            return False

        if code == 127:
            return True

        markers = [
            # Missing local tools/dependencies.
            "command not found",
            "sqlite3: not found",
            ": not found",
            "no module named",
            "cannot find module",
            "cannot find package",
            "err_module_not_found",
            "module_not_found",
            "err_unknown_builtin_module",
            "node:sqlite",
            "better-sqlite3 is required",
            "requires a node runtime that exposes",
            "could not locate the bindings file",
            # Python/package-manager environment issues.
            "externally-managed-environment",
            "could not find a version that satisfies the requirement",

            # Network/package registry issues.
            "failed to establish a new connection",
            "temporary failure in name resolution",
            "network is unreachable",
            "connection refused",
            # Native dependency / binary ABI mismatch.
            # Example: better-sqlite3 compiled for a different OS/arch/container.
            "invalid elf header",
            "err_dlopen_failed",
            "node_module_version",
            "was compiled against a different node.js version",
            "wrong architecture",
            "bad cpu type in executable",
            "mach-o file",
            "cannot open shared object file",
            "shared object",
            "dynamic module",
            "node-gyp",
            "gyp err!",
            "prebuild-install",
            "make: not found",
            "python: not found",

            # Permission/sandbox issues.
            "permission denied",
            "read-only file system",
            "erofs:",
            "enoent: no such file or directory",
        ]
        if any(marker in text for marker in markers):
            return True

        return bool(environment_requirements) and code in {126, 127}

    def _looks_like_executed_diagnostic_failure(self, text: str) -> bool:
        """Return True when a quality tool ran and emitted actionable diagnostics."""
        diagnostic_markers = [
            r"error ts\d+:",
            r"\btsc\b.*--noemit",
            r"\beslint\b.*\b(error|errors)\b",
            r"\bprettier\b.*\b(error|errors|failed)\b",
            r"\bpytest\b.*\bfailed\b",
            r"\bvitest\b.*\bfailed\b",
            r"\bjest\b.*\bfailed\b",
            r"\bnode --test\b.*\bfail\b",
            r"found \d+ vulnerabilit",
            r"\bcritical\b.*\bvulnerabilit",
            r"\bhigh\b.*\bvulnerabilit",
        ]
        # A test runner ran the tests and some failed (vitest, jest, Playwright, pytest, go, cargo,
        # node --test): its errors are the candidate's, whatever their wording ("element(s) not
        # found", "Unable to find an element"). Matched line by line.
        runner_markers = [
            r"^\s*\d+ failed\b",
            r"\btests?\b[^\n]*\b\d+ failed\b",
            r"=+ .*\d+ failed",
            r"\bassertionerror\b",
            r"\btestinglibraryelementerror\b",
            r"\bexpect\([^\n]*\)\.\w+",
            r"^--- fail:",
            r"test result: failed",
            r"^# fail\s+[1-9]",
        ]
        return any(
            re.search(marker, text, flags=re.IGNORECASE | re.DOTALL) for marker in diagnostic_markers
        ) or any(re.search(marker, text, flags=re.IGNORECASE | re.MULTILINE) for marker in runner_markers)

    def _safe_req_id(self, req_id: Optional[str]) -> str:
        raw = req_id or "REQ-UNKNOWN"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)

    def _is_writable_dir(self, path: Path) -> bool:
        """
        Return True only if the directory can be created and written to.

        This is intentionally stronger than os.access because Podman/bind mounts
        may look accessible but fail at actual write time.
        """
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".clike-write-probe"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def _eval_base_dir(self) -> Path:
        """
        Resolve the writable eval base directory.

        Preferred:
        - CLIKE_EVAL_ROOT when explicitly provided
        - <project>/runs/eval when writable

        Fallback:
        - system temp directory, useful when the project is mounted read-only
          inside Podman or other restricted runners.
        """
        explicit = os.getenv("CLIKE_EVAL_ROOT", "").strip()
        candidates: List[Path] = []

        if explicit:
            candidates.append(Path(explicit))

        candidates.append(self.project_root / "runs" / "eval")

        project_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.project_root.name or "project")
        # Eval sandbox: a disk volume, so venvs, node_modules and caches do not take the memory
        # of the container as a tmpfs /tmp does (an npm install of a Next app was OOM-killed).
        base = os.getenv("CLIKE_EVAL_BASE_DIR", "").strip()
        if base:
            candidates.append(Path(base) / project_key)
        candidates.append(Path(tempfile.gettempdir()) / "clike-eval" / project_key)

        for candidate in candidates:
            resolved = candidate if candidate.is_absolute() else (self.project_root / candidate)
            if self._is_writable_dir(resolved):
                return resolved.resolve()

        raise OSError(
            "No writable eval directory found. Tried: "
            + ", ".join(str(candidate) for candidate in candidates)
        )



    def _npm_store_dir(self, key: str) -> Path:
        """Installed node_modules by manifest + lockfile digest, shared by every eval and regression
        of the project: a fresh work copy links them instead of running npm again (minutes per JS
        REQ in each regression)."""
        return self._eval_base_dir() / ".npm-store" / key

    @staticmethod
    def _link_tree(src: Path, dst: Path) -> bool:
        """Copy a tree with hard links (instant, no extra disk); copies when linking is not possible.
        Directories are new, so files a test creates never reach the store."""
        try:
            for dirpath, dirnames, filenames in os.walk(src):
                rel = Path(dirpath).relative_to(src)
                (dst / rel).mkdir(parents=True, exist_ok=True)
                for name in filenames:
                    s_file, d_file = Path(dirpath) / name, dst / rel / name
                    if s_file.is_symlink():
                        os.symlink(os.readlink(s_file), d_file)
                        continue
                    try:
                        os.link(s_file, d_file)
                    except OSError:
                        shutil.copy2(s_file, d_file)
                for name in dirnames:  # symlinked directories (npm bin links, workspaces)
                    if (Path(dirpath) / name).is_symlink():
                        os.symlink(os.readlink(Path(dirpath) / name), dst / rel / name)
            return True
        except OSError as exc:
            log.info("npm store link %s -> %s failed: %s", src, dst, exc)
            shutil.rmtree(dst, ignore_errors=True)
            return False

    def _npm_cache_dir(self) -> Path:
        """One npm cache per project, shared by the REQ, its regression and its services: the
        REQs install the same packages (one cache per eval directory held 40 copies, 7.6 GB, and
        every regression downloaded them again). npm's cache is safe to share."""
        return self._eval_base_dir() / ".npm-cache"

    def _resolve_req_file(self, req_file: str) -> Path:
        raw = Path(req_file)
        return raw if raw.is_absolute() else (self.project_root / raw).resolve()

    def _shared_test_support_cases(self, req_id: str) -> List[EvalCase]:
        """A KIT replacing a test-support file of the promoted tree (a helper or fixture module, not
        a test: test/fixtures.ts, a *_support.py, a TestBase.java, a Go helper) must keep the
        public names the promoted REQs' tests use, in any language CLike reads (_public_names). A
        dropped one breaks their regression late (a suite that does not load, an e2e that times
        out); caught here, the repair knows the file and the names. A name counts as used when a
        test of the promoted tree — in the version after promotion, the candidate's reconciled one
        when it has it — names it and refers to the module (its stem) or sits in the same directory
        (Go, Java packages). The root conftest.py has its own check."""
        cases: List[EvalCase] = []
        kit = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
        for top in ("test", "tests"):
            canonical_root, kit_root = self.project_root / top, kit / top
            if not (canonical_root.is_dir() and kit_root.is_dir()):
                continue
            canonical_texts: Dict[str, str] = {}
            for item in canonical_root.rglob("*"):
                rel_parts = item.relative_to(canonical_root).parts
                if not item.is_file() or any(part in _SHARED_SCAN_SKIP or part == "node_modules" for part in rel_parts):
                    continue
                if item.stat().st_size > 512 * 1024:
                    continue
                try:
                    canonical_texts[item.relative_to(canonical_root).as_posix()] = item.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            for rel, before_text in sorted(canonical_texts.items()):
                candidate = kit_root / rel
                if rel in _SHARED_ROOT_TEST_FILES or not candidate.is_file():
                    continue
                if _TEST_FILE_NAME_RE.search(Path(rel).name) or _DEFINES_TESTS_RE.search(before_text):
                    continue  # a test, not a support file
                try:
                    after_text = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if after_text == before_text:
                    continue
                before, after = _public_names(candidate, before_text), _public_names(candidate, after_text)
                if before is None or after is None or not (before - after):
                    continue
                stem, here = Path(rel).stem, Path(rel).parent
                users: Dict[str, List[str]] = {}
                for other_rel, other_text in canonical_texts.items():
                    if other_rel == rel:
                        continue
                    reconciled = kit_root / other_rel
                    if reconciled.is_file():
                        try:
                            other_text = reconciled.read_text(encoding="utf-8")
                        except (OSError, UnicodeDecodeError):
                            pass
                    if stem not in other_text and Path(other_rel).parent != here:
                        continue
                    for name in sorted(before - after):
                        if re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", other_text):
                            users.setdefault(name, []).append(f"{top}/{other_rel}")
                if not users:
                    continue
                listed = "; ".join(
                    f"{name} (used by {', '.join(files[:3])}{' …' if len(files) > 3 else ''})" for name, files in sorted(users.items())
                )
                message = (
                    f"runs/kit/{req_id}/{top}/{rel} replaces the shared {top}/{rel} of the promoted REQs and drops "
                    f"{len(users)} name(s) their tests use: {listed}. Keep them (add this REQ's part next to them), "
                    f"or reconcile the tests that use them in runs/kit/{req_id}/{top}/ if this REQ changes them on purpose."
                )
                cases.append(EvalCase(name=f"structure::shared-test-support::{top}/{rel}", passed=False, code=1, stdout="",
                                      stderr=message, blocking=True, excerpt=message,
                                      fingerprint=f"shared-test-support-{top}/{rel}"))
        return cases

    def _test_layout_cases(self, req_id: str) -> List[EvalCase]:
        """A KIT must not add a file that changes how the promoted REQs' tests are collected or
        import their helpers (_TEST_LAYOUT_FILE: a package marker, a conftest, a runner or build
        config) in a test directory of the promoted tree or one of its parents. After promotion it
        sits next to their tests: B2B REQ-025 added __init__.py files under test/ and REQ-003's
        tests no longer imported their helpers by name. The regression shows it only once the
        REQ's own checks pass; this check needs no run, so the first eval names the files."""
        cases: List[EvalCase] = []
        kit = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
        for top in ("test", "tests"):
            canonical_root, kit_root = self.project_root / top, kit / top
            if not (canonical_root.is_dir() and kit_root.is_dir()):
                continue
            shared_dirs = {Path(".")}
            for item in canonical_root.rglob("*"):
                rel_parts = item.relative_to(canonical_root).parts
                if any(part in _SHARED_SCAN_SKIP or part == "node_modules" for part in rel_parts):
                    continue
                if item.is_file():
                    parent = item.parent.relative_to(canonical_root)
                    shared_dirs.update([parent, *parent.parents])
            added = []
            for rel_dir in sorted(shared_dirs):
                folder = kit_root / rel_dir
                if not folder.is_dir():
                    continue
                for path in sorted(folder.iterdir()):
                    rel = (rel_dir / path.name).as_posix()
                    if path.is_file() and _TEST_LAYOUT_FILE.match(path.name) and not (canonical_root / rel).exists():
                        added.append(f"{top}/{rel}")
            if not added:
                continue
            listed = ", ".join(f"runs/kit/{req_id}/{rel}" for rel in added[:12]) + (" …" if len(added) > 12 else "")
            message = (
                f"This KIT adds {len(added)} file(s) that change how the tests of the promoted REQs are collected or "
                f"import their helpers, in test directories they share: {listed}. After promotion they sit next to "
                f"those tests (a package marker turns their directory into a package: imports by name of a sibling "
                f"helper stop working; a conftest or runner config changes their fixtures and options). Remove them; "
                f"make this REQ's tests import their helpers the way the promoted tests do (the check's import path), "
                f"and put this REQ's own fixtures or config in a directory of its own."
            )
            cases.append(EvalCase(name=f"structure::test-layout::{top}", passed=False, code=1, stdout="",
                                  stderr=message, blocking=True, excerpt=message, fingerprint=f"test-layout-{top}"))
        return cases

    def _shared_conftest_cases(self, req_id: str) -> List[EvalCase]:
        """A KIT's root conftest.py replaces the canonical one shared by every promoted REQ at
        promotion: it must keep each fixture/helper the canonical one defines. Dropping them breaks
        the earlier REQs' tests and stops the promotion on a conflict after a passing gate; caught
        here, the repair moves the REQ's fixtures into its own test package."""
        import ast

        cases: List[EvalCase] = []
        kit = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
        for top in ("test", "tests"):
            canonical, candidate = self.project_root / top / "conftest.py", kit / top / "conftest.py"
            if not (canonical.is_file() and candidate.is_file()):
                continue

            def names(path: Path) -> Optional[set]:
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except (OSError, SyntaxError, ValueError):
                    return None
                return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

            before, after = names(canonical), names(candidate)
            if before is None or after is None:
                continue
            missing = sorted(before - after)
            name = f"structure::shared-conftest::{top}"
            if missing:
                message = (
                    f"runs/kit/{req_id}/{top}/conftest.py replaces the shared {top}/conftest.py of the promoted REQs "
                    f"and drops {len(missing)} of its definitions: {', '.join(missing)}. The root conftest is shared: "
                    f"keep every existing fixture and helper (copy the canonical {top}/conftest.py and add to it), or "
                    f"put this REQ's fixtures in its own package conftest (runs/kit/{req_id}/{top}/<package>/conftest.py) "
                    f"and do not ship a root conftest."
                )
                cases.append(EvalCase(name=name, passed=False, code=1, stdout="", stderr=message, blocking=True,
                                      excerpt=message, fingerprint=f"shared-conftest-{top}"))
            else:
                cases.append(EvalCase(name=name, passed=True, code=0, stdout="keeps every shared definition",
                                      stderr="", blocking=False))
        return cases

    def _compose_root_files(self, kit_root: Path, work_kit_root: Path, dependency_roots: List[str]) -> None:
        """Repository-root deliverables (scripts/, deploy/, root manifests…) at the workspace root, as
        they will be after promotion: the canonical ones, the root/ of the dependency KITs not
        promoted yet, then the candidate's root/ (and, in a regression, the candidate being checked)."""
        policy = root_policy(self.project_root)
        # (layer, newer_check): a done REQ without a promotion record keeps newer canonical files
        # history: the project KIT root/ a dependency copy comes from, for the commit times
        layers: List[tuple] = [(self.project_root, False, None)]
        for dep_raw in dependency_roots:
            dep = Path(dep_raw)
            mode = self._kit_layer_mode(dep.name)
            if mode != "skip":
                history = self.project_root / "runs" / "kit" / dep.name / KIT_ROOT_DIR
                layers.append((dep / KIT_ROOT_DIR, mode == "newer", history))
        own_mode = self._kit_layer_mode(kit_root.name) if self.regression else "full"
        if own_mode != "skip":
            layers.append((kit_root / KIT_ROOT_DIR, own_mode == "newer", None))
        layers += [(Path(p), False, None) for p in self.extra_root_roots]
        for layer, newer_check, history in layers:
            for name in policy["folders"]:
                if (layer / name).is_dir():
                    canonical = self.project_root / name if newer_check else None
                    self._copy_tree_overlay(
                        layer / name, work_kit_root / name, canonical=canonical,
                        history=history / name if history is not None else None,
                    )
            for name in policy["files"]:
                if (layer / name).is_file() and not (
                    newer_check and self._canonical_is_newer(
                        layer / name, self.project_root / name, history / name if history is not None else None
                    )
                ):
                    shutil.copy2(layer / name, work_kit_root / name)
            # env examples, ignore files, the solution eval profile, project docs (not the project
            # tree itself: it has them already where they are)
            if layer != self.project_root:
                for rel in extra_root_files(layer, policy):
                    target = work_kit_root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(layer / rel, target)

    def _copy_tree_overlay(
        self,
        src: Path,
        dst: Path,
        canonical: Optional[Path] = None,
        history: Optional[Path] = None,
        take_canonical: bool = False,
        kit_only: frozenset = frozenset(),
    ) -> List[str]:
        """
        Copy a tree into an overlay destination.

        Later copies win. This keeps the implementation intentionally simple:
        promoted roots first, dependency KIT roots next, current KIT last.
        With ``canonical`` (the canonical root ``dst`` was composed from), a file whose canonical
        copy is newer is kept (see ``_kit_layer_mode``); ``history`` is the project tree ``src`` was
        copied from, for the commit times. ``take_canonical`` writes that newer canonical copy (when
        ``dst`` was not composed from the canonical tree); ``kit_only`` relative paths always keep
        the ``src`` copy. Returns the relative paths whose canonical copy was taken.
        """
        taken: List[str] = []
        if not src.exists():
            return taken

        # installed dependencies, build output and scratch are never composed: a candidate's
        # node_modules overlaid into a regression workspace shadowed the other REQ's own install
        ignored_names = {
            "__pycache__", "__MACOSX", ".DS_Store", ".pytest_cache", ".mypy_cache", ".ruff_cache",
            "node_modules", ".venv", ".next", ".turbo", ".tmp", ".cache", ".npm-cache", ".npm",
            "local-eval-workspaces",
        }

        if src.is_file():
            if canonical is not None and self._canonical_is_newer(src, canonical, history):
                return taken
            if src.name not in ignored_names and src.suffix not in {".pyc", ".pyo"} and not _PROMOTION_SCRATCH_RE.search(src.name):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return taken

        for item in src.rglob("*"):
            rel = item.relative_to(src)
            if any(part in ignored_names for part in rel.parts):
                continue
            if item.suffix in {".pyc", ".pyo"} or _PROMOTION_SCRATCH_RE.search(item.name):
                continue

            target = dst / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if canonical is not None and rel.as_posix() not in kit_only and self._canonical_is_newer(
                item, canonical / rel, history / rel if history is not None else None
            ):
                if take_canonical:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(canonical / rel, target)
                    taken.append(rel.as_posix())
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        return taken

    def _overlay_existing_files(self, src: Path, dst: Path, canonical: Optional[Path] = None) -> List[str]:
        """Copy over ``dst`` the files of ``src`` that ``dst`` already has with different content (the
        candidate's version of a regressed REQ's test) and, once one is replaced, the candidate's new
        support files that version needs: the modules it imports, directly or through another copied
        module, from anywhere in the candidate's test tree, and a package marker or a conftest beside
        a replaced file. Other new files stay out: a conftest elsewhere is loaded by the test runner
        for the regressed REQ's own tests, and the candidate's tests run in its own checks. A
        candidate file identical to its ``canonical`` copy reconciles nothing (promotion does not
        change it). Returns the replaced or added relative paths."""
        changed: List[str] = []
        if not src.is_dir() or not dst.is_dir():
            return changed
        for target in sorted(dst.rglob("*")):
            if not target.is_file():
                continue
            rel = target.relative_to(dst)
            item = src / rel
            if not item.is_file():
                continue
            try:
                content = item.read_bytes()
                if content == target.read_bytes():
                    continue
                if canonical is not None and (canonical / rel).is_file() and (canonical / rel).read_bytes() == content:
                    continue  # the candidate carries the promoted file unchanged
            except OSError:
                continue
            shutil.copy2(item, target)
            changed.append(rel.as_posix())
        if not changed:
            return changed
        return changed + self._bring_imported_support(src, dst, changed)

    def _bring_imported_support(
        self, src: Path, dst: Path, changed: List[str], exclude: frozenset = frozenset()
    ) -> List[str]:
        """Copy into ``dst`` the support files of ``src`` (not in ``dst``, defining no test) that the
        ``changed`` files need: the modules they import, directly or through another copied module,
        and a package marker or a conftest beside a changed file; ``exclude`` relative paths never
        come. Returns the added paths."""
        added: List[str] = []
        support: Dict[str, Path] = {}  # new support files of src, by relative path
        for item in sorted(src.rglob("*")):
            rel = item.relative_to(src)
            if not item.is_file() or (dst / rel).exists() or rel.as_posix() in exclude:
                continue
            if any(part in _SHARED_SCAN_SKIP for part in rel.parts) or item.suffix in {".pyc", ".pyo"}:
                continue
            try:
                text = item.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _TEST_FILE_NAME_RE.search(item.name) or _DEFINES_TESTS_RE.search(text):
                continue  # a test of the candidate: its own checks run it
            support[rel.as_posix()] = item

        replaced_dirs = {Path(rel).parent for rel in changed}
        wanted = [
            rel for rel in support
            if Path(rel).parent in replaced_dirs and Path(rel).name in _BESIDE_SUPPORT_NAMES
        ]
        pending = [*changed, *wanted]
        seen = set(pending)
        while pending:
            rel = pending.pop()
            path = dst / rel if (dst / rel).is_file() else support.get(rel)
            for needed in _imported_support(rel, path, support, dst.parent / "src"):
                if needed not in seen:
                    seen.add(needed)
                    wanted.append(needed)
                    pending.append(needed)
        for rel in sorted(set(wanted)):
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(support[rel], dst / rel)
            added.append(rel)
        return added

    def _load_plan_dependencies(self, req_id: Optional[str]) -> List[str]:
        if not req_id:
            return []

        plan_path = self.project_root / "docs" / "harper" / "plan.json"
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
        except Exception:
            return []

        reqs = plan_data.get("reqs") or plan_data.get("req") or []
        current_req = next(
            (
                item
                for item in reqs
                if isinstance(item, dict) and str(item.get("id") or "") == str(req_id)
            ),
            None,
        )
        if not isinstance(current_req, dict):
            return []

        return [str(dep).strip() for dep in (current_req.get("dependsOn") or []) if str(dep).strip()]

    

    def _promoted_into_canonical(self, req_id: str) -> bool:
        """True when the REQ is done and an auto-merge promotion of it succeeded: the canonical tree
        already holds its source, merged with what later REQs changed. Overlaying its KIT copy
        again would put back files those later REQs had changed (stale code in the eval)."""
        cache = getattr(self, "_promoted_cache", None)
        if cache is None:
            cache = self._promoted_cache = {}
        if req_id in cache:
            return cache[req_id]
        promoted = False
        try:
            plan = json.loads((self.project_root / "docs" / "harper" / "plan.json").read_text(encoding="utf-8"))
            reqs = plan.get("reqs") or plan.get("req") or []
            entry = next((r for r in reqs if isinstance(r, dict) and str(r.get("id") or "") == str(req_id)), None)
            if isinstance(entry, dict) and str(entry.get("status") or "").strip().lower() in PROMOTED_REQ_STATUSES:
                promotion_dir = self.project_root / "runs" / "kit" / self._safe_req_id(str(req_id)) / "promotion"
                for report in sorted(promotion_dir.glob("*/report.json")):
                    try:
                        data = json.loads(report.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        data = {}  # unreadable report: not a promotion record
                    if isinstance(data, dict) and data.get("promoted") is True:
                        promoted = True
                        break
        except (OSError, ValueError, AttributeError):
            promoted = False
        cache[req_id] = promoted
        return promoted

    def _kit_layer_mode(self, req_id: str) -> str:
        """How a REQ's KIT copy goes over the canonical tree: ``skip`` once an auto-merge promotion of
        it is recorded; ``newer`` for a done REQ without that record (promoted before records, by an
        overwrite, or kept beside the tree by a folder/suffix strategy): each KIT file wins unless
        its canonical copy was committed later (a later REQ changed it); ``full`` for a REQ not
        promoted yet."""
        if self._promoted_into_canonical(req_id):
            return "skip"
        try:
            plan = json.loads((self.project_root / "docs" / "harper" / "plan.json").read_text(encoding="utf-8"))
            reqs = plan.get("reqs") or plan.get("req") or []
            entry = next((r for r in reqs if isinstance(r, dict) and str(r.get("id") or "") == str(req_id)), None)
            status = str(entry.get("status") or "").strip().lower() if isinstance(entry, dict) else ""
        except (OSError, ValueError, AttributeError):
            status = ""
        return "newer" if status in PROMOTED_REQ_STATUSES else "full"

    def _overlay_kit_layer(
        self, req_id: str, src: Path, dst: Path, canonical: Path, history: Optional[Path] = None
    ) -> None:
        mode = self._kit_layer_mode(req_id)
        if mode != "skip":
            self._copy_tree_overlay(src, dst, canonical=canonical if mode == "newer" else None, history=history)

    def _commit_time(self, path: Path) -> Optional[int]:
        """Unix time of the last commit touching ``path`` in the project repository, or None."""
        cache = getattr(self, "_commit_time_cache", None)
        if cache is None:
            cache = self._commit_time_cache = {}
        key = str(path)
        if key not in cache:
            try:
                rel = path.resolve().relative_to(self.project_root.resolve())
                out = subprocess.run(
                    ["git", "log", "-1", "--format=%ct", "--", rel.as_posix()],
                    cwd=self.project_root, capture_output=True, text=True, timeout=20,
                )
                cache[key] = int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
            except (OSError, ValueError, subprocess.SubprocessError):
                cache[key] = None
        return cache[key]

    def _canonical_is_newer(self, kit_file: Path, canonical_file: Path, history_file: Optional[Path] = None) -> bool:
        """True when ``canonical_file`` differs from the KIT copy and was committed after it
        (``history_file``: the KIT file in the project, when ``kit_file`` is a copy of it)."""
        try:
            if not canonical_file.is_file() or canonical_file.read_bytes() == kit_file.read_bytes():
                return False
        except OSError:
            return False
        canonical_time, kit_time = self._commit_time(canonical_file), self._commit_time(history_file or kit_file)
        return canonical_time is not None and kit_time is not None and canonical_time > kit_time

    def _prepare_eval_overlay_workspace(
        self,
        *,
        req_id: Optional[str],
        profile_path: Path,
    ) -> tuple[Optional[Path], List[str], Dict[str, str]]:
        """
        Build a dependency-aware eval overlay.

        Composition order:
        1. promoted src/test/tests
        2. dependency KIT src/test/tests in PLAN order
        3. current KIT src/test/tests

        This mirrors Harper dependency semantics without introducing runtime-specific logic.
        """
        kit_root = self._resolve_kit_root(profile_path=profile_path, req_id=req_id)
        if not kit_root:
            return None, [], {}

        eval_root = self._eval_dir(req_id)
        overlay = eval_root / "overlay" / "workspace"

        if overlay.exists():
            shutil.rmtree(overlay)
        overlay.mkdir(parents=True, exist_ok=True)

        dependency_roots: List[str] = []

        # Promoted canonical roots first.
        self._copy_tree_overlay(self.project_root / "src", overlay / "src")
        self._copy_tree_overlay(self.project_root / "test", overlay / "test")
        self._copy_tree_overlay(self.project_root / "tests", overlay / "tests")

        # Dependency KIT roots next.
        for dep_id in self._load_plan_dependencies(req_id):
            dep_root = self.project_root / "runs" / "kit" / self._safe_req_id(dep_id)
            if not dep_root.exists():
                continue

            dependency_roots.append(str(dep_root))
            for logical in ("src", "test", "tests"):
                self._overlay_kit_layer(dep_id, dep_root / logical, overlay / logical, self.project_root / logical)

        # Current KIT wins last (its source too, unless this is a regression of a promoted REQ).
        if self.regression:
            self._overlay_kit_layer(kit_root.name, kit_root / "src", overlay / "src", self.project_root / "src")
        else:
            self._copy_tree_overlay(kit_root / "src", overlay / "src")
        promoted_tests = self.regression and self._kit_layer_mode(kit_root.name) != "full"
        for logical in ("test", "tests"):
            # the promoted version of a reconciled test is the canonical one already copied above
            canonical = self.project_root / logical if promoted_tests else None
            self._copy_tree_overlay(
                kit_root / logical, overlay / logical, canonical=canonical, kit_only=_SHARED_ROOT_TEST_FILES
            )

        # Eval workspace contract hardening.
        #
        # If CLike exposes CLIKE_EVAL_WORKSPACE to generated CI scripts, that
        # workspace must be directly runnable. Existing generated scripts may
        # run test globs from either "test/" or "tests/"; both conventions are
        # valid, so the canonical overlay must bridge them.
        overlay_test = overlay / "test"
        overlay_tests = overlay / "tests"

        try:
            overlay_test_has_cases = overlay_test.exists() and any(overlay_test.rglob("*.test.*"))
            overlay_tests_has_cases = overlay_tests.exists() and any(overlay_tests.rglob("*.test.*"))

            if overlay_test_has_cases and not overlay_tests_has_cases:
                shutil.copytree(overlay_test, overlay_tests, dirs_exist_ok=True)

            if overlay_tests_has_cases and not overlay_test_has_cases:
                shutil.copytree(overlay_tests, overlay_test, dirs_exist_ok=True)

            # Last-resort current KIT enforcement. This protects canonical eval
            # from diverging from local-agent pre-pass when the overlay was
            # partially composed or one test convention was skipped upstream.
            overlay_test_has_cases = overlay_test.exists() and any(overlay_test.rglob("*.test.*"))
            overlay_tests_has_cases = overlay_tests.exists() and any(overlay_tests.rglob("*.test.*"))

            if not overlay_test_has_cases and (kit_root / "test").exists():
                self._copy_tree_overlay(kit_root / "test", overlay_test)

            if not overlay_tests_has_cases and (kit_root / "tests").exists():
                self._copy_tree_overlay(kit_root / "tests", overlay_tests)

            overlay_test_has_cases = overlay_test.exists() and any(overlay_test.rglob("*.test.*"))
            overlay_tests_has_cases = overlay_tests.exists() and any(overlay_tests.rglob("*.test.*"))

            if overlay_test_has_cases and not overlay_tests_has_cases:
                shutil.copytree(overlay_test, overlay_tests, dirs_exist_ok=True)

            if overlay_tests_has_cases and not overlay_test_has_cases:
                shutil.copytree(overlay_tests, overlay_test, dirs_exist_ok=True)

            log.info(
                "eval overlay prepared for %s: workspace=%s test_cases=%s tests_cases=%s",
                req_id,
                overlay,
                overlay_test_has_cases,
                overlay_tests_has_cases,
            )
        except Exception as exc:
            log.warning("Could not harden eval overlay test roots for %s: %s", req_id, exc)

        path_map = {
            "src": str(overlay / "src"),
            "test": str(overlay / "test"),
            "tests": str(overlay / "tests"),
            str(self.project_root / "src"): str(overlay / "src"),
            str(self.project_root / "test"): str(overlay / "test"),
            str(self.project_root / "tests"): str(overlay / "tests"),
        }

        if not kit_root:
            return None, [], {}
        return overlay, dependency_roots, path_map

    def _resolve_eval_path(self, value: Optional[str], path_map: Dict[str, str]) -> Path:
        if not value:
            return self.project_root

        raw = str(value)
        for source, target in sorted(path_map.items(), key=lambda item: len(item[0]), reverse=True):
            if raw == source or raw.startswith(source + "/"):
                raw = raw.replace(source, target, 1)
                break

        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path).resolve()

    def _runtime_working_directory(self, ltc: Dict[str, Any]) -> str:
        runtime = ltc.get("runtime") or {}
        if not isinstance(runtime, dict):
            return ""
        return str(
            runtime.get("working_directory")
            or runtime.get("workdir")
            or runtime.get("cwd")
            or ""
        ).strip()

    def _venv_dir(self, req_id: Optional[str]) -> Path:
        """
        Runtime eval virtualenvs must not be created under .clike or any path
        that may be read-only in a containerized runner.
        """
        return self._eval_base_dir() / ".venvs" / self._safe_req_id(req_id)

    def _venv_python(self, venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def _venv_bin(self, venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts"
        return venv_dir / "bin"

    def _requirements_hash(self, req_file: Path) -> str:
        try:
            data = req_file.read_bytes()
        except Exception:
            data = str(req_file).encode("utf-8")
        return hashlib.sha256(data).hexdigest()[:16]

    def _build_venv_env(self, base_env: Dict[str, str], venv_dir: Path) -> Dict[str, str]:
        env = dict(base_env)
        bin_dir = self._venv_bin(venv_dir)
        env["VIRTUAL_ENV"] = str(venv_dir)
        env["CLIKE_EVAL_VENV"] = str(venv_dir)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    def _ensure_eval_venv(
        self,
        *,
        req_id: Optional[str],
        requirements_file: Optional[str],
        env: Dict[str, str],
        cwd: Path,
    ) -> tuple[Dict[str, str], List[EvalCase]]:
        if not requirements_file:
            return env, []
        with _keyed_lock(f"venv:{self._venv_dir(req_id)}"):
            return self._ensure_eval_venv_locked(req_id=req_id, requirements_file=requirements_file, env=env, cwd=cwd)

    def _ensure_eval_venv_locked(
        self,
        *,
        req_id: Optional[str],
        requirements_file: str,
        env: Dict[str, str],
        cwd: Path,
    ) -> tuple[Dict[str, str], List[EvalCase]]:

        req_path = self._resolve_req_file(requirements_file)
        if not req_path.exists():
            case = EvalCase(
                name="env::requirements",
                passed=False,
                code=3,
                stdout="",
                stderr=f"requirements file not found: {req_path}",
                cmd=None,
                cwd=str(cwd),
                blocked=True,
                blocking=False,
            )
            return env, [case]

        venv_dir = self._venv_dir(req_id)
        venv_py = self._venv_python(venv_dir)
        cases: List[EvalCase] = []

        if not venv_py.exists():
            try:
                venv_dir.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                case = EvalCase(
                    name="env::venv-dir",
                    passed=False,
                    code=30,
                    stdout="",
                    stderr=f"cannot create eval venv directory {venv_dir.parent}: {exc}",
                    cmd=None,
                    cwd=str(cwd),
                    blocked=True,
                    blocking=False,
                )
                return env, [case]

            create_cmd = f"{shlex.quote(sys.executable)} -m venv {shlex.quote(str(venv_dir))}"        
            create_case = self._run(
                name="env::venv-create",
                cmd=create_cmd,
                cwd=cwd,
                expect=0,
                env=env,
                blocking=False,
            )
            cases.append(create_case)
            if not create_case.passed:
                create_case.blocked = True
                return env, cases

        venv_env = self._build_venv_env(env, venv_dir)
        marker = venv_dir / f".requirements-{self._requirements_hash(req_path)}.installed"

        if marker.exists():
            cases.append(
                EvalCase(
                    name="env::requirements",
                    passed=True,
                    code=0,
                    stdout=f"requirements already installed in {venv_dir}",
                    stderr="",
                    cmd=None,
                    cwd=str(cwd),
                    blocking=False,
                )
            )
            return venv_env, cases

        install_cmd = (
            f"{shlex.quote(str(venv_py))} -m pip install "
            f"--disable-pip-version-check --no-input -r {shlex.quote(str(req_path))}"
        )
        install_case = self._run(
            name="env::pip-install",
            cmd=install_cmd,
            cwd=cwd,
            expect=0,
            env=venv_env,
            blocking=True,
            environment_requirements=["pip", "network", "python-dependencies"],
        )

        if install_case.passed:
            try:
                marker.write_text("ok\n", encoding="utf-8")
            except Exception as exc:
                install_case.stderr = (install_case.stderr + f"\nmarker write warning: {exc}")[-4000:]
        else:
            install_case.blocked = False
            install_case.blocking = True

        cases.append(install_case)
        return venv_env, cases


    def _normalize_cases(self, ltc: Dict[str, Any]) -> List[Dict[str, Any]]:
        norm_cases: List[Dict[str, Any]] = []

        if isinstance(ltc.get("checks"), list) and ltc["checks"]:
            for check in ltc["checks"]:
                if not isinstance(check, dict):
                    continue

                required = check.get("required", True)
                blocking = bool(check.get("blocking", required))

                norm_cases.append(
                    {
                        "name": check.get("id") or check.get("name") or check.get("command") or "check",
                        "run": check.get("command") or check.get("run"),
                        "cwd": check.get("cwd"),
                        "expect": int(check.get("expect", check.get("expect_exit", 0))),
                        "timeout": check.get("timeout"),
                        "env": check.get("env") or {},
                        "blocking": blocking,
                        "environment_requirements": check.get("environment_requirements") or [],
                    }
                )
            return norm_cases

        if isinstance(ltc.get("cases"), list) and ltc["cases"]:
            for index, case in enumerate(ltc["cases"], start=1):
                if isinstance(case, str):
                    run = case.strip()
                    if not run:
                        continue
                    norm_cases.append(
                        {
                            "name": f"case::{index}",
                            "run": run,
                            "cwd": ltc.get("cwd") or ltc.get("working_directory"),
                            "expect": 0,
                            "timeout": None,
                            "env": {},
                            "blocking": True,
                            "environment_requirements": [],
                        }
                    )
                    continue

                if not isinstance(case, dict):
                    continue

                run = (
                    case.get("run")
                    or case.get("command")
                    or case.get("cmd")
                    or case.get("shell")
                )


                if not run:
                    norm_cases.append(
                        {
                            "name": case.get("id") or case.get("name") or f"case::{index}",
                            "run": None,
                            "cwd": case.get("cwd") or case.get("working_dir") or ltc.get("cwd") or ltc.get("working_directory"),
                            "expect": 0,
                            "timeout": case.get("timeout"),
                            "env": case.get("env") or {},
                            "blocking": bool(case.get("blocking", True)),
                            "environment_requirements": case.get("environment_requirements") or [],
                            "invalid_reason": "missing 'run' or 'command'",
                        }
                    )
                    continue

                expected = case.get(
                    "expected_exit_code",
                    case.get("expect_exit", case.get("expect", 0)),
                )

                required = case.get("required", True)
                blocking = bool(case.get("blocking", required))

                norm_cases.append(
                    {
                        "name": case.get("id") or case.get("name") or case.get("label") or f"case::{index}",
                        "run": run,
                        "setup": case.get("setup"),
                        "cwd": case.get("cwd") or case.get("working_dir") or ltc.get("cwd") or ltc.get("working_directory"),
                        "expect": int(expected),
                        "timeout": case.get("timeout"),
                        "env": case.get("env") or {},
                        "blocking": blocking,
                        "environment_requirements": case.get("environment_requirements") or [],
                    }
                )
            return norm_cases

        if isinstance(ltc.get("steps"), list) and ltc["steps"]:
            for step in ltc["steps"]:
                if not isinstance(step, dict):
                    continue
                norm_cases.append(
                    {
                        "name": step.get("name") or step.get("run") or "step",
                        "run": step.get("run"),
                        "cwd": step.get("cwd"),
                        "expect": int(step.get("expect_exit", step.get("expect", 0))),
                        "timeout": step.get("timeout"),
                        "env": step.get("env") or {},
                        "blocking": bool(step.get("blocking", True)),
                        "environment_requirements": step.get("environment_requirements") or [],
                    }
                )
            return norm_cases

        if isinstance(ltc.get("commands"), list) and ltc["commands"]:
            for index, command in enumerate(ltc["commands"], start=1):
                if isinstance(command, str):
                    run = command.strip()
                    if not run:
                        continue
                    norm_cases.append(
                        {
                            "name": f"command::{index}",
                            "run": run,
                            "cwd": ltc.get("cwd"),
                            "expect": 0,
                            "timeout": None,
                            "env": {},
                            "blocking": True,
                            "environment_requirements": [],
                        }
                    )
                    continue

                if not isinstance(command, dict):
                    continue

                run = (
                    command.get("run")
                    or command.get("command")
                    or command.get("cmd")
                    or command.get("shell")
                )
                if not run:
                    continue

                expected = command.get(
                    "expected_exit_code",
                    command.get("expect_exit", command.get("expect", 0)),
                )

                required = command.get("required", True)
                blocking = bool(command.get("blocking", required))

                norm_cases.append(
                    {
                        "name": command.get("id") or command.get("name") or command.get("label") or run,
                        "run": run,
                        "cwd": command.get("cwd") or command.get("working_dir") or ltc.get("cwd"),
                        "expect": int(expected),
                        "timeout": command.get("timeout"),
                        "env": command.get("env") or {},
                        "blocking": blocking,
                        "environment_requirements": command.get("environment_requirements") or [],
                    }
                )
            return norm_cases

        if isinstance(ltc.get("commands"), dict) and ltc["commands"]:
            for name, raw in ltc["commands"].items():
                if isinstance(raw, list):
                    run = " && ".join(str(item) for item in raw if str(item).strip())
                elif isinstance(raw, dict):
                    run = raw.get("run") or raw.get("command")
                else:
                    run = str(raw)

                if not run:
                    continue

                norm_cases.append(
                    {
                        "name": str(name),
                        "run": run,
                        "cwd": raw.get("cwd") if isinstance(raw, dict) else ltc.get("cwd"),
                        "expect": int(raw.get("expect", 0)) if isinstance(raw, dict) else 0,
                        "timeout": raw.get("timeout") if isinstance(raw, dict) else None,
                        "env": raw.get("env") if isinstance(raw, dict) else {},
                        "blocking": bool(raw.get("blocking", raw.get("required", True))) if isinstance(raw, dict) else True,                       
                        "environment_requirements": raw.get("environment_requirements") if isinstance(raw, dict) else [],
                    }
                )
            return norm_cases

        if ltc.get("run"):
            norm_cases.append(
                {
                    "name": "default",
                    "run": ltc.get("run"),
                    "cwd": ltc.get("cwd"),
                    "expect": int(ltc.get("expect", 0)),
                    "timeout": ltc.get("timeout"),
                    "env": ltc.get("env_case") or {},
                    "blocking": True,
                    "environment_requirements": ltc.get("environment_requirements") or [],
                }
            )

        return norm_cases

    def _eval_dir(self, req_id: Optional[str]) -> Path:
        if self.eval_key:
            return self._eval_base_dir().joinpath(*(self._safe_req_id(part) for part in self.eval_key.split("/")))
        return self._eval_base_dir() / self._safe_req_id(req_id)

    def _path_relative_to_project(self, path: Path) -> Optional[str]:
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except Exception:
            return None

    def _resolve_kit_root(
        self,
        *,
        profile_path: Path,
        req_id: Optional[str],
    ) -> Optional[Path]:
        """
        Resolve the candidate KIT root from the LTC profile path.

        Expected shape:
        runs/kit/<REQ-ID>/ci/LTC.json
        """
        try:
            current = profile_path.resolve()
        except Exception:
            current = profile_path

        for parent in [current.parent, *current.parents]:
            if parent.name == "ci" and parent.parent.name:
                candidate = parent.parent
                if (candidate / "ci").exists() and (candidate / "src").exists():
                    return candidate.resolve()

        if req_id:
            candidate = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
            if candidate.exists():
                return candidate.resolve()

        return None

    def _prepare_eval_workspace(
        self,
        *,
        req_id: Optional[str],
        profile_path: Path,
    ) -> tuple[Path, Path, Path, Dict[str, str], Optional[Path], List[str]]:
        """
        Create a writable eval workspace.

        runs/kit/<REQ-ID> is treated as candidate input.
        runs/eval/<REQ-ID>/work/<REQ-ID> is the writable execution copy.
        runs/eval/<REQ-ID>/reports is the report output root.
        """

        eval_dir = self._eval_dir(req_id)
        work_root = eval_dir / "work"
        reports_root = eval_dir / "reports"
        logs_root = eval_dir / "logs"
        dependency_roots: List[str] = []

        for path in (
            work_root,
            reports_root,
            logs_root,
            eval_dir / ".npm-cache",
            eval_dir / ".ruff-cache",
            eval_dir / ".mypy-cache",
            eval_dir / ".pycache",
            eval_dir / ".cache",
        ):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise OSError(
                    f"Cannot create writable eval workspace path {path}. "
                    f"Resolved eval base was {self._eval_base_dir()}. "
                    f"Original error: {exc}"
                ) from exc

        kit_root = self._resolve_kit_root(profile_path=profile_path, req_id=req_id)
        if not kit_root:
            return work_root, reports_root, logs_root, {}, None, dependency_roots

        work_kit_root = work_root / kit_root.name
        if work_kit_root.exists():
            shutil.rmtree(work_kit_root)

        everywhere = _KIT_COPY_IGNORE
        # The solution profile (ci/SOLUTION_LTC.json at the project root, /finalize): the canonical
        # tree without CLike's runs, the local state and the git history (top level only: a
        # source directory may be called runs).
        solution_root = kit_root == self.project_root
        top_level_skip = {".git", "runs", ".clike", ".vscode", ".idea", "local-eval-workspaces", ".next", "coverage"}

        def ignore(directory: str, names: List[str]) -> set:
            skipped = set(everywhere(directory, names))
            skipped |= {n for n in names if _PROMOTION_SCRATCH_RE.search(n)}
            if solution_root:
                here = Path(directory).resolve()
                if here == kit_root:
                    skipped |= {n for n in names if n in top_level_skip}
                elif here == kit_root / "docs":
                    skipped |= {n for n in names if n == "_private"}
            return skipped

        shutil.copytree(kit_root, work_kit_root, ignore=ignore, copy_function=_copy_if_present)
        
        plan_path = self.project_root / "docs" / "harper" / "plan.json"
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
            reqs = plan_data.get("reqs") or plan_data.get("req") or []
            current_req = next(
                (
                    item
                    for item in reqs
                    if isinstance(item, dict) and str(item.get("id") or "") == kit_root.name
                ),
                None,
            )
            depends_on = list(current_req.get("dependsOn") or []) if isinstance(current_req, dict) else []

            deps_root = work_root / "_deps"
            deps_root.mkdir(parents=True, exist_ok=True)

            for dep_id in depends_on:
                dep_safe = self._safe_req_id(str(dep_id))
                dep_kit = self.project_root / "runs" / "kit" / dep_safe
                if not dep_kit.exists():
                    continue

                dep_work = deps_root / dep_safe
                if dep_work.exists():
                    shutil.rmtree(dep_work)

                shutil.copytree(
                    dep_kit,
                    dep_work,
                    ignore=_KIT_COPY_IGNORE,
                    copy_function=_copy_if_present,
                )
                dependency_roots.append(str(dep_work))
        except Exception:
            dependency_roots = []
            
        # Canonical eval workspace for generated KIT scripts.
        #
        # Do not expose a second overlay workspace to already-generated CI
        # scripts. REQ-local scripts commonly execute from work/<REQ>/ci and
        # resolve ../src or ../test. Therefore the safest runtime contract is:
        #
        #   CLIKE_EVAL_WORKSPACE = work/<REQ>
        #
        # and work/<REQ> must contain the composed dependency-aware src/test
        # tree:
        #
        #   promoted src/test/tests
        #   + dependency KIT src/test/tests
        #   + current KIT src/test/tests
        #
        # Current KIT wins last. ci/docs remain from the current KIT copy.
        composed_root = work_root / "_composed" / kit_root.name

        try:
            if composed_root.exists():
                shutil.rmtree(composed_root)
            composed_root.mkdir(parents=True, exist_ok=True)

            for logical_root in ("src", "test", "tests"):
                composed_logical_root = composed_root / logical_root

                if logical_root == "src":
                    # Source must be dependency-aware:
                    # promoted src + dependency KIT src + current KIT src.
                    self._copy_tree_overlay(
                        self.project_root / logical_root,
                        composed_logical_root,
                    )

                    for dep_work_raw in dependency_roots:
                        dep_work = Path(dep_work_raw)
                        # a promoted dependency is in the promoted src copied above: its KIT copy
                        # never replaces a file there (later REQs may have changed it)
                        # dep_work is a copy: commit times come from the project's own KIT
                        self._overlay_kit_layer(
                            dep_work.name,
                            dep_work / logical_root,
                            composed_logical_root,
                            self.project_root / logical_root,
                            history=self.project_root / "runs" / "kit" / dep_work.name / logical_root,
                        )

                    if self.regression:
                        self._overlay_kit_layer(
                            kit_root.name, kit_root / logical_root, composed_logical_root, self.project_root / logical_root
                        )
                    else:
                        self._copy_tree_overlay(
                            kit_root / logical_root,
                            composed_logical_root,
                        )

                    for extra_src in self.extra_src_roots:
                        self._copy_tree_overlay(Path(extra_src), composed_logical_root)
                else:
                    # Default /eval is target-scoped.
                    #
                    # Do not place promoted/dependency tests under work/<REQ>/test
                    # unless the caller explicitly requested a full regression mode.
                    # Generated REQ-local CI scripts commonly scan work/<REQ>/test
                    # for tests, secrets, and typecheck inputs. Mixing dependency
                    # tests here causes false failures in downstream REQs.
                    # In the regression of a promoted REQ its tests are the promoted version: a later
                    # REQ that reconciled one of them delivered it to the canonical tree.
                    promoted_tests = self.regression and self._kit_layer_mode(kit_root.name) != "full"
                    taken = self._copy_tree_overlay(
                        kit_root / logical_root,
                        composed_logical_root,
                        canonical=self.project_root / logical_root if promoted_tests else None,
                        take_canonical=True,
                        kit_only=_SHARED_ROOT_TEST_FILES,
                    )
                    if taken:
                        # the promoted version may import helpers promotion put elsewhere in the tree
                        self._bring_imported_support(
                            self.project_root / logical_root, composed_logical_root, taken, exclude=_SHARED_ROOT_TEST_FILES
                        )
                    for extra_test in self.extra_test_roots:
                        self.reconciled_tests += [
                            f"{logical_root}/{rel}"
                            for rel in self._overlay_existing_files(
                                Path(extra_test) / logical_root,
                                composed_logical_root,
                                canonical=self.project_root / logical_root,
                            )
                        ]

                if composed_logical_root.exists():
                    target_logical_root = work_kit_root / logical_root
                    if target_logical_root.exists():
                        shutil.rmtree(target_logical_root)
                    shutil.copytree(
                        composed_logical_root,
                        target_logical_root,
                        dirs_exist_ok=True,
                    )

            self._compose_root_files(kit_root, work_kit_root, dependency_roots or [])

            log.info(
                "prepared composed eval work kit for %s: work_kit=%s dependencies=%s",
                req_id,
                work_kit_root,
                dependency_roots,
            )

        except Exception as exc:
            log.warning(
                "Could not prepare composed eval work kit for %s: %s",
                req_id,
                exc,
            )

        eval_temp_root = work_kit_root / "ci" / "local-eval-workspaces"
        try:
            eval_temp_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        path_map: Dict[str, str] = {
            str(kit_root): str(work_kit_root),
            str(self.project_root / "src"): str(work_kit_root / "src"),
            str(self.project_root / "test"): str(work_kit_root / "test"),
            str(self.project_root / "tests"): str(work_kit_root / "tests"),
            "src": str(work_kit_root / "src"),
            "test": str(work_kit_root / "test"),
            "tests": str(work_kit_root / "tests"),

            # Runtime-neutral eval workspace contract.
            # Important: point all workspace aliases to the composed work KIT,
            # not to a separate overlay/workspace tree.
            "CLIKE_EVAL_WORKSPACE": str(work_kit_root),
            "CLIKE_EVAL_WORKSPACE_ROOT": str(work_kit_root),
            "CLIKE_EVAL_PROJECT_ROOT": str(self.project_root),
            "CLIKE_EVAL_CANDIDATE_KIT_DIR": str(work_kit_root),
            "CLIKE_EVAL_SOURCE_ROOT": str(work_kit_root / "src"),
            "CLIKE_EVAL_SRC_ROOT": str(work_kit_root / "src"),
            "CLIKE_EVAL_TEST_ROOT": str(work_kit_root / "test"),
            "CLIKE_EVAL_TESTS_ROOT": str(work_kit_root / "tests"),
            "CLIKE_EVAL_TEMP_ROOT": str(eval_temp_root),

            # Backward-compatible aliases used by already-generated scripts.
            # They intentionally point to the same composed work KIT.
            "CLIKE_EVAL_OVERLAY_WORKSPACE": str(work_kit_root),
            "CLIKE_EVAL_OVERLAY_SRC": str(work_kit_root / "src"),
            "CLIKE_EVAL_OVERLAY_TEST": str(work_kit_root / "test"),
            "CLIKE_EVAL_OVERLAY_TESTS": str(work_kit_root / "tests"),
            "CLIKE_OVERLAY_WORKSPACE": str(work_kit_root),
            "CLIKE_OVERLAY_SRC": str(work_kit_root / "src"),
            "CLIKE_OVERLAY_TEST": str(work_kit_root / "test"),
            "CLIKE_OVERLAY_TESTS": str(work_kit_root / "tests"),
        }

        rel_kit_root = self._path_relative_to_project(kit_root)
        if rel_kit_root:
            path_map[rel_kit_root] = str(work_kit_root)
        # absolute repository-root deliverables point to their composed copy (bare names never rewritten)
        policy = root_policy(self.project_root)
        for name in [*policy["folders"], *policy["files"]]:
            if (work_kit_root / name).exists():
                path_map[str(self.project_root / name)] = str(work_kit_root / name)

        # Compatibility view for CI scripts that infer runs/kit/<REQ> paths from their own location
        # (e.g. ../../../../runs/kit/REQ-001/test) instead of using CLIKE_EVAL_KIT_DIR /
        # CLIKE_EVAL_PROJECT_ROOT. Next to the eval dir (where such a relative path lands, also for
        # the nested regression and service runs) runs/kit/ holds this REQ -> its work copy, its
        # dependencies -> their composed copies, every other REQ -> the project KIT (read-only).
        self._link_compat_kits(
            self._eval_dir(req_id).parent / "runs" / "kit",
            work_kit_root,
            kit_root.name,
            dependency_roots or [],
        )

        if path_map is None:
            path_map = {}

        if dependency_roots is None:
            dependency_roots = []

        return work_root, reports_root, logs_root, path_map, work_kit_root, dependency_roots

    def _link_compat_kits(self, compat_root: Path, work_kit_root: Path, req_name: str, dependency_roots: List[str]) -> None:
        targets: Dict[str, Path] = {}
        project_kits = self.project_root / "runs" / "kit"
        try:
            for entry in sorted(project_kits.iterdir()):
                if entry.is_dir() and re.match(r"^REQ-[A-Za-z0-9_.-]+$", entry.name):
                    targets[entry.name] = entry
        except OSError:
            pass
        for dep in dependency_roots:
            targets[Path(dep).name] = Path(dep)
        targets[req_name] = work_kit_root
        try:
            compat_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        for name, target in targets.items():
            link = compat_root / name
            try:
                if link.is_symlink() or link.is_file():
                    link.unlink()
                elif link.exists():
                    shutil.rmtree(link)
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                try:
                    shutil.copytree(target, link)
                except Exception:
                    pass  # best effort: the explicit CLIKE_EVAL_* paths remain the contract

    def _rewrite_for_eval_workspace(self, value: Any, path_map: Dict[str, str]) -> Any:
        """Map project paths to the eval workspace: one pass (a rewritten path is never rewritten
        again) and whole path segments only, so a short key such as "test" or "src" never matches
        inside a word ("pytest", "/tmp/test-projects/...") or inside an already absolute path."""
        if not isinstance(value, str) or not path_map:
            return value
        keys = sorted((k for k in path_map if k), key=len, reverse=True)
        if not keys:
            return value
        pattern = re.compile(
            r"(?<![^\s/'\"=:({$,])(" + "|".join(re.escape(k) for k in keys) + r")(?=$|[\s/'\":)};,])"
        )

        def replace(match: "re.Match[str]") -> str:
            start = match.start()
            # a relative key never applies inside an absolute path written in the value
            if not match.group(1).startswith("/") and start > 0 and value[start - 1] == "/":
                return match.group(0)
            return path_map[match.group(1)]

        return pattern.sub(replace, value)

    def _rewrite_command_for_eval_workspace(self, command: str, path_map: Dict[str, str]) -> str:
        """
        Rewrite filesystem paths inside shell commands without rewriting script names.

        Important:
        - `npm run test` must stay `npm run test`.
        - `npm run lint` must stay `npm run lint`.
        - `npm run build` must stay `npm run build`.
        - path-like tokens such as `src/foo.js`, `./test/foo.test.js`,
          `runs/kit/<REQ>/src`, or absolute project paths may be rewritten.

        Node/TypeScript special case:
        when CLike installs dependencies through an explicit package_json, the
        installed package prefix is exposed as CLIKE_EVAL_NPM_PREFIX. Dependency
        backed npm scripts must run from that same prefix, otherwise eval may
        install into overlay/src/frontend but execute from work/REQ/src/frontend,
        causing false `tsc/vitest/next not found` failures.
        """
        if not command:
            return command

        rewritten = str(command)

        for source, target in sorted(path_map.items(), key=lambda item: len(item[0]), reverse=True):
            if not source or source.startswith("CLIKE_"):
                continue

            # Bare logical roots are not shell-command paths unless followed by a slash.
            # This avoids corrupting commands like `npm run test`.
            if source in {"src", "test", "tests"}:
                rewritten = re.sub(
                    rf"(?<![\w./:-]){re.escape(source)}/",
                    f"{target}/",
                    rewritten,
                )
                rewritten = rewritten.replace(f"./{source}/", f"{target}/")
                rewritten = rewritten.replace(f"../{source}/", f"{target}/")
                continue

            # Rewrite explicit absolute or staged paths only.
            if "/" in source or "\\" in source:
                rewritten = rewritten.replace(source, target)

        dependency_scripts = {
            "test",
            "test:a11y",
            "test:accessibility",
            "test:coverage",
            "coverage",
            "typecheck",
            "lint",
            "build",
            "security:deps",
        }

        def _align_npm_prefix(match: re.Match[str]) -> str:
            lead = match.group("lead") or ""
            script = match.group("script")
            tail = match.group("tail") or ""
            if script not in dependency_scripts:
                return match.group(0)
            return f'{lead}npm --prefix "$CLIKE_EVAL_NPM_PREFIX" run {script}{tail}'
        
        def _align_npm_prefix_short_script(match: re.Match[str]) -> str:
            lead = match.group("lead") or ""
            script = match.group("script")
            tail = match.group("tail") or ""
            if script not in dependency_scripts:
                return match.group(0)
            return f'{lead}npm --prefix "$CLIKE_EVAL_NPM_PREFIX" run {script}{tail}'

        rewritten = re.sub(
            r"(?P<lead>(?:^|\s))npm\s+--prefix\s+(?P<prefix>\"[^\"]+\"|'[^']+'|\S+)\s+(?P<script>test|test:a11y|test:accessibility|typecheck|lint|build|coverage|security:deps)(?P<tail>(?:\s+[^;&|]+)*)?",
            _align_npm_prefix_short_script,
            rewritten,
        )

        rewritten = re.sub(
            r"(?P<lead>(?:^|\s))npm\s+--prefix\s+(?P<prefix>\"[^\"]+\"|'[^']+'|\S+)\s+run\s+(?P<script>[\w:.-]+)(?P<tail>(?:\s+[^;&|]+)*)?",
            _align_npm_prefix,
            rewritten,
        )
        if "python3 -m ruff check" in rewritten and "--no-cache" not in rewritten:
            rewritten = rewritten.replace(
                "python3 -m ruff check",
                "python3 -m ruff check --no-cache",
            )

        if "python -m ruff check" in rewritten and "--no-cache" not in rewritten:
            rewritten = rewritten.replace(
                "python -m ruff check",
                "python -m ruff check --no-cache",
            )
        if " -m mypy " in rewritten and "--no-incremental" not in rewritten:
            rewritten = rewritten.replace(
                " -m mypy ",
                " -m mypy --no-incremental ",
                1,
            )

        if " -m mypy " in rewritten and "--cache-dir" not in rewritten:
            rewritten = rewritten.replace(
                " -m mypy ",
                ' -m mypy --cache-dir "$MYPY_CACHE_DIR" ',
                1,
            )

        if " -m mypy " in rewritten and "--follow-imports" not in rewritten:
            rewritten = rewritten.replace(
                " -m mypy ",
                " -m mypy --follow-imports=skip ",
                1,
            )
        return rewritten
    def _resolve_workdir(self, raw_cwd: Optional[str], path_map: Dict[str, str]) -> Path:
        if not raw_cwd:
            return self.project_root

        rewritten = self._rewrite_for_eval_workspace(raw_cwd, path_map)
        path = Path(str(rewritten))
        return path if path.is_absolute() else (self.project_root / path).resolve()

    def _resolve_node_manifest(
        self,
        *,
        runtime: Dict[str, Any],
        ltc: Dict[str, Any],
        profile_path: Path,
        path_map: Dict[str, str],
    ) -> Optional[Path]:
        """
        Resolve a KIT-local Node/npm manifest without forcing Node as a default.
        """
        explicit = (
            runtime.get("manifest")
            or runtime.get("manifest_file")
            or runtime.get("package_json")
            or runtime.get("package-json")
            or ltc.get("manifest")
            or ltc.get("manifest_file")
            or ltc.get("package_json")
            or ltc.get("package-json")
        )

        if explicit:
            explicit_text = str(explicit)

            # Resolve explicit package manifests without applying bare logical-root
            # rewrites such as "src" -> overlay/src. Those rewrites are safe for
            # shell commands, but they corrupt already-resolved paths like:
            # runs/kit/REQ-008/src/frontend/package.json
            rewritten = explicit_text
            for source, target in sorted(path_map.items(), key=lambda item: len(item[0]), reverse=True):
                if not source or source.startswith("CLIKE_") or source in {"src", "test", "tests"}:
                    continue
                if "/" in source or "\\" in source:
                    rewritten = rewritten.replace(source, target)

            path = Path(rewritten)
            path = path if path.is_absolute() else (self.project_root / path).resolve()

            # If the explicit manifest points to the candidate KIT src tree and
            # an overlay workspace exists, install dependencies into the overlay
            # execution area because generated commands run from overlay/src/...
            work_kit_raw = path_map.get("CLIKE_EVAL_CANDIDATE_KIT_DIR")
            overlay_raw = path_map.get("CLIKE_EVAL_OVERLAY_WORKSPACE")
            if work_kit_raw and overlay_raw:
                work_kit = Path(work_kit_raw)
                overlay = Path(overlay_raw)
                try:
                    rel_to_src = path.relative_to(work_kit / "src")
                    overlay_manifest = overlay / "src" / rel_to_src
                    if overlay_manifest.exists():
                        return overlay_manifest.resolve()
                except ValueError:
                    pass

            return path

        candidates = [
            profile_path.parent / "package.json",
            profile_path.parent.parent / "package.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()

        return None

    def _ensure_node_dependencies(
        self,
        *,
        req_id: Optional[str],
        package_json: Path,
        env: Dict[str, str],
        cwd: Path,
    ) -> tuple[Dict[str, str], List[EvalCase]]:
        """
        Install Node/npm dependencies in the writable eval copy.

        Never install under canonical src roots. Never rely on global modules.
        """
        cases: List[EvalCase] = []

        if not package_json.exists():
            return env, [
                EvalCase(
                    name="env::npm-manifest",
                    passed=False,
                    code=3,
                    stdout="",
                    stderr=f"package.json not found: {package_json}",
                    cmd=None,
                    cwd=str(cwd),
                    blocked=False,
                    blocking=True,
                )
            ]

        manifest_dir = package_json.parent
        node_modules = manifest_dir / "node_modules"
        lock_file = manifest_dir / "package-lock.json"
        lock_hash = self._requirements_hash(lock_file) if lock_file.exists() else "no-lock"
        marker = manifest_dir / f".npm-{self._requirements_hash(package_json)}-{lock_hash}.installed"

        node_env = dict(env)
        npm_cache = self._npm_cache_dir()
        npm_cache.mkdir(parents=True, exist_ok=True)
        node_env["npm_config_cache"] = str(npm_cache)
        node_env["NPM_CONFIG_CACHE"] = str(npm_cache)
        node_env["CLIKE_EVAL_NPM_PREFIX"] = str(manifest_dir)
        existing_node_path = node_env.get("NODE_PATH", "")
        package_node_modules = str(manifest_dir / "node_modules")
        node_env["NODE_PATH"] = (
            package_node_modules
            if not existing_node_path
            else f"{package_node_modules}{os.pathsep}{existing_node_path}"
        )

        store = self._npm_store_dir(marker.name.removeprefix(".npm-").removesuffix(".installed"))
        if not (node_modules.exists() and marker.exists()) and (store / "node_modules" / ".clike-complete").is_file():
            shutil.rmtree(node_modules, ignore_errors=True)
            if self._link_tree(store / "node_modules", node_modules):
                try:
                    marker.write_text("ok\n", encoding="utf-8")
                except OSError:
                    pass
                cases.append(EvalCase(
                    name="env::npm-install", passed=True, code=0,
                    stdout=f"npm dependencies linked from the install store {store} (same package.json and lockfile)",
                    stderr="", cmd=None, cwd=str(cwd), blocking=False,
                ))
                return node_env, cases

        if node_modules.exists() and marker.exists():
            cases.append(
                EvalCase(
                    name="env::npm-install",
                    passed=True,
                    code=0,
                    stdout=f"npm dependencies already installed in {manifest_dir}",
                    stderr="",
                    cmd=None,
                    cwd=str(cwd),
                    blocking=False,
                )
            )
            return node_env, cases

        try:
            manifest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return node_env, [
                EvalCase(
                    name="env::npm-dir",
                    passed=False,
                    code=30,
                    stdout="",
                    stderr=f"cannot create npm manifest directory {manifest_dir}: {exc}",
                    cmd=None,
                    cwd=str(cwd),
                    blocked=True,
                    blocking=False,
                )
            ]

        install_mode = "ci" if lock_file.exists() else "install"
        install_cmd = (
            f"npm {install_mode} "
            f"--prefix {shlex.quote(str(manifest_dir))} "
            "--no-audit --no-fund"
        )

        install_case = self._run(
            name="env::npm-install",
            cmd=install_cmd,
            cwd=cwd,
            expect=0,
            env=node_env,
            blocking=True,
            environment_requirements=["npm", "network", "native-dependencies"],
        )

        if install_case.passed:
            try:
                marker.write_text("ok\n", encoding="utf-8")
            except Exception as exc:
                install_case.stderr = (install_case.stderr + f"\nmarker write warning: {exc}")[-4000:]
            # keep this install for the next work copies with the same manifest and lockfile
            with _keyed_lock(f"npm-store:{store}"):  # parallel regressions with the same manifest
                if node_modules.is_dir() and not (store / "node_modules" / ".clike-complete").is_file():
                    shutil.rmtree(store, ignore_errors=True)
                    if self._link_tree(node_modules, store / "node_modules"):
                        try:
                            (store / "node_modules" / ".clike-complete").write_text("ok\n", encoding="utf-8")
                        except OSError:
                            pass
        else:
            install_case.blocked = False
            install_case.blocking = True

        cases.append(install_case)
        return node_env, cases

    def _case_depends_on_failed_setup(self, cmd: Optional[str]) -> bool:
        if not cmd:
            return False

        text = cmd.lower()
        dependency_sensitive_markers = [
            "npm run test",
            "npm run typecheck",
            "npm run lint",
            "npm run build",
            "npm run test:coverage",
            "npm run coverage",
            "npm run security:deps",
            "node --test",
            "next build",
            "next lint",
            "tsc --noemit",
            "tsc --noEmit",
            "vitest",
            "better-sqlite3",
        ]
        return any(marker in text for marker in dependency_sensitive_markers)

    def _blocked_due_to_setup(
        self,
        *,
        case_name: str,
        cmd: Optional[str],
        cwd: Path,
        reason: str,
    ) -> EvalCase:
        return EvalCase(
            name=case_name,
            passed=False,
            code=994,
            stdout="",
            stderr=reason,
            cmd=cmd,
            cwd=str(cwd),
            expect=0,
            blocked=True,
            blocking=False,
        )
    def _report_from_cases(
        self,
        *,
        profile_path: Path,
        req_id: Optional[str],
        mode: str,
        cases: List[EvalCase],
    ) -> EvalReport:
        for case in cases:
            if not case.passed and not case.excerpt:
                case.excerpt = eval_failures.excerpt(case.stdout or "", case.stderr or "")
                case.fingerprint = eval_failures.fingerprint(case.excerpt) or None
        passed = sum(1 for case in cases if case.passed)
        blocked = sum(1 for case in cases if case.blocked)
        hard_failed = sum(
            1 for case in cases if not case.passed and case.blocking
        )
        warnings = sum(
            1 for case in cases if not case.passed and not case.blocking
        )

        if hard_failed > 0:
            status = "FAIL"
        elif warnings > 0:
            status = "PASS_WITH_WARNINGS"
        else:
            status = "PASS"

        return EvalReport(
            profile=str(profile_path),
            req_id=req_id,
            mode=mode,
            passed=passed,
            failed=hard_failed,
            cases=cases,
            blocked=blocked,
            warnings=warnings,
            status=status,
            json_path=str(self._eval_dir(req_id)),
        )

    def run_profile(
        self,
        profile: str,
        ltc: Dict[str, Any],
        mode: str = "auto",
        verdict: Optional[str] = None,
        req_id: Optional[str] = None,
        regression: bool = False,
        checks: Optional[List[str]] = None,
        regression_reqs: Optional[List[str]] = None,
        reuse_cases: Optional[List[Dict[str, Any]]] = None,
    ) -> EvalReport:
        """Run the LTC. ``checks``: only these checks (by name), after the same environment
        setup, and no regression — a quick re-run of failed checks while repairing.
        ``regression_reqs``: every check of the REQ, and the regression of these promoted REQs only
        (a targeted re-eval in a repair loop: never the REQ's verdict).
        ``reuse_cases``: results of a run on the same inputs (the targeted re-eval that just passed):
        the REQ's checks and the promoted REQs' regressions found there are taken, not run again."""
        self._services: List[eval_environment.RunningService] = []
        self._reuse = {str(c.get("name")): c for c in (reuse_cases or []) if isinstance(c, dict) and c.get("name")}
        self._reuse_reqs = {n.split("::")[1].upper() for n in self._reuse if n.startswith("regression::") and n.count("::") >= 2}
        self._only_checks = {str(c) for c in (checks or []) if str(c).strip()} or None
        self._regression_only = {str(r).strip().upper() for r in (regression_reqs or []) if str(r).strip()} or None
        self._progress_start(req_id or (ltc or {}).get("req_id"), partial=bool(self._only_checks or self._regression_only))
        try:
            exhausted = sandbox_resources.preflight()
            if not exhausted and not self.eval_key:  # the top-level run, not a nested regression or service
                exhausted = self._prepare_eval_disk(req_id or (ltc or {}).get("req_id"))
            if exhausted:
                return self._sandbox_exhausted_report(profile, req_id or (ltc or {}).get("req_id"), exhausted)
            report = self._run_profile(
                profile, ltc, mode, verdict, req_id, regression and (not self._only_checks or bool(self._regression_only))
            )
            if any(_sandbox_exhausted_case(c) for c in report.cases):
                report.reason_code = sandbox_resources.SANDBOX_EXHAUSTED_REASON
            missing = sorted({
                b for c in report.cases if not c.passed and _MISSING_TOOLS_NOTE in (c.stderr or "")
                for b in eval_tools.missing_from_failure(f"{c.stdout}\n{c.stderr}", self._tools_catalog())
            })
            if missing:
                report.missing_tools = missing
            if not self.eval_key:
                report.tools = eval_tools.installed_versions() or None
            return report
        finally:
            cancelled = self.cancel_event is not None and self.cancel_event.is_set()
            self._progress(state="cancelled" if cancelled else "done", phase="done", current=None, ended_at=time.time())
            for svc in reversed(self._services):
                eval_environment.stop_process(svc.proc)
            self._services = []

    def _tools_catalog(self) -> Dict[str, Dict[str, Any]]:
        if getattr(self, "_catalog", None) is None:
            try:
                self._catalog = eval_tools.load_catalog(self.project_root)
            except Exception:
                self._catalog = {}
        return self._catalog

    def _prepare_eval_disk(self, req_id: Optional[str]) -> Optional[str]:
        """Prune stale eval directories of the sandbox volume; why the eval cannot run, or None."""
        try:
            base = self._eval_base_dir()
        except OSError:
            return None
        removed = sandbox_resources.prune_eval_dirs(base, self._safe_req_id(req_id) if req_id else None)
        if removed:
            log.info("eval disk: removed %d stale eval directories: %s", len(removed), ", ".join(Path(r).name for r in removed))
        return sandbox_resources.disk_preflight(base)

    def _sandbox_exhausted_report(self, profile: str, req_id: Optional[str], reason: str) -> EvalReport:
        case = EvalCase(
            name="env::sandbox-resources", passed=False, code=1, stdout="", stderr=reason, blocked=True,
            excerpt=reason, fingerprint="sandbox-resources",
        )
        report = self._report_from_cases(profile_path=Path(profile), req_id=req_id, mode="auto", cases=[case])
        report.status = "BLOCKED"
        report.reason_code = sandbox_resources.SANDBOX_EXHAUSTED_REASON
        return report

    def _provision_environment(
        self,
        *,
        ltc: Dict[str, Any],
        req_id: Optional[str],
        env: Dict[str, str],
        work_kit_root: Optional[Path],
        logs_root: Path,
    ) -> tuple[Dict[str, str], List[EvalCase]]:
        """Create the variables and start the services the LTC declares (eval_environment).

        Values already in the environment win. Each provisioned item is reported as an
        env::provision::<name> / env::service::<name> case; a failure is blocking."""
        specs = eval_environment.variable_specs(ltc)
        services = eval_environment.service_specs(ltc)
        if not specs and not services:
            return env, []
        cases: List[EvalCase] = []
        values: Dict[str, str] = {k: v for k, v in env.items() if isinstance(v, str)}
        provided: Dict[str, str] = {}
        project_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.project_root.name or "project")
        req = self._safe_req_id(req_id)

        def fail(name: str, message: str) -> None:
            cases.append(EvalCase(name=name, passed=False, code=79, stdout="", stderr=message, blocking=True))

        def note(name: str, message: str) -> None:
            cases.append(EvalCase(name=name, passed=True, code=0, stdout=message, stderr="", blocking=False))

        pending = [s for s in specs if not str(env.get(s.name, "")).strip()]
        admin = str(env.get(eval_environment.ADMIN_URL_VAR, "")).strip()
        # 1. generated values that need nothing else, then databases
        for spec in list(pending):
            kind = spec.effective_provision()
            try:
                if kind in {"token", "uuid", "timestamp"}:
                    value = eval_environment.generate(spec, values)
                elif kind == "postgres_database" and admin:
                    value = eval_environment.provision_postgres(spec, admin, project_key, req)
                else:
                    continue
            except Exception as exc:  # database server unreachable, bad URL...
                fail(f"env::provision::{spec.name}", f"cannot provision {spec.name} ({kind}): {exc}")
                pending.remove(spec)
                continue
            values[spec.name] = provided[spec.name] = value
            pending.remove(spec)
            note(f"env::provision::{spec.name}", f"{kind} provisioned" + (f": database {value.rsplit('/', 1)[-1]}" if kind == "postgres_database" else ""))

        def resolve_templates() -> None:
            for spec in list(pending):
                if spec.effective_provision() != "template":
                    continue
                try:
                    value = eval_environment.generate(spec, values)
                except eval_environment.ProvisionError:
                    continue  # needs a service export: retried after the services
                values[spec.name] = provided[spec.name] = value or ""
                pending.remove(spec)
                note(f"env::provision::{spec.name}", "template provisioned")

        resolve_templates()
        # 2. services
        for svc in services:
            name = str(svc["name"])
            try:
                workdir, svc_env, setup_cases = self._service_runtime(svc, req_id=req_id, env={**env, **provided}, work_kit_root=work_kit_root)
            except Exception as exc:
                fail(f"env::service::{name}", f"cannot prepare service {name}: {exc}")
                continue
            cases.extend(setup_cases)
            if any(not c.passed and c.blocking for c in setup_cases):
                fail(f"env::service::{name}", f"service {name}: dependency setup failed (see the env:: cases above)")
                continue

            def run_setup(label: str, cmd: str, cwd: Path, setup_env: Dict[str, str]) -> tuple[bool, str]:
                result = self._run(name=f"env::service::{label}", cmd=cmd, cwd=cwd, env=setup_env, timeout=300, blocking=True)
                cases.append(result)
                return result.passed, f"{result.stdout}\n{result.stderr}"

            try:
                running, exports, text = eval_environment.start_service(
                    svc, workdir=workdir, env=svc_env, values=values, log_dir=logs_root / "services", run_setup=run_setup,
                )
            except eval_environment.ProvisionError as exc:
                fail(f"env::service::{name}", f"service {name}: {exc}")
                continue
            if running is None:
                fail(f"env::service::{name}", f"service {name}: {text}")
                continue
            self._services.append(running)
            for key, value in exports.items():
                if not str(env.get(key, "")).strip():
                    values[key] = provided[key] = value
                    pending[:] = [p for p in pending if p.name != key]
            note(f"env::service::{name}", text)
        resolve_templates()
        for spec in pending:
            if spec.effective_provision() in {"template", "service"}:
                fail(f"env::provision::{spec.name}", f"{spec.name}: no value ({spec.effective_provision()} could not be resolved)")
        return {**env, **provided}, cases

    def _service_runtime(
        self,
        svc: Dict[str, Any],
        *,
        req_id: Optional[str],
        env: Dict[str, str],
        work_kit_root: Optional[Path],
    ) -> tuple[Path, Dict[str, str], List[EvalCase]]:
        """Working directory and environment of a service: the composed source of another REQ
        (`req`, with its own Python venv / npm dependencies) or of the candidate."""
        other = str(svc.get("req") or "").strip()
        if not other or other == str(req_id or ""):
            if work_kit_root is None:
                raise OSError("no candidate workspace")
            return (work_kit_root / str(svc.get("cwd") or "")).resolve(), dict(env), []
        other = validate_req_id(other)
        profile = self.project_root / "runs" / "kit" / other / "ci" / "LTC.json"
        # a promoted REQ's service runs its promoted code, with the candidate's source over it (the
        # state after promotion), as in a regression
        promoted = self._kit_layer_mode(other) != "full"
        sub = EvalRunner(
            self.project_root,
            eval_key=f"{self._safe_req_id(req_id)}/services/{other}",
            cancel_event=self.cancel_event,
            regression=promoted,
            extra_src_roots=list(self.extra_src_roots) if promoted else None,
        )
        _work, _reports, _logs, path_map, kit_root, _deps = sub._prepare_eval_workspace(req_id=other, profile_path=profile)
        if kit_root is None:
            raise OSError(f"no KIT workspace for {other}")
        src = path_map.get("CLIKE_EVAL_OVERLAY_SRC") or str(kit_root / "src")
        svc_env = {**env, "PYTHONPATH": src, "PYTHONDONTWRITEBYTECODE": "1", "SERVICE_KIT_DIR": str(kit_root), "SERVICE_SRC_DIR": src}
        cases: List[EvalCase] = []
        requirements = kit_root / "ci" / "requirements.txt"
        if requirements.is_file():
            svc_env, setup = sub._ensure_eval_venv(req_id=other, requirements_file=str(requirements), env=svc_env, cwd=kit_root)
            cases.extend(setup)
        package_json = kit_root / "ci" / "package.json"
        if package_json.is_file():
            svc_env, setup = sub._ensure_node_dependencies(req_id=other, package_json=package_json, env=svc_env, cwd=kit_root)
            cases.extend(setup)
        for case in cases:
            case.name = f"env::service::{svc.get('name')}::{case.name}"
        return (kit_root / str(svc.get("cwd") or "")).resolve(), svc_env, cases

    def _run_profile(
        self,
        profile: str,
        ltc: Dict[str, Any],
        mode: str = "auto",
        verdict: Optional[str] = None,
        req_id: Optional[str] = None,
        regression: bool = False,
    ) -> EvalReport:
        profile_path = Path(profile or "LTC.json")
        if not profile_path.is_absolute():
            profile_path = self.project_root / profile_path
        profile_path = profile_path.resolve()

        if mode.lower() == "manual":
            if verdict not in ("pass", "fail"):
                raise ValueError("manual mode requires verdict in {'pass','fail'}")
            case = EvalCase(
                name=f"manual::{req_id or (ltc.get('req_id') if isinstance(ltc, dict) else 'REQ')}",
                passed=verdict == "pass",
                code=0 if verdict == "pass" else 1,
                stdout="",
                stderr="",
            )
            return self._report_from_cases(
                profile_path=profile_path,
                req_id=req_id,
                mode="manual",
                cases=[case],
            )

        if ltc is None:
            return self._report_from_cases(
                profile_path=profile_path,
                req_id=req_id,
                mode="auto",
                cases=[
                    EvalCase(
                        name="ltc::missing",
                        passed=False,
                        code=2,
                        stdout="",
                        stderr="Unsupported profile: expected inline LTC JSON.",
                    )
                ],
            )

        eff_req = req_id or ltc.get("req_id")
        top_env = ltc.get("env") or {}
        out_cases: List[EvalCase] = []

        missing_env = missing_environment_case(ltc)
        if missing_env is not None:
            report = self._report_from_cases(
                profile_path=profile_path, req_id=eff_req, mode="auto", cases=[missing_env],
            )
            report.status = "BLOCKED"
            report.reason_code = ENVIRONMENT_MISSING_REASON
            report.environment_repairable = eval_environment.repairable(
                eval_environment.missing_variables(ltc, scrubbed_process_env())
            )
            return report

        try:
            try:
                workspace_result = self._prepare_eval_workspace(req_id=eff_req, profile_path=profile_path)
            except Exception as first:  # a file changed during the copy: once more, then report
                log.warning("prepare eval workspace failed, retrying once: %s", first)
                workspace_result = self._prepare_eval_workspace(req_id=eff_req, profile_path=profile_path)
        except Exception as exc:
            return self._report_from_cases(
                profile_path=profile_path,
                req_id=eff_req,
                mode="auto",
                cases=[
                    EvalCase(
                        name="env::prepare-workspace",
                        passed=False,
                        code=997,
                        stdout="",
                        stderr=(
                            f"prepare eval workspace failed: {exc}\n[CLike EvalRunner] CLike could not compose the "
                            "eval workspace (copying the KIT and the canonical tree): not a defect of the code, nothing "
                            "to repair. Check that no process is writing into runs/kit/<REQ>/ and run again."
                        ),
                        cmd=None,
                        cwd=str(self.project_root),
                        blocked=True,
                        blocking=True,
                    )
                ],
            )

        if not isinstance(workspace_result, tuple) or len(workspace_result) != 6:
            return self._report_from_cases(
                profile_path=profile_path,
                req_id=eff_req,
                mode="auto",
                cases=[
                    EvalCase(
                        name="env::prepare-workspace",
                        passed=False,
                        code=997,
                        stdout="",
                        stderr=f"prepare eval workspace returned invalid result: {workspace_result!r}",
                        cmd=None,
                        cwd=str(self.project_root),
                        blocked=True,
                        blocking=True,
                    )
                ],
            )

        work_root, reports_root, logs_root, path_map, work_kit_root, dependency_roots = workspace_result

        active_profile_path = Path(
            self._rewrite_for_eval_workspace(str(profile_path), path_map)
        ).resolve()

        runtime_working_directory = self._runtime_working_directory(ltc)
        # run_from (KIT LTC contract) is the directory the check commands are written for.
        default_cwd = self._resolve_workdir(
            ltc.get("cwd") or ltc.get("run_from") or runtime_working_directory or "",
            path_map,
        )

        overlay_workspace_raw = path_map.get("CLIKE_EVAL_OVERLAY_WORKSPACE", "")
        overlay_src_raw = path_map.get("CLIKE_EVAL_OVERLAY_SRC", "")
        overlay_test_raw = path_map.get("CLIKE_EVAL_OVERLAY_TEST", "")
        overlay_tests_raw = path_map.get("CLIKE_EVAL_OVERLAY_TESTS", "")

        eval_path_env = {
            "CLIKE_EVAL_WORK_DIR": str(work_root),
            "CLIKE_EVAL_REPORT_DIR": str(reports_root),
            # documented to KIT scripts as the writable temp/staging root (it was only in the
            # internal path map, so scripts requiring it failed)
            "CLIKE_EVAL_TEMP_ROOT": path_map.get("CLIKE_EVAL_TEMP_ROOT") or str(self._eval_dir(eff_req) / "tmp"),
            "CLIKE_EVAL_LOG_DIR": str(logs_root),
            "CLIKE_EVAL_KIT_DIR": str(work_kit_root or ""),
            "CLIKE_EVAL_CANDIDATE_KIT_DIR": str(work_kit_root or ""),
            "CLIKE_EVAL_PROJECT_ROOT": str(self.project_root),
            "CLIKE_EVAL_DEPENDENCY_KIT_DIRS": os.pathsep.join(dependency_roots),

            # Preferred runtime-neutral workspace contract.
            # Preferred runtime-neutral workspace contract.
            # Generated CI scripts should use these first.
            "CLIKE_EVAL_WORKSPACE": overlay_workspace_raw,
            "CLIKE_EVAL_WORKSPACE_ROOT": overlay_workspace_raw,
            "CLIKE_EVAL_SOURCE_ROOT": overlay_src_raw,
            "CLIKE_EVAL_SRC_ROOT": overlay_src_raw,
            "CLIKE_EVAL_TEST_ROOT": overlay_test_raw,
            "CLIKE_EVAL_TESTS_ROOT": overlay_tests_raw,

            # Official dependency-aware overlay prepared by CLike EvalRunner.
            "CLIKE_EVAL_OVERLAY_WORKSPACE": overlay_workspace_raw,
            "CLIKE_EVAL_OVERLAY_SRC": overlay_src_raw,
            "CLIKE_EVAL_OVERLAY_TEST": overlay_test_raw,
            "CLIKE_EVAL_OVERLAY_TESTS": overlay_tests_raw,

            # Compatibility aliases for REQ-local CI scripts.
            # Scripts must prefer these paths when present and create their own overlay
            # only as a manual-execution fallback outside canonical CLike eval.
            "CLIKE_OVERLAY_WORKSPACE": overlay_workspace_raw,
            "CLIKE_OVERLAY_SRC": overlay_src_raw,
            "CLIKE_OVERLAY_TEST": overlay_test_raw,
            "CLIKE_OVERLAY_TESTS": overlay_tests_raw,

            "CLIKE_EVAL_ORIGINAL_PROFILE": str(profile_path),
            "CLIKE_EVAL_ACTIVE_PROFILE": str(active_profile_path),

            # Keep ecosystem tool caches inside the writable eval workspace.
            # Project roots may be read-only in containerized/sandboxed eval.
            "RUFF_CACHE_DIR": str(self._eval_dir(eff_req) / ".ruff-cache"),
            # coverage.py writes its data file in the cwd, which may be the read-only project root
            "COVERAGE_FILE": str(self._eval_dir(eff_req) / ".coverage"),
            "MYPY_CACHE_DIR": str(self._eval_dir(eff_req) / ".mypy-cache"),
            "PYTHONPYCACHEPREFIX": str(self._eval_dir(eff_req) / ".pycache"),

            "npm_config_cache": str(self._npm_cache_dir()),
            "NPM_CONFIG_CACHE": str(self._npm_cache_dir()),
        }

        base_env = self._merge_env(
            top_env if isinstance(top_env, dict) else {},
            eval_path_env,
        )

        raw_runtime = ltc.get("runtime") or {}
        if isinstance(raw_runtime, dict):
            runtime = raw_runtime
            runtime_name = str(
                raw_runtime.get("name")
                or raw_runtime.get("runtime")
                or raw_runtime.get("type")
                or raw_runtime.get("ecosystem")
                or raw_runtime.get("language")
                or ""
            ).strip().lower()
        else:
            runtime = {}
            runtime_name = str(raw_runtime or "").strip().lower()

        if not runtime_name:
            runtime_name = str(
                ltc.get("implementation_runtime")
                or ltc.get("runtime_language")
                or ltc.get("runtime_ecosystem")
                or ltc.get("lane")
                or ltc.get("profile")
                or ltc.get("ecosystem")
                or ltc.get("language")
                or ""
            ).strip().lower()

        if runtime_name.startswith("python"):
            runtime_name = "python"

        requirements_file = None

        if runtime_name in {"python", "python3", "py"}:
            requirements_file = (
                runtime.get("requirements_file")
                or ltc.get("requirements_file")
                or ltc.get("pip_file")
                or ltc.get("pip-file")
            )

        if requirements_file:
            requirements_file = self._rewrite_for_eval_workspace(str(requirements_file), path_map)

        if not requirements_file and runtime_name in {"python", "python3", "py"}:
            inferred_candidates = [
                active_profile_path.parent / "requirements.txt",
                active_profile_path.parent.parent / "ci" / "requirements.txt",
                active_profile_path.parent.parent / "requirements.txt",
            ]

            if work_kit_root:
                inferred_candidates.extend(
                    [
                        work_kit_root / "ci" / "requirements.txt",
                        work_kit_root / "requirements.txt",
                    ]
                )

            if eff_req:
                inferred_candidates.append(
                    self.project_root
                    / "runs"
                    / "kit"
                    / self._safe_req_id(str(eff_req))
                    / "ci"
                    / "requirements.txt"
                )

            seen_requirements: set[str] = set()
            for inferred_requirements in inferred_candidates:
                key = str(inferred_requirements)
                if key in seen_requirements:
                    continue
                seen_requirements.add(key)

                if inferred_requirements.exists():
                    requirements_file = str(inferred_requirements)
                    break

        eval_env = base_env

        eval_env = base_env

        if runtime_name in {"python", "python3", "py"}:
            overlay_python_paths = [
                str(path)
                for path in [
                    Path(overlay_src_raw).resolve() if overlay_src_raw else None,
                    self.project_root / "src",
                ]
                if path
            ]

            existing_pythonpath = eval_env.get("PYTHONPATH", "").strip()
            if existing_pythonpath:
                overlay_python_paths.append(existing_pythonpath)

            if overlay_python_paths:
                python_path_value = os.pathsep.join(overlay_python_paths)
                eval_env = {
                    **eval_env,
                    "PYTHONPATH": python_path_value,
                    "MYPYPATH": python_path_value,
                }

        if requirements_file:
            eval_env, setup_cases = self._ensure_eval_venv(
                req_id=eff_req,
                requirements_file=requirements_file,
                env=eval_env,
                cwd=default_cwd,
            )
            out_cases.extend(setup_cases)

        node_runtime_names = {
            "node",
            "nodejs",
            "node.js",
            "javascript",
            "typescript",
            "js",
            "js-ts",
            "npm",
            "react",
            "vite",
        }

        package_json = None
        # a manifest the LTC names (package_json / manifest) or a Node version it requires installs
        # the dependencies whatever its main runtime (B2B REQ-038: a Python LTC with a web frontend
        # declared src/web/package.json, and the frontend checks ran without node_modules)
        env_decl = ltc.get("environment") if isinstance(ltc.get("environment"), dict) else {}
        declared_manifest = any(
            src.get(key) for src in (runtime, ltc) for key in ("package_json", "package-json", "manifest", "manifest_file")
            if isinstance(src, dict) and str(src.get(key) or "").endswith("package.json")
        )
        if (runtime_name in node_runtime_names or (active_profile_path.parent / "package.json").exists()
                or declared_manifest or env_decl.get("node")):
            package_json = self._resolve_node_manifest(
                runtime=runtime,
                ltc=ltc,
                profile_path=active_profile_path,
                path_map=path_map,
            )

        if package_json:
            eval_env, setup_cases = self._ensure_node_dependencies(
                req_id=eff_req,
                package_json=package_json,
                env=eval_env,
                cwd=default_cwd,
            )
            out_cases.extend(setup_cases)

        setup_failed = any(
            (not case.passed) and (case.blocked or case.blocking)
            for case in out_cases
            if case.name.startswith("env::")
        )

        # setup: what must happen before the environment and its services start — installing and
        # building the components the services run (a solution profile: the services are the
        # solution itself). Each step blocks; a failing one stops the eval before the services.
        if not setup_failed:
            for i, step in enumerate(ltc.get("setup") or [], start=1):
                item = step if isinstance(step, dict) else {"command": step}
                command = str(item.get("command") or item.get("run") or "").strip()
                if not command:
                    continue
                step_cwd = (default_cwd / str(item["cwd"])) if item.get("cwd") else default_cwd
                case = self._run(
                    name=f"setup::{item.get('id') or i}",
                    cmd=str(self._rewrite_for_eval_workspace(command, path_map)),
                    cwd=step_cwd,
                    expect=0,
                    env=eval_env,
                    timeout=int(item.get("timeout") or 1800),
                    blocking=True,
                )
                out_cases.append(case)
                if not case.passed:
                    setup_failed = True
                    break

        if not setup_failed:
            eval_env, provision_cases = self._provision_environment(
                ltc=ltc, req_id=eff_req, env=eval_env, work_kit_root=work_kit_root, logs_root=logs_root,
            )
            out_cases.extend(provision_cases)

        pre_cmds = ltc.get("pre") or []
        for i, pre in enumerate(pre_cmds, start=1):
            pre_cmd = str(self._rewrite_for_eval_workspace(pre, path_map))
            out_cases.append(
                self._run(
                    name=f"pre::{i}",
                    cmd=pre_cmd,
                    cwd=default_cwd,
                    expect=0,
                    env=eval_env,
                    timeout=None,
                    blocking=True,
                )
            )

        norm_cases = self._normalize_cases(ltc)
        if not norm_cases:
            out_cases.append(
                EvalCase(
                    name="ltc::no-executable-checks",
                    passed=False,
                    code=4,
                    stdout="",
                    stderr="LTC contains no executable checks. Expected one of checks[], cases[], steps[], commands[], or run.",
                    cmd=None,
                    cwd=str(default_cwd),
                    blocking=True,
                )
            )
            return self._report_from_cases(
                profile_path=profile_path,
                req_id=eff_req,
                mode="auto",
                cases=out_cases,
            )

        skip = getattr(self, "_skip_checks", None)
        if skip:
            # checks a MODIFIED REQ superseded, in whatever section the LTC declares them
            norm_cases = [c for c in norm_cases if str(c.get("name") or "case") not in skip]
        only = getattr(self, "_only_checks", None)
        if only:
            unknown = sorted(n for n in only - {str(c.get("name") or "case") for c in norm_cases}
                             if not n.startswith("acceptance::"))  # CLike's own check, not in the LTC
            if unknown:
                out_cases.append(EvalCase(
                    name="ltc::unknown-checks", passed=False, code=4, stdout="",
                    stderr=f"unknown check(s) {unknown}; the LTC checks are "
                    f"{[str(c.get('name') or 'case') for c in norm_cases]}",
                    cmd=None, cwd=str(default_cwd), blocking=True,
                ))
            norm_cases = [c for c in norm_cases if str(c.get("name") or "case") in only]
        elif regression and not self.regression:
            # The candidate's own "regression" checks re-run tests of earlier REQs (B2B REQ-025,
            # REQ-026: "file not found", as those tests are not in the KIT, and the repair cannot drop
            # a locked check, so it copied other REQs' tests into the KIT). CLike's regression below
            # runs them itself on their promoted tests with this candidate overlaid: not run twice.
            names = [str(c.get("name") or "case") for c in norm_cases]
            repeated = [n for n in names if _is_kit_regression_check(n)]
            if repeated and len(repeated) < len(names) and any(
                not _is_kit_regression_check(n) and {t for t in re.split(r"[^a-z0-9]+", n.lower()) if t} & _TEST_CHECK_TOKENS
                for n in names
            ):
                norm_cases = [c for c in norm_cases if str(c.get("name") or "case") not in repeated]
                out_cases.append(EvalCase(
                    name="regression-checks::not-run", passed=True, code=0,
                    stdout=f"not run: {', '.join(repeated)} (this KIT's own regression checks re-run tests of earlier "
                    "REQs; CLike's regression runs them on their promoted tests, with this candidate overlaid)",
                    stderr="", cmd=None, cwd=str(default_cwd), blocking=False,
                ))
        elif self.regression:
            static = [str(c.get("name") or "case") for c in norm_cases if _is_static_regression_check(str(c.get("name") or ""))]
            if static:
                norm_cases = [c for c in norm_cases if str(c.get("name") or "case") not in static]
                out_cases.append(EvalCase(
                    name="static-checks::not-run", passed=True, code=0,
                    stdout=f"regression runs only what guards behaviour; not run: {', '.join(static)} "
                    "(static/quality checks of a promoted REQ: passed at its gate, never blocking here)",
                    stderr="", cmd=None, cwd=str(default_cwd), blocking=False,
                ))
            names = [str(c.get("name") or "case") for c in norm_cases]
            repeated = [n for n in names if _is_kit_regression_check(n)]
            # never all of them: a REQ whose only test check is named "regression" keeps it
            if repeated and len(repeated) < len(names) and any(
                not _is_kit_regression_check(n) and {t for t in re.split(r"[^a-z0-9]+", n.lower()) if t} & _TEST_CHECK_TOKENS
                for n in names
            ):
                norm_cases = [c for c in norm_cases if str(c.get("name") or "case") not in repeated]
                out_cases.append(EvalCase(
                    name="regression-checks::not-run", passed=True, code=0,
                    stdout=f"not run: {', '.join(repeated)} (this promoted REQ's own regression checks re-run tests of "
                    "earlier REQs, which CLike's regression runs itself on their promoted tests)",
                    stderr="", cmd=None, cwd=str(default_cwd), blocking=False,
                ))

        # each check's duration (seconds), in the report: where an eval spends its time
        stamp_from, stamp_at = len(out_cases), time.monotonic()

        def _stamp() -> None:
            now = time.monotonic()
            for done in out_cases[stamp_from:]:
                if done.duration_s is None:
                    done.duration_s = round(now - stamp_at, 2)

        loop_from = len(out_cases)
        self._progress(phase="checks", checks_total=len(norm_cases), checks_done=0)
        for case_index, case in enumerate(norm_cases):
            _stamp()
            stamp_from, stamp_at = len(out_cases), time.monotonic()
            if self.cancel_event is not None and self.cancel_event.is_set():
                break
            own = out_cases[loop_from:]
            self._progress(checks_done=case_index, current=str(case.get("name") or "case"),
                           passed=sum(1 for c in own if c.passed), failed=sum(1 for c in own if not c.passed and c.blocking))
            raw_cmd = case.get("run")
            cmd = self._rewrite_command_for_eval_workspace(raw_cmd, path_map)
            setup = self._rewrite_for_eval_workspace(case.get("setup"), path_map)
            workdir = self._resolve_workdir(case.get("cwd"), path_map) if case.get("cwd") else default_cwd
            case_env = self._merge_env(eval_env, case.get("env") or {})
            blocking = bool(case.get("blocking", True))
            environment_requirements = list(case.get("environment_requirements") or [])
            timeout = case.get("timeout")
            case_name = case.get("name") or "case"
            reused = self._reused_case(case_name)
            if reused is not None:
                out_cases.append(reused)
                continue



            try:
                workdir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                out_cases.append(
                    EvalCase(
                        name=f"{case_name}::cwd",
                        passed=False,
                        code=996,
                        stdout="",
                        stderr=f"cannot create cwd {workdir}: {exc}",
                        cmd=None,
                        cwd=str(workdir),
                        expect=0,
                        blocked=True,
                        blocking=False,
                    )
                )
                continue

            if setup_failed and self._case_depends_on_failed_setup(str(cmd or "")):
                out_cases.append(
                    self._blocked_due_to_setup(
                        case_name=case_name,
                        cmd=str(cmd or ""),
                        cwd=workdir,
                        reason=(
                            "Skipped because dependency setup failed earlier. "
                            "This is classified as environment-blocked to avoid reporting "
                            "downstream dependency/runtime failures as application code defects."
                        ),
                    )
                )
                continue


            if setup:
                setup_cmd = str(setup)
                npm_prefix_match = re.search(
                    r"(?:^|\s)npm\s+(?:install|ci)\s+--prefix\s+([^\s]+)",
                    setup_cmd,
                )
                if npm_prefix_match:
                    prefix_raw = npm_prefix_match.group(1).strip().strip("'\"")
                    prefix_path = Path(prefix_raw)
                    if not prefix_path.is_absolute():
                        prefix_path = (workdir / prefix_path).resolve()
                    try:
                        prefix_path.mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        out_cases.append(
                            EvalCase(
                                name=f"{case_name}::setup",
                                passed=False,
                                code=995,
                                stdout="",
                                stderr=f"cannot create npm --prefix directory {prefix_path}: {exc}",
                                cmd=setup_cmd,
                                cwd=str(workdir),
                                expect=0,
                                blocked=True,
                                blocking=False,
                            )
                        )
                        continue

                setup_case = self._run(
                    name=f"{case_name}::setup",
                    cmd=setup_cmd,
                    cwd=workdir,
                    expect=0,
                    env=case_env,
                    timeout=timeout,
                    blocking=blocking,
                    environment_requirements=environment_requirements,
                )
                out_cases.append(setup_case)

                if not setup_case.passed:
                    continue

            if not cmd:
                out_cases.append(
                    EvalCase(
                        name=case_name,
                        passed=False,
                        code=997,
                        stdout="",
                        stderr="missing 'run' or 'command'",
                        cmd=None,
                        cwd=str(workdir),
                        expect=case.get("expect"),
                        blocking=blocking,
                    )
                )
                continue

            result = self._run(
                name=case_name,
                cmd=str(cmd),
                cwd=workdir,
                expect=case.get("expect", 0),
                env=case_env,
                timeout=timeout,
                blocking=blocking,
                environment_requirements=environment_requirements,
            )

            result = self._recover_node_test_glob_failure(
                result=result,
                cmd=str(cmd),
                cwd=workdir,
                env=case_env,
                work_kit_root=work_kit_root,
                timeout=timeout,
                blocking=blocking,
            )

            result = self._recover_missing_browser(
                result=result,
                cmd=str(cmd),
                cwd=workdir,
                env=case_env,
                work_kit_root=work_kit_root,
                timeout=timeout,
                blocking=blocking,
                environment_requirements=environment_requirements,
            )

            result = self._normalize_raw_secret_scan_result(result)

            out_cases.append(result)
        _stamp()

        cancelled = self.cancel_event is not None and self.cancel_event.is_set()
        if cancelled:
            out_cases.append(
                EvalCase(
                    name="eval::cancelled",
                    passed=False,
                    code=997,
                    stdout="",
                    stderr="[CLike EvalRunner] cancelled: the caller disconnected; remaining checks were not run.",
                    blocked=True,
                    blocking=True,
                )
            )
        # The regression of the promoted REQs runs once the REQ's own blocking checks pass: while
        # they fail the REQ is not promotable anyway, and the regression (minutes: every other REQ's
        # environment, services and suites) would only delay the repair loop.
        if not self.regression and eff_req:
            out_cases.extend(self._shared_conftest_cases(eff_req))
            out_cases.extend(self._shared_test_support_cases(eff_req))
            out_cases.extend(self._test_layout_cases(eff_req))
            out_cases.extend(self._staged_root_cases(eff_req))
            only_names = getattr(self, "_only_checks", None)
            if not only_names or "acceptance::coverage" in only_names:
                out_cases.extend(self._acceptance_coverage_cases(eff_req, ltc))
        own_failed = any(not c.passed and c.blocking for c in out_cases)
        own = out_cases[loop_from:]
        self._progress(**({} if cancelled else {"checks_done": len(norm_cases)}), current=None,
                       passed=sum(1 for c in own if c.passed), failed=sum(1 for c in own if not c.passed and c.blocking))
        if regression and work_kit_root and not cancelled and own_failed:
            log.info("regression deferred req=%s: the REQ's own blocking checks fail", eff_req)
        elif regression and work_kit_root and not cancelled:
            started = time.monotonic()
            out_cases.extend(self.run_regression(eff_req, work_kit_root / "src"))
            log.info("regression req=%s took %.1fs", eff_req, time.monotonic() - started)

        return self._report_from_cases(
            profile_path=profile_path,
            req_id=eff_req,
            mode="auto",
            cases=out_cases,
        )

    def _staged_root_cases(self, req_id: str) -> List[EvalCase]:
        """``structure::root-deliverables``: repository-root deliverables a KIT keeps outside root/
        (a ci/<staging>/scripts/, ci/<staging>/.env.x.example, a staging map of its own) are never
        promoted. B2B REQ-032…038 staged scripts, env examples, the solution eval profile and runbooks
        under ci/shared/ with a STAGING_MAP.json: every check passed, the gate promoted src/ and test/,
        and the solution had no --oidc / --live."""
        kit = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
        ci = kit / "ci"
        policy = root_policy(self.project_root)
        staged: List[str] = []
        maps: List[str] = []
        for path in sorted(kit.rglob("*")) if kit.is_dir() else []:
            if not path.is_file() or any(part in {"node_modules", ".venv", "__pycache__", "reports", "local-eval-workspaces"}
                                         for part in path.relative_to(kit).parts):
                continue
            if re.fullmatch(r"STAGING_MAP\.json|staging[_-]?map\.json", path.name, re.IGNORECASE):
                maps.append(path.relative_to(kit).as_posix())
                continue
            if ci in path.parents:
                parts = path.relative_to(ci).parts
                if len(parts) >= 2 and is_allowed_root_path("/".join(parts[1:]), policy):
                    staged.append(f"{path.relative_to(kit).as_posix()} → root/{'/'.join(parts[1:])}")
        if not staged and not maps:
            return []
        shown = "\n".join(f"  {s}" for s in staged[:20]) + (f"\n  … {len(staged) - 20} more" if len(staged) > 20 else "")
        return [EvalCase(name="structure::root-deliverables", passed=False, code=1, blocking=True, stdout="", stderr=(
            f"[CLike EvalRunner] Repository-root deliverables outside root/: only runs/kit/{req_id}/root/<repository path> "
            "is promoted to the repository (scripts/, deploy/, .env.<name>.example, .gitignore, ci/SOLUTION_LTC.json, "
            "docs/<runbook>.md); a staging folder or a staging map of the KIT never is. Move them:\n" + shown +
            (f"\nRemove the staging map(s): {', '.join(maps)} — CLike promotes root/ as it is." if maps else "") +
            "\nThe eval sees root/ at the workspace root: checks run them there (scripts/…, not ci/<staging>/scripts/…)."))]

    def _acceptance_coverage_cases(self, req_id: str, ltc: Dict[str, Any]) -> List[EvalCase]:
        """``acceptance::coverage``: the KIT's own account of its acceptance criteria
        (runs/kit/<REQ>/docs/ACCEPTANCE.json), checked against the plan and the LTC. The checks can
        all pass while criteria are not implemented (B2B REQ-038: no LTC check covered the live probes
        or the browser journey, and the KIT's SELF_REVIEW said it was not promotable): a criterion
        partial or missing, or one claimed done without a blocking check of the LTC, keeps the REQ
        from promotion and goes to the repair. developer_evidence is listed, not blocking. Without
        the file, a SELF_REVIEW that declares the KIT incomplete blocks the same way."""
        req = next((r for r in self._plan_reqs() if str(r["id"]).upper() == str(req_id).upper()), None)
        acceptance = [str(a) for a in (req or {}).get("acceptance") or [] if str(a).strip()]
        if not acceptance:
            return []
        kit = self.project_root / "runs" / "kit" / self._safe_req_id(req_id)
        ids = []
        for index, text in enumerate(acceptance, start=1):
            m = re.match(r"\s*(REQ-[\w-]+?-A\d+)\b", text) or re.match(r"\s*(A\d+)\b", text)
            ids.append(m.group(1) if m else f"A{index:02d}")
        review = ""
        try:
            review = (kit / "docs" / "SELF_REVIEW.md").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
        incomplete = [line.strip() for line in review.split("\n") if _SELF_INCOMPLETE_RE.search(line)][:6]
        path = kit / "docs" / "ACCEPTANCE.json"
        name = "acceptance::coverage"
        if not path.is_file():
            if not incomplete:
                return []  # nothing declared either way: the checks decide, as before
            return [EvalCase(name=name, passed=False, code=1, blocking=True, stdout="", stderr=(
                f"{_ACCEPTANCE_NOTE}: the KIT's SELF_REVIEW.md declares {req_id} incomplete and the KIT has no "
                f"docs/ACCEPTANCE.json:\n" + "\n".join(f"  {line}" for line in incomplete) +
                f"\nImplement what is left, then write runs/kit/{req_id}/docs/ACCEPTANCE.json with the status of each "
                f"criterion ({', '.join(ids)}) and the blocking checks that verify it."))]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = {str(e.get("id") or "").strip(): e for e in (data.get("criteria") or []) if isinstance(e, dict)}
        except Exception as exc:
            return [EvalCase(name=name, passed=False, code=2, blocking=True, stdout="",
                             stderr=f"{_ACCEPTANCE_NOTE}: docs/ACCEPTANCE.json is not valid JSON with a criteria list: {exc}")]
        blocking_checks = {str(c.get("name") or "") for c in self._normalize_cases(ltc) if c.get("blocking", True)}
        problems: List[str] = []
        external: List[str] = []
        for cid, text in zip(ids, acceptance):
            entry = entries.get(cid)
            short = text[:140]
            if entry is None:
                problems.append(f"{cid}: not in ACCEPTANCE.json — {short}")
                continue
            status = str(entry.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
            # the names agents use for the same fields (B2B REQ-038: blocking_checks, evidence)
            note = next((str(entry[k]).strip() for k in ("note", "evidence", "reason", "notes", "details")
                         if str(entry.get(k) or "").strip()), "")
            raw_checks = next((entry[k] for k in ("checks", "blocking_checks", "verified_by", "check_ids")
                               if isinstance(entry.get(k), list) and entry.get(k)), [])
            checks = [str(c) for c in raw_checks if str(c).strip()]
            if status == "done":
                valid = [c for c in checks if c in blocking_checks]
                if not valid:
                    problems.append(f"{cid}: done, but names no blocking check of ci/LTC.json that verifies it "
                                    f"(named: {', '.join(checks) or 'none'})")
            elif status == "developer_evidence":
                if not note:
                    problems.append(f"{cid}: developer_evidence without a note saying how it is proved")
                else:
                    external.append(f"{cid}: {note[:200]}")
            elif status in {"partial", "missing"}:
                problems.append(f"{cid}: {status}{f' — {note[:240]}' if note else ''}")
            else:
                problems.append(f"{cid}: unknown status {status or '(none)'} (done | partial | missing | developer_evidence)")
        if incomplete and not problems:
            problems.append("ACCEPTANCE.json says every criterion is done, but SELF_REVIEW.md says otherwise:\n" +
                            "\n".join(f"    {line}" for line in incomplete))
        shown_external = ("\nProved on the developer machine or by a real service (reported, not blocking):\n" +
                          "\n".join(f"  {line}" for line in external)) if external else ""
        if problems:
            return [EvalCase(name=name, passed=False, code=1, blocking=True, stdout=shown_external.strip(), stderr=(
                f"{_ACCEPTANCE_NOTE}: {len(problems)} acceptance criterion/criteria of {req_id} not delivered — the checks "
                "passing is not enough to promote it:\n" + "\n".join(f"  {p}" for p in problems) +
                f"\nImplement them (with blocking checks in ci/LTC.json that verify them) and update docs/ACCEPTANCE.json."))]
        return [EvalCase(name=name, passed=True, code=0, blocking=True, stderr="",
                         stdout=f"{len(ids)} acceptance criteria of {req_id}: done with their checks.{shown_external}")]

    def _plan_reqs(self) -> List[Dict[str, Any]]:
        plan_path = self.project_root / "docs" / "harper" / "plan.json"
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [r for r in (plan.get("reqs") or plan.get("req") or []) if isinstance(r, dict) and r.get("id")]

    def _declared_changes(self, req_id: Optional[str]) -> List[Dict[str, Any]]:
        """REQs whose declared changes (/idea --extend: MODIFIED supersedes, REMOVED retires) hold
        for this eval: the promoted ones, and the candidate itself."""
        return [
            r for r in self._plan_reqs()
            if str(r["id"]) == str(req_id) or str(r.get("status") or "").strip().lower() in PROMOTED_REQ_STATUSES
        ]

    def superseded_checks(self, req_id: Optional[str]) -> Dict[str, Dict[str, str]]:
        """{amended REQ: {check id: "REQ-y: reason"}} — checks a MODIFIED REQ declared it replaces.
        They leave the amended REQ's regression (its other checks stay); the replacement lives,
        locked, in the changing REQ's own KIT."""
        out: Dict[str, Dict[str, str]] = {}
        for r in self._declared_changes(req_id):
            for entry in r.get("supersedes") or []:
                ref = str(entry.get("check") if isinstance(entry, dict) else entry or "")
                other, sep, check = ref.partition("#")
                if sep and other and check:
                    reason = str(entry.get("reason") or "") if isinstance(entry, dict) else ""
                    out.setdefault(other, {})[check] = f"{r['id']}: {reason}".rstrip(": ")
        return out

    def superseded_tests(self, req_id: Optional[str]) -> Dict[str, str]:
        """{test reference "path::name": "REQ-y: reason"} — delivered tests a MODIFIED REQ declared it
        replaces (``REQ-x#path::name``). Whichever promoted REQ's check runs that test (B2B: REQ-016's
        test ran in REQ-014's unit check), its failure is the declared change, not a regression."""
        return {check: by for checks in self.superseded_checks(req_id).values() for check, by in checks.items() if "::" in check}

    def regression_req_ids(self, req_id: Optional[str]) -> List[str]:
        """Promoted REQs (plan status done) whose acceptance checks must still pass with this
        candidate, in plan order, when they have an LTC profile. Dependencies that are not
        promoted are not regression targets: their source is already composed into the
        candidate's eval and they have no passing state to regress from. A REQ retired by a
        REMOVED REQ (promoted, or the candidate) leaves the regression set."""
        retired = {str(t) for r in self._declared_changes(req_id) for t in (r.get("retires") or [])}
        return [
            str(r["id"])
            for r in self._plan_reqs()
            if str(r.get("status") or "").strip().lower() in PROMOTED_REQ_STATUSES
            and str(r["id"]) != str(req_id)
            and str(r["id"]) not in retired
            and (self.project_root / "runs" / "kit" / self._safe_req_id(str(r["id"])) / "ci" / "LTC.json").is_file()
        ]

    def _retry_failed_regression_tests(
        self, runner: "EvalRunner", profile: Path, ltc: Dict[str, Any], other: str, report: EvalReport,
        known_failing: frozenset = frozenset(), baseline: Optional["_BaselineCache"] = None,
    ) -> None:
        """Re-run once the blocking tests of a promoted REQ that failed in its regression. One that
        passes the second time is nondeterministic (timing, order, async UI): a warning naming the
        REQ, not a regression of the candidate, so it neither blocks the gate nor goes to the
        candidate's repair (it is the promoted REQ's own test to make deterministic)."""
        failed = [
            c.name for c in report.cases
            if not c.passed and c.blocking and not c.blocked and _is_regression_test_case(c)
            and not c.name.startswith(("env::", "structure::", "ltc::"))
            # it fails on the promoted tree alone too (baseline of this tree): a re-run cannot clear it
            and c.name not in known_failing
        ]
        if not failed or (self.cancel_event is not None and self.cancel_event.is_set()):
            return
        try:
            retry = runner.run_profile(profile=str(profile), ltc=ltc, req_id=other, checks=failed)
        except Exception as exc:  # the first verdict stands
            log.warning("regression retry of %s failed to run: %s", other, exc)
            return
        passed_now = {c.name for c in retry.cases if c.passed and c.name in failed}
        for case in report.cases:
            if case.name in passed_now:
                note = (
                    f"{_NONDETERMINISTIC_NOTE}: {case.name} of {other} failed, then passed on a re-run of the same code. "
                    f"Not a regression of this candidate: make the test of {other} deterministic."
                )
                if baseline is not None:
                    baseline.record_flaky(case.name, case.excerpt)
                case.blocking = False
                case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                case.excerpt = f"{note}\n\n{case.excerpt or ''}"
                log.info("regression %s::%s nondeterministic (passed on retry)", other, case.name)

    def _mark_preexisting_regression_failures(
        self, req_id: Optional[str], profile: Path, ltc: Dict[str, Any], other: str, report: EvalReport,
        baseline: Optional["_BaselineCache"] = None,
    ) -> None:
        """Re-run the blocking failures of a promoted REQ's regression on the promoted tree alone
        (without the candidate). One that fails there too was already broken before this candidate (a
        stale check environment, an earlier REQ): a warning naming the REQ, not a regression of the
        candidate, so it neither blocks the gate nor goes to the candidate's repair.

        The result depends on the promoted tree only, not on the candidate: ``baseline`` keeps it per
        promoted state, so the next eval or repair cycle of any candidate on the same tree reuses it
        instead of running those checks again."""
        failing = [c for c in report.cases if not c.passed and c.blocking and not c.blocked]
        if not failing or (self.cancel_event is not None and self.cancel_event.is_set()):
            return
        baseline = baseline or _BaselineCache(None)
        check_ids = {str(c.get("id") or "") for c in ltc.get("checks") or []}
        # unknown, or known to fail without the error lines to compare (a baseline kept before them)
        unknown = [c.name for c in failing if baseline.result(c.name) is None
                   or (baseline.result(c.name) and c.name not in baseline.errors)]
        retry = sorted({name for name in unknown if name in check_ids})
        if unknown:
            try:
                baseline_runner = EvalRunner(
                    self.project_root,
                    eval_key=f"{self._safe_req_id(req_id)}/regression-baseline/{self._safe_req_id(other)}",
                    cancel_event=self.cancel_event,
                    regression=True,
                )
                rerun = baseline_runner.run_profile(profile=str(profile), ltc=ltc, req_id=other, checks=retry or None)
            except Exception as exc:  # the first verdict stands
                log.warning("regression baseline of %s failed to run: %s", other, exc)
                return
            if self.cancel_event is not None and self.cancel_event.is_set():
                return  # a cancelled run is no baseline
            baseline.store(
                {c.name: (not c.passed and not c.blocked) for c in rerun.cases if not c.blocked},
                {c.name: eval_failures.error_keys(c.excerpt or "") for c in rerun.cases if not c.passed and not c.blocked},
            )
        else:
            log.info("regression %s: baseline of the promoted tree reused for %d check(s)", other, len(failing))
        failing_without = {c.name for c in failing if baseline.result(c.name)}
        for case in failing:
            new = baseline.new_errors(case.name, case.excerpt) if case.name in failing_without else []
            if new:
                # it fails on the promoted tree too, but the candidate adds errors of its own (B2B
                # REQ-003: coverage below the threshold there, an import error with the candidate)
                shown = "\n".join(f"  {key}" for key in new[:6])
                note = (
                    f"{_NEW_ERRORS_NOTE}: {case.name} of {other} fails on the promoted tree without this candidate "
                    f"too, but with the candidate it shows errors it does not show there:\n{shown}\n"
                    "These are a regression of this candidate."
                )
                case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                case.excerpt = f"{note}\n\n{case.excerpt or ''}"
                log.info("regression %s::%s fails without the candidate, with new errors", other, case.name)
                continue
            flaky_at = baseline.known_flaky(case.name, case.excerpt) if case.name not in failing_without else None
            if flaky_at and not case.name.startswith("env::"):
                # it failed and then passed on a re-run in a recent eval, it passes on the promoted tree
                # alone, and it fails again with errors seen only in those nondeterministic runs
                when = time.strftime("%Y-%m-%d", time.localtime(flaky_at))
                note = (
                    f"{_NONDETERMINISTIC_NOTE}: {case.name} of {other} failed, then passed on a re-run of the same "
                    f"code in an earlier eval ({when}), passes on the promoted tree alone, and fails here only with "
                    f"errors it showed then: a known unstable check, not a regression of this candidate. Make the "
                    f"test of {other} deterministic."
                )
                case.blocking = False
                case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                case.excerpt = f"{note}\n\n{case.excerpt or ''}"
                log.info("regression %s::%s known unstable (nondeterministic before)", other, case.name)
                continue
            failed_at = baseline.failed_before(case.name)
            if case.name not in failing_without and failed_at and not case.name.startswith("env::"):
                # it passes on the promoted tree now, but it failed there without any candidate on a
                # recent promoted state: the check is unstable, its result proves nothing about this
                # candidate (the gate shows it as a warning to review; the REQ's test needs a fix)
                when = time.strftime("%Y-%m-%d", time.localtime(failed_at))
                note = (
                    f"{_NONDETERMINISTIC_NOTE}: {case.name} of {other} failed without any candidate on the "
                    f"promoted tree ({when}) and passes there now: an unstable check, not a regression of this "
                    f"candidate. Make the test of {other} deterministic."
                )
                case.blocking = False
                case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                case.excerpt = f"{note}\n\n{case.excerpt or ''}"
                log.info("regression %s::%s unstable (failed without the candidate before)", other, case.name)
                continue
            if case.name not in failing_without:
                if case.name.startswith("env::service::"):
                    # it starts on the promoted tree: the candidate broke the service's environment
                    note = (
                        f"{_SERVICE_BROKEN_NOTE}: {case.name} of {other} starts on the promoted tree but not with this "
                        f"candidate. A configuration or dependency the candidate makes mandatory is missing from "
                        f"{other}'s service environment: keep it optional with a safe default (existing deployments "
                        "and services do not set it), or declare the change with /idea --extend."
                    )
                    case.excerpt = f"{note}\n\n{case.excerpt or ''}"
                    case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                continue
            note = (
                f"{_PREEXISTING_NOTE}: {case.name} of {other} fails on the promoted tree without this candidate too. "
                f"Not a regression of this candidate: {other}'s check or its environment needs a fix."
            )
            case.blocking = False
            case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
            case.excerpt = f"{note}\n\n{case.excerpt or ''}"
            log.info("regression %s::%s already failing without the candidate", other, case.name)

    def _note_shared_file_changes(self, other: str, candidate_root: Path, report: EvalReport) -> None:
        """Name, on each failing blocking check of a promoted REQ, the files of that REQ the candidate
        replaced and how: the repair then sees the cause ("No tests found" after a rewritten test
        runner config, an exact-set check after a new compose service) instead of guessing it."""
        failing = [c for c in report.cases if not c.passed and c.blocking and not c.blocked]
        if not failing:
            return
        other_kit = self.project_root / "runs" / "kit" / self._safe_req_id(other)
        try:
            changes = _shared_file_changes(self.project_root, candidate_root, other_kit)
        except Exception as exc:  # a diagnosis only: the verdict stands without it
            log.warning("shared-file diagnosis of %s failed: %s", other, exc)
            return
        if not changes:
            return
        note = _shared_files_note(other, changes)
        for case in failing:
            case.stderr = f"{case.stderr or ''}\n{note}"[-8000:]
            case.excerpt = f"{note}\n\n{case.excerpt or ''}"
        log.info("regression %s: candidate replaced %d shared file(s)", other, len(changes))

    def _promoted_state_digest(self, req_id: Optional[str]) -> Optional[str]:
        """Digest of what a promoted REQ's baseline (its checks on the promoted tree, without the
        candidate) depends on: the canonical tree, the KITs of the promoted REQs, every LTC,
        plan.json, CLike's version and the eval environment. Not the candidate's KIT: its repair
        cycles and the gate keep the same baseline. Computed once per regression run."""
        cached = getattr(self, "_promoted_digest", None)
        if cached is not None:
            return cached or None
        try:
            from services import eval_verdicts

            root = self.project_root.resolve()
            h = hashlib.sha256()
            h.update(f"clike={eval_verdicts._clike_version()}\0".encode())
            env = scrubbed_process_env()  # docker/eval.env values, tool paths
            for key in sorted(k for k in env if k not in _VOLATILE_ENV_NAMES):
                h.update(f"{key}={env[key]}\0".encode())

            def add_tree(path: Path) -> None:
                if path.is_file():
                    h.update(f"{path.relative_to(root).as_posix()}\0".encode())
                    h.update(path.read_bytes())
                    return
                if not path.is_dir():
                    return
                for dirpath, dirnames, filenames in os.walk(path):
                    dirnames[:] = sorted(d for d in dirnames if d not in eval_verdicts._SKIP_DIRS and not d.endswith(".egg-info"))
                    for name in sorted(filenames):
                        if name.endswith((".pyc", ".log")) or name == ".DS_Store":
                            continue
                        file = Path(dirpath) / name
                        try:
                            h.update(f"{file.relative_to(root).as_posix()}\0".encode())
                            h.update(file.read_bytes())
                        except OSError:
                            continue

            policy = root_policy(root)
            for name in ("src", "test", "tests", *policy["folders"], *policy["files"]):
                add_tree(root / name)
            for other in self.regression_req_ids(req_id):
                kit = root / "runs" / "kit" / self._safe_req_id(other)
                for name in ("src", "test", "tests", "ci", KIT_ROOT_DIR):
                    add_tree(kit / name)
            add_tree(root / "docs" / "harper" / "plan.json")
            for ltc in sorted((root / "runs" / "kit").glob("*/ci/LTC.json")):
                add_tree(ltc)
            digest = h.hexdigest()
        except Exception as exc:  # no cache: every baseline runs, as before
            log.warning("promoted state digest failed: %s", exc)
            digest = ""
        self._promoted_digest = digest
        return digest or None

    def _baseline_cache(self, req_id: Optional[str], other: str) -> "_BaselineCache":
        """Baseline results of ``other`` on the current promoted tree, kept in the eval base dir
        only when it is outside the project (the sandbox volume): the project is writable by local
        agents, and a planted "already failing" result would turn a regression into a warning."""
        try:
            base = self._eval_base_dir()
            root = self.project_root.resolve()
            if base == root or root in base.parents:
                return _BaselineCache(None)
            digest = self._promoted_state_digest(req_id)
            if not digest:
                return _BaselineCache(None)
            return _BaselineCache(base / ".regression-baseline" / f"{self._safe_req_id(other)}.json", digest)
        except Exception as exc:
            log.warning("regression baseline cache unavailable for %s: %s", other, exc)
            return _BaselineCache(None)

    def _reused_case(self, name: str) -> Optional[EvalCase]:
        """A result taken from the run on the same inputs (reuse_cases), marked as such."""
        data = getattr(self, "_reuse", {}).get(str(name))
        if not data:
            return None
        known = {f.name for f in fields(EvalCase)}
        case = EvalCase(**{k: v for k, v in data.items() if k in known})
        case.stdout = f"{_REUSED_NOTE}\n{case.stdout or ''}"
        return case

    def run_regression(self, req_id: Optional[str], candidate_src: Path) -> List[EvalCase]:
        """L2 auto-eval: re-run each regression REQ's own acceptance checks against its composed
        source with the candidate's composed source overlaid last (the state after promotion).
        Cases are named ``regression::<REQ>::<case>`` and keep their blocking flag."""
        superseded = self.superseded_checks(req_id)
        self._superseded_test_refs = self.superseded_tests(req_id)
        candidate = next((r for r in self._plan_reqs() if str(r["id"]) == str(req_id)), {})
        self._candidate_amends = [str(a) for a in (candidate.get("amends") or [])]
        # the REQ promises the amended REQs' tests keep passing: no supersede to suggest
        self._candidate_keeps = bool(_KEEPS_TESTS_RE.search(" ".join(str(a) for a in candidate.get("acceptance") or [])))
        others = self.regression_req_ids(req_id)
        only = getattr(self, "_regression_only", None)
        if only:
            # a targeted re-eval: the promoted REQs that failed before the last repair
            others = [other for other in others if other.upper() in only]
        # the promoted REQs whose regression ran on the same inputs: their results are taken
        reuse_reqs = getattr(self, "_reuse_reqs", set())
        reused: Dict[str, List[EvalCase]] = {
            other: [c for c in (self._reused_case(n) for n in self._reuse if n.upper().startswith(f"REGRESSION::{other.upper()}::")) if c]
            for other in others if other.upper() in reuse_reqs
        }
        if reused:
            log.info("regression of %s: %s taken from the run on the same inputs", req_id, ", ".join(reused))
        others_all = others
        others = [other for other in others if other not in reused]

        def in_plan_order(ran: Dict[str, List[EvalCase]]) -> List[EvalCase]:
            return [case for other in others_all for case in (reused.get(other) or ran.get(other) or [])]

        workers = min(regression_workers(), len(others))
        self._promoted_state_digest(req_id)  # once, before the workers share it
        self._progress(phase="regression", regression_total=len(others), regression_done=0, regression_current=[], current=None)
        if workers <= 1:
            return in_plan_order({other: self._regress_tracked(req_id, other, candidate_src, superseded) for other in others})
        # Each promoted REQ has its own work dir, venv, test databases and service ports: they run
        # side by side, and their cases are reported in plan order as before.
        log.info("regression of %s: %d promoted REQ(s), %d at a time", req_id, len(others), workers)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="clike-regression") as pool:
            futures = {other: pool.submit(self._regress_tracked, req_id, other, candidate_src, superseded) for other in others}
            try:
                ran = in_plan_order({other: future.result() for other, future in futures.items()})
            except BaseException:
                for future in futures.values():
                    future.cancel()
                raise
        self._rerun_timeouts_alone(req_id, candidate_src, ran, superseded)
        return ran

    def _regression_runner(self, req_id: Optional[str], other: str, candidate_src: Path) -> "EvalRunner":
        """The runner of a promoted REQ's checks with the candidate overlaid (the state after promotion)."""
        return EvalRunner(
            self.project_root,
            eval_key=f"{self._safe_req_id(req_id)}/regression/{self._safe_req_id(other)}",
            extra_src_roots=[candidate_src],
            extra_root_roots=[candidate_src.parent / KIT_ROOT_DIR],
            extra_test_roots=[candidate_src.parent],
            cancel_event=self.cancel_event,
            regression=True,
        )

    def _mark_superseded_tests(self, other: str, report: EvalReport) -> None:
        """A failing check of a promoted REQ whose failed tests are all tests a MODIFIED REQ superseded:
        the declared change, not a regression (non-blocking, never repaired). When only some are, the
        note names them, so the repair leaves them alone and fixes the others."""
        refs = getattr(self, "_superseded_test_refs", None) or {}
        if not refs:
            return
        for case in report.cases:
            if case.passed or not case.blocking or case.blocked:
                continue
            failed = eval_failures.failed_tests(f"{case.stdout or ''}\n{case.stderr or ''}\n{case.excerpt or ''}")
            if not failed:
                continue
            hits = {ref: by for ref, by in refs.items() if any(eval_failures.test_matches(f, ref) for f in failed)}
            if not hits:
                continue
            covered = [f for f in failed if any(eval_failures.test_matches(f, ref) for ref in hits)]
            listed = "\n".join(f"- {ref} (superseded by {by})" for ref, by in sorted(hits.items()))
            # the runner's summary may count failures it does not name as tests (a collection error,
            # an unhandled error, a crash): then the check does not hold
            unseen = eval_failures.reported_failures(f"{case.stdout or ''}\n{case.stderr or ''}") > len(failed)
            if len(covered) == len(failed) and not unseen:
                note = (f"{_SUPERSEDED_TESTS_NOTE}: {case.name} of {other} fails only in tests a MODIFIED REQ declared it "
                        f"replaces (/idea --extend):\n{listed}\nThe declared change, not a regression of this candidate.")
                # every other test of the check passed: it holds, as a superseded check does
                case.passed, case.blocking = True, False
                log.info("regression %s::%s fails only in superseded tests", other, case.name)
            else:
                note = (f"{_SUPERSEDED_TESTS_NOTE}: some failures of {case.name} of {other} are tests a MODIFIED REQ "
                        f"declared it replaces — leave them as they are:\n{listed}\nThe other failed tests are a regression.")
            case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
            case.excerpt = f"{note}\n\n{case.excerpt or ''}"

    def _suggest_declared_change(self, req_id: Optional[str], other: str, report: EvalReport) -> None:
        """A blocking failure in a test that a REQ the candidate amends delivered: if the candidate
        changes it on purpose (B2B REQ-037 extends the session fields a REQ-015 test pins, and the
        cascade had not named it), only the developer can declare it — a repair may not change the
        plan. The note gives the exact command; otherwise the candidate keeps that test passing."""
        amends = getattr(self, "_candidate_amends", None) or []
        if not amends or not req_id:
            return
        kits = self.project_root / "runs" / "kit"
        for case in report.cases:
            if case.passed or not case.blocking or case.blocked:
                continue
            refs = []
            for file, name in eval_failures.failed_tests(f"{case.stdout or ''}\n{case.stderr or ''}\n{case.excerpt or ''}"):
                parts = file.replace("\\", "/").split("/")
                for i in range(len(parts)):
                    rel = "/".join(parts[i:])
                    if not rel.startswith(("test/", "tests/")):
                        continue
                    owner = next((a for a in amends if (kits / self._safe_req_id(a) / rel).is_file()), None)
                    if owner:
                        test_name = re.sub(r'\[[^\]]*\]$', '', name)
                        last = re.split(r"::| > ", test_name)[-1].strip()
                        try:
                            body = (kits / self._safe_req_id(owner) / rel).read_text(encoding="utf-8", errors="ignore")
                        except OSError:
                            body = ""
                        if not last or not re.search(rf"(?<![\w-]){re.escape(last)}(?![\w-])", body):
                            break  # a name cut in the output, or not a test of that file: no command to give
                        ref = f"{owner}#{rel}::{test_name}"
                        if ref not in refs:
                            refs.append(ref)
                        break
            if not refs:
                continue
            text = f"{case.stdout or ''}\n{case.stderr or ''}"
            if not getattr(self, "_candidate_keeps", False) and _ADDITIVE_DIFF_RE.search(text):
                commands = "\n".join(f'  /eval {req_id} --supersede {ref} "<why the release changes it>"' for ref in refs)
                note = (f"{_DECLARE_NOTE}: {case.name} of {other} fails in delivered tests of REQs {req_id} amends, and the "
                        "failure shows the new value extends the old one (more items in a set, list or mapping). If "
                        f"{req_id} extends what they pin on purpose, the developer declares it — a repair may not change "
                        f"the plan:\n{commands}\nOtherwise {req_id} must keep them passing.")
            else:
                # a refusal that no longer happens, another error, a missing route: a guarantee broken, not a
                # list extended (B2B REQ-038: its own A01 says the REQ-035 refusal tests "still hold")
                listed = "\n".join(f"  {ref.split('#', 1)[1]}" for ref in refs)
                note = (f"{_DECLARE_NOTE}: {case.name} of {other} fails in delivered tests of REQs {req_id} amends, and "
                        f"the failure is not an extension of what they pin: a regression {req_id} must fix (keep "
                        f"these tests passing):\n{listed}")
            case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
            case.excerpt = f"{note}\n\n{case.excerpt or ''}"

    def _rerun_timeouts_alone(
        self, req_id: Optional[str], candidate_src: Path, cases: List[EvalCase], superseded: Dict[str, Dict[str, str]],
    ) -> None:
        """Blocking regression failures that ran out of time while several promoted REQs ran side by
        side: each runs again alone, after the others. One that passes alone was slowed by the parallel
        load (B2B REQ-037: a 30 s test, a database connection, a 300 s suite, a dev server start), not
        broken by the candidate: a warning, never repaired. One that fails alone too stays blocking."""
        slow: Dict[str, List[EvalCase]] = {}
        for case in cases:
            if case.passed or not case.blocking or case.blocked or not _is_regression_test_case(case):
                continue
            other, sep, check = case.name.partition("::")[2].partition("::")
            if not sep or not eval_failures.timed_out(case.excerpt or f"{case.stdout or ''}\n{case.stderr or ''}"):
                continue
            slow.setdefault(other, []).append(case)
        for other, failing in slow.items():
            if self.cancel_event is not None and self.cancel_event.is_set():
                return
            profile = self.project_root / "runs" / "kit" / self._safe_req_id(other) / "ci" / "LTC.json"
            try:
                ltc = json.loads(profile.read_text(encoding="utf-8"))
                names = [c.name.split("::", 2)[2] for c in failing]
                runner = self._regression_runner(req_id, other, candidate_src)
                runner._skip_checks = {k for k in (superseded.get(other) or {}) if "::" not in k} or None
                rerun = runner.run_profile(profile=str(profile), ltc=ltc, req_id=other, checks=names)
            except Exception as exc:  # the first verdict stands
                log.warning("regression %s: re-run alone failed to run: %s", other, exc)
                continue
            alone = {c.name: c for c in rerun.cases}
            for case in failing:
                again = alone.get(case.name.split("::", 2)[2])
                if again is not None and again.passed:
                    note = (f"{_CONTENTION_NOTE}: {case.name} ran out of time while {regression_workers()} promoted REQs ran "
                            "side by side, and passes when run alone: the sandbox load, not this candidate "
                            "(fewer at a time: CLIKE_EVAL_REGRESSION_WORKERS).")
                    case.blocking = False
                    log.info("%s passes alone: parallel load", case.name)
                else:
                    note = (f"{_CONTENTION_NOTE}: {case.name} ran out of time, and again when run alone: the slowdown "
                            "comes with the candidate (a slower path, a wait that never ends, a service that does not start).")
                case.stderr = f"{case.stderr or ''}\n{note}"[-4000:]
                case.excerpt = f"{note}\n\n{case.excerpt or ''}"

    def _regress_tracked(
        self, req_id: Optional[str], other: str, candidate_src: Path, superseded: Dict[str, Dict[str, str]]
    ) -> List[EvalCase]:
        """_regress_one, with the promoted REQ in the live progress while it runs."""
        self._progress_regression(other, started=True)
        try:
            return self._regress_one(req_id, other, candidate_src, superseded)
        finally:
            self._progress_regression(other, started=False)

    def _regress_one(
        self, req_id: Optional[str], other: str, candidate_src: Path, superseded: Dict[str, Dict[str, str]]
    ) -> List[EvalCase]:
        """The regression of one promoted REQ: its checks with the candidate overlaid, the retry of
        a failing test, the baseline without the candidate, the shared-file diagnosis."""
        cases: List[EvalCase] = []
        profile = self.project_root / "runs" / "kit" / self._safe_req_id(other) / "ci" / "LTC.json"
        try:
            ltc = json.loads(profile.read_text(encoding="utf-8"))
        except Exception as exc:
            cases.append(
                EvalCase(
                    name=f"regression::{other}::ltc",
                    passed=False,
                    code=2,
                    stdout="",
                    stderr=f"unreadable LTC profile {profile}: {exc}",
                    blocking=False,
                )
            )
            return cases
        runner = self._regression_runner(req_id, other, candidate_src)
        # declared, approved change: these checks of the amended REQ no longer hold (a test reference,
        # path::name, is not a check: its failure is recognised where it runs, _mark_superseded_tests)
        dropped = {check: by for check, by in (superseded.get(other) or {}).items() if "::" not in check}
        if dropped:
            runner._skip_checks = set(dropped)
            for check, by in sorted(dropped.items()):
                note = f"superseded by {by} — not run (declared change of /idea --extend)"
                cases.append(EvalCase(name=f"regression::{other}::{check}::superseded", passed=True, code=0,
                                      stdout=note, stderr="", blocking=False))
                log.info("regression %s: check %s superseded by %s", other, check, by)
            if not [c for c in self._normalize_cases(ltc) if str(c.get("name") or "case") not in dropped]:
                return cases  # every check of the amended REQ is replaced: nothing left to regress
        report = runner.run_profile(profile=str(profile), ltc=ltc, req_id=other)
        if runner.reconciled_tests:
            # visible, never silent: the candidate changes tests another REQ delivered
            files = sorted(set(runner.reconciled_tests))
            cases.append(EvalCase(
                # a warning (non-blocking failure): shown in the report, never repaired
                name=f"regression::{other}::reconciled-tests", passed=False, code=1, blocking=False,
                stdout=(f"{other}'s checks ran with the candidate's version of {len(files)} file(s) in its test directories "
                        "(the state after promotion); review the change before the gate:\n"
                        + "\n".join(f"- {f}" for f in files)),
                stderr="",
            ))
            log.info("regression %s: candidate reconciles %d test file(s)", other, len(files))
        baseline = self._baseline_cache(req_id, other)
        self._retry_failed_regression_tests(runner, profile, ltc, other, report, known_failing=baseline.failing(), baseline=baseline)
        self._mark_preexisting_regression_failures(req_id, profile, ltc, other, report, baseline=baseline)
        self._mark_superseded_tests(other, report)
        self._suggest_declared_change(req_id, other, report)
        self._note_shared_file_changes(other, candidate_src.parent, report)
        for case in report.cases:
            if not _is_regression_test_case(case):
                # Lint, types, coverage of the other REQ now measure the candidate's code too
                # (the candidate's own checks cover it): reported, not blocking.
                case.blocking = False
            case.name = f"regression::{other}::{case.name}"
            cases.append(case)
        return cases
