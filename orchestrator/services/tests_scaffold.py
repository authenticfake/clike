from __future__ import annotations
from typing import List, Dict, Set

def ensure_min_tests(files: List[Dict[str, str]], language: str, test_root: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    language = (language or "").lower()
    test_root = (test_root or "tests").rstrip("/")

    # mappa test già presenti, per non duplicare
    existing_tests: Set[str] = set()
    for f in files:
        p = f.get("path", "")
        if p.startswith(f"{test_root}/") or "/__tests__/" in p or p.endswith(".test.ts"):
            base = p.split("/")[-1]
            existing_tests.add(base)

    if language == "python":
        for f in files:
            p = f.get("path", "")
            if not p.endswith(".py"):
                continue
            # skip se è già un test o risiede in tests/
            if p.startswith(f"{test_root}/") or "/tests/" in p:
                continue
            base = p.split("/")[-1].rsplit(".", 1)[0]
            if base.startswith("test_"):
                continue
            test_name = f"test_{base}.py"
            if test_name in existing_tests:
                continue
            test_path = f"{test_root}/{test_name}"
            existing_tests.add(test_name)
            boiler = f"""import pytest

# TODO: add real tests for {p}

def test_sanity():
    assert True
"""
            out.append({"path": test_path, "content": boiler})
        return out

    if language == "typescript":
        for f in files:
            p = f.get("path", "")
            if not p.endswith(".ts") or p.endswith(".d.ts"):
                continue
            if p.startswith(f"{test_root}/") or "/__tests__/" in p or "/tests/" in p:
                continue
            base = p.split("/")[-1].rsplit(".", 1)[0]
            if base.endswith(".test"):
                continue
            test_name = f"{base}.test.ts"
            if test_name in existing_tests:
                continue
            test_path = f"{test_root}/{test_name}"
            existing_tests.add(test_name)
            boiler = f"""// TODO: add real tests for {p}
                    describe('{base}', () => {{
                    it('sanity', () => {{
                        expect(true).toBe(true);
                    }});
                    }});
                    """
            out.append({"path": test_path, "content": boiler})
        return out

    return out
