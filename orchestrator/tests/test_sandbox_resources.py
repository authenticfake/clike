"""An eval sandbox out of processes/memory: recognised, never sent to a repair, refused up front."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import sandbox_resources  # noqa: E402
from eval_runner import EvalRunner  # noqa: E402

from tests.test_eval_regression import _RegressionProject  # noqa: E402


class ExhaustionMarkersTests(unittest.TestCase):
    def test_os_refusals_are_recognised(self):
        for text in (
            "Error: spawn /usr/bin/node EAGAIN\n    at ChildProcess._handle.onexit",
            "Error: spawnSync /bin/sh EAGAIN",
            "[pid=12][err] [0101/000000.000:FATAL:platform_thread_posix.cc(155)] pthread_create: Resource temporarily unavailable (11)",
            "bash: fork: retry: Resource temporarily unavailable",
            "OSError: [Errno 12] Cannot allocate memory",
            "Error: ENOSPC: no space left on device, write",
            "Error: EMFILE: too many open files, open 'x'",
        ):
            self.assertTrue(sandbox_resources.exhaustion(text), text)
        line = sandbox_resources.exhaustion("ok\nError: spawn /usr/bin/node EAGAIN\nmore")
        self.assertEqual(line, "Error: spawn /usr/bin/node EAGAIN")

    def test_code_failures_are_not(self):
        for text in (
            "AssertionError: expected 1 to equal 2",
            "Error: Timed out 5000ms waiting for expect(locator).toBeVisible()",
            "Error: Process from config.webServer exited early.",
            "read EAGAIN on socket",  # an application-level EAGAIN, not a spawn
        ):
            self.assertIsNone(sandbox_resources.exhaustion(text), text)


class PreflightTests(unittest.TestCase):
    def _fake(self, root, current, limit, zombies):
        cg = root / "cg"
        cg.mkdir()
        (cg / "pids.current").write_text(f"{current}\n")
        (cg / "pids.max").write_text(f"{limit}\n")
        proc = root / "proc"
        (proc / "1").mkdir(parents=True)
        (proc / "1" / "comm").write_text("uvicorn\n")
        (proc / "1" / "stat").write_text("1 (uvicorn) S 0 1 1")
        for pid in range(2, 2 + zombies):
            (proc / str(pid)).mkdir()
            (proc / str(pid) / "stat").write_text(f"{pid} (node (x)) Z 1 1 1")
        return cg, proc

    def test_near_the_process_limit_the_eval_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cg, proc = self._fake(Path(tmp), 998, 1024, 3)
            reason = sandbox_resources.preflight(cg, proc)
            self.assertIn("998 of its 1024 processes", reason)
            self.assertIn("3 zombies", reason)
            self.assertIn("PID 1 is uvicorn", reason)
            self.assertEqual(sandbox_resources.snapshot(cg, proc)["zombies"], 3)

    def test_a_healthy_or_unknown_sandbox_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cg, proc = self._fake(Path(tmp), 40, 1024, 0)
            self.assertIsNone(sandbox_resources.preflight(cg, proc))
            self.assertIsNone(sandbox_resources.preflight(Path(tmp) / "none", proc))


class RunnerTests(unittest.TestCase):
    def test_an_exhausted_check_is_environment_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cmd = f"{sys.executable} -c \"import sys; print('FAIL e2e'); sys.stderr.write('Error: spawn /usr/bin/node EAGAIN\\\\n'); sys.exit(1)\""
            case = EvalRunner(root)._run(name="test:e2e", cmd=cmd, cwd=root, timeout=30)
            self.assertFalse(case.passed)
            self.assertTrue(case.blocked)
            self.assertIn("Sandbox resources exhausted (Error: spawn /usr/bin/node EAGAIN)", case.stderr)
            self.assertIn("podman restart", case.stderr)

    @unittest.skipIf(os.name == "nt", "process groups are POSIX")
    def test_what_a_check_leaves_running_is_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "child.pid"
            # A background server whose output does not hold the check's pipes.
            cmd = (
                f"{sys.executable} -c \"import os,time; open('{marker}','w').write(str(os.getpid())); time.sleep(60)\""
                " >/dev/null 2>&1 & sleep 1; echo done"
            )
            case = EvalRunner(root)._run(name="unit", cmd=cmd, cwd=root, timeout=30)
            self.assertTrue(case.passed, case.stderr)
            pid = int(marker.read_text())
            time.sleep(0.5)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class SandboxExhaustedGateTests(_RegressionProject):
    def test_preflight_blocks_eval_and_gate_without_a_code_verdict(self):
        reason = "The eval sandbox already uses 998 of its 1024 processes."
        with patch("sandbox_resources.preflight", return_value=reason):
            evaluated = self._post("/v1/eval/run", "REQ-002").json()
            gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        self.assertEqual(evaluated["reason_code"], "EVAL_SANDBOX_EXHAUSTED")
        self.assertTrue(evaluated["sandbox_exhausted"])
        self.assertEqual(evaluated["environment_blocked"], ["env::sandbox-resources"])
        self.assertEqual(gate["gate"], "FAIL")
        self.assertEqual(gate["reason_code"], "GATE_BLOCKED_SANDBOX_EXHAUSTED")
        self.assertTrue(gate["sandbox_exhausted"])

    def test_an_exhausted_regression_check_marks_the_gate(self):
        kit = self.proj / "runs" / "kit" / "REQ-001"
        (kit / "test" / "test_pricing.py").write_text(
            "import sys\nsys.stderr.write('pthread_create: Resource temporarily unavailable (11)\\n')\nsys.exit(1)\n"
        )
        gate = self._post("/v1/gate/check", "REQ-002", regression=True).json()
        self.assertEqual(gate["reason_code"], "GATE_BLOCKED_SANDBOX_EXHAUSTED", gate)


if __name__ == "__main__":
    unittest.main()
