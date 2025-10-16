# orchestrator/app/eval_runner.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging, os, shlex, subprocess, sys

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

@dataclass
class EvalReport:
    profile: str
    req_id: Optional[str]
    mode: str                      # "auto" | "manual"
    passed: int
    failed: int
    cases: List[EvalCase]
    junit_path: Optional[str] = None
    json_path: Optional[str] = None

class EvalRunner:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    # ------------------------ helpers -------------------------
    def _merge_env(self, base: Optional[Dict[str, str]], extra: Optional[Dict[str, str]]) -> Dict[str, str]:
        env = os.environ.copy()
        if base:
            env.update({str(k): str(v) for k, v in base.items()})
        if extra:
            env.update({str(k): str(v) for k, v in extra.items()})
        return env

    def _run(self, *, name: str, cmd: str, cwd: Path, expect: int = 0, env: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> EvalCase:
        try:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            ok = (p.returncode == expect)
            return EvalCase(
                name=name,
                passed=ok,
                code=p.returncode,
                stdout=(p.stdout or "")[-4000:],
                stderr=(p.stderr or "")[-4000:],
                cmd=cmd,
                cwd=str(cwd),
                expect=expect
            )
        except subprocess.TimeoutExpired as e:
            return EvalCase(
                name=name,
                passed=False,
                code=998,
                stdout=(e.stdout or ""),
                stderr=f"timeout: {e}",
                cmd=cmd,
                cwd=str(cwd),
                expect=expect
            )
        except Exception as e:
            return EvalCase(
                name=name,
                passed=False,
                code=999,
                stdout="",
                stderr=str(e),
                cmd=cmd,
                cwd=str(cwd),
                expect=expect
            )

    # ---- PIP install helpers (sicuri) ----
    def _pip_install_packages(self, pkgs: List[str], env: Dict[str, str], workdir: Path) -> EvalCase:
        """Install only PyPI-style names. Filtra path o token vuoti."""
        if not pkgs:
            return EvalCase(name="pip::noop", passed=True, code=0, stdout="no pkgs", stderr="")

        clean: List[str] = []
        bad: List[str] = []
        for p in pkgs:
            s = (p or "").strip()
            # escludi path o file requirements passati per errore
            if not s or s.startswith(("/", "./", "../", "~")) or os.sep in s or s.endswith(".txt"):
                bad.append(p)
                continue
            clean.append(s)

        if bad:
            msg = f"Skipped invalid pip entries (paths/files): {bad}. Use PyPI names or 'pip_file'."
            # Non blocchiamo tutto: proviamo a installare i validi, ma segnaliamo.
        else:
            msg = ""

        if not clean:
            return EvalCase(name="pip::skip", passed=True, code=0, stdout="no valid pkgs", stderr=msg)

        quoted = " ".join(shlex.quote(x) for x in clean)
        cmd = f"{shlex.quote(sys.executable)} -m pip install --disable-pip-version-check --no-input {quoted}"
        res = self._run(name=f"pip install ({len(clean)} pkgs)", cmd=cmd, cwd=workdir, expect=0, env=env)
        if msg:
            # Aggiungi nota sugli scarti
            res.stderr = (res.stderr + ("\n" if res.stderr else "") + msg)[-4000:]
        return res

    def _pip_install_file(self, req_file: str, env: Dict[str, str], workdir: Path) -> EvalCase:
        """Install da requirements file, risolto rispetto a project_root."""
        if not req_file or not isinstance(req_file, str):
            return EvalCase(name="pip::file::skip", passed=True, code=0, stdout="no pip_file", stderr="")
        abs_path = (self.project_root / req_file).resolve()
        if not abs_path.exists():
            return EvalCase(
                name="pip::file::missing",
                passed=False,
                code=3,
                stdout="",
                stderr=f"requirements file not found: {abs_path}"
            )
        cmd = f"{shlex.quote(sys.executable)} -m pip install --disable-pip-version-check --no-input -r {shlex.quote(str(abs_path))}"
        return self._run(name=f"pip install (-r {abs_path.name})", cmd=cmd, cwd=workdir, expect=0, env=env)

    # ------------------------ PUBLIC: run profile -------------------------
    def run_profile(self, profile: str, ltc: Dict[str, Any], mode: str = "auto", verdict: Optional[str] = None, req_id: Optional[str] = None ) -> EvalReport:
        """
        Esegue l'LTC in modalità 'auto' (default) oppure produce un esito manuale
        ('manual' + verdict in {'pass','fail'}). Nessun side-effect sui file di progetto.
        """
        # normalizza il path dell’LTC
        profile_path = Path(profile)
        if not profile_path.is_absolute():
            profile_path = (self.project_root / profile_path)

        # -------- manual mode ----------
        if mode.lower() == "manual":
            if verdict not in ("pass", "fail"):
                raise ValueError("manual mode requires verdict in {'pass','fail'}")
            cases = [EvalCase(
                name=f"manual::{req_id or (ltc.get('req_id') if isinstance(ltc, dict) else 'REQ')}",
                passed=(verdict == "pass"),
                code=(0 if verdict == "pass" else 1),
                stdout="",
                stderr=""
            )]
            passed = 1 if verdict == "pass" else 0
            failed = 0 if verdict == "pass" else 1
            return EvalReport(profile=str(profile_path), req_id=req_id, mode="manual", passed=passed, failed=failed, cases=cases)

        # -------- auto mode ----------
        if ltc is None:
            rep = EvalReport(
                profile=str(profile_path),
                req_id=req_id,
                mode="auto",
                passed=0,
                failed=1,
                cases=[EvalCase(name="noop", passed=False, code=2, stdout="", stderr="Unsupported profile (expect .json LTC).")]
            )
            return rep

        eff_req = req_id or ltc.get("req_id")

        # Env & workdir
        top_env = ltc.get("env") or {}
        default_cwd = self.project_root / (ltc.get("cwd") or "")
        out_cases: List[EvalCase] = []

        # Optional: top-level pip installs
        top_pip_file = ltc.get("pip_file")
        top_pip = ltc.get("pip") or []
        if top_pip_file:
            env = self._merge_env(top_env, None)
            out_cases.append(self._pip_install_file(top_pip_file, env, default_cwd))
        elif top_pip:
            env = self._merge_env(top_env, None)
            out_cases.append(self._pip_install_packages(top_pip, env, default_cwd))

        # Optional: top-level pre-commands
        pre_cmds = ltc.get("pre") or []
        for i, pre in enumerate(pre_cmds, start=1):
            env = self._merge_env(top_env, None)
            out_cases.append(self._run(
                name=f"pre::{i}",
                cmd=pre,
                cwd=default_cwd,
                expect=0,
                env=env,
                timeout=None
            ))

        # Normalizza casi (supporta 'cases[]', 'steps[]', o singolo 'run')
        norm_cases: List[Dict[str, Any]] = []
        if isinstance(ltc.get("cases"), list) and ltc["cases"]:
            for c in ltc["cases"]:
                norm_cases.append({
                    "name": c.get("name") or c.get("run") or "case",
                    "run": c.get("run"),
                    "cwd": c.get("cwd"),
                    "expect": int(c.get("expect", 0)),
                    "timeout": c.get("timeout"),
                    "pip": c.get("pip") or [],
                    "pip_file": c.get("pip_file"),
                    "env": c.get("env") or {}
                })
        elif isinstance(ltc.get("steps"), list) and ltc["steps"]:
            for s in ltc["steps"]:
                norm_cases.append({
                    "name": s.get("name") or s.get("run") or "step",
                    "run": s.get("run"),
                    "cwd": s.get("cwd"),
                    "expect": int(s.get("expect_exit", 0)),
                    "timeout": s.get("timeout"),
                    "pip": s.get("pip") or [],
                    "pip_file": s.get("pip_file"),
                    "env": s.get("env") or {}
                })
        elif ltc.get("run"):
            norm_cases.append({
                "name": "default",
                "run": ltc.get("run"),
                "cwd": ltc.get("cwd"),
                "expect": int(ltc.get("expect", 0)),
                "timeout": ltc.get("timeout"),
                "pip": ltc.get("pip_case") or [],
                "pip_file": ltc.get("pip_file_case"),
                "env": ltc.get("env_case") or {}
            })

        # Esecuzione casi (con eventuali pip/env per-caso)
        for c in norm_cases:
            cmd = c.get("run")
            workdir = self.project_root / c.get("cwd") if c.get("cwd") else self.project_root
            case_env = self._merge_env(top_env, c.get("env") or {})
            timeout = c.get("timeout")

            if not cmd:
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=997,
                    stdout="", stderr="missing 'run'",
                    cmd=None, cwd=str(workdir),
                    expect=c.get("expect")))
                continue

            # per-case optional pip
            if c.get("pip_file"):
                out_cases.append(self._pip_install_file(c["pip_file"], case_env, workdir))
            elif c.get("pip"):
                out_cases.append(self._pip_install_packages(c["pip"], case_env, workdir))

            # run real case
            out_cases.append(self._run(
                name=c.get("name") or "case",
                cmd=cmd,
                cwd=workdir,
                expect=c.get("expect", 0),
                env=case_env,
                timeout=timeout
            ))

        # Report
        passed = sum(1 for c in out_cases if c.passed)
        failed = len(out_cases) - passed
        rep = EvalReport(
            profile=str(profile_path),
            req_id=eff_req,
            mode="auto",
            passed=passed,
            failed=failed,
            cases=out_cases
        )
        return rep
