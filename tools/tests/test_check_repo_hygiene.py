import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_repo_hygiene import find_violations  # noqa: E402

FAKE_KEY = "sk-proj-" + "A" * 40


def _check(files: dict[str, str]) -> list[str]:
    return find_violations(files.keys(), lambda p: files[p])


class RepoHygieneTests(unittest.TestCase):
    def test_forbidden_paths_are_reported(self):
        for path in [
            "telemetry/clike_raw/x.json",
            "telemetry/project.jsonl",
            "docs/_private/01_assessment.md",
            ".env",
            "gateway/.env",
            "extensions/vscode/node_modules/diff/index.js",
            "extensions/vscode/clike-0.5.3.vsix",
            "gateway/.DS_Store",
            "docker/certs/corp-ca.pem",
            ".venv-orch/bin/python",
            "orchestrator/requirements.txt~clike.bak",
        ]:
            with self.subTest(path):
                self.assertEqual(len(_check({path: ""})), 1)

    def test_allowed_paths_pass(self):
        self.assertEqual(_check({".env.example": "OPENAI_API_KEY=...", "orchestrator/app.py": "print('ok')"}), [])

    def test_secret_in_content_is_reported(self):
        violations = _check({"orchestrator/config.py": f'KEY = "{FAKE_KEY}"'})
        self.assertEqual(len(violations), 1)
        self.assertIn("possible secret", violations[0])

    def test_private_key_is_reported(self):
        self.assertEqual(len(_check({"x.txt": "-----BEGIN PRIVATE KEY-----\nabc"})), 1)

    def test_allowlisted_fixtures_are_not_scanned_for_secrets(self):
        self.assertEqual(_check({"gateway/tests/golden/snapshots/a.json": FAKE_KEY}), [])


if __name__ == "__main__":
    unittest.main()
