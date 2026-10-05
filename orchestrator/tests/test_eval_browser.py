"""A Playwright check failing for a missing browser downloads it in the project's version and re-runs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

from eval_runner import EvalCase, EvalRunner  # noqa: E402

MISSING = "browserType.launch: Executable doesn't exist at /tmp/.cache/ms-playwright/chromium_headless_shell-1161/x"


class MissingBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        core = self.root / "ci" / "node_modules" / "playwright-core"
        core.mkdir(parents=True)
        (core / "package.json").write_text(json.dumps({"name": "playwright-core", "version": "1.51.1"}))
        self.runner = EvalRunner(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _recover(self, failed, runs):
        calls = []

        def fake_run(**kwargs):
            calls.append(kwargs["cmd"])
            return runs.pop(0)

        with patch.object(self.runner, "_run", side_effect=fake_run):
            result = self.runner._recover_missing_browser(
                result=failed, cmd="npm test", cwd=self.root / "ci", env={}, work_kit_root=self.root,
                timeout=60, blocking=True)
        return result, calls

    def test_downloads_the_projects_chromium_and_reruns(self):
        failed = EvalCase(name="browser", passed=False, code=1, stdout="", stderr=MISSING, expect=0)
        ok = EvalCase(name="x", passed=True, code=0, stdout="", stderr="")
        result, calls = self._recover(failed, [ok, EvalCase(name="browser", passed=True, code=0, stdout="", stderr="")])
        self.assertEqual(calls, ["npx --yes playwright@1.51.1 install chromium", "npm test"])
        self.assertTrue(result.passed)
        self.assertIn("Chromium downloaded", result.stderr)

    def test_other_failures_are_untouched(self):
        failed = EvalCase(name="unit", passed=False, code=1, stdout="1 failed", stderr="")
        result, calls = self._recover(failed, [])
        self.assertEqual(calls, [])
        self.assertIs(result, failed)

    def test_failed_download_is_reported(self):
        failed = EvalCase(name="browser", passed=False, code=1, stdout="", stderr=MISSING)
        bad = EvalCase(name="x", passed=False, code=1, stdout="", stderr="network unreachable")
        result, calls = self._recover(failed, [bad])
        self.assertFalse(result.passed)
        self.assertIn("browser download failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
