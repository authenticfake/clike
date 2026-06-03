import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOTS = [
    REPO_ROOT / "orchestrator",
    REPO_ROOT / "gateway",
    REPO_ROOT / "extensions" / "vscode",
]
SOURCE_SUFFIXES = {".py", ".js"}
EXCLUDED_PARTS = {"tests", "test", "docs", "methodologies"}


def _runtime_sources():
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            yield path, path.read_text(encoding="utf-8", errors="ignore")


class BmadSafetyBoundaryTests(unittest.TestCase):
    def test_no_bmad_runtime_cli_or_subprocess_call_exists(self):
        ref = "b" + "mad"
        method = "method"
        forbidden_patterns = [
            rf"npx\s+{ref}-{method}",
            rf"{ref}-{method}",
            rf"subprocess[^\n]*{ref}",
            rf"{ref}[^\n]*subprocess",
            rf"child_process[^\n]*{ref}",
            rf"\bspawn\([^\n]*{ref}",
            rf"\bexec\([^\n]*{ref}",
            rf"\bPopen\([^\n]*{ref}",
        ]

        for path, source in _runtime_sources():
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                for pattern in forbidden_patterns:
                    self.assertIsNone(re.search(pattern, source, flags=re.IGNORECASE), pattern)

    def test_bmad_does_not_reuse_profile_hint_or_local_agent_executor_identity(self):
        ref = "b" + "mad"
        forbidden_patterns = [
            rf"{ref}[^\n]*profileHint",
            rf"profileHint[^\n]*{ref}",
            rf"{ref}[^\n]*localAgentExecutor",
            rf"localAgentExecutor[^\n]*{ref}",
        ]

        for path, source in _runtime_sources():
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                for pattern in forbidden_patterns:
                    self.assertIsNone(re.search(pattern, source, flags=re.IGNORECASE), pattern)

    def test_orchestrator_mcp_surface_remains_read_only(self):
        source = (REPO_ROOT / "orchestrator" / "mcp_server.py").read_text(encoding="utf-8")

        self.assertIn("Read-only MCP server for CLike", source)
        self.assertIn("No phase execution, no git mutation, no arbitrary shell or filesystem writes.", source)
        self.assertIn("# MCP tools (read-only / contract-first)", source)
        self.assertIn('"arbitrary filesystem write"', source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_file(", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
