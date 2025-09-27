# orchestrator/app/eval_runner.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess, json, time, shlex
from capabilities.engine import CapabilityEngine

@dataclass
class EvalCase:
    name: str
    passed: bool
    stdout: str = ""
    stderr: str = ""

@dataclass
class EvalReport:
    profile: str
    passed: int
    failed: int
    cases: list[EvalCase]
    junit_path: str
    json_path: str

class EvalRunner:
    """Phase-aware evaluation runner."""
    def __init__(self, project_root: Path):
        self.root = project_root
        self.engine = CapabilityEngine(project_root)

    def _run_local(self, cmd: str) -> EvalCase:
        proc = subprocess.Popen(shlex.split(cmd), cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate()
        return EvalCase(name=cmd, passed=(proc.returncode == 0), stdout=out, stderr=err)

    def run_profile(self, profile: str) -> EvalReport:
        ts = time.strftime("%Y%m%d-%H%M%S")
        outdir = self.root / "runs" / ts / "eval"
        outdir.mkdir(parents=True, exist_ok=True)
        cases: list[EvalCase] = []

        if profile == "spec":
            cases.append(self._run_local("python -m orchestrator.app.spec_plan_gates check-spec --file SPEC.md"))
        elif profile == "plan":
            cases.append(self._run_local("python -m orchestrator.app.spec_plan_gates check-plan --file PLAN.md"))
        else:
            for cap in self.engine.resolve_profile(profile):
                code, out, err = self.engine.run_cmd(cap)
                cases.append(EvalCase(name=f"{cap.name}: {cap.cmd}", passed=(code == 0), stdout=out, stderr=err))

        passed = sum(1 for c in cases if c.passed)
        failed = len(cases) - passed
        junit_path = str(outdir / f"{profile}.junit.xml")
        json_path  = str(outdir / f"{profile}.report.json")
        self._write_junit(junit_path, profile, cases)
        with open(json_path, "w", encoding="utf8") as f:
            json.dump({
                "profile": profile, "passed": passed, "failed": failed,
                "cases": [{"name": c.name, "passed": c.passed, "stdout": c.stdout[-8000:], "stderr": c.stderr[-8000:]} for c in cases]
            }, f, ensure_ascii=False, indent=2)
        return EvalReport(profile, passed, failed, cases, junit_path, json_path)

    def _write_junit(self, path: str, profile: str, cases: list[EvalCase]) -> None:
        from xml.sax.saxutils import escape
        with open(path, "w", encoding="utf8") as f:
            f.write(f'<testsuite name="{escape(profile)}" tests="{len(cases)}">\n')
            for c in cases:
                status = "" if c.passed else f'<failure message="failed">{escape((c.stderr or c.stdout)[-1000:])}</failure>'
                f.write(f'  <testcase name="{escape(c.name)}">{status}</testcase>\n')
            f.write("</testsuite>\n")
