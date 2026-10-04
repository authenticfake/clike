"""Gateway telemetry path confinement (WP4)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "h" * 48


class TelemetryPathTests(unittest.TestCase):
    def test_identifiers_cannot_escape_the_telemetry_dir(self):
        from routes import harper

        with tempfile.TemporaryDirectory() as tmp, patch.object(harper, "TELEMETRY_DIR", tmp):
            root = Path(tmp).resolve()
            for pid, run_id, phase in [
                ("../../etc/cron.d/x", "../y", "../../z"),
                ("/abs/path", "run", "spec"),
                ("..", "..", ".."),
            ]:
                with self.subTest(pid):
                    self.assertTrue(harper._telemetry_path(pid).resolve().is_relative_to(root))
                    self.assertTrue(harper._prompt_debug_path(pid, run_id, phase).resolve().is_relative_to(root))
            # normal ids keep their historical file names
            self.assertEqual(harper._telemetry_path("coffebuddy_bmad").name, "coffebuddy_bmad.json")
            self.assertEqual(
                harper._prompt_debug_path("mvp_digital_twin", "155d4259fd412819ed73e3095", "kit").name,
                "mvp_digital_twin__155d4259fd412819ed73e3095__kit.json",
            )


class TelemetryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-tel-")).resolve()
        (cls.tmp / "tel").mkdir()
        (cls.tmp / "tel2").mkdir()
        (cls.tmp / "tel2" / "leak.json").write_text('{"secret": 1}\n')
        cls._env = patch.dict(
            os.environ,
            {
                "CLIKE_API_TOKEN": TOKEN,
                "MODELS_CONFIG": str(REPO_ROOT / "configs/models.yaml"),
                "HARPER_TELEMETRY_DIR": str(cls.tmp / "tel"),
            },
        )
        cls._env.start()
        from app import app
        from routes import telemetry_api

        cls._patch = patch.object(telemetry_api, "TELEMETRY_DIR", cls.tmp / "tel")
        cls._patch.start()
        cls.client = TestClient(app, base_url="http://127.0.0.1:8000")

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()
        cls._env.stop()

    def test_relpath_traversal_and_sibling_prefix_are_rejected(self):
        auth = {"Authorization": f"Bearer {TOKEN}"}
        for rel in ["../tel2/leak.json", "/etc/passwd", "..%2Ftel2%2Fleak.json"]:
            with self.subTest(rel):
                r = self.client.get("/v1/metrics/harper/raw_file", params={"relpath": rel}, headers=auth)
                self.assertIn(r.status_code, (400, 404))
                self.assertNotIn("secret", r.text)

    def test_project_id_traversal_reads_nothing_outside(self):
        auth = {"Authorization": f"Bearer {TOKEN}"}
        r = self.client.get("/v1/metrics/harper/raw", params={"project_id": "../tel2/leak"}, headers=auth)
        self.assertNotIn("secret", r.text)


if __name__ == "__main__":
    unittest.main()
