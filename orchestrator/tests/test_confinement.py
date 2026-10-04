"""File/exec confinement regression suite (WP4)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from starlette.testclient import TestClient  # noqa: E402

from utils.safe_paths import (  # noqa: E402
    UnsafePathError,
    is_within,
    resolve_within,
    safe_segment,
    validate_req_id,
)

TOKEN = "c" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class SafePathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="clike-safe-")).resolve()
        (self.tmp / "root").mkdir()
        (self.tmp / "root2").mkdir()
        self.root = self.tmp / "root"

    def test_relative_inside_is_resolved(self):
        self.assertEqual(resolve_within(self.root, "a/b.txt"), self.root / "a/b.txt")

    def test_traversal_and_absolute_are_rejected(self):
        for bad in ["../x", "a/../../x", "/etc/passwd", "C:\\x", "C:/x", "\\\\server\\share", "", "  ", "a\x00b"]:
            with self.subTest(repr(bad)):
                with self.assertRaises(UnsafePathError):
                    resolve_within(self.root, bad)

    def test_backslash_traversal_is_rejected(self):
        with self.assertRaises(UnsafePathError):
            resolve_within(self.root, "..\\..\\x")

    def test_sibling_prefix_is_not_inside(self):
        # the old startswith() check accepted /tmp/root2 as inside /tmp/root
        self.assertFalse(is_within(self.tmp / "root2", self.root))
        with self.assertRaises(UnsafePathError):
            resolve_within(self.root, str(self.tmp / "root2" / "x"), allow_absolute_inside=True)

    def test_absolute_inside_allowed_only_on_request(self):
        target = self.root / "ci" / "LTC.json"
        self.assertEqual(resolve_within(self.root, str(target), allow_absolute_inside=True), target)
        with self.assertRaises(UnsafePathError):
            resolve_within(self.root, str(target))

    def test_symlink_escape_is_rejected(self):
        (self.root / "link").symlink_to(self.tmp / "root2")
        with self.assertRaises(UnsafePathError):
            resolve_within(self.root, "link/x")

    def test_safe_segment(self):
        self.assertEqual(safe_segment("coffebuddy_bmad"), "coffebuddy_bmad")
        self.assertEqual(safe_segment("../../etc"), "_.._etc")
        self.assertEqual(safe_segment(".."), "default")
        self.assertEqual(safe_segment("a/b\\c"), "a_b_c")
        self.assertEqual(safe_segment(None, "n-a"), "n-a")

    def test_req_id(self):
        self.assertEqual(validate_req_id("REQ-001"), "REQ-001")
        for bad in ["REQ-../x", "../REQ-001", "REQ-", "req-001", "REQ-001/x", ""]:
            with self.subTest(bad):
                with self.assertRaises(UnsafePathError):
                    validate_req_id(bad)

    def test_gateway_copy_is_identical(self):
        self.assertEqual(
            (ORCHESTRATOR_ROOT / "utils/safe_paths.py").read_bytes(),
            (REPO_ROOT / "gateway/utils/safe_paths.py").read_bytes(),
        )


class StageArtifactPathTests(unittest.TestCase):
    def test_llm_paths_cannot_escape_the_req_stage_dir(self):
        from services import harper

        with tempfile.TemporaryDirectory() as runs, patch.dict(os.environ, {"RUNS_DIR": runs}):
            ok = harper._stage_artifact_path("REQ-001", "src/app.py")
            self.assertTrue(is_within(ok, Path(runs) / "kit" / "REQ-001"))
            for req_id, rel in [("REQ-001", "../../../etc/x"), ("REQ-001", "/etc/x"), ("../x", "a.py")]:
                with self.subTest((req_id, rel)):
                    with self.assertRaises(UnsafePathError):
                        harper._stage_artifact_path(req_id, rel)
            # the writer swallows the error and writes nothing
            self.assertIsNone(harper._write_stage_artifact("REQ-001", "../../escape.txt", "x"))
            self.assertFalse((Path(runs) / "escape.txt").exists())


class McpSafeChildTests(unittest.TestCase):
    def test_safe_child(self):
        import mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            self.assertEqual(mcp_server._safe_child(base, "/docs/x.md"), base / "docs/x.md")
            with self.assertRaises(ValueError):
                mcp_server._safe_child(base, "../../etc/passwd")


class EvalEnvironmentTests(unittest.TestCase):
    def test_secrets_are_not_passed_to_eval_commands(self):
        from eval_runner import EvalRunner, scrubbed_process_env

        secrets = {
            "OPENAI_API_KEY": "sk-x",
            "ANTHROPIC_API_KEY": "sk-y",
            "CLIKE_API_TOKEN": "t",
            "AWS_SECRET_ACCESS_KEY": "a",
            "DB_PASSWORD": "p",
            "KEEP_ME": "ok",
        }
        with patch.dict(os.environ, secrets):
            env = scrubbed_process_env()
            for k in secrets:
                if k != "KEEP_ME":
                    self.assertNotIn(k, env)
            self.assertEqual(env["KEEP_ME"], "ok")
            self.assertIn("PATH", env)
            with tempfile.TemporaryDirectory() as tmp:
                runner = EvalRunner(Path(tmp))
                # implicit env (env=None) and merged env are both scrubbed; LTC-provided vars are kept
                case = runner._run(name="env", cmd="env", cwd=Path(tmp))
                self.assertNotIn("sk-x", case.stdout)
                self.assertNotIn("CLIKE_API_TOKEN", case.stdout)
                merged = runner._merge_env({"LTC_VAR": "1"}, None)
                self.assertEqual(merged["LTC_VAR"], "1")
                self.assertNotIn("OPENAI_API_KEY", merged)


class EvalRouteConfinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clike-eval-")).resolve()
        cls.projects = cls.tmp / "projects"
        cls.proj = cls.projects / "demo"
        (cls.proj / "ci").mkdir(parents=True)
        cls.ltc = {"req_id": "REQ-001", "checks": [{"id": "ok", "command": "true", "blocking": True}]}
        (cls.proj / "ci" / "LTC.json").write_text(json.dumps(cls.ltc))
        (cls.tmp / "outside").mkdir()
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(cls.projects)})
        cls._env.start()
        os.environ.pop("CLIKE_ALLOW_INLINE_LTC", None)
        os.environ.pop("CLIKE_EVAL_ALLOWED_ROOTS", None)
        from app import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8080", raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def _eval(self, body, **params):
        return self.client.post("/v1/eval/run", params=params, json=body, headers=AUTH)

    def test_workspace_ltc_runs(self):
        r = self._eval({"ltc": self.ltc}, profile="ci/LTC.json", project_root=str(self.proj), req_id="REQ-001")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([c["cmd"] for c in r.json()["cases"]][-1], "true")

    def test_workspace_ltc_without_inline_echo_runs(self):
        r = self._eval(None, profile="ci/LTC.json", project_root=str(self.proj))
        self.assertEqual(r.status_code, 200, r.text)

    def test_inline_ltc_that_differs_from_workspace_is_refused(self):
        evil = {"checks": [{"id": "x", "command": "id"}]}
        r = self._eval({"ltc": evil}, profile="ci/LTC.json", project_root=str(self.proj))
        self.assertEqual(r.status_code, 409)

    def test_inline_only_ltc_is_refused_by_default(self):
        r = self._eval({"ltc": {"checks": [{"id": "x", "command": "id"}]}}, profile="ci/NOPE.json", project_root=str(self.proj))
        self.assertEqual(r.status_code, 403)

    def test_project_root_outside_allowed_roots_is_refused(self):
        for root in [str(self.tmp / "outside"), "/", "/tmp", str(REPO_ROOT)]:
            with self.subTest(root):
                r = self._eval({"ltc": self.ltc}, profile="ci/LTC.json", project_root=root)
                self.assertEqual(r.status_code, 403, r.text)

    def test_profile_traversal_is_refused(self):
        r = self._eval(None, profile="../../outside/LTC.json", project_root=str(self.proj))
        self.assertEqual(r.status_code, 400)

    def test_gate_uses_the_same_confinement(self):
        r = self.client.post(
            "/v1/gate/check",
            params={"profile": "ci/LTC.json", "project_root": str(self.tmp / "outside")},
            json={"ltc": self.ltc},
            headers=AUTH,
        )
        self.assertEqual(r.status_code, 403)

    def test_eval_disabled_without_allowed_roots(self):
        with patch.dict(os.environ, {"DEV_FOLDER": ""}):
            r = self._eval({"ltc": self.ltc}, profile="ci/LTC.json", project_root=str(self.proj))
            self.assertEqual(r.status_code, 403)

    def test_apply_endpoint_is_gone(self):
        r = self.client.post("/v1/apply", json={"files": [{"path": "/tmp/x", "content": "x"}]}, headers=AUTH)
        self.assertIn(r.status_code, (404, 405))


if __name__ == "__main__":
    unittest.main()
