"""What a failed eval check tells the repair model: the errors, all of them, readable.

A check's output is often long (a test runner prints every passing test, DOM dumps, coloured
text) and the useful part is spread through it: keeping only its tail lost the first failures.
``excerpt`` keeps the error blocks of the whole output (any language or runner: they are found by
generic markers), without ANSI codes, DOM dumps and library stack frames, plus the final summary.
``fingerprint`` identifies the errors (not the check name), so a repair loop can tell "the same
errors again" from "different errors in the same check".
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Tuple

EXCERPT_LIMIT = 6000

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
# Lines that start or describe an error, in the common runners (pytest, unittest, vitest, jest,
# node --test, Playwright, tsc, eslint, ruff, mypy, go test, cargo, maven/gradle, dotnet).
_KEY = re.compile(
    r"(\bFAIL(ED|URE)?\b|\bERROR\b|\bError\b|Exception\b|Traceback|AssertionError|\bassert\b|"
    r"\bExpected\b|\bReceived\b|Locator:|error TS\d+|\berror\b:|^E\s{2,}|^\s*\d+\) |✗|×|✘|"
    r"\bpanicked\b|--- FAIL|\bnot ok\b|Timeout|timed out|Cannot |Unable to|is not defined|"
    r"undefined|has no attribute|No module named|Failed to|not found|strict mode violation)",
)
_LIB_FRAME = re.compile(r"^\s*(❯|at\s|File\s\").*(node_modules|node:internal|site-packages|<frozen |/usr/lib/)")
# A passing test's line (vitest/jest ✓, pytest -v PASSED, node --test / TAP ok, go --- PASS).
_PASS_LINE = re.compile(r"^\s*(✓|√|ok \d+ |--- PASS|=== RUN)|\sPASSED\s*\[\s*\d+%\]\s*$")
_DOM_START = re.compile(r"Ignored nodes:|^\s*<body>")
_DOM_END = re.compile(r"</body>")
_SUMMARY = re.compile(
    r"(\b\d+\s+(passed|failed|errors?|skipped)\b|Test Files|Tests\s|Duration|=====|coverage|Coverage|"
    r"\bFAIL\b|\bPASS\b|exit code|threshold)",
    re.IGNORECASE,
)
_BEFORE, _AFTER = 2, 10


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "").replace("\r\n", "\n").replace("\r", "\n")


def _clean_lines(text: str) -> List[str]:
    out: List[str] = []
    in_dom = False
    for line in strip_ansi(text).split("\n"):
        if in_dom:
            if _DOM_END.search(line):
                in_dom = False
            continue
        if _DOM_START.search(line):
            in_dom = True
            if not out or out[-1] != "  [DOM dump omitted]":
                out.append("  [DOM dump omitted]")
            continue
        if _LIB_FRAME.search(line) or _PASS_LINE.search(line):
            continue
        if re.fullmatch(r"\s*[⎯─━=\-]{8,}\s*(\[\d+/\d+\])?[⎯─━=\-]*\s*", line):
            continue
        out.append(line.rstrip())
    # collapse runs of blank lines
    collapsed: List[str] = []
    for line in out:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    return collapsed


def _windows(lines: List[str]) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for i, line in enumerate(lines):
        if _KEY.search(line):
            start, end = max(0, i - _BEFORE), min(len(lines), i + _AFTER + 1)
            if spans and start <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(spans[-1][1], end))
            else:
                spans.append((start, end))
    return spans


def excerpt(stdout: str, stderr: str = "", limit: int = EXCERPT_LIMIT) -> str:
    """The error blocks of a failed check's output, readable and bounded (see module doc)."""
    parts = [p for p in (stderr, stdout) if p and p.strip()]
    lines = _clean_lines("\n".join(parts))
    text = "\n".join(lines).strip()
    if len(text) <= limit:
        return text
    blocks: List[str] = []
    seen = set()
    for start, end in _windows(lines):
        block = "\n".join(lines[start:end]).strip()
        key = re.sub(r"\d+", "#", block)
        if block and key not in seen:
            seen.add(key)
            blocks.append(block)
    tail = [line for line in lines[-40:] if line.strip() and _SUMMARY.search(line)][-12:]
    summary = "\n".join(tail)
    budget = max(limit - len(summary) - 40, limit // 2)
    if blocks:
        share = max(400, budget // len(blocks))
        body: List[str] = []
        used = 0
        for block in blocks:
            if used >= budget:
                body.append(f"[{len(blocks) - len(body)} more error block(s) omitted]")
                break
            piece = block if len(block) <= share else block[:share].rstrip() + "\n  [...]"
            body.append(piece)
            used += len(piece)
        out = "\n---\n".join(body)
    else:
        out = text[-budget:]
    if summary and summary not in out:
        out += "\n--- summary ---\n" + summary
    return out[:limit]


# Mixed-case letters and digits, 20+ chars (base64/base64url): a generated value, not a name.
_RANDOM_TOKEN = re.compile(r"(?<![\w-])(?=[\w-]*[a-z])(?=[\w-]*[A-Z])(?=[\w-]*\d)[\w-]{20,}(?![\w-])")


def error_keys(text: str) -> list:
    """The error lines of an excerpt, normalized (numbers, hex ids, random tokens, temp paths and ports ignored)."""
    keys = set()
    for line in (text or "").split("\n"):
        if not _KEY.search(line):
            continue
        norm = re.sub(r"/[\w./@+-]*?/(work|tmp|var|private)/[\w./@+-]*", "<path>", line)
        # Random values printed by a failed assertion (session tokens, nonces): new on every run.
        norm = _RANDOM_TOKEN.sub("<token>", norm)
        norm = re.sub(r"0x[0-9a-f]+|[0-9a-f]{8,}|\d+", "#", norm.strip().lower())
        keys.add(norm)
    return sorted(keys)


def fingerprint(text: str) -> str:
    """Stable id of the errors in an excerpt: numbers, hex ids, random tokens, temp paths and ports ignored."""
    keys = error_keys(text)
    if not keys:
        return ""
    return hashlib.sha1("\n".join(keys).encode("utf-8")).hexdigest()[:12]
