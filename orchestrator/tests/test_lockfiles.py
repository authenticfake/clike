"""Lockfiles resolved in the eval sandbox for a local agent with no network (services/lockfiles.py)."""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import lockfiles  # noqa: E402


def _fake_tool(bin_dir: Path, name: str, script: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class ResolveLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.proj = root / "proj"
        self.kit = self.proj / "runs" / "kit" / "REQ-001" / "src"
        self.kit.mkdir(parents=True)
        (self.kit / "pyproject.toml").write_text('[project]\nname = "app"\nversion = "0.1.0"\n')
        (self.kit / "node_modules").mkdir()
        (self.kit / "node_modules" / "big.js").write_text("x" * 1000)
        self.bin = root / "bin"
        self.bin.mkdir()
        self.base = root / "evalbase"
        self._env = patch.dict(os.environ, {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "CLIKE_EVAL_BASE_DIR": str(self.base)})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_uv_lock_is_resolved_and_returned_without_touching_the_kit(self):
        # lead-generation REQ-001: the agent spent four eval-check runs smuggling uv.lock out of a check
        _fake_tool(self.bin, "uv", '[ "$1" = lock ] && [ ! -d node_modules ] && printf "version = 1\\n[[package]]\\nname = \\"app\\"\\n" > uv.lock\n')
        result = lockfiles.resolve_lock(self.proj, "runs/kit/REQ-001/src/pyproject.toml")
        self.assertEqual(result["status"], "OK", result)
        self.assertEqual(result["lockfile"], "runs/kit/REQ-001/src/uv.lock")
        self.assertIn('name = "app"', result["content"])
        self.assertFalse((self.kit / "uv.lock").exists())  # the extension writes it, the sandbox never does
        self.assertEqual(list(self.base.iterdir()), [])  # scratch removed

    def test_package_json_uses_npm_lock_only_without_scripts(self):
        (self.kit / "package.json").write_text('{"name": "web", "version": "1.0.0"}')
        _fake_tool(self.bin, "npm", 'echo "$@" > args.txt; [ "$1 $2" = "install --package-lock-only" ] && echo "$@" | grep -q -- --ignore-scripts && echo \'{"lockfileVersion": 3}\' > package-lock.json\n')
        result = lockfiles.resolve_lock(self.proj, "runs/kit/REQ-001/src/package.json")
        self.assertEqual(result["status"], "OK", result)
        self.assertEqual(result["lockfile"], "runs/kit/REQ-001/src/package-lock.json")
        self.assertIn("lockfileVersion", result["content"])

    def test_only_kit_manifests_of_known_types(self):
        (self.proj / "pyproject.toml").write_text("[project]\nname='x'\n")
        cases = {
            "pyproject.toml": "inside the REQ's KIT",
            "runs/kit/REQ-001/src/setup.py": "unsupported manifest",
            "runs/kit/REQ-001/../../../pyproject.toml": "unsafe manifest path",
            "runs/kit/REQ-001/src/missing/pyproject.toml": "manifest not found",
        }
        for manifest, message in cases.items():
            result = lockfiles.resolve_lock(self.proj, manifest)
            self.assertEqual(result["status"], "FAIL", manifest)
            self.assertIn(message, result["error"], manifest)

    def test_a_failing_resolver_returns_its_output(self):
        _fake_tool(self.bin, "uv", 'echo "No solution found: app depends on missing-pkg" >&2; exit 1\n')
        result = lockfiles.resolve_lock(self.proj, "runs/kit/REQ-001/src/pyproject.toml")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("exited 1", result["error"])
        self.assertIn("No solution found", result["log"])

    def test_no_credentials_reach_the_package_manager(self):
        _fake_tool(self.bin, "uv", 'env > env.txt; printf "version = 1\\n" > uv.lock; cat env.txt > uv.lock\n')
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-secret", "CLIKE_API_TOKEN": "tok"}):
            result = lockfiles.resolve_lock(self.proj, "runs/kit/REQ-001/src/pyproject.toml")
        self.assertEqual(result["status"], "OK", result)
        self.assertNotIn("sk-secret", result["content"])
        self.assertNotIn("CLIKE_API_TOKEN", result["content"])


class EvalLockRouteTests(unittest.TestCase):
    def test_the_route_resolves_in_process_and_refuses_projects_outside_the_roots(self):
        from tests.test_eval_regression import AUTH, TOKEN
        from starlette.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp).resolve() / "projects"
            kit = projects / "app" / "runs" / "kit" / "REQ-002" / "src"
            kit.mkdir(parents=True)
            (kit / "pyproject.toml").write_text('[project]\nname = "app"\n')
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            _fake_tool(bin_dir, "uv", 'printf "version = 1\\n" > uv.lock\n')
            env = {"CLIKE_API_TOKEN": TOKEN, "DEV_FOLDER": str(projects), "CLIKE_STATE_DIR": str(Path(tmp) / "state"),
                   "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "CLIKE_EVAL_BASE_DIR": str(Path(tmp) / "base")}
            with patch.dict(os.environ, env):
                os.environ.pop("CLIKE_EVAL_SANDBOX_URL", None)
                from app import app

                client = TestClient(app, base_url="http://127.0.0.1:8080")
                ok = client.post("/v1/eval/lock", headers=AUTH, json={
                    "project_root": str(projects / "app"), "manifest": "runs/kit/REQ-002/src/pyproject.toml"}).json()
                self.assertEqual((ok["status"], ok["lockfile"]), ("OK", "runs/kit/REQ-002/src/uv.lock"), ok)
                outside = client.post("/v1/eval/lock", headers=AUTH, json={
                    "project_root": tmp, "manifest": "runs/kit/REQ-002/src/pyproject.toml"})
                self.assertIn(outside.status_code, (400, 403))
                self.assertEqual(client.post("/v1/eval/lock", json={"project_root": str(projects / "app"), "manifest": "x"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
