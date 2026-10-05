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


if __name__ == "__main__":
    unittest.main()
