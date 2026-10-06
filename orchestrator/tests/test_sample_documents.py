"""The sample IDEA/SPEC documents shipped in the repository pass the same validation as the
product (B14): examples must follow the rules they illustrate."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "orchestrator"))

from services.cloud_prompt.canonical_validation import validate_current_canonical_core_blobs  # noqa: E402

SAMPLES = [
    "CoffeeBuddy/IDEA.md", "CoffeeBuddy/SPEC.md", "CoffeeBuddy/aws/IDEA.md", "CoffeeBuddy/aws/SPEC.md",
    "docs/IDEAs/CoffeeBuddy/IDEA.md", "docs/IDEAs/CoffeeBuddy/SPEC.md",
    "benchmark/projects/pingboard/IDEA.md", "benchmark/projects/shortlink/IDEA.md",
]


class SampleDocumentTests(unittest.TestCase):
    def test_samples_are_canonical(self):
        for rel in SAMPLES:
            with self.subTest(rel):
                name = "docs/harper/" + Path(rel).name
                result = validate_current_canonical_core_blobs({name: (ROOT / rel).read_text(encoding="utf-8")})
                self.assertEqual(result.get("invalid_canonical") or [], [], rel)


if __name__ == "__main__":
    unittest.main()
