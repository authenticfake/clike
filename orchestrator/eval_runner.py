# orchestrator/app/eval_runner.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json, logging
import subprocess
import time
import xml.etree.ElementTree as ET

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

    # ------------------------ PUBLIC: run profile -------------------------
    def run_profile(self, profile: str,ltc: Dict[str, Any], mode: str = "auto", verdict: Optional[str] = None, req_id: Optional[str] = None ) -> EvalReport:
        """
        Esegue l'LTC in modalità 'auto' (default) oppure produce un esito manuale
        ('manual' + verdict in {'pass','fail'}). Nessun side-effect sui file di progetto.
        """
        # normalizza il path dell’LTC
        profile_path = Path(profile)
        
        if not profile_path.is_absolute():
            profile_path = (self.project_root / profile_path)

        if mode.lower() == "manual":
            log.info("run_profile req-id form manual -->%s", req_id)
            if verdict not in ("pass", "fail"):
                raise ValueError("manual mode requires verdict in {'pass','fail'}")
            passed = ('all' if verdict == "pass" else 0)
            failed = (0 if verdict == "pass" else 'all')
            cases = [EvalCase(name=f"manual::{req_id or 'REQ'}", passed=(verdict == "pass"), code=(0 if verdict == "pass" else 1), stdout="", stderr="")]
            rep = EvalReport(profile=str(profile_path), req_id=req_id, mode="manual", passed=passed, failed=failed, cases=cases)
            log.info("run_profile report (manual) -->%s", rep)
            return rep
        
        
        # AUTO: supporto LTC.json (nuovo 'cases[]' o legacy 'steps[]' o singolo 'run')
        if ltc is None:
            # profilo non supportato
            rep = EvalReport(
                profile=str(profile_path),
                req_id=req_id,
                mode="auto",
                passed=0,
                failed=1,
                cases=[EvalCase(name="noop", passed=False, code=2, stdout="", stderr="Unsupported profile (expect .json LTC).")]
            )
            return rep
        
        log.info("run_profile req-id form ltc -->%s", ltc.get("req_id"))
        # se non passato esplicitamente, prendi req_id dall’LTC
        eff_req = req_id or ltc.get("req_id")
        log.info("run_profile eff_req=%s", eff_req)

        # normalizza: preferisci 'cases[]/run/cwd/expect', fallback a 'steps[]/run/expect_exit', fallback a singolo 'run'
        norm_cases: List[Dict[str, Any]] = []
        if isinstance(ltc.get("cases"), list) and ltc["cases"]:
            for c in ltc["cases"]:
                norm_cases.append({
                    "name": c.get("name") or c.get("run") or "case",
                    "run": c.get("run"),
                    "cwd": c.get("cwd"),
                    "expect": int(c.get("expect", 0)),
                    "timeout": c.get("timeout")
                })
        elif isinstance(ltc.get("steps"), list) and ltc["steps"]:
            for s in ltc["steps"]:
                norm_cases.append({
                    "name": s.get("name") or s.get("run") or "step",
                    "run": s.get("run"),
                    "cwd": s.get("cwd"),
                    "expect": int(s.get("expect_exit", 0)),
                    "timeout": s.get("timeout")
                })
        elif ltc.get("run"):
            norm_cases.append({
                "name": "default",
                "run": ltc.get("run"),
                "cwd": ltc.get("cwd"),
                "expect": int(ltc.get("expect", 0)),
                "timeout": ltc.get("timeout")
            })
        log.info("run_profile norm_cases=%s", norm_cases)

        out_cases: List[EvalCase] = []
        for c in norm_cases:
            cmd = c.get("run")
            if not cmd:
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=997,
                    stdout="", stderr="missing 'run'",
                    cmd=None, cwd=str(self.project_root if not c.get("cwd") else self.project_root / c["cwd"]),
                    expect=c.get("expect")))
                continue

            workdir = self.project_root / c.get("cwd") if c.get("cwd") else self.project_root
            timeout = c.get("timeout")  # può essere None
            try:
                p = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                log.info("run_profile p=%s", p)
                ok = (p.returncode == c.get("expect", 0))
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=ok,
                    code=p.returncode,
                    stdout=(p.stdout or "")[-4000:],   # tail safety
                    stderr=(p.stderr or "")[-4000:],
                    cmd=cmd,
                    cwd=str(workdir),
                    expect=c.get("expect", 0)
                ))
                log.info("run_profile ok=%s", ok)
            except subprocess.TimeoutExpired as e:
                log.error("timeout expired: %s", e)
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=998,
                    stdout=(e.stdout or ""),
                    stderr=f"timeout: {e}",
                    cmd=cmd, cwd=str(workdir), expect=c.get("expect", 0)
                ))
            except Exception as e:
                log.error("exception: %s", e)
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=999,
                    stdout="",
                    stderr=str(e),
                    cmd=cmd, cwd=str(workdir), expect=c.get("expect", 0)
                ))
        log.info("run_profile out_cases=%s", out_cases)
        
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