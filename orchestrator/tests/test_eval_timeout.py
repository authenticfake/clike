"""A check that hangs is stopped with its whole process group and the report says where it hung."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

from eval_runner import EvalRunner  # noqa: E402


class EvalTimeoutTests(unittest.TestCase):
    def test_hanging_pytest_test_is_named_and_its_processes_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_hang.py").write_text(
                "import time\n\ndef test_fast():\n    assert True\n\ndef test_hangs():\n    time.sleep(60)\n"
            )
            marker = root / "child.pid"
            cmd = (
                f"{sys.executable} -c \"import os,time; open('{marker}','w').write(str(os.getpid())); time.sleep(60)\" & "
                f"{sys.executable} -m pytest -q -p no:cacheprovider test_hang.py"
            )
            started = time.time()
            case = EvalRunner(root)._run(name="tests", cmd=cmd, cwd=root, timeout=10)

            self.assertLess(time.time() - started, 30)
            self.assertFalse(case.passed)
            self.assertEqual(case.code, 998)
            self.assertIn("test_hangs", case.stderr)
            self.assertIn("timeout: the check was stopped after 10 s", case.stderr)
            self.assertNotIn("b'", case.stdout)
            # The id of the running test is the last thing printed before the hang.
            self.assertTrue(case.stdout.rstrip().endswith("test_hang.py::test_hangs"), case.stdout[-300:])

            pid = int(marker.read_text())
            time.sleep(0.5)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class EvalWritablePathsTests(unittest.TestCase):
    def test_coverage_data_file_goes_to_the_eval_dir(self):
        # The project root is read-only in the sandbox; coverage.py writes .coverage in the cwd.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs" / "kit" / "REQ-001" / "ci").mkdir(parents=True)
            (root / "runs" / "kit" / "REQ-001" / "src").mkdir()
            ltc = {"req_id": "REQ-001", "checks": [{"id": "env", "command": f"{sys.executable} -c \"import os; print(os.environ['COVERAGE_FILE'])\""}]}
            profile = root / "runs" / "kit" / "REQ-001" / "ci" / "LTC.json"
            profile.write_text(__import__("json").dumps(ltc))
            report = EvalRunner(root).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001")
            case = next(c for c in report.cases if c.name == "env")
            self.assertTrue(case.passed, case.stderr)
            self.assertIn(str(Path("runs") / "eval" / "REQ-001" / ".coverage"), case.stdout)


if __name__ == "__main__":
    unittest.main()


class EvalCancellationTests(unittest.TestCase):
    def test_a_cancelled_eval_stops_the_running_check_and_the_remaining_ones(self):
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001"
            (kit / "ci").mkdir(parents=True)
            (kit / "src").mkdir()
            marker = root / "child.pid"
            ltc = {"req_id": "REQ-001", "checks": [
                {"id": "slow", "command": f"{sys.executable} -c \"import os,time; open('{marker}','w').write(str(os.getpid())); time.sleep(60)\"", "timeout": 120},
                {"id": "never", "command": "true"},
            ]}
            profile = kit / "ci" / "LTC.json"
            profile.write_text(__import__("json").dumps(ltc))
            cancel = threading.Event()
            threading.Timer(3.0, cancel.set).start()
            started = time.time()
            report = EvalRunner(root, cancel_event=cancel).run_profile(profile=str(profile), ltc=ltc, req_id="REQ-001")

            self.assertLess(time.time() - started, 20)
            names = [c.name for c in report.cases]
            self.assertIn("slow", names)
            self.assertNotIn("never", names)
            self.assertIn("eval::cancelled", names)
            self.assertIn("cancelled", next(c for c in report.cases if c.name == "slow").stderr)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(marker.read_text()), 0)
