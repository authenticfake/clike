# Auto-eval: governed KIT ⇄ EVAL repair loop

Auto-eval turns a failing `/eval` into a bounded repair loop. The model gets the **real** failures
of the canonical eval and fixes the code; the acceptance criteria stay locked. A REQ is promotable
only when its own checks pass **and** it does not break what is already promoted.

```
/eval REQ-002 --fix
  EVAL (sandbox) ── PASS ─────────────────────────────▶ done → /gate REQ-002
     │ FAIL
     ▼
  KIT repair (cycle 1/2): failed checks + current candidate files (+ hint)
     ▼ files written by the extension
  EVAL ── PASS ──▶ done
     │ FAIL
     ▼
  KIT repair (cycle 2/2) → EVAL ── still failing ──▶ stop, report what fails
```

## How to use it

| What | Command / setting |
|---|---|
| Evaluate and repair | `/eval REQ-002 --fix` |
| Repair with guidance | `/eval REQ-002 --fix "price() must stay in pricing.py; add the discount in checkout"` |
| Continue after the loop stopped | run `/eval REQ-002 --fix ["hint"]` again: it restarts from the current files, with a new cycle budget |
| Repair a failing gate | `/gate REQ-002 --fix ["hint"]` (see [Auto-gate](#auto-gate-gate---fix)) |
| Run it automatically after every `/kit` | `clike.autoEval.afterKit: true` (default `false`) |
| Number of repair cycles | `clike.autoEval.maxCycles` (default `2`, max `5`) |
| Extra cycles while improving | `clike.autoEval.extraCyclesOnProgress` (default `3`): after `maxCycles`, the loop goes on as long as each cycle leaves fewer failing checks |
| Agent re-runs failed checks in the sandbox | `clike.autoEval.agentEvalChecks` (default `8` runs per repair, `0` = off) |
| Re-check the promoted REQs | `clike.eval.regression` (default `true`) |
| Make warnings block the gate | `clike.gate.strictWarnings` (default `false`) |

Then promote as usual with `/gate REQ-002`.

The hint is **optional**. Without it the repair works from the failures alone, plus CLike's own
diagnosis (below); with it, both reach the repair. What each cycle received is written next to the
report: `runs/eval/<REQ>/repair_<REQ>_<ts>.md` (`runs/gate/...` for `/gate --fix`), and the chat
shows its path.

## What the repair model receives

- **Every failed check with its errors**, not the tail of its output: the eval runner extracts the
  error blocks of the whole output (failed tests, assertions, TypeScript/lint errors, code frames,
  the final summary) without ANSI codes, DOM dumps, passing-test lines and library stack frames
  (`excerpt` in the eval report, ≤ 6000 characters per check).
- Checks with the **same errors** (unit and coverage run the same tests) are listed once.
- Non-blocking failures of the **regression of other REQs** (their coverage) are left out: they do
  not fail the eval and this REQ cannot fix them. A blocking regression failure (this REQ broke a
  promoted REQ) is included.
- A test that ran and failed is **never classified as environment-blocked** (`element(s) not
  found`, a module of the candidate not found): only missing tools, registries, native binaries and
  sandbox limits are.
- **An eval sandbox out of resources stops the loop.** When the OS refuses a process, a thread,
  memory or disk (`spawn node EAGAIN`, `pthread_create: Resource temporarily unavailable`, `ENOMEM`,
  `ENOSPC`, `EMFILE`) the check is environment-blocked and the report says
  `EVAL_SANDBOX_EXHAUSTED` (gate: `GATE_BLOCKED_SANDBOX_EXHAUSTED`): `--fix` stops instead of
  changing correct code, and a local agent's `eval-check` answers `BLOCKED`. An eval does not start
  when the sandbox already uses 60% of its process limit. The sandbox runs with an init (`init:
  true`) that reaps the processes the checks orphan, and what a check leaves running in its process
  group (a server, a browser) is stopped when it ends; `GET /health` of the sandbox shows the
  processes in use, the zombies and PID 1. To recover: `podman restart docker_eval-sandbox_1`.
- **Cloud**: the files named in the errors first, then tests, sources, the eval profile and CI, then
  the KIT docs (160k characters). CLike's own context files (`CLIKE_SELECTED_CAPABILITY_CONTEXT.*`,
  `AGENT_PROMPT.md`, `FILE_REQUIREMENTS.json`…) and lockfiles are listed, not shown.
- **Local agent** (Codex, Claude Code): the same errors in its prompt, and it can **re-run the failed
  checks in the real eval sandbox** while it repairs: `node .clike/bin/eval-check.mjs test:unit
  test:e2e` (composed workspace, provisioned variables, services of other REQs), so it iterates
  until they pass in one session. The extension serves the requests (it holds the token; the agent
  gets neither the token nor network access), up to `clike.autoEval.agentEvalChecks` runs. Such a
  partial run is never the REQ's verdict: the full eval follows.

## CLike diagnosis: intermittent failures

Before each repair CLike reads the earlier eval and gate reports of the REQ
(`runs/eval/<REQ>/report_*.json`, `runs/gate/<REQ>/report_*.json`). Each report stores
`inputs_fingerprint`, a hash of what the run used: the canonical `src/`, `test/`, `tests/` and the
KIT (`src/`, `test/`, `tests/`, `ci/`). Installed dependencies and CLike's promotion leftovers
(`.conflict-…`, `.incoming-…`) are not counted. A failing check that passed earlier is flagged:

- **passed on the same code** (same fingerprint): its errors reach the repair behind a note such as

  > CLike note: test_foreign_records passed in 3 of 5 earlier eval/gate run(s) of this REQ on the
  > same code (src/, test/ and the KIT unchanged), so the failure is nondeterministic (order of
  > rows or jobs by random ids, timing, concurrency, unseeded randomness): make the behavior
  > deterministic in src/, do not adjust the asserted value.

- **passed only on other code** (or in a report without a fingerprint): the note says that the
  code changed since then and that the failure most likely comes from that change, not from
  nondeterminism.

The note names the test when its id appears as `PASSED` in an earlier output, else the check. The
chat says `ℹ AUTO-EVAL REQ: <check> passed in earlier runs`. Why it matters: from a single failing
run (`assert 1 == 3`) a model tends to change the value; the history is what shows that the code
is not deterministic. The tests stay locked either way.

## Auto-gate: `/gate --fix`

`/gate` re-runs every check and the regression of the promoted REQs, so it can fail where the
last eval passed (an intermittent test, a change in the canonical tree). `/gate REQ --fix ["hint"]`
then runs the same loop as `/eval --fix`, driven by the gate verdict:

```
/gate REQ-006 --fix
  GATE ── PASS ──▶ promotion (auto-merge) → done
    │ FAIL (checks, regression, required outputs)
    ▼
  KIT repair (same failures shape, same governance, same CLike diagnosis)
    ▼
  GATE (full) ── PASS ──▶ promotion
    │ FAIL → next cycle, or stop (same limits as /eval --fix)
```

- Same rules as `/eval --fix`: tests locked, test/ci changes governed, `clike.autoEval.maxCycles`
  and `extraCyclesOnProgress`, stop on no progress or a failed KIT request.
- A repaired candidate is promoted only by a gate that ran on it: there is no eval in between,
  the gate runs the same checks and more.
- Missing required outputs (`GATE_BLOCKED_REQUIRED_OUTPUTS_MISSING`) reach the repair as failures
  `required-output::<role>`.
- It stops without repairing on a tampered acceptance surface (`GATE_BLOCKED_ACCEPTANCE_TAMPERED`:
  restore the files or re-run `/kit`) and on a manual override.
- A gate **PASS whose promotion left conflicts** ends the loop: the conflict is a merge with the
  canonical tree (`<file>.conflict-<REQ>-<ts>`), not a defect of the candidate, and a KIT repair
  cannot resolve it. Resolve it, commit, and run `/gate REQ` again.
- Messages: `↻ AUTO-GATE REQ: repair cycle n/m`, `✔ AUTO-GATE REQ: gate PASS after n repair
  cycle(s)`, `✖ AUTO-GATE REQ stopped: <reason>`.

Even when the gate passes after a repair of an intermittent failure, look at what the repair
changed (`src/` of the KIT): a passing run of a nondeterministic test may still be luck.

## Time of a cycle

A cycle is: the repair (the agent verifies its fix with eval checks, ~1 minute each), then the
full eval. To keep it short and stable:

- the eval right after a repair runs **without the local-agent pre-pass**: the repair already
  changed and checked the candidate; a pre-pass changed it again unverified (it once undid a repair
  that had made the unit tests pass) and cost 3–5 minutes per cycle;
- the **regression of the promoted REQs runs only once the REQ's own blocking checks pass**: while
  they fail the REQ is not promotable anyway, and the regression (every other REQ's environment,
  services and suites: ~4 of the ~6 minutes of a full eval in a 5-REQ project) would only delay
  the loop. `/gate` is unaffected: it needs the REQ's checks to pass, then runs the regression.

## When the loop stops

| Outcome | Message | What to do |
|---|---|---|
| Eval passes | `✔ AUTO-EVAL REQ-002: eval PASS after N repair cycle(s)` | `/gate REQ-002` |
| Cycles exhausted | `still failing after N repair cycle(s)` and the failing checks | read the eval report, re-run with a hint, or fix manually |
| No progress | `no progress: the same checks still fail` (same checks **and** same errors; different errors in the same check are progress) | a hint usually helps; or the failure is environmental |
| Repair request failed | `the KIT repair request failed` | see the error in the chat (provider, validation) |
| Acceptance surface changed | `the acceptance surface (test/ or ci/) changed after the lock` | tests/LTC were edited outside the governed path: re-run `/kit` to re-baseline |
| Nothing to repair | `eval failed without failing checks` | see the eval report (e.g. integrity or setup errors) |

The same outcomes apply to `/gate --fix` (`AUTO-GATE`, `gate failed without failing checks`).

## What the repair may change (governance)

The repair prompt (cloud) and the orchestrator enforce the same rules:

- **Source and docs** (`runs/kit/<REQ>/src/**`, `docs/**`): free to change. Only the changed files
  are returned; the others stay as they are.
- **Tests** (`runs/kit/<REQ>/test/**`): **locked**. They are the acceptance criteria taken at the
  first eval: the repair makes the code pass them. Other changes are rejected
  (`repair_change_rejected:...`) and never written. Two exceptions, both checked by the
  orchestrator on the AST and audited:
  - *unused imports* (lint failures): a Python test may only drop imports;
  - *the test itself is wrong*: when the eval shows an error raised **in the test file** that is
    not a failed assertion (`TypeError`, `AttributeError`, `NameError`, `ImportError`, a missing
    fixture — e.g. a wrong API call), or a type checker error reported on it (mypy
    `test_a.py:286: error: … [arg-type]`, pyright, TypeScript `error TS…`), the test is fixed, not the code. Every test function, every
    `assert` and every `pytest.raises/warns/approx` must stay identical and no skip/xfail may be
    added. The fix is reported as `repair_test_fixed_review_required:<file>` and the gate shows
    `review_required: true` (VS Code: *REVIEW* in the gate message) so the developer checks it.
- **`ci/LTC.json`**: only the *command* of a check that cannot run may be fixed (wrong path,
  module or flag). Removing a check, making it non-blocking or weakening it is rejected, with one
  exception: a check the eval shows needs a **container runtime** (docker, podman, compose — the
  sandbox has none) may become `"blocking": false`; it stays runnable on the developer's machine.
  The checks are read in every shape the runner accepts (`checks`, `cases`, `commands`). Accepted
  changes are recorded as audited amendments of the acceptance lock
  (`audit/acceptance_amendments.jsonl` in the CLike state directory) and reported as
  `repair_amendment_accepted:...`.
- **Other `ci/**`** (e.g. `ci/requirements.txt`): accepted and audited, so the repair can upgrade
  vulnerable dependencies. Vulnerable dependencies keep blocking the gate until upgraded.
- **Environment failures** (network, missing system tool) are not "fixed" in code: the model
  documents them in `docs/KIT_<REQ>.md`.
- **Local agents**: the changes it made to locked files are governed (the rejected ones restored)
  *before* the phase commit, so git never holds a change CLike then reverts.

The eval sandbox has Python 3.12, Node 22, Java 21, Chromium's system libraries and the PostgreSQL
client tools (`psql`, `pg_dump`, `pg_restore`, major 18: they also work with older servers; build
argument `PG_CLIENT_MAJOR`). It has no container runtime and no privileges.

With a local agent (Claude Code, Codex) the repair follows the same rules:
- the agent package carries the failed checks, the hint and the rules
  (`repair_context.auto_eval`), since the canonical eval reports stay in the sandbox;
- the agent writes directly, so the extension snapshots `test/` and `ci/` before the repair and
  submits what changed to `POST /v1/acceptance/amend` (with the previous content). Accepted
  amendments are audited; rejected changes and deleted files are restored
  (`↺ AUTO-EVAL ... restored`).

Follow-up KIT stages (`/kit REQ --integrity|--hardener|--promotion-eval`) work on the current
candidate: they do not start a new KIT generation, and once the tests are locked (first eval)
their changes to `test/` and `ci/` go through the same governance as a repair.

## Promotability: regression of promoted REQs (L2)

With `clike.eval.regression` (default on), `/eval` and `/gate` also run the acceptance checks of
every promoted REQ (`status: done` in `plan.json`) with **their own LTC commands**, against their source with the candidate's composed source
overlaid on top, i.e. the code as it would be after promotion. These cases appear as
`regression::<REQ>::<check>`, run in `runs/eval/<REQ>/regression/<OTHER>/` (the other REQ's own
eval results are not touched), and their acceptance locks are verified first.

Only behavioural checks of the promoted REQ block (tests, contract/e2e checks). Its lint, types,
security, build and coverage checks now also measure the candidate's code, which the candidate's
own checks already cover: they are reported as non-blocking warnings, and so is a test check whose
only failure is the coverage threshold.

Dependencies that are not promoted yet are not regression targets: their source is already part
of the candidate's eval (promoted `src/` + dependency KITs + current KIT), and a REQ that never
passed has nothing to regress from.

A REQ that passes its own tests but breaks a promoted REQ fails the eval; the gate reports
`GATE_BLOCKED_REGRESSION` with the list in `regression_failures`. In an auto-eval loop the
regression failures are part of what the repair receives.

## Required outputs in the eval

Required outputs missing from the candidate (FILE_REQUIREMENTS, e.g. a runnable launcher) block
the gate (`GATE_BLOCKED_REQUIRED_OUTPUTS_MISSING`). The eval reports them too, as failed checks
`structure::<role>` with what is accepted, so the auto-eval repair can add them. A launcher is a
conventional entry file (`main.py`, `app.py`, `__main__.py`, `server.js`, `Program.cs`, …) or a
source file that starts the application (`if __name__ == "__main__"`, `FastAPI(...)`,
`def create_app(...)`, `.listen(...)`).

## Browser (e2e) checks

The sandbox image carries Chromium's system libraries. When a Playwright check fails because the
browser is not downloaded, the EvalRunner downloads Chromium in the version of the project's
Playwright (`npx playwright@<version> install chromium`) and runs the check once more; the report
says so. The download needs egress and memory (see `docs/development.md`).

## Native tools of the sandbox (`/tools`)

The image has Python, Node, a Java runtime, Chromium's libraries and the PostgreSQL client tools.
Any other native program a check runs — a database or messaging client (`mysqldump`, `mongodump`,
`kcat`), a cloud or IaC CLI (`aws`, `az`, `gcloud`, `kubectl`, `helm`, `terraform`), a toolchain
(`jdk@17`, `mvn`, `gradle`, `dotnet`, `go`) — comes from CLike's **tools catalog**
(`orchestrator/eval_tools_catalog.yaml`, conda-forge, linux-64 and linux-aarch64), installed into a
volume the sandbox mounts read-only and appends to the PATH of the checks (never before the
image's own programs).

CLike finds what an eval needs **before** running it:

- *declared*: `"environment": {"tools": ["kcat", "jdk@17"]}` in `ci/LTC.json` (the KIT rules ask
  for it);
- *used*: a catalog program the KIT's code, tests or scripts run (`"pg_dump"`, `["kcat", …]`, a
  script line `aws s3 ls`);
- *failed*: a check that stopped on a missing program (`kcat: command not found`, `spawn kcat
  ENOENT`, `No such file or directory: 'kcat'`, `Cannot run program "mvn"`): it is
  environment-blocked (`missing_tools` in the report), never sent to a repair.

What is missing is installed after the developer's confirmation (VS Code: *Install*, *Always for
this project*, *No*; `clike.evalTools.install`: `ask` | `always` | `never`); tools listed in
`.clike/eval-tools.yaml` (`tools:`) install without asking, so a team shares the same tools. A
check that stopped on a missing tool runs again once it is installed; without an answer within 5
minutes the eval runs without it, and `--fix` stops saying how to install it. A project can add
other conda-forge packages under `custom:` in the same file. Libraries of a language (psycopg,
ojdbc, kafka-python…) are not tools: the project's manifests install them.

`/tools` lists the catalog and what is installed, `/tools search <text>` finds an entry, `/tools add
<tool>[@version]…` installs and approves for the project, `/tools remove <tool>` withdraws the
approval. The installs run in the `eval-tools` service: only the orchestrator reaches it (its own
network), no credentials, conda-forge packages only (no scripts or URLs), versions recorded in
`/opt/clike-tools/installed.json` and returned to the chat.

## Eval disk

Eval directories (composed workspaces, `node_modules`, venvs) are caches on the sandbox volume.
Before an eval CLike keeps the directories of the 3 REQs of the project used last
(`CLIKE_EVAL_KEEP_REQS`) and, when the volume has less than 10 GB free (`CLIKE_EVAL_MIN_FREE_GB`),
removes the least recently used ones of any project; below 2 GB free the eval does not start
(`EVAL_SANDBOX_EXHAUSTED`, with how to free the Podman disk). The npm cache is one per project,
shared by the REQ, its regression and its services.

## Gate warnings policy

A *warning* is a failed check marked `blocking: false` in the LTC (style, optional scans).

- Default: warnings are reported and the gate passes with `reason_code: GATE_PASS_WITH_WARNINGS`.
- Strict: `clike.gate.strictWarnings: true` (per workspace) or `CLIKE_GATE_STRICT_WARNINGS=1`
  (orchestrator, for all projects) → `GATE_BLOCKED_WARNINGS_PRESENT`.

## API

| Endpoint | Field | Meaning |
|---|---|---|
| `POST /v1/eval/run`, `POST /v1/gate/check` | `regression: true` (body) | add the regression stage |
| `POST /v1/gate/check` | `strict: true` (body) | warnings block the gate |
| `POST /v1/acceptance/amend` | `req_id`, `changes`, `previous`, `evidence` | govern the acceptance files a local agent changed: `{accepted, rejected, test_fixes, audit_id}` |
| `POST /v1/harper/run` (phase `kit`) | `kit.repair: {cycle, max_cycles, failures, files, hint}` | KIT repair request; `failures[]` = `{name, code, command, output}`, `files[]` = `{path, content}` |

`kit.repair: true` keeps its previous meaning (BMAD developer repair pass, `/kit REQ --repair`).

Gate responses add `regression`, `regression_failures` and `strict_warnings`.

## Measuring it

The benchmark runs the same loop without the extension:

```bash
python benchmark/run_benchmark.py --runner cloud --projects pingboard --auto-eval 2
```

The summary has a *Repair cycles* column; see `benchmark/README.md`.

## Not yet covered (L3)

An end-to-end smoke test of the whole solution (all promoted REQs started together, e.g. at
`/finalize`) is planned; today regression runs each REQ's own acceptance checks.
