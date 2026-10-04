"""Telemetry retention (WP7): opt-in, age based, confined, throttled."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import telemetry_retention as tr

DAY = 86400


class TelemetryRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-telemetry-")).resolve()
        self.root = self.tmp / "telemetry"
        self.old = self._file("prompt_debug/old.json", age_days=40)
        self.new = self._file("project.json", age_days=1)
        self.outside = self._file("../outside.json", age_days=400)
        tr._last_run = 0.0

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, rel, age_days):
        path = (self.root / rel).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
        t = time.time() - age_days * DAY
        os.utime(path, (t, t))
        return path

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tr.maybe_prune(self.root), 0)
        self.assertTrue(self.old.exists())

    def test_prunes_only_old_files_inside_the_root(self):
        os.symlink(self.outside, self.root / "link.json")
        os.utime(self.root / "link.json", follow_symlinks=False, times=(0, 0))
        with patch.dict(os.environ, {"CLIKE_TELEMETRY_RETENTION_DAYS": "30"}):
            self.assertEqual(tr.maybe_prune(self.root), 1)
        self.assertFalse(self.old.exists())
        self.assertFalse(self.old.parent.exists())  # emptied directory removed
        self.assertTrue(self.new.exists())
        self.assertTrue(self.outside.exists())
        self.assertTrue((self.root / "link.json").is_symlink())
        self.assertTrue(self.root.is_dir())

    def test_throttled(self):
        with patch.dict(os.environ, {"CLIKE_TELEMETRY_RETENTION_DAYS": "30"}):
            tr.maybe_prune(self.root)
            self._file("again/old.json", age_days=40)
            self.assertEqual(tr.maybe_prune(self.root), 0)

    def test_invalid_value_disables(self):
        with patch.dict(os.environ, {"CLIKE_TELEMETRY_RETENTION_DAYS": "a month"}):
            self.assertEqual(tr.maybe_prune(self.root), 0)
        self.assertTrue(self.old.exists())


if __name__ == "__main__":
    unittest.main()
