"""Coding-mode output paths are workspace-relative (regression: /generated/... refused by the extension)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

os.environ.setdefault("CLIKE_API_TOKEN", "t" * 48)
from routes import v1  # noqa: E402


def test_generated_files_are_workspace_relative_even_with_an_absolute_root():
    for root in ("/generated", "generated", "/generated/"):
        with patch.dict(os.environ, {"GENERATED_ROOT": root}):
            out = v1._retarget_files_under_generated([{"path": "radice_quadrata.py", "content": "x"}], "1e754027")
        assert out == [{"path": "generated/1e754027/src/radice_quadrata.py", "content": "x"}], root
        assert not out[0]["path"].startswith("/")
