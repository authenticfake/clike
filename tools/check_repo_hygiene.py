#!/usr/bin/env python3
"""Block files that must never be published from this (public) repository.

Usage:
    python3 tools/check_repo_hygiene.py --staged   # pre-commit: staged files and staged content
    python3 tools/check_repo_hygiene.py --all      # CI: every tracked file

Exit code 1 lists every violation. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import Iterable

FORBIDDEN_PATHS = [
    (re.compile(r"^telemetry/"), "runtime telemetry (prompts and LLM outputs)"),
    (re.compile(r"^docs/_private/"), "private analysis notes"),
    (re.compile(r"(^|/)\.env$"), "environment file with secrets"),
    (re.compile(r"(^|/)node_modules/"), "installed dependencies"),
    (re.compile(r"\.vsix$"), "packaged extension build"),
    (re.compile(r"(^|/)\.DS_Store$"), "macOS metadata"),
    (re.compile(r"\.(pem|key|p12|pfx)$"), "certificate or key material"),
    (re.compile(r"(^|/)\.venv[^/]*/"), "virtual environment"),
    (re.compile(r"(\.bak|~clike\.bak)$"), "backup file"),
]

SECRET_PATTERNS = [
    (re.compile(r"sk-(proj|ant|svcacct)-[A-Za-z0-9_\-]{20,}"), "OpenAI/Anthropic API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub token"),
]

# Fixtures that intentionally contain fake key-shaped strings.
SECRET_SCAN_ALLOWLIST = [
    re.compile(r"^tools/tests/"),
    re.compile(r"^gateway/tests/golden/"),
]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _paths(staged: bool) -> list[str]:
    if staged:
        out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        out = _git("ls-files", "-z")
    return [p for p in out.split("\0") if p]


def _content(path: str, staged: bool) -> str:
    try:
        if staged:
            raw = subprocess.run(["git", "show", f":{path}"], check=True, capture_output=True).stdout
        else:
            with open(path, "rb") as fh:
                raw = fh.read()
    except (subprocess.CalledProcessError, OSError):
        return ""
    if b"\0" in raw[:8192]:
        return ""  # binary
    return raw.decode("utf-8", errors="ignore")


def find_violations(paths: Iterable[str], read) -> list[str]:
    violations = []
    for path in paths:
        for pattern, reason in FORBIDDEN_PATHS:
            if pattern.search(path) and not path.endswith(".env.example"):
                violations.append(f"{path}: forbidden path ({reason})")
                break
        else:
            if any(p.search(path) for p in SECRET_SCAN_ALLOWLIST):
                continue
            text = read(path)
            for pattern, reason in SECRET_PATTERNS:
                if pattern.search(text):
                    violations.append(f"{path}: possible secret ({reason})")
                    break
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    violations = find_violations(_paths(args.staged), lambda p: _content(p, args.staged))
    if violations:
        print("Repository hygiene check failed:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print("Unstage/untrack these files (see .gitignore). Never commit telemetry, secrets or private notes.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
