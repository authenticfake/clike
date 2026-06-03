import tempfile
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.companion_collector import (
    CompanionArtifactCollector,
    companion_core_blob_key,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class BmadCompanionCollectorTests(unittest.TestCase):
    def test_discovers_project_ux_and_req_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs/harper/bmad/idea/BRIEF.md", "# Brief\nIdea context.")
            _write(root / "docs/harper/bmad/idea/DEEP_DIVE_X.md", "# Deep Dive\nCustom notes.")
            _write(root / "docs/harper/ux/DESIGN.md", "# Design\nUX context.")
            _write(root / "runs/kit/REQ-001/docs/BMAD_DEV_STORY.md", "# Dev Story\nREQ context.")

            artifacts = CompanionArtifactCollector(
                workspace_root=root,
                doc_root=root / "docs/harper",
                phase="kit",
                methodology_context={"methodology": "bmad"},
                req_id="REQ-001",
            ).collect()

            paths = {item["path"] for item in artifacts}
            self.assertIn("docs/harper/bmad/idea/BRIEF.md", paths)
            self.assertIn("docs/harper/bmad/idea/DEEP_DIVE_X.md", paths)
            self.assertIn("docs/harper/ux/DESIGN.md", paths)
            self.assertIn("runs/kit/REQ-001/docs/BMAD_DEV_STORY.md", paths)
            groups = {item["path"]: item["source_group"] for item in artifacts}
            self.assertEqual(groups["docs/harper/bmad/idea/BRIEF.md"], "bmad_project")
            self.assertEqual(groups["docs/harper/ux/DESIGN.md"], "ux")
            self.assertEqual(groups["runs/kit/REQ-001/docs/BMAD_DEV_STORY.md"], "req_docs")

    def test_ignores_unsafe_disallowed_and_binary_files(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            root = Path(tmp)
            external_file = Path(external) / "SECRET.md"
            _write(external_file, "external")
            _write(root / "docs/harper/bmad/idea/BRIEF.md", "allowed")
            _write(root / "docs/harper/bmad/idea/ignored.py", "not allowed")
            binary_path = root / "docs/harper/bmad/idea/binary.md"
            binary_path.parent.mkdir(parents=True, exist_ok=True)
            binary_path.write_bytes(b"abc\x00def")
            symlink_path = root / "docs/harper/bmad/idea/EXTERNAL.md"
            try:
                symlink_path.symlink_to(external_file)
            except OSError:
                pass

            artifacts = CompanionArtifactCollector(
                workspace_root=root,
                doc_root=root / "docs/harper",
                phase="spec",
                methodology_context={"methodology": "bmad"},
            ).collect()

            paths = {item["path"] for item in artifacts}
            self.assertEqual(paths, {"docs/harper/bmad/idea/BRIEF.md"})

    def test_alternate_doc_root_does_not_expand_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs/harper/bmad/idea/BRIEF.md", "allowed")
            _write(root / "otherdocs/bmad/SECRET.md", "not allowed")

            artifacts = CompanionArtifactCollector(
                workspace_root=root,
                doc_root=root / "otherdocs",
                phase="idea",
                methodology_context={"methodology": "bmad"},
            ).collect()

            paths = {item["path"] for item in artifacts}
            self.assertEqual(paths, {"docs/harper/bmad/idea/BRIEF.md"})

    def test_applies_file_count_and_truncation_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "docs/harper/bmad/idea/A.md", "A" * 100)
            _write(root / "docs/harper/bmad/idea/B.md", "B" * 100)

            artifacts = CompanionArtifactCollector(
                workspace_root=root,
                doc_root=root / "docs/harper",
                phase="idea",
                methodology_context={"methodology": "bmad"},
                max_file_count=1,
                max_bytes_per_file=10,
                max_total_snippet_chars=10,
            ).collect()

            self.assertEqual(len(artifacts), 1)
            self.assertEqual(len(artifacts[0]["snippet"]), 10)
            self.assertIs(artifacts[0]["truncated"], True)

    def test_stable_core_blob_key(self):
        self.assertEqual(
            companion_core_blob_key("docs/harper/bmad/idea/BRIEF.md"),
            "companion::docs/harper/bmad/idea/BRIEF.md",
        )


if __name__ == "__main__":
    unittest.main()
