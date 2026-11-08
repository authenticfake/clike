#!/usr/bin/env python3
"""Third-party skills vendored into CLike: pinned, reviewed, verifiable and updatable.

The skills live in extensions/vscode/templates/harper-init/.clike/skills/vendor/<vendor>/<skill>/
(shipped by /init, installed for the agents as <vendor>-<skill>, indexed for the cloud prompt).
VENDORED.json records for each vendor the repository, the pinned commit, the license, the review
date and the sha256 of every vendored file.

  verify                         every vendored file matches VENDORED.json (run in CI by the tests)
  check-updates                  the pinned commit vs the repository's current HEAD (network)
  update <vendor> [--ref R] [--apply]
                                 fetch the repository at R (default HEAD) into a temporary folder,
                                 print the diff and the review findings (license, scripts, remote
                                 fetches, tool pre-approval, AI product names); --apply copies the
                                 files and re-pins VENDORED.json after you reviewed the diff.

Nothing is fetched at run time by CLike or by the agents: an update is a reviewed commit.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO / "extensions" / "vscode" / "templates" / "harper-init" / ".clike" / "skills" / "vendor"
MANIFEST = VENDOR_DIR / "VENDORED.json"

RISKS = [
    (re.compile(r"\b(curl|wget|Invoke-WebRequest|fetch\()", re.I), "fetches from the network"),
    (re.compile(r"https?://(?!github\.com/[^ ]+/blob/|opensource\.org)", re.I), "remote URL (check it is a reference, not instructions to load)"),
    (re.compile(r"^allowed-tools:", re.M), "pre-approves tools (allowed-tools)"),
    (re.compile(r"\b(rm -rf|sudo |chmod \+x|eval )", re.I), "shell command with side effects"),
]
SCRIPT_SUFFIXES = {".sh", ".ps1", ".py", ".js", ".cjs", ".mjs", ".ts", ".bat", ".cmd", ".exe"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> Dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(manifest: Dict) -> None:
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def vendored_files(vendor: str, skill: str) -> Dict[str, Path]:
    base = VENDOR_DIR / vendor / skill
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*")) if p.is_file()}


def verify() -> List[str]:
    """Problems: a vendored file missing, changed, or not recorded in VENDORED.json."""
    problems: List[str] = []
    for vendor in load_manifest().get("vendors") or []:
        vid = vendor["id"]
        if not (VENDOR_DIR / vid / "LICENSE").is_file():
            problems.append(f"{vid}: LICENSE file missing")
        for skill in vendor.get("skills") or []:
            recorded = skill.get("files") or {}
            present = vendored_files(vid, skill["name"])
            for rel, digest in recorded.items():
                if rel not in present:
                    problems.append(f"{vid}/{skill['name']}/{rel}: missing")
                elif sha256(present[rel]) != digest:
                    problems.append(f"{vid}/{skill['name']}/{rel}: changed since the reviewed pin (run update, review, --apply)")
            for rel in present:
                if rel not in recorded:
                    problems.append(f"{vid}/{skill['name']}/{rel}: not recorded in VENDORED.json")
    return problems


def review_findings(root: Path, files: List[str]) -> List[str]:
    findings = []
    for rel in files:
        path = root / rel
        if path.suffix.lower() in SCRIPT_SUFFIXES:
            findings.append(f"{rel}: executable script — excluded unless the manifest allows it")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in RISKS:
            if pattern.search(text):
                findings.append(f"{rel}: {label}")
        if re.search(r"\b(Claude|Anthropic|OpenAI|GPT-\d|Codex|Gemini)\b", text):
            findings.append(f"{rel}: names an AI product (CLike capability docs name capabilities only) — review")
    return findings


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def check_updates() -> int:
    stale = 0
    for vendor in load_manifest().get("vendors") or []:
        head = git("ls-remote", vendor["repo"], "HEAD").split()[0]
        state = "up to date" if head == vendor["ref"] else f"update available: {vendor['ref'][:12]} → {head[:12]}"
        stale += head != vendor["ref"]
        print(f"{vendor['id']}: {state}")
    return 1 if stale else 0


def update(vendor_id: str, ref: str | None, apply: bool) -> int:
    manifest = load_manifest()
    vendor = next((v for v in manifest.get("vendors") or [] if v["id"] == vendor_id), None)
    if vendor is None:
        print(f"unknown vendor {vendor_id}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        git("clone", "--quiet", "--filter=blob:none", vendor["repo"], str(src))
        git("checkout", "--quiet", ref or "HEAD", cwd=src)
        new_ref = git("rev-parse", "HEAD", cwd=src)
        license_text = (src / vendor.get("license_file", "LICENSE")).read_text(encoding="utf-8", errors="replace")
        if vendor["license"].split("-")[0].lower() not in license_text.lower()[:400]:
            print(f"! license changed: expected {vendor['license']}, review LICENSE before applying")
        findings: List[str] = []
        for skill in vendor.get("skills") or []:
            upstream = src / skill["path"]
            allowed = set(skill.get("allow_scripts") or [])
            files = [p.relative_to(upstream).as_posix() for p in sorted(upstream.rglob("*")) if p.is_file()
                     and (p.suffix.lower() not in SCRIPT_SUFFIXES or p.relative_to(upstream).as_posix() in allowed)]
            findings += [f"{skill['name']}/{f}" for f in review_findings(upstream, files)]
            current = vendored_files(vendor_id, skill["name"])
            for rel in sorted(set(files) | set(current)):
                old = current[rel].read_text(encoding="utf-8", errors="replace").splitlines(True) if rel in current else []
                new = (upstream / rel).read_text(encoding="utf-8", errors="replace").splitlines(True) if rel in files else []
                sys.stdout.writelines(difflib.unified_diff(old, new, f"vendored/{skill['name']}/{rel}", f"{new_ref[:12]}/{skill['name']}/{rel}"))
            if apply:
                target = VENDOR_DIR / vendor_id / skill["name"]
                shutil.rmtree(target, ignore_errors=True)
                for rel in files:
                    (target / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(upstream / rel, target / rel)
                skill["files"] = {rel: sha256(target / rel) for rel in files}
        print("\nReview findings:" if findings else "\nReview findings: none")
        for f in findings:
            print(f"  - {f}")
        if apply:
            shutil.copy2(src / vendor.get("license_file", "LICENSE"), VENDOR_DIR / vendor_id / "LICENSE")
            vendor["ref"] = new_ref
            vendor["reviewed"] = date.today().isoformat()
            save_manifest(manifest)
            print(f"\n{vendor_id} pinned at {new_ref}; commit the vendored files and VENDORED.json together.")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    sub.add_parser("check-updates")
    up = sub.add_parser("update")
    up.add_argument("vendor")
    up.add_argument("--ref")
    up.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "verify":
        problems = verify()
        for p in problems:
            print(p)
        print("vendored skills: OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if args.cmd == "check-updates":
        return check_updates()
    return update(args.vendor, args.ref, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
