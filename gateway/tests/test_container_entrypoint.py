"""The container entry point must be importable (WP9 regression: a cleanup removed the re-export
in gateway/main.py that `uvicorn main:app` relies on; unit tests import app.py directly)."""

import importlib
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def test_dockerfile_cmd_target_is_importable():
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text(encoding="utf-8")
    cmd = json.loads(re.search(r"^CMD\s+(\[.*\])\s*$", dockerfile, re.M).group(1))
    target = next(arg for arg in cmd if re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", arg))
    module_name, attr = target.split(":")
    with patch.dict(os.environ, {"CLIKE_API_TOKEN": "e" * 48}):
        module = importlib.import_module(module_name)
    app = getattr(module, attr, None)
    assert app is not None, f"{target} is not defined"
    assert callable(app), f"{target} is not an ASGI app"
