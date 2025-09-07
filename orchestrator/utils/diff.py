# -*- coding: utf-8 -*-
import os, difflib
from typing import List, Dict

def _read_existing(root: str, relative_path: str) -> str:
    full = os.path.join(root, relative_path)
    if not os.path.exists(full):
        return ""
    with open(full, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def unified_diff_for_files(files: List[Dict[str, str]], root: str) -> List[Dict]:
    diffs = []
    for blob in files:
        path = blob["path"]
        new_text = blob["content"]
        old_text = _read_existing(root, path)
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        )
        diffs.append({"path": path, "format": "unified", "content": "".join(diff)})
    return diffs
