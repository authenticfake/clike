"""/finalize verification: the integrated solution must run end to end, checked by CLike.

/finalize writes ``ci/SOLUTION_LTC.json``, the eval profile of the whole solution (same LTC
contract as a KIT). After /finalize the extension runs it in the eval sandbox against the
canonical tree (the sources and tests promoted by the gates); when it fails, /finalize runs again
with the errors (``finalize_verify.repair``), a bounded number of cycles, no flag needed. A local
agent can re-run the profile's checks in the sandbox while it works (eval-check bridge).
Shared by the cloud prompt and the local-agent package, so both paths follow the same rules."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from services.kit_repair import repair_failures, repair_file_priority

SOLUTION_PROFILE = "ci/SOLUTION_LTC.json"
SOLUTION_EVAL_ID = "SOLUTION"

# Agents stop shell commands after a timeout (Claude Code: 2 min by default); the helper resumes.
EVAL_CHECK_TIMEOUT_NOTE = (
    " Give the command a long timeout (it takes minutes); if it is stopped by a timeout, run the same command again: it resumes waiting for the same run."
)

_PROFILES_BUDGET = 30000       # chars of the REQs' eval profiles shown to the model
_REPAIR_FILE_BUDGET = 16000
_REPAIR_TOTAL_BUDGET = 160000


def deployment_hint(payload: Dict[str, Any]) -> str:
    """The deployment target declared in TECH_CONSTRAINTS (e.g. on-prem, cloud), as raw text."""
    blobs = payload.get("core_blobs") if isinstance(payload.get("core_blobs"), dict) else {}
    text = ""
    for name, content in (blobs or {}).items():
        if str(name).endswith("TECH_CONSTRAINTS.yaml"):
            text = str(content or "")
            break
    return " ".join(
        line.split(":", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if ":" in line and "deploy" in line.split(":", 1)[0].lower()
    )


def solution_verify_rules(deployment: str = "") -> List[str]:
    target = (deployment or "").lower()
    cloud = any(word in target for word in ("cloud", "aws", "azure", "gcp", "kubernetes", "k8s"))
    deploy_rule = (
        "Cloud deployment: also write guarded deploy scripts (mutating only with CLIKE_ALLOW_CLOUD_MUTATION=1) and "
        "check them in the profile without mutating anything (validate/plan/dry-run), non-blocking when the provider CLI "
        "is not installed. The local run below stays required: it is how the solution is developed and tested."
        if cloud else
        "On-premises / local deployment: the local run below is the target — every step must work on the developer's machine."
    )
    return [
        f"Write {SOLUTION_PROFILE}: the eval profile of the WHOLE solution. CLike runs it automatically after /finalize in "
        "its eval sandbox (a Linux container; the project is copied without runs/ and .git) against the canonical tree: "
        "the sources and tests the gates promoted under src/ and test/. When it fails, CLike sends you its errors to fix.",
        'Format: the LTC contract of a KIT — {"req_id": "SOLUTION", "checks": [{"id", "command", "cwd" (relative to the '
        'project root), "blocking": true, "timeout"}], "environment": {"required_variables": [{name, purpose, provision}]}, '
        '"services": [{name, cwd, setup, start, env, port_env, ready: {http_path}, exports}]} — provision token | uuid | '
        "timestamp | template | postgres_database | service | external, as in the KIT rules; omit `req` in services: they run "
        "from the canonical tree.",
        "Blocking checks, in order: (1) install every component from its manifest (lockfile when present) inside the "
        "tree, no global installs; (2) the test suites of every promoted REQ on the canonical tree — derive them from each "
        "REQ's eval profile listed below, re-pointing runs/kit/<REQ>/ paths to the root; (3) build/type-check of every "
        "component; (4) the solution started as the user runs it (database migrations, backend, workers, frontend) as "
        "`services` with readiness probes; (5) end-to-end checks against the running solution: the promoted UI e2e tests "
        "with the base URL the services export, and an API smoke of the main user flow (health plus one real request per "
        "main capability).",
        "Reports, caches and temp files only under CLIKE_EVAL_REPORT_DIR / CLIKE_EVAL_TEMP_ROOT. No hardcoded secrets: "
        "values come from provisioning; checks that need a real external provider are non-blocking and their variables "
        "provision `external`.",
        "Local run on the developer's machine: scripts/check_solution_local.sh and .ps1 run the same steps as the profile "
        "(install, migrate, start, smoke, stop) with the variables of .env.example; docs/harper/HOWTO_RUN.md documents "
        "prerequisites, the one command that starts the solution, its URLs, how to stop it and how to run the checks.",
        deploy_rule,
        "Make the profile pass by fixing code, configuration and wiring (composition roots, settings, routes, scripts) inside "
        "your write roots. The promoted tests under test/ are the REQs' acceptance: do not change them; if one cannot "
        "pass, explain why in docs/harper/TODO_NEXT.md.",
    ]


def req_profiles_text(req_profiles: Any) -> str:
    """The eval profiles of the promoted REQs (checks, environment, services), bounded."""
    items = [p for p in (req_profiles or []) if isinstance(p, dict) and p.get("req")]
    if not items:
        return ""
    text = json.dumps(items, indent=1, ensure_ascii=False)
    if len(text) > _PROFILES_BUDGET:
        text = text[:_PROFILES_BUDGET] + "\n… (truncated: read runs/kit/<REQ>/ci/LTC.json)"
    return text


def solution_repair_rules() -> List[str]:
    return [
        f"The solution eval ({SOLUTION_PROFILE}) failed: its errors are below. Read ALL of them before changing anything, "
        "group them by root cause (one cause often fails install, tests, build and e2e) and fix every cause in this run.",
        "Fix the code, the configuration, the scripts and the wiring. A profile command that is wrong (path, flag, cwd) may "
        "be fixed; never remove a check, make it non-blocking or weaken a test.",
        "A check that ran and failed (an assertion, an element not found, a module not found, a timeout) is a defect of "
        "the solution, not of the sandbox.",
    ]


def cloud_finalize_section(verify: Dict[str, Any], deployment: str = "") -> str:
    """Section appended to the cloud /finalize prompt."""
    lines = ["## SOLUTION VERIFICATION — ci/SOLUTION_LTC.json (CLike runs it after /finalize)", ""]
    lines += [f"- {rule}" for rule in solution_verify_rules(deployment)]
    lines += [f"- Emit `BEGIN_FILE {SOLUTION_PROFILE}` … `END_FILE` (valid JSON) whenever runnable code exists under src/."]
    profiles = req_profiles_text(verify.get("req_profiles"))
    if profiles:
        lines += ["", "### Eval profiles of the promoted REQs", "```json", profiles, "```"]
    repair = verify.get("repair")
    if isinstance(repair, dict) and repair:
        lines += ["", repair_section(repair)]
    return "\n".join(lines)


def repair_section(repair: Dict[str, Any]) -> str:
    cycle = repair.get("cycle") or 1
    lines = [f"## SOLUTION REPAIR — cycle {cycle} of {repair.get('max_cycles') or cycle}", ""]
    lines += [f"- {rule}" for rule in solution_repair_rules()]
    lines += ["- Return ONLY the files you change, each complete in a BEGIN_FILE / END_FILE block.", "", "### Failed checks"]
    failures = repair_failures(repair)
    for item in failures:
        lines += [f"#### {item['name']} (exit {item.get('code')})", f"command: {item.get('command') or ''}",
                  "```", item["output"].rstrip(), "```"]
    hint = str(repair.get("hint") or "").strip()
    if hint:
        lines += ["", "### Developer hint", hint]
    files = [f for f in (repair.get("files") or []) if isinstance(f, dict) and f.get("path")]
    if files:
        failures_text = "\n".join(f"{i['command']}\n{i['output']}" for i in failures)
        ranked = sorted(
            ((repair_file_priority(str(f["path"]), failures_text, ""), n, f) for n, f in enumerate(files)),
            key=lambda item: (item[0] < 0, item[0], item[1]),
        )
        budget = _REPAIR_TOTAL_BUDGET
        omitted: List[str] = []
        lines += ["", "### Current solution files"]
        for priority, _, f in ranked:
            content = str(f.get("content") or "")
            if priority < 0 or budget <= 0:
                omitted.append(str(f["path"]))
                continue
            shown = content[:min(_REPAIR_FILE_BUDGET, budget)]
            budget -= len(shown)
            truncated = " (truncated)" if len(shown) < len(content) else ""
            lines += [f"#### {f['path']}{truncated}", "```", shown.rstrip(), "```"]
        if omitted:
            lines += ["", "Other files (not shown; unchanged unless you return them):", *[f"- {p}" for p in omitted]]
    return "\n".join(lines)


def agent_finalize_lines(verify: Dict[str, Any], deployment: str = "", eval_check_max_runs: int = 0) -> List[str]:
    """Prompt lines of the local-agent /finalize package (eval_check_max_runs > 0: the extension
    serves eval checks of the profile during the run)."""
    lines = ["", "SOLUTION VERIFICATION (CLike runs ci/SOLUTION_LTC.json after you finish):"]
    lines += [f"- {rule}" for rule in solution_verify_rules(deployment)]
    if eval_check_max_runs > 0:
        lines.append(
            f"- Check it yourself in the real CLike eval sandbox before finishing: `node .clike/bin/eval-check.mjs` runs "
            f"all its checks, `node .clike/bin/eval-check.mjs <check> ...` only some, and prints their errors (a few "
            f"minutes; at most {eval_check_max_runs} runs). Iterate until they pass." + EVAL_CHECK_TIMEOUT_NOTE
        )
    lines += [
        "- On this machine, run scripts/check_solution_local.sh (or .ps1 on Windows) when the tools it needs are installed, "
        "and fix what fails: the solution must run on the developer's PC as HOWTO_RUN says.",
    ]
    profiles = req_profiles_text(verify.get("req_profiles"))
    if profiles:
        lines += ["- Eval profiles of the promoted REQs (also under runs/kit/<REQ>/ci/LTC.json):", "```json", profiles, "```"]
    repair = verify.get("repair")
    if isinstance(repair, dict) and repair:
        lines += ["", f"SOLUTION REPAIR — cycle {repair.get('cycle') or 1} of {repair.get('max_cycles') or 1}:"]
        lines += [f"- {rule}" for rule in solution_repair_rules()]
        for item in repair_failures(repair):
            lines += [f"Failed check `{item['name']}` (exit {item.get('code')}, command `{item.get('command')}`):",
                      "```text", item["output"].rstrip()[:6000], "```"]
        hint = str(repair.get("hint") or "").strip()
        if hint:
            lines.append(f"Developer hint: {hint}")
    return lines
