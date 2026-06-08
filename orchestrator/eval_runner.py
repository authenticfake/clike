from __future__ import annotations
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("eval_runner")


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


class EvalRunner:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def _merge_env(
        self,
        base: Optional[Dict[str, str]],
        extra: Optional[Dict[str, str]],
    ) -> Dict[str, str]:
        env = os.environ.copy()
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
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stderr = proc.stderr or ""
            stdout = proc.stdout or ""
            ok = proc.returncode == expect
            blocked = False
            if not ok:
                blocked = self._is_environment_blocked(
                    code=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    environment_requirements=environment_requirements or [],
                )

            if blocked and not ok:
                stderr = (
                    stderr
                    + "\n[CLike EvalRunner] Classified as environment-blocked: "
                    "missing tool, unavailable dependency, native binary mismatch, "
                    "network restriction, or sandbox/runtime incompatibility."
                )[-4000:]
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
            )
        except subprocess.TimeoutExpired as exc:
            return EvalCase(
                name=name,
                passed=False,
                code=998,
                stdout=str(exc.stdout or "")[-4000:],
                stderr=f"timeout: {exc}",
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
    ) -> bool:
        text = f"{stdout}\n{stderr}".lower()

        if code not in {126, 127} and self._looks_like_executed_diagnostic_failure(text):
            return False

        if "cannot find module './" in text or 'cannot find module "../' in text:
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
            "not found",
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
        return any(re.search(marker, text, flags=re.IGNORECASE | re.DOTALL) for marker in diagnostic_markers)

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
        candidates.append(Path(tempfile.gettempdir()) / "clike-eval" / project_key)

        for candidate in candidates:
            resolved = candidate if candidate.is_absolute() else (self.project_root / candidate)
            if self._is_writable_dir(resolved):
                return resolved.resolve()

        raise OSError(
            "No writable eval directory found. Tried: "
            + ", ".join(str(candidate) for candidate in candidates)
        )



    def _resolve_req_file(self, req_file: str) -> Path:
        raw = Path(req_file)
        return raw if raw.is_absolute() else (self.project_root / raw).resolve()

    def _copy_tree_overlay(self, src: Path, dst: Path) -> None:
        """
        Copy a tree into an overlay destination.

        Later copies win. This keeps the implementation intentionally simple:
        promoted roots first, dependency KIT roots next, current KIT last.
        """
        if not src.exists():
            return

        ignored_names = {"__pycache__", "__MACOSX", ".DS_Store", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

        if src.is_file():
            if src.name not in ignored_names and src.suffix not in {".pyc", ".pyo"}:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return

        for item in src.rglob("*"):
            rel = item.relative_to(src)
            if any(part in ignored_names for part in rel.parts):
                continue
            if item.suffix in {".pyc", ".pyo"}:
                continue

            target = dst / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

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
            self._copy_tree_overlay(dep_root / "src", overlay / "src")
            self._copy_tree_overlay(dep_root / "test", overlay / "test")
            self._copy_tree_overlay(dep_root / "tests", overlay / "tests")

        # Current KIT wins last.
        self._copy_tree_overlay(kit_root / "src", overlay / "src")
        self._copy_tree_overlay(kit_root / "test", overlay / "test")
        self._copy_tree_overlay(kit_root / "tests", overlay / "tests")

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

        shutil.copytree(
            kit_root,
            work_kit_root,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".npm-*",
                ".venv",
                "__pycache__",
                "__MACOSX",
                ".DS_Store",
                "*.pyc",
                "*.pyo",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                "reports",
            ),
        )
        
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
                    ignore=shutil.ignore_patterns(
                        "node_modules",
                        ".npm-*",
                        ".venv",
                        "__pycache__",
                        "__MACOSX",
                        ".DS_Store",
                        "*.pyc",
                        "*.pyo",
                        ".pytest_cache",
                        ".mypy_cache",
                        ".ruff_cache",
                        "reports",
                    ),
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
                        self._copy_tree_overlay(
                            dep_work / logical_root,
                            composed_logical_root,
                        )

                    self._copy_tree_overlay(
                        kit_root / logical_root,
                        composed_logical_root,
                    )
                else:
                    # Default /eval is target-scoped.
                    #
                    # Do not place promoted/dependency tests under work/<REQ>/test
                    # unless the caller explicitly requested a full regression mode.
                    # Generated REQ-local CI scripts commonly scan work/<REQ>/test
                    # for tests, secrets, and typecheck inputs. Mixing dependency
                    # tests here causes false failures in downstream REQs.
                    self._copy_tree_overlay(
                        kit_root / logical_root,
                        composed_logical_root,
                    )

                if composed_logical_root.exists():
                    target_logical_root = work_kit_root / logical_root
                    if target_logical_root.exists():
                        shutil.rmtree(target_logical_root)
                    shutil.copytree(
                        composed_logical_root,
                        target_logical_root,
                        dirs_exist_ok=True,
                    )

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

        # Compatibility shim for CI scripts that still infer:        #   <eval-base>/runs/kit/<REQ-ID>
        # from __dirname instead of using CLIKE_EVAL_KIT_DIR.
        # This keeps already generated KITs runnable while future KITs migrate
        # to explicit env vars.
        compat_kit_root = self._eval_base_dir() / "runs" / "kit" / kit_root.name
        try:
            compat_kit_root.parent.mkdir(parents=True, exist_ok=True)
            if compat_kit_root.exists() or compat_kit_root.is_symlink():
                if compat_kit_root.is_symlink() or compat_kit_root.is_file():
                    compat_kit_root.unlink()
                else:
                    shutil.rmtree(compat_kit_root)
            try:
                compat_kit_root.symlink_to(work_kit_root, target_is_directory=True)
            except OSError:
                shutil.copytree(work_kit_root, compat_kit_root)
        except Exception:
            # Best-effort compatibility only. The canonical path rewrite above
            # remains the source of truth.
            pass

        if path_map is None:
            path_map = {}

        if dependency_roots is None:
            dependency_roots = []

        return work_root, reports_root, logs_root, path_map, work_kit_root, dependency_roots

    def _rewrite_for_eval_workspace(self, value: Any, path_map: Dict[str, str]) -> Any:
        if not isinstance(value, str) or not path_map:
            return value

        rewritten = value
        for source, target in sorted(path_map.items(), key=lambda item: len(item[0]), reverse=True):
            rewritten = rewritten.replace(source, target)
        return rewritten

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
        npm_cache = self._eval_dir(req_id) / ".npm-cache"
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

        try:
            workspace_result = self._prepare_eval_workspace(
                req_id=eff_req,
                profile_path=profile_path,
            )
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
                        stderr=f"prepare eval workspace failed: {exc}",
                        cmd=None,
                        cwd=str(self.project_root),
                        blocked=False,
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
                        blocked=False,
                        blocking=True,
                    )
                ],
            )

        work_root, reports_root, logs_root, path_map, work_kit_root, dependency_roots = workspace_result

        active_profile_path = Path(
            self._rewrite_for_eval_workspace(str(profile_path), path_map)
        ).resolve()

        runtime_working_directory = self._runtime_working_directory(ltc)
        default_cwd = self._resolve_workdir(
            ltc.get("cwd") or runtime_working_directory or "",
            path_map,
        )

        overlay_workspace_raw = path_map.get("CLIKE_EVAL_OVERLAY_WORKSPACE", "")
        overlay_src_raw = path_map.get("CLIKE_EVAL_OVERLAY_SRC", "")
        overlay_test_raw = path_map.get("CLIKE_EVAL_OVERLAY_TEST", "")
        overlay_tests_raw = path_map.get("CLIKE_EVAL_OVERLAY_TESTS", "")

        eval_path_env = {
            "CLIKE_EVAL_WORK_DIR": str(work_root),
            "CLIKE_EVAL_REPORT_DIR": str(reports_root),
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
            "MYPY_CACHE_DIR": str(self._eval_dir(eff_req) / ".mypy-cache"),
            "PYTHONPYCACHEPREFIX": str(self._eval_dir(eff_req) / ".pycache"),

            "npm_config_cache": str(self._eval_dir(eff_req) / ".npm-cache"),
            "NPM_CONFIG_CACHE": str(self._eval_dir(eff_req) / ".npm-cache"),
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
        if runtime_name in node_runtime_names or (active_profile_path.parent / "package.json").exists():
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

        for case in norm_cases:
            raw_cmd = case.get("run")
            cmd = self._rewrite_command_for_eval_workspace(raw_cmd, path_map)
            setup = self._rewrite_for_eval_workspace(case.get("setup"), path_map)
            workdir = self._resolve_workdir(case.get("cwd"), path_map) if case.get("cwd") else default_cwd
            case_env = self._merge_env(eval_env, case.get("env") or {})
            blocking = bool(case.get("blocking", True))
            environment_requirements = list(case.get("environment_requirements") or [])
            timeout = case.get("timeout")
            case_name = case.get("name") or "case"



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

            result = self._normalize_raw_secret_scan_result(result)

            out_cases.append(result)

        return self._report_from_cases(
            profile_path=profile_path,
            req_id=eff_req,
            mode="auto",
            cases=out_cases,
        )
