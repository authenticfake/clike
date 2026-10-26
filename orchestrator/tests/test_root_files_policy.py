"""Root deliverables of a KIT (mirror of extensions/vscode/root-files-policy.js) and the staging check."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from eval_runner import EvalRunner  # noqa: E402
from services.root_files import is_allowed_root_path, root_policy, staged_root_deliverables  # noqa: E402


class RootPolicyTests(unittest.TestCase):
    def test_same_answers_as_the_extension(self):
        policy = root_policy(None)
        for p in (".env.oidc.example", ".gitignore", "ci/SOLUTION_LTC.json", "docs/LOCAL_LIVE.md", "scripts/a.sh"):
            self.assertTrue(is_allowed_root_path(p, policy), p)
        for p in (".env", ".env.live", "docs/harper/plan.json", "docs/inputs/v3/a.md", "ci/check.py", "src/a.py"):
            self.assertFalse(is_allowed_root_path(p, policy), p)


class StagedRootTests(unittest.TestCase):
    def _project(self, tmp):
        root = Path(tmp)
        kit = root / "runs" / "kit" / "REQ-038"
        (kit / "ci" / "shared" / "scripts").mkdir(parents=True)
        (kit / "ci" / "shared" / "scripts" / "solution_local.py").write_text("live = True\n")
        (kit / "ci" / "shared" / ".env.live.example").write_text("LEADINTEL_PROFILE=\n")
        (kit / "ci" / "regression" / "test").mkdir(parents=True)
        (kit / "ci" / "regression" / "test" / "a.test.ts").write_text("x")
        (kit / "ci" / "check.py").write_text("x")
        (kit / "docs").mkdir()
        (kit / "docs" / "LOCAL_LIVE.md").write_text("# live\n")
        (kit / "ci" / "STAGING_MAP.json").write_text(json.dumps({"shared": {"docs/LOCAL_LIVE.md": "docs/LOCAL_LIVE.md"}}))
        (root / "scripts").mkdir()
        (root / "scripts" / "solution_local.py").write_text("live = False\n")
        return root

    def test_the_eval_blocks_root_deliverables_left_in_a_staging_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = EvalRunner(self._project(tmp))._staged_root_cases("REQ-038")[0]
            self.assertTrue(case.blocking)
            self.assertIn("ci/shared/scripts/solution_local.py → root/scripts/solution_local.py", case.stderr)
            self.assertIn("ci/shared/.env.live.example → root/.env.live.example", case.stderr)
            self.assertIn("Remove the staging map(s): ci/STAGING_MAP.json", case.stderr)
            self.assertNotIn("check.py", case.stderr)
            self.assertNotIn("a.test.ts", case.stderr)

    def test_finalize_gets_what_the_repository_does_not_hold_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            found = {d["repository_path"]: d["state"] for d in staged_root_deliverables(root)}
            self.assertEqual(found, {"scripts/solution_local.py": "differs", ".env.live.example": "missing",
                                     "docs/LOCAL_LIVE.md": "missing"})
            (root / ".env.live.example").write_text("LEADINTEL_PROFILE=\n")
            self.assertNotIn(".env.live.example", {d["repository_path"] for d in staged_root_deliverables(root)})


if __name__ == "__main__":
    unittest.main()
