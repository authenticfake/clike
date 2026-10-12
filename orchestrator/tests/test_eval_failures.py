"""Failure evidence of eval checks: excerpt of the whole output, fingerprint, and the
environment-blocked classifier (a test failure is never 'the sandbox')."""

from __future__ import annotations

from pathlib import Path

import eval_failures
from eval_runner import EvalRunner

ESC = "\x1b"

VITEST = "\n".join(
    [
        f"{ESC}[41m{ESC}[1m FAIL {ESC}[22m{ESC}[49m test/runs.states.test.tsx > launch > keeps the first failure",
        f"{ESC}[31mAssertionError: expected 'Pausa' to be 'Ripresa'{ESC}[39m",
        " ❯ test/runs.states.test.tsx:41:7",
        "     39|   const view = render(<RunMonitor />);",
        "  > 41|   expect(screen.getByText('Ripresa')).toBeVisible();",
        "",
        " FAIL test/runs.states.test.tsx > scope > renders each routed workspace",
        "TestingLibraryElementError: Unable to find an element with the text: Esecuzione · 10.",
        "",
        "Ignored nodes: comments, script, style",
        "<body>",
        *[f"  <div>row {i}</div>" for i in range(400)],
        "</body>",
        " ❯ waitForWrapper ../../../src/web/node_modules/@testing-library/dom/dist/wait-for.js:163:27",
        " ❯ test/runs.states.test.tsx:197:18",
        *[f" ✓ test/other.test.ts > passing case {i}" for i in range(200)],
        " Test Files  1 failed | 4 passed (5)",
        "      Tests  2 failed | 40 passed (42)",
    ]
)


def test_excerpt_keeps_every_failure_without_ansi_dom_and_library_frames():
    out = eval_failures.excerpt(VITEST, "")
    assert ESC not in out
    assert "expected 'Pausa' to be 'Ripresa'" in out  # the first failure (lost by a tail)
    assert "Unable to find an element with the text: Esecuzione" in out
    assert "row 399" not in out and "[DOM dump omitted]" in out
    assert "node_modules" not in out
    assert "test/runs.states.test.tsx:197:18" in out  # the candidate frame stays
    assert "2 failed | 40 passed" in out  # the summary
    assert len(out) <= eval_failures.EXCERPT_LIMIT


def test_short_output_is_returned_whole_and_clean():
    assert eval_failures.excerpt(f"{ESC}[31mboom{ESC}[0m\n", "err") == "err\nboom"


def test_fingerprint_ignores_numbers_and_temp_paths_but_not_the_error():
    a = eval_failures.fingerprint("Error: port 41233 refused at /var/clike-eval/P/REQ-5/work/REQ-5/x.ts:3")
    b = eval_failures.fingerprint("Error: port 50111 refused at /var/clike-eval/P/REQ-5/work/REQ-5/x.ts:9")
    c = eval_failures.fingerprint("Error: element not found")
    assert a == b and a != c
    assert eval_failures.fingerprint("all good") == ""


def _blocked(text: str, code: int = 1) -> bool:
    runner = EvalRunner(Path("."))
    return runner._is_environment_blocked(code=code, stdout=text, stderr="", environment_requirements=[])


def test_a_playwright_assertion_is_not_an_environment_block():
    text = (
        "Error: expect(locator).toBeVisible() failed\n"
        "Locator: getByText('Esecuzione')\nExpected: visible\nError: element(s) not found\n\n  2 failed\n"
    )
    assert not _blocked(text)


def test_a_missing_candidate_module_is_a_code_defect():
    absolute = (
        "Error: Cannot find module '/var/clike-eval/P/REQ-005/work/REQ-005/ci/local-eval-workspaces/"
        "web-e2e/test/fixtures' imported from /var/.../runs.spec.ts\nError: No tests found\n"
    )
    assert not _blocked(absolute)
    assert not _blocked('Error: Failed to resolve import "./fixtures" from "test/a.test.ts".')
    assert not _blocked("Error: Cannot find module '@/lib/api'")


def test_real_environment_problems_stay_blocked():
    assert _blocked("sh: 1: playwright: command not found", code=127)
    assert _blocked("Error: Cannot find module 'better-sqlite3'")
    assert _blocked("pip: Temporary failure in name resolution")
    assert _blocked("Error: invalid ELF header")


def test_passing_test_lines_are_dropped():
    out = eval_failures.excerpt(
        "src::test_a <- ../test/a.py PASSED [ 50%]\nsrc::test_b <- ../test/b.py FAILED [100%]\n ✓ x.test.ts (3 tests)\n", ""
    )
    assert "test_a" not in out and "x.test.ts" not in out and "test_b" in out


def test_only_the_requested_checks_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_ROOT", str(tmp_path / "eval"))
    kit = tmp_path / "runs" / "kit" / "REQ-001"
    (kit / "ci").mkdir(parents=True)
    ran_a = tmp_path / "ran-a"
    ltc = {"req_id": "REQ-001", "checks": [
        {"id": "a", "command": f"touch {ran_a}", "blocking": True},
        {"id": "b", "command": "echo 'AssertionError: 1 != 2' && exit 1", "blocking": True},
    ]}
    report = EvalRunner(tmp_path).run_profile(
        profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001", checks=["b"], regression=True,
    )
    names = [c.name for c in report.cases if not c.name.startswith("env::")]
    assert names == ["b"] and not ran_a.exists()
    failed = report.cases[-1]
    assert failed.excerpt and "AssertionError" in failed.excerpt and failed.fingerprint

    unknown = EvalRunner(tmp_path).run_profile(
        profile=str(kit / "ci" / "LTC.json"), ltc=ltc, req_id="REQ-001", checks=["zzz"],
    )
    assert [c.name for c in unknown.cases if not c.name.startswith("env::")] == ["ltc::unknown-checks"]
    assert "'a', 'b'" in unknown.cases[-1].stderr
