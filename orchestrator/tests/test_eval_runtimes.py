"""Runtimes an LTC declares beyond the sandbox image (eval_runtimes): Python 3.14 with uv, Node 24."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

import eval_runtimes  # noqa: E402
import eval_tools  # noqa: E402

LTC = {"environment": {"python": "3.14", "node": ">=24"}}


class RuntimeTests(unittest.TestCase):
    def test_only_what_the_image_does_not_satisfy(self):
        self.assertEqual(eval_runtimes.runtime_tools(LTC, python=(3, 12), node=22), ["python3.14", "nodejs24"])
        self.assertEqual(eval_runtimes.runtime_tools({"environment": {"python": ">=3.11", "node": ">=22.14"}},
                                                     python=(3, 12), node=22), [])
        self.assertEqual(eval_runtimes.runtime_tools({"environment": {"python": "3"}}, python=(3, 12), node=22), [])
        self.assertEqual(eval_runtimes.runtime_tools({}, python=(3, 12), node=22), [])

    def test_the_reqs_checks_get_the_runtime_and_a_writable_uv_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            envs = Path(tmp) / "envs"
            (envs / "python3.14" / "bin").mkdir(parents=True)
            (envs / "python3.14" / "bin" / "python3.14").write_text("")
            (envs / "nodejs24" / "bin").mkdir(parents=True)
            with patch.object(eval_runtimes, "image_node_major", return_value=22), \
                    patch.object(eval_runtimes.sys, "version_info", (3, 12, 0)):
                env, python = eval_runtimes.runtime_env({"PATH": "/usr/bin", "UV_PROJECT_ENVIRONMENT": "/opt/venv"},
                                                        LTC, Path(tmp) / "REQ-001-uv", envs_dir=envs)
            self.assertEqual(python, str(envs / "python3.14" / "bin" / "python3.14"))
            self.assertEqual(env["UV_PYTHON"], python)
            self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(Path(tmp) / "REQ-001-uv"))  # never CLike's /opt/venv
            self.assertEqual(env["UV_PYTHON_DOWNLOADS"], "never")
            path = env["PATH"].split(":")
            self.assertEqual(path[:2], [str(envs / "nodejs24" / "bin"), str(envs / "python3.14" / "bin")])

    def test_an_ltc_without_runtimes_only_gets_its_own_uv_environment(self):
        env, python = eval_runtimes.runtime_env({"PATH": "/usr/bin"}, {}, Path("/w/REQ-002-uv"), envs_dir=Path("/none"))
        self.assertIsNone(python)
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], "/w/REQ-002-uv")

    def test_a_declared_runtime_is_installed_without_a_question(self):
        catalog = eval_tools.load_catalog()
        self.assertTrue(catalog["python3.14"]["declared_auto"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "runs" / "kit" / "REQ-001" / "ci"
            kit.mkdir(parents=True)
            (kit / "LTC.json").write_text('{"environment": {"python": "3.14", "node": ">=24"}}')
            with patch.object(eval_runtimes, "image_node_major", return_value=22), \
                    patch.object(eval_runtimes.sys, "version_info", (3, 12, 0)), \
                    patch.object(eval_runtimes, "tools_envs_dir", return_value=root / "no-envs"):
                result = eval_tools.check(root, "REQ-001")
        found = {m["tool"]: m for m in result["missing"]}
        self.assertEqual(set(found), {"python3.14", "nodejs24"})
        self.assertTrue(all(m["approved"] and m["source"] == "declared" for m in found.values()))


if __name__ == "__main__":
    unittest.main()
