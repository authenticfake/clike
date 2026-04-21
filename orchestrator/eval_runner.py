from __future__ import annotations

import hashlib
import logging
import os
import re
import shlex
import subprocess
import sys
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
            blocked = self._is_environment_blocked(
                code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                environment_requirements=environment_requirements or [],
            )
            ok = proc.returncode == expect
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

    def _is_environment_blocked(
        self,
        *,
        code: int,
        stdout: str,
        stderr: str,
        environment_requirements: List[str],
    ) -> bool:
        text = f"{stdout}\n{stderr}".lower()
        if code == 127:
            return True

        markers = [
            "command not found",
            "no module named",
            "externally-managed-environment",
            "could not find a version that satisfies the requirement",
            "failed to establish a new connection",
            "temporary failure in name resolution",
            "network is unreachable",
            "connection refused",
            "permission denied",
        ]
        if any(marker in text for marker in markers):
            return True

        return bool(environment_requirements) and code in {126, 127}

    def _safe_req_id(self, req_id: Optional[str]) -> str:
        raw = req_id or "REQ-UNKNOWN"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)

    def _resolve_req_file(self, req_file: str) -> Path:
        raw = Path(req_file)
        return raw if raw.is_absolute() else (self.project_root / raw).resolve()

    def _venv_dir(self, req_id: Optional[str]) -> Path:
        """
        Runtime eval virtualenvs must not be created under .clike.

        .clike is project capability/configuration space and may be read-only,
        versioned, or managed by templates. Eval runtime artifacts belong under
        runs/eval, which is the canonical writable evaluation area.
        """
        return self.project_root / "runs" / "eval" / ".venvs" / self._safe_req_id(req_id)

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
            blocking=False,
            environment_requirements=["pip", "network", "requirements"],
        )

        if install_case.passed:
            try:
                marker.write_text("ok\n", encoding="utf-8")
            except Exception as exc:
                install_case.stderr = (install_case.stderr + f"\nmarker write warning: {exc}")[-4000:]
        else:
            install_case.blocked = True

        cases.append(install_case)
        return venv_env, cases

    def _normalize_cases(self, ltc: Dict[str, Any]) -> List[Dict[str, Any]]:
        norm_cases: List[Dict[str, Any]] = []

        if isinstance(ltc.get("checks"), list) and ltc["checks"]:
            for check in ltc["checks"]:
                if not isinstance(check, dict):
                    continue
                norm_cases.append(
                    {
                        "name": check.get("id") or check.get("name") or check.get("command") or "check",
                        "run": check.get("command") or check.get("run"),
                        "cwd": check.get("cwd"),
                        "expect": int(check.get("expect", check.get("expect_exit", 0))),
                        "timeout": check.get("timeout"),
                        "env": check.get("env") or {},
                        "blocking": bool(check.get("blocking", True)),
                        "environment_requirements": check.get("environment_requirements") or [],
                    }
                )
            return norm_cases

        if isinstance(ltc.get("cases"), list) and ltc["cases"]:
            for case in ltc["cases"]:
                if not isinstance(case, dict):
                    continue
                norm_cases.append(
                    {
                        "name": case.get("name") or case.get("run") or "case",
                        "run": case.get("run"),
                        "cwd": case.get("cwd"),
                        "expect": int(case.get("expect", 0)),
                        "timeout": case.get("timeout"),
                        "env": case.get("env") or {},
                        "blocking": bool(case.get("blocking", True)),
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
            for command in ltc["commands"]:
                if not isinstance(command, dict):
                    continue

                run = command.get("run") or command.get("command")
                if not run:
                    continue

                expected = command.get(
                    "expected_exit_code",
                    command.get("expect_exit", command.get("expect", 0)),
                )

                required = command.get("required", True)
                blocking = bool(required)

                norm_cases.append(
                    {
                        "name": command.get("id") or command.get("name") or command.get("label") or run,
                        "run": run,
                        "cwd": command.get("cwd") or command.get("working_dir"),
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
                        "blocking": bool(raw.get("required", True)) if isinstance(raw, dict) else True,
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
            1 for case in cases if not case.passed and not case.blocked and case.blocking
        )
        warnings = sum(
            1 for case in cases if not case.passed and (case.blocked or not case.blocking)
        )

        if hard_failed > 0:
            status = "FAIL"
        elif warnings > 0 or blocked > 0:
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
        default_cwd = self.project_root / (ltc.get("cwd") or "")
        out_cases: List[EvalCase] = []

        base_env = self._merge_env(top_env, None)
        runtime = ltc.get("runtime") or {}
        requirements_file = (
            runtime.get("requirements_file")
            or ltc.get("requirements_file")
            or ltc.get("pip_file")
            or ltc.get("pip-file")
        )

        if not requirements_file:
            inferred_candidates = [
                profile_path.parent / "requirements.txt",
                profile_path.parent.parent / "requirements.txt",
            ]
            for inferred_requirements in inferred_candidates:
                if inferred_requirements.exists():
                    requirements_file = str(inferred_requirements)
                    break

        eval_env, setup_cases = self._ensure_eval_venv(
            req_id=eff_req,
            requirements_file=requirements_file,
            env=base_env,
            cwd=default_cwd,
        )
        out_cases.extend(setup_cases)

        pre_cmds = ltc.get("pre") or []
        for i, pre in enumerate(pre_cmds, start=1):
            out_cases.append(
                self._run(
                    name=f"pre::{i}",
                    cmd=pre,
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
            cmd = case.get("run")
            workdir = self.project_root / case.get("cwd") if case.get("cwd") else self.project_root
            case_env = self._merge_env(eval_env, case.get("env") or {})
            blocking = bool(case.get("blocking", True))
            environment_requirements = list(case.get("environment_requirements") or [])

            if not cmd:
                out_cases.append(
                    EvalCase(
                        name=case.get("name") or "case",
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

            out_cases.append(
                self._run(
                    name=case.get("name") or "case",
                    cmd=cmd,
                    cwd=workdir,
                    expect=case.get("expect", 0),
                    env=case_env,
                    timeout=case.get("timeout"),
                    blocking=blocking,
                    environment_requirements=environment_requirements,
                )
            )

        return self._report_from_cases(
            profile_path=profile_path,
            req_id=eff_req,
            mode="auto",
            cases=out_cases,
        )