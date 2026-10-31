"""/finalize verification: the integrated solution must start and answer, checked by CLike.

/finalize writes ``ci/SOLUTION_LTC.json``, the eval profile of the whole solution (same LTC
contract as a KIT). It does not run the REQs' test suites again: every REQ passed them at its gate.
It installs, builds, configures and starts the solution and checks that it answers. After
/finalize the extension runs it in the eval sandbox against the canonical tree; when it fails,
/finalize runs again with the errors (``finalize_verify.repair``), a bounded number of cycles, no
flag needed. A local agent can re-run the profile's checks in the sandbox while it works
(eval-check bridge).
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

_PROFILES_BUDGET = 30000       # chars of the REQs' environments and services shown to the model
REPORT_PATH = "docs/harper/FINALIZE_REPORT.md"
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
        f"Write {SOLUTION_PROFILE}: the eval profile of the WHOLE solution running. CLike runs it automatically after "
        "/finalize in its eval sandbox (a Linux container; the project is copied without runs/ and .git) against the "
        "canonical tree the gates promoted. When it fails, CLike sends you its errors to fix.",
        'Format: the LTC contract of a KIT — {"req_id": "SOLUTION", "setup": [{"id", "command", "cwd", "timeout"}], '
        '"checks": [{"id", "command", "cwd" (relative to the '
        'project root), "blocking": true, "timeout"}], "environment": {"required_variables": [{name, purpose, provision}], "tools": [native programs the checks run, e.g. "kcat", "jdk@17"]}, '
        '"services": [{name, cwd, setup, start, env, port_env, ready: {http_path}, exports}]} — provision token | uuid | '
        "timestamp | template | postgres_database | service | external, as in the KIT rules; omit `req` in services: they run "
        "from the canonical tree. Reuse the environments and services the REQs already declared (listed below).",
        "Do NOT run the REQs' test suites, linters, type checks or coverage again: every REQ passed them at its gate. "
        "The profile proves that the integrated solution runs.",
        "CLike runs the profile in this order: `setup`, then the environment and the `services`, then the `checks`. So: "
        "(1) `setup` installs every component from its manifest (lockfile when present) inside the tree, no global "
        "installs, and builds every component that needs a build to run — the services start from what setup "
        "installed; (2) `services`: the solution configured and started as the user runs it (database migrations in "
        "the setup of the service that owns them, backend, workers, frontend) with readiness probes; (3) blocking "
        "`checks`: smoke checks against the running solution, as small scripts under ci/solution/ — health of each "
        "service, one real request per main capability of the SPEC through the public API, and every main UI page "
        "answering with its content. A smoke check asserts what the user would see, it is not a test suite.",
        "Use cases: the journeys to verify are the `## Use Cases` of docs/harper/SPEC.md (`UC-nn`, steps "
        "`UC-nn.n`). The smoke checks of the profile and scripts/check_solution_local follow the use cases that can "
        "run (one check per use case, named after it, e.g. `uc-03-sign-in`), the modes too (`--oidc`, `--live` when "
        "the solution has them). FINALIZE_REPORT.md has a `## Use cases` table: UC, name, verified by (the check or "
        "the local step), status — verified in the sandbox | verified on the developer machine | needs the developer "
        "(real identity provider, real external service: which command and which values) | not covered (why). A SPEC "
        "without use cases: say so in that section and verify the main capabilities as above.",
        "Repeatable checks: the developer's database already holds data (earlier runs, demo data, work done by "
        "hand), and scripts/check_solution_local runs again and again on it. A smoke journey creates what it "
        "needs under new names every run (a client, product or campaign of its own, unique per run) and never "
        "assumes an empty database; it must pass the second time as the first (B2B v3: a 409 on a company the "
        "demo data already held).",
        "Configuration examples are usable as they are: a structured variable (a JSON or YAML value, a list) gets a "
        "minimal valid example value in its example file, with obvious placeholders for secrets and identifiers, "
        "never only a name or a sentence; every mode the solution has (default, an identity provider, live, …) has "
        "its example file. The profile has a check that loads every example with the solution's own configuration "
        "loader, so an example that does not parse fails the verification (B2B v3: ten JSON settings of the live "
        "mode had no example value).",
        "Private files stay private in every mode: every file or folder the scripts write that holds local values "
        "(the local configuration, generated secrets, an identity provider's import, caches) is in .gitignore, for "
        "every start option, not only the default one; the report lists them (B2B v3: the realm import with the "
        "local passwords under .runtime/ was not ignored). CLike's local check fails when the run leaves files git "
        "does not ignore.",
        "Configuration: the solution runs with configuration only, never with code edits. Every variable the solution "
        "reads is in .env.example (or the ecosystem equivalent) with its purpose; in the profile it is provisioned "
        "(token, uuid, template, postgres_database, service) or `external` when only the developer can give it "
        "(a real provider key). Checks that need an external value are non-blocking.",
        "Reports, caches and temp files only under CLIKE_EVAL_REPORT_DIR / CLIKE_EVAL_TEMP_ROOT. No hardcoded secrets.",
        "Ready for the developer: scripts/setup_local.sh and .ps1 create the local configuration (.env or the ecosystem "
        "equivalent, git-ignored) from .env.example when it is missing — local URLs and ports, generated local secrets "
        "and tokens, the local database — never overwriting a value already set, and print the external values still "
        "to fill in. scripts/start_solution_local.sh and .ps1 start the whole solution with that configuration (setup "
        "first when needed) and print its URLs. scripts/check_solution_local.sh and .ps1 run the profile's steps "
        "(setup, install, build, start, smoke, stop).",
        "Host ports on the developer's machine: other programs already listen there (the sandbox ports being free "
        "proves nothing). Every published host port comes from the local configuration, never a fixed number in "
        "compose files or scripts; setup checks each one is free and, when it is taken, picks a free one, writes it "
        "and every value derived from it (origins, URLs) and says which it changed; start checks the ports again "
        "before starting and names the port and the variable to change when one is taken. The report lists the "
        "ports and their variables.",
        "Container runtime on the developer's machine: scripts that use containers detect what is installed — "
        "`docker compose`, `podman compose` or `podman-compose` (many developers run Podman, not Docker) — and say "
        "exactly which is missing. When the solution also runs natively (as the profile runs it in the sandbox), the "
        "start and check scripts offer that native path when no container runtime is available, with the language "
        "versions it needs.",
        "Listening address: the sandbox runs the services natively on loopback, the containers run them bound to "
        "every interface (0.0.0.0) and reach them through published ports. Nothing may depend on the address a "
        "server listens on: origin, CSRF and redirect checks compare the configured public origin with the request's "
        "Host/Origin headers, never with the URL the server builds from its own bind address (a check that passes on "
        "127.0.0.1 and refuses every request on 0.0.0.0 breaks the containers). In the profile, web services listen on "
        "every interface, as in the containers, and are reached through 127.0.0.1.",
        "Local values that expire (generated fixture sessions, tokens, demo identities): setup renews them when they "
        "have expired, keeping their identifiers, so the solution still starts weeks later; start never stops on an "
        "expired generated value without renewing it.",
        "After the sandbox verification passes, CLike runs scripts/check_solution_local on the developer's machine — "
        "the default start, with containers when a runtime is installed; when it fails, its output comes back to you "
        "as a failed check `local::check_solution_local` to fix like the others.",
        deploy_rule,
        f"Write {REPORT_PATH}, the report of this /finalize for the developer, exhaustive and specific: (1) what the "
        "solution is and its components; (2) how to start it (the one command, what it starts, the URLs) and how to see "
        "each main capability (page or request, what to do, what to expect); (3) configuration: a table of every "
        "variable — purpose, value or how it is generated, who sets it (setup script, provisioned, developer), required "
        "or optional; (4) MISSING INFORMATION: every value or decision only the developer can provide — what, why it "
        "is needed, where to get it, where to put it, what does not work without it (write 'none' when nothing is "
        "missing); (5) everything this /finalize did, file by file: the change and why (the problem found, its cause, "
        "the fix); (6) problems met during the verification and how each was solved; (7) limitations left, with the "
        "reason. Facts only, from the files and the errors you saw. When the report already exists (an earlier "
        "/finalize run or repair cycle), extend it: keep the earlier entries of (5) and (6), marked with their run, and "
        "add this run's — a change an earlier run made is not 'already present', it is part of this /finalize.",
        "Make the profile pass by fixing code, configuration and wiring (composition roots, settings, routes, scripts) inside "
        "your write roots. The promoted tests under test/ are the REQs' acceptance: do not change them.",
    ]


def req_profiles_text(req_profiles: Any) -> str:
    """How the promoted REQs ran: their environment (variables, tools) and services, bounded. Their
    checks are left out: the solution profile does not run the REQs' test suites again."""
    items = [
        {k: v for k, v in p.items() if k in ("req", "run_from", "environment", "services")}
        for p in (req_profiles or []) if isinstance(p, dict) and p.get("req")
    ]
    items = [p for p in items if p.get("environment") or p.get("services")]
    if not items:
        return ""
    text = json.dumps(items, indent=1, ensure_ascii=False)
    if len(text) > _PROFILES_BUDGET:
        text = text[:_PROFILES_BUDGET] + "\n… (truncated: read runs/kit/<REQ>/ci/LTC.json)"
    return text


def solution_repair_rules() -> List[str]:
    return [
        f"The solution eval ({SOLUTION_PROFILE}) failed: its errors are below. Read ALL of them before changing anything, "
        "group them by root cause (one cause often fails install, build, start and smoke) and fix every cause in this run.",
        "Find the cause in this order: configuration (a variable missing or wrong, a URL, port or host, a service not "
        "ready or started in the wrong order, a migration not run), a native tool missing (declare it in "
        "environment.tools), the wiring (composition root, routes, settings), then the code. A missing variable is "
        "provisioned in the profile and documented in .env.example, never hardcoded.",
        "Fix the code, the configuration, the scripts and the wiring. A profile command that is wrong (path, flag, cwd) may "
        "be fixed; never remove a check, make it non-blocking or weaken a smoke check.",
        "A check that ran and failed (an error response, a page without its content, a module not found, a timeout) is a "
        "defect of the solution, not of the sandbox.",
        f"Update {REPORT_PATH}: add each problem of this cycle, its cause and the fix.",
    ]


def cloud_finalize_section(verify: Dict[str, Any], deployment: str = "") -> str:
    """Section appended to the cloud /finalize prompt."""
    lines = ["## SOLUTION VERIFICATION — ci/SOLUTION_LTC.json (CLike runs it after /finalize)", ""]
    lines += [f"- {rule}" for rule in solution_verify_rules(deployment)]
    lines += [f"- Emit `BEGIN_FILE {SOLUTION_PROFILE}` … `END_FILE` (valid JSON) whenever runnable code exists under src/."]
    profiles = req_profiles_text(verify.get("req_profiles"))
    if profiles:
        lines += ["", "### Environments and services of the promoted REQs", "```json", profiles, "```"]
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
        "and fix what fails: the solution must run on the developer's PC as HOWTO_RUN says. When your sandbox cannot "
        "reach the container runtime, say so in the report: CLike runs the check on the developer's machine after you.",
    ]
    profiles = req_profiles_text(verify.get("req_profiles"))
    if profiles:
        lines += ["- Environments and services of the promoted REQs (also under runs/kit/<REQ>/ci/LTC.json):", "```json", profiles, "```"]
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
