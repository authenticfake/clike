"""Safe mechanical lint fixes of generated KIT files (import order, unused imports, whitespace)."""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.kit_format import autofix_kit_files  # noqa: E402

UNSORTED = (
    '"""Tests."""\n\nfrom __future__ import annotations\nimport pytest\nfrom pingboard.config import load\nimport os\n\n'
    "def test_load():  \n    with pytest.raises(ValueError):\n        load({})\n"
)


def _body(source):
    return [ast.dump(n) for n in ast.parse(source).body if not isinstance(n, (ast.Import, ast.ImportFrom))]


class KitFormatTests(unittest.TestCase):
    def test_import_order_unused_imports_and_whitespace_are_fixed_without_changing_the_code(self):
        files = [
            {"path": "runs/kit/REQ-001/test/test_load.py", "content": UNSORTED},
            {"path": "runs/kit/REQ-001/src/pingboard/config/__init__.py", "content": "def load(env):\n    raise ValueError(env)\n"},
            {"path": "runs/kit/REQ-001/ci/LTC.json", "content": "{}"},
        ]
        fixed, changed = autofix_kit_files(files, "REQ-001")
        self.assertEqual(changed, ["runs/kit/REQ-001/test/test_load.py"])
        test = fixed[0]["content"]
        self.assertIn("import pytest\n\nfrom pingboard.config import load\n", test)  # third-party, then first-party
        self.assertNotIn("import os", test)
        self.assertNotIn(":  \n", test)
        self.assertEqual(_body(test), _body(UNSORTED))  # same code once imports are set aside
        self.assertEqual(fixed[2], files[2])

    def test_other_reqs_and_clean_files_are_untouched(self):
        files = [{"path": "runs/kit/REQ-002/test/test_x.py", "content": UNSORTED},
                 {"path": "runs/kit/REQ-001/src/app.py", "content": "VALUE = 1\n"}]
        self.assertEqual(autofix_kit_files(files, "REQ-001"), (files, []))


if __name__ == "__main__":
    unittest.main()
