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
        log.info("run_profile profile_path=%s", profile_path)
        log.info("run_profile now is_absolute profile_path=%s", profile_path.is_absolute())

        if not profile_path.is_absolute():
            profile_path = (self.project_root / profile_path)

        log.info("run_profile now is_absolute profile_path=%s", profile_path)
        log.info("run_profile now is_absolute self.project_root=%s", self.project_root)
                

        if mode.lower() == "manual":
            if verdict not in ("pass", "fail"):
                raise ValueError("manual mode requires verdict in {'pass','fail'}")
            passed = (1 if verdict == "pass" else 0)
            failed = (0 if verdict == "pass" else 1)
            cases = [EvalCase(name=f"manual::{req_id or 'REQ'}", passed=(verdict == "pass"), code=(0 if verdict == "pass" else 1), stdout="", stderr="")]
            rep = EvalReport(profile=str(profile_path), req_id=req_id, mode="manual", passed=passed, failed=failed, cases=cases)
            self._persist_reports(rep)
            return rep
        
        log.info("run_profile profile_path.suffix.lower()=%s", profile_path.suffix.lower())
        log.info("run_profile profile_path.exists()=%s", profile_path.exists())


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
            self._persist_reports(rep)
            return rep



        
        log.info("run_profile ltc=%s", ltc)
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
            except subprocess.TimeoutExpired as e:
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=998,
                    stdout=(e.stdout or ""),
                    stderr=f"timeout: {e}",
                    cmd=cmd, cwd=str(workdir), expect=c.get("expect", 0)
                ))
            except Exception as e:
                out_cases.append(EvalCase(
                    name=c.get("name") or "case",
                    passed=False, code=999,
                    stdout="",
                    stderr=str(e),
                    cmd=cmd, cwd=str(workdir), expect=c.get("expect", 0)
                ))

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
        self._persist_reports(rep)
        return rep

    # --------------------------- persistence (reports) ----------------------
    def _persist_reports(self, rep: EvalReport) -> None:
        out_dir = self.project_root / "runs" / "eval"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())

        # JSON summary
        rep.json_path = str(out_dir / f"report_{ts}.json")
        with open(rep.json_path, "w", encoding="utf-8") as f:
            json.dump({
                "profile": rep.profile,
                "req_id": rep.req_id,
                "mode": rep.mode,
                "passed": rep.passed,
                "failed": rep.failed,
                "cases": [{
                    "name": c.name,
                    "passed": c.passed,
                    "code": c.code,
                    "cmd": c.cmd,
                    "cwd": c.cwd,
                    "expect": c.expect
                } for c in rep.cases],
            }, f, indent=2)

        # JUnit minimal
        rep.junit_path = str(out_dir / f"report_{ts}.junit.xml")
        testsuite = ET.Element("testsuite", name="clike-eval", tests=str(len(rep.cases)), failures=str(rep.failed))
        for c in rep.cases:
            tc = ET.SubElement(testsuite, "testcase", name=c.name)
            if not c.passed:
                fail = ET.SubElement(tc, "failure", message=f"exit={c.code}")
                fail.text = (c.stderr or "").strip()
            if c.stdout:
                sysout = ET.SubElement(tc, "system-out")
                sysout.text = c.stdout
            if c.stderr:
                syserr = ET.SubElement(tc, "system-err")
                syserr.text = c.stderr
        tree = ET.ElementTree(testsuite)
        tree.write(rep.junit_path, encoding="utf-8", xml_declaration=True)
