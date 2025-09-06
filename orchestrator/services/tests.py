import os
from typing import Tuple

def make_tests(lang: str, path: str) -> Tuple[str, str]:
    base = os.path.basename(path)
    base_noext = base.rsplit(".", 1)[0]
    dname = os.path.dirname(path) or "."
    if lang == "python":
        test_path = os.path.join(dname, f"test_{base_noext}.py")
        return test_path, "def test_placeholder():\n    assert 1 == 1\n"
    if lang == "java":
        test_path = os.path.join(dname, f"{base_noext}Test.java")
        return test_path, "import org.junit.jupiter.api.*;\nclass " + base_noext + "Test { @Test void t(){ Assertions.assertTrue(True) } }\n".replace("True","true")
    if lang == "go":
        test_path = os.path.join(dname, f"{base_noext}_test.go")
        return test_path, "package main\nimport \"testing\"\nfunc TestPlaceholder(t *testing.T){ if 1!=1 { t.Fail() } }\n"
    if lang in ("javascript", "typescript", "node", "react"):
        ext = "ts" if lang == "typescript" else "js"
        test_path = os.path.join(dname, f"{base_noext}.test.{ext}")
        return test_path, "test('placeholder', ()=>{ expect(1).toBe(1) })\n"
    if lang == "mendix":
        test_path = os.path.join(dname, f"{base_noext}_test.mdx")
        return test_path, "// Mendix test placeholder\n"
    return path, "// no tests generated\n"
