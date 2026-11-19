"""Test strength: a test must fail before it can count as acceptance.

Once per KIT generation (and again when its tests change), when the REQ's own checks pass, the
eval re-runs its test checks on the code before the KIT: the promoted tree and the dependency KITs,
without the KIT's own ``src/`` and ``root/`` deliverables (``EvalRunner(baseline=True)``). A test
check that passes there too verifies nothing the REQ adds (fixtures built to pass, assertions on
the test's own data, a smoke that only imports). It is reported as the non-blocking check
``acceptance::test-strength`` (a warning: the gate passes unless warnings are strict); the
developer, or a repair under strict warnings, adds a test that fails without the KIT.

A check that fails on that code but where some tests pass is only described (a MODIFIED REQ keeps
testing behaviour that existed before). The baseline costs one sandbox run and no model tokens;
``CLIKE_EVAL_TEST_STRENGTH=0`` turns it off.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional

CASE = "acceptance::test-strength"

_TEST_COMMAND_RE = re.compile(
    r"\b(?:pytest|py\.test|unittest|vitest|jest|playwright\s+test|mocha|ava|node\s+--test|go\s+test|"
    r"cargo\s+test|mvn\b[^|;&]*\btest|gradlew?\b[^|;&]*\btest|dotnet\s+test|(?:npm|pnpm|yarn)\s+(?:run\s+)?test\b)",
    re.IGNORECASE,
)
_TEST_NAME_TOKENS = {"test", "tests", "unit", "integration", "e2e", "smoke", "pytest", "vitest", "jest",
                     "playwright", "acceptance", "behaviour", "behavior", "functional", "contract"}
_STATIC_NAME_RE = re.compile(
    r"lint|format|style|ruff|flake8|eslint|prettier|type|mypy|pyright|tsc|security|secret|audit|bandit|"
    r"vuln|sast|build|compile|syntax|coverage|license|sbom",
    re.IGNORECASE,
)

# Summaries of the common runners: (passed, failed) counts.
_COUNT_RES = (
    re.compile(r"=+ (?:(?P<failed>\d+) failed, )?(?P<passed>\d+) passed\b"),            # pytest
    re.compile(r"=+ (?P<failed>\d+) failed(?:, (?P<passed>\d+) passed)?\b"),           # pytest, failures first
    re.compile(r"Tests:\s+(?:(?P<failed>\d+) failed, )?(?:\d+ \w+, )*?(?P<passed>\d+) passed"),  # jest
    re.compile(r"Tests\s+(?:(?P<failed>\d+) failed \| )?(?P<passed>\d+) passed"),      # vitest
    re.compile(r"(?P<passed>\d+) passed(?: \([\d.]+m?s\))?\s*\n\s*(?P<failed>\d+) failed"),  # playwright
)


def enabled() -> bool:
    return os.getenv("CLIKE_EVAL_TEST_STRENGTH", "1").strip().lower() not in {"0", "false", "no", "off"}


def _ltc_commands(ltc: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Check id -> command, for every shape the runner accepts (checks / cases / commands)."""
    doc = ltc or {}
    items = doc.get("checks") or doc.get("cases") or doc.get("commands") or []
    if isinstance(items, dict):
        items = [{**raw, "id": name} if isinstance(raw, dict) else {"id": name, "run": raw} for name, raw in items.items()]
    out: Dict[str, str] = {}
    for index, item in enumerate(items if isinstance(items, list) else []):
        if isinstance(item, str):
            out[f"case::{index + 1}"] = item
        elif isinstance(item, dict):
            key = str(item.get("id") or item.get("name") or f"case::{index + 1}")
            out[key] = str(item.get("command") or item.get("run") or item.get("cmd") or "")
    return out


def is_test_check(name: str, command: str) -> bool:
    """A check that runs tests (not a linter, a type checker, a build or an audit)."""
    if _STATIC_NAME_RE.search(name or "") and not _TEST_COMMAND_RE.search(command or ""):
        return False
    tokens = {t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t}
    return bool(tokens & _TEST_NAME_TOKENS) or bool(_TEST_COMMAND_RE.search(command or ""))


def own_failures(cases: Iterable[Any]) -> List[str]:
    """The REQ's own blocking failures (not the regression of promoted REQs)."""
    return [c.name for c in cases if not c.passed and c.blocking and not str(c.name).startswith("regression::")]


def candidates(cases: Iterable[Any], ltc: Optional[Dict[str, Any]]) -> List[str]:
    """The REQ's own blocking test checks that passed: the ones the baseline re-runs."""
    commands = _ltc_commands(ltc)
    return [
        c.name for c in cases
        if c.name in commands and c.passed and c.blocking and not c.blocked and is_test_check(c.name, commands[c.name])
    ]


def counts(output: str) -> Optional[Dict[str, int]]:
    """Passed/failed test counts from a runner summary, when the output has one."""
    for regex in _COUNT_RES:
        found = list(regex.finditer(output or ""))
        if found:
            last = found[-1]
            return {"passed": int(last.group("passed") or 0), "failed": int(last.group("failed") or 0)}
    return None


def summarize(names: List[str], baseline_cases: Iterable[Any]) -> Dict[str, Any]:
    """What the baseline run shows: the checks that pass without the KIT (weak) and, for the others,
    how many of their tests already pass there."""
    by_name = {c.name: c for c in baseline_cases}
    weak: List[str] = []
    partial: Dict[str, Dict[str, int]] = {}
    failing: List[str] = []
    unknown: List[str] = []
    for name in names:
        case = by_name.get(name)
        if case is None or case.blocked:
            unknown.append(name)
            continue
        if case.passed:
            weak.append(name)
            continue
        failing.append(name)
        seen = counts(f"{case.stdout or ''}\n{case.stderr or ''}")
        if seen and seen["passed"]:
            partial[name] = seen
    return {"checks": names, "weak": weak, "failing": failing, "partial": partial, "unknown": unknown}


def case_fields(result: Dict[str, Any], req_id: str) -> Optional[Dict[str, Any]]:
    """The non-blocking ``acceptance::test-strength`` check for a recorded result (None: nothing to say)."""
    if result.get("error") or not result.get("checks"):
        return None
    weak, partial = list(result.get("weak") or []), dict(result.get("partial") or {})
    lines = []
    if weak:
        lines.append(
            f"[CLike EvalRunner] Test strength: {', '.join(weak)} of {req_id} pass on the code before this KIT too "
            f"(the promoted tree and its dependencies, without runs/kit/{req_id}/src and root/): they do not verify "
            "what this REQ adds. Add at least one test per acceptance criterion that fails without the KIT and passes "
            "with it (assert on the behaviour, not on the test's own fixtures). For a MODIFIED REQ, tests of unchanged "
            "behaviour may pass before: at least one test must cover the change."
        )
    else:
        lines.append(
            f"[CLike EvalRunner] Test strength: every test check of {req_id} ({', '.join(result.get('failing') or [])}) "
            "fails on the code before this KIT and passes with it."
        )
    for name, seen in sorted(partial.items()):
        total = seen["passed"] + seen["failed"]
        lines.append(f"  {name}: {seen['passed']} of {total} tests already pass before the KIT (only the others verify it).")
    if result.get("unknown"):
        lines.append(f"  not measured (blocked on that code): {', '.join(result['unknown'])}")
    text = "\n".join(lines)
    return {
        "name": CASE, "passed": not weak, "code": 1 if weak else 0, "blocking": False,
        "stdout": text, "stderr": text if weak else "", "excerpt": text if weak else None,
    }
