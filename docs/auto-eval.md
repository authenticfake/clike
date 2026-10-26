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
| Stop an eval, a gate or a `--fix` loop | **Cancel** in the chat (or `cancel_run` over MCP): the eval running in the sandbox, the repair agent and the next cycles stop; a cancelled agent's files are not sent to the orchestrator |
| Run it automatically after every `/kit` | `clike.autoEval.afterKit: true` (default `false`) |
| Number of repair cycles | `clike.autoEval.maxCycles` (default `2`, max `5`) |
| Extra cycles while improving | `clike.autoEval.extraCyclesOnProgress` (default `3`): after `maxCycles`, the loop goes on as long as each cycle leaves fewer failing checks, or fewer failing checks of the REQ itself (the regression of the promoted REQs runs only once those pass: its failures are new, not a step back) |
| Targeted re-eval | after a repair of regression failures, the next eval runs every check of the REQ and the regression of the promoted REQs that failed only (`regression_reqs`, minutes instead of the whole set); when it passes, a full eval confirms it in the same cycle — taking the results the targeted eval just produced on the same inputs (the REQ's checks, the regression of those promoted REQs; marked *Reused*) and running the rest. A targeted eval is never the REQ's verdict (`partial`, not promotable, not reused by the gate) |
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
  sandbox limits are. A missing module that is a file of the project (`No module named
  'req019_support'`, `Cannot find module 'x'` where `x` is a project source file, outside
  `node_modules` / venvs) is a wrong import or path, any language: it goes to the repair as a
  failure. A missing dependency stays environment-blocked.
- **An eval sandbox out of resources stops the loop.** When the OS refuses a process, a thread,
  memory or disk (`spawn node EAGAIN`, `pthread_create: Resource temporarily unavailable`, `ENOMEM`,
  `ENOSPC`, `EMFILE`), **or the kernel killed processes for lack of memory or held the sandbox at its
  memory limit while the check ran** (read from the cgroup counters: a check under memory pressure fails
  with time-outs and no `ENOMEM` in its output), the check is environment-blocked and the report says
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
  `regression::<REQ-ID>` (e.g. `regression::REQ-014`) re-runs a promoted REQ's checks with the
  candidate overlaid, as the regression does: a repair of a regression failure is verified before
  the full eval. Only the checks the repair was given decide: a failure the eval marks non-blocking
  (already failing without the candidate, unstable, a warning) prints `WARN … not yours to fix` and
  does not make the result `FAIL`; when every given check passes the result says `DONE … finish
  now`. On a real project an agent whose two checks passed at its second run went on for 25 more
  minutes chasing non-blocking coverage checks.

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
  restore the files, accept a deliberate non-weakening edit with `/eval <REQ> --accept "reason"`,
  or re-run `/kit`) and on a manual override.
- A gate **PASS whose promotion left conflicts** ends the loop: the conflict is a merge with the
  canonical tree (`<file>.conflict-<REQ>-<ts>`), not a defect of the candidate, and a KIT repair
  cannot resolve it. Resolve it, commit, and run `/gate REQ` again.
- Messages: `↻ AUTO-GATE REQ: repair cycle n/m`, `✔ AUTO-GATE REQ: gate PASS after n repair
  cycle(s)`, `✖ AUTO-GATE REQ stopped: <reason>`.

Even when the gate passes after a repair of an intermittent failure, look at what the repair
changed (`src/` of the KIT): a passing run of a nondeterministic test may still be luck.

## Unattended: `/autopilot`

`/autopilot` chains, for every REQ of the plan, `/kit`, `/eval --fix` and `/gate` through the same
handlers (any executor), so the loop above runs for each REQ without anyone typing. A REQ whose
loop stops is parked with the reason and the REQs that do not depend on it go on; a provider quota
or rate limit waits and retries. See [commands.md](commands.md#autopilot).

## Following a run

The chat's run card and the status bar follow the loop step by step: each eval, repair and gate with
its outcome and duration, the cycle (`cycle 2 of 2 (+3 while failures drop)`), an estimate from the
same step's previous duration. During an eval or a gate the sandbox reports its progress
(`GET /v1/eval/progress?req_id=…`: setup, checks done of total and the check running, then the
promoted REQs of the regression being re-run), polled every 2 s. **After this step** ends the loop at
the next step boundary (the eval in flight finishes and keeps its report; no new repair starts);
re-run `/eval REQ --fix` to go on. **Stop now** stops the check running in the sandbox, as Cancel.

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
| No progress | `no progress: the same checks still fail` (same checks **and** same errors; different errors in the same check are progress; numbers, ids and random values such as session tokens printed by the test do not make an error different) | a hint usually helps; or the failure is environmental |
| Repair request failed | `the KIT repair request failed` | see the error in the chat (provider, validation) |
| Acceptance surface changed | `the acceptance surface (test/ or ci/) of REQ-002 changed after the lock: ci/LTC.json modified` | tests/LTC of that REQ (the candidate, or a promoted REQ its regression runs) were edited outside the governed path: edited on purpose and nothing weakened → `/eval REQ-002 --accept "<why>"` (audited); otherwise restore them or re-run `/kit` |
| REQ not KIT-ready | `stopped before a repair: not KIT-ready, the plan waits for your answers: …` (the plan marks it `kit_ready: false`; no hint given) | answer in the SPEC Note section and run `/spec`, `/plan`, `/kit`; or `/eval REQ-002 --fix "<your decisions>"` to give the answers to the repair |
| Repair changed a locked test without proof | `stopped: the repair says a locked test is wrong … Its change is saved: runs/eval/<REQ>/proposed_test_fix_<ts>.patch` (the lock restored the test; the eval showed no error raised in the test itself) | review the patch: if the test is wrong, `/eval REQ-002 --accept "<why>"` applies it and records your reason (audited); if the code is wrong, `/eval REQ-002 --fix "<hint for the code>"` |
| Nothing to repair | `eval failed without failing checks` | see the eval report (e.g. integrity or setup errors) |

The same outcomes apply to `/gate --fix` (`AUTO-GATE`, `gate failed without failing checks`).

## What the repair may change (governance)

The repair prompt (cloud) and the orchestrator enforce the same rules:

- **Source and docs** (`runs/kit/<REQ>/src/**`, `docs/**`): free to change. Only the changed files
  are returned; the others stay as they are.
- **Tests** (`runs/kit/<REQ>/test/**`): **locked**. They are the acceptance criteria taken at the
  first eval: the repair makes the code pass them. A test file the lock does not hold (new, or added by an
  earlier repair, e.g. a reconciled test of a promoted REQ) is not locked: it is kept as written,
  by a cloud model or a local agent alike. Other changes are rejected
  (`repair_change_rejected:...`) and never written. Two exceptions, both checked by the
  orchestrator on the AST and audited:
  - *unused imports* (lint failures): a Python test may only drop imports;
  - *the test itself is wrong*: when the eval shows an error raised **in the test file** that is
    not a failed assertion (`TypeError`, `AttributeError`, `NameError`, `ImportError`, a missing
    fixture — e.g. a wrong API call; or a test that contacts a reserved name that never resolves,
    such as `example.test`, its stack in the test file), or a type checker error reported on it (mypy
    `test_a.py:286: error: … [arg-type]`, pyright, TypeScript `error TS…`), the test is fixed, not the code. Every test function, every
    `assert` and every `pytest.raises/warns/approx` must stay identical and no skip/xfail may be
    added (JS/TS tests: every test title and `expect` line). When the error is on an assertion
    line itself, only the API misuse the eval proves may change there, expected values kept:
    an option or keyword argument the type checker or the runtime reports as unknown on that line
    is removed (TypeScript `'exact' does not exist in type 'ByRoleOptions'`, mypy `Unexpected
    keyword argument "exact"`, pyright `No parameter named`, Python `got an unexpected keyword
    argument`), and a regex-shaped string that a pattern matcher (`toMatch`, `toThrow`,
    `toHaveText`, …) compared literally — the failure shows the received value matching it as a
    regex — becomes the same regex literal. The orchestrator applies exactly these corrections to
    the locked test and requires the repaired one to be identical; anything else is rejected.
    The fix is reported as `repair_test_fixed_review_required:<file>` and the gate shows
    `review_required: true` (VS Code: *REVIEW* in the gate message) so the developer checks it.
  - *a failed assertion the repair is sure comes from the test* (a helper, fixture or setup that
    contradicts the SPEC/PLAN, e.g. an HTTPS-only helper on a local HTTP origin): the repair writes
    the smallest correction in the REQ's own test instead of only describing it. The lock restores
    the test, CLike saves the change as `runs/eval/<REQ>/proposed_test_fix_<ts>.patch` and stops
    the loop; `/eval <REQ> --accept "<why>"` applies it and records the reason.
- **`ci/LTC.json`**: only the *command* of a check that cannot run may be fixed (wrong path,
  module or flag). Removing a check, making it non-blocking or weakening it is rejected, with one
  exception: a check the eval shows needs a **container runtime** (docker, podman, compose — the
  sandbox has none) or **waits for a person** (an observation, a sign-off, a manual verification:
  the eval output says so) may become `"blocking": false`; it stays runnable on the developer's
  machine, described in `ci/HOWTO.md`.
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

## Promotability: the acceptance criteria are delivered

Passing checks are not enough: a check can only fail for what it tests. Every KIT writes
`runs/kit/<REQ>/docs/ACCEPTANCE.json`, one entry per acceptance criterion of the plan:

```json
{"criteria": [
  {"id": "REQ-038-A01", "status": "done", "checks": ["tests", "unit"]},
  {"id": "REQ-038-A06", "status": "missing", "note": "the adapter probes are not implemented"},
  {"id": "REQ-038-A07", "status": "developer_evidence", "note": "a real IT+GB research on the developer machine"}
]}
```

The eval adds a blocking check `acceptance::coverage`. It fails when a criterion is `partial` or
`missing`, is not in the file, or is `done` without a blocking check of `ci/LTC.json` that verifies
it; the repair receives the list and implements what is left. `developer_evidence` (only for what
the criterion itself says is proved on the developer machine or by a real external service) is
reported, not blocking. Without the file, a `SELF_REVIEW.md` that declares the KIT incomplete
("not complete or promotable", "remains unimplemented") blocks the same way, and so does a file
that says everything is done while the self review says otherwise. Nothing declared either way
(KITs written before this rule): the checks decide, as before.

## Promotability: regression of promoted REQs (L2)

With `clike.eval.regression` (default on), `/eval` and `/gate` also run the acceptance checks of
every promoted REQ (`status: done` in `plan.json`) with **their own LTC commands**, against their source with the candidate's composed source
overlaid on top, i.e. the code as it would be after promotion. These cases appear as
`regression::<REQ>::<check>`, run in `runs/eval/<REQ>/regression/<OTHER>/` (the other REQ's own
eval results are not touched), and their acceptance locks are verified first.

Only behavioural checks of the promoted REQ run and block (tests, contract/e2e checks, with the
installs and builds they need). Its static checks — lint, format, types, security scans, coverage,
syntax, SBOM/licence — passed at its own gate and would now measure the candidate's code, which the
candidate's own checks already cover: they are **not run** in the regression (one non-blocking
`static-checks::not-run` case lists them). A test check whose only failure is the coverage threshold
is a warning.

A promoted REQ's **own regression checks** (a check named `regression`, `test:backend-regression`,
… — they re-run tests of earlier REQs, often copies of them in its KIT) are not run in its
regression either: those earlier REQs are regressed themselves, on their promoted tests
(`regression-checks::not-run` lists them). A REQ whose only test check is called `regression` keeps
it. The KIT prompt (cloud and local agents) asks not to copy other REQs' tests into a KIT nor to add
such checks. The same holds for the **candidate's** own eval when it includes CLike's regression: its
`regression` checks would re-run tests of earlier REQs that are not in its KIT ("file not found"),
and a locked check cannot be dropped by the repair, which then copied other REQs' tests into the
KIT; they are not run (`regression-checks::not-run`), CLike's regression runs those tests on their
promoted version with the candidate overlaid. An eval without CLike's regression runs them as declared.

## Speed: what is not done twice

- **The gate reuses the eval verdict when nothing changed.** Every full `/eval` records its
  verdict with a digest the orchestrator computes from the project itself (canonical `src/`,
  `test/`, repository-root deliverables, the REQ's KIT, every LTC, `plan.json`, CLike's version),
  in `CLIKE_STATE_DIR` where agents cannot write. `/gate` on the same inputs with the same
  regression mode takes that passing verdict instead of running everything again (`executor:
  reused_eval`, chat: "nothing changed since the passing eval"); the acceptance integrity and the
  required outputs are still checked by the gate. Any changed file, LTC or REQ status, a failed
  verdict, or a verdict older than 24 h: the gate runs the profile as before.
- **Installed `node_modules` are shared** by package.json + lockfile digest
  (`<eval base>/.npm-store/`): a fresh work copy of the REQ or of a regression REQ links them
  (hard links, no extra disk) instead of running npm again. Python venvs were already kept per REQ.
- **Every check has its duration** (`duration_s` in the report cases), and the log has the
  regression time: where an eval spends its time is measurable.
- **Promoted REQs are regressed side by side**: `CLIKE_EVAL_REGRESSION_WORKERS` (docker/.env,
  default 2, `1` = one after the other, at most 8) of them at a time, each in its own work dir with
  its own venv, test databases and service ports; installs they share (a REQ's venv that another
  REQ's service also uses, the npm install store) are created by one at a time, and the report
  lists the cases in plan order as before. Language-independent: it runs the LTC checks, whatever
  they are. More workers need more sandbox memory (`CLIKE_EVAL_SANDBOX_MEM_LIMIT`): with a large
  frontend count about 1.5 GB per worker; if the sandbox runs out of memory, lower it.

Dependencies that are not promoted yet are not regression targets: their source is already part
of the candidate's eval (promoted `src/` + dependency KITs + current KIT), and a REQ that never
passed has nothing to regress from.

Declared changes of a release (`/idea --extend`) narrow the regression, when the REQ that declares
them is promoted or is the candidate: the checks a MODIFIED REQ `supersedes` (`REQ-x#check`) are
not run in the amended REQ's regression, in whatever section of its LTC they are declared (reported
as `regression::<REQ>::<check>::superseded`, its other checks still run), and a REQ a REMOVED REQ
`retires` leaves the regression set. A superseded **test** (`REQ-x#path::name`) is recognised in
the output of any check that runs it, whichever promoted REQ the check belongs to: a check whose
failed tests are all superseded holds (`[CLike EvalRunner] Superseded tests: …`); one with other
failed tests still fails, and the note names the superseded ones so the repair leaves them alone.
The failed tests are read in the formats of the common runners (pytest, vitest/jest, Playwright, Go,
Rust, .NET, Maven/Gradle, RSpec, PHPUnit), and the runner's summary must not count more failures
than those. A failing delivered test of a REQ the candidate amends, not declared, gets a note with
the exact `/eval <REQ> --supersede REQ-x#path::name "<why>"` to run if the change is on purpose
(see [commands.md](commands.md)): a repair may not change the plan.

A REQ that passes its own tests but breaks a promoted REQ fails the eval; the gate reports
`GATE_BLOCKED_REGRESSION` with the list in `regression_failures`. In an auto-eval loop the
regression failures are part of what the repair receives.

A blocking test of a promoted REQ that fails is **run once more** on the same code. If it passes,
it is nondeterministic (timing, order, asynchronous UI): it is reported as a non-blocking warning
(`[CLike EvalRunner] Nondeterministic: … make the test of REQ-0xx deterministic`), does not block
the gate and is not sent to the candidate's repair. Failing twice, it is a regression. Unless it is
**known unstable**: CLike remembers (7 days, any promoted state, in the eval sandbox volume) each
check that failed and then passed on a re-run, with its error lines; failing twice with a later
candidate while it passes on the promoted tree alone, and showing only errors seen in those runs (a
timeout, a missing UI element), it is a warning (`… a known unstable check`). A failure with an
error it never showed, or with no error line to compare, is a regression.

Promoted REQs are regressed side by side (`CLIKE_EVAL_REGRESSION_WORKERS`, default 2). A blocking
failure that **ran out of time** (a test over its limit, a database connection, a suite over the
check's own timeout, a dev server that did not start in time) runs again **alone** once the others
are done: passing alone, it was the parallel load, a non-blocking warning (`[CLike EvalRunner]
Timeout under parallel load: …`) never sent to a repair; failing alone too, it stays blocking and
the note says the slowdown comes with the candidate.

A blocking failure of a promoted REQ that remains (a test, a service it starts, a value it
provisions) is then run on the promoted tree **without the candidate**. If it fails there too, the
candidate did not cause it (a check environment that later REQs outgrew, an earlier REQ): it is a
non-blocking warning (`[CLike EvalRunner] Already failing without this candidate: … REQ-0xx's check
or its environment needs a fix`), not sent to the candidate's repair. Unless the candidate adds errors of its
own: the error lines of the run without the candidate are kept, and a failure that shows lines
not seen there (an import error where the promoted tree only missed the coverage threshold) stays
blocking (`[CLike EvalRunner] New errors from this candidate: …`). Only what the candidate
breaks blocks its gate. When a service of a promoted REQ starts on the promoted tree but not with
the candidate, the failure stays blocking and says why (`[CLike EvalRunner] Service broken by the
candidate`): a configuration the candidate makes mandatory must stay optional with a safe default,
or be declared with `/idea --extend`.

That run without the candidate depends only on the promoted tree, so it is **done once per
promoted state**: its results are kept in the eval base dir (`<eval base>/.regression-baseline/
<REQ>.json`) with a digest of the canonical tree, the promoted REQs' KITs, every LTC, `plan.json`,
CLike's version and the eval environment, for at most 24 h. The next repair cycle, the gate and the
next REQ's evals on the same tree reuse it: a check known to fail there is neither retried nor run
again, one known to pass there is not run again either. Any change of the promoted tree computes it
again. The candidate's own KIT is not part of the digest. A check that failed there on a recent promoted state
(7 days) and passes there now, while it fails with the candidate and on its re-run, is **unstable**:
a non-blocking warning (`[CLike EvalRunner] Nondeterministic: … an unstable check`), since its
result proves nothing about the candidate. The results are kept only when the eval
base dir is outside the project (the eval sandbox volume): a project directory is writable by local
agents, which must not be able to turn a regression into a warning; there every eval runs it again.

When a check of a promoted REQ fails and the candidate KIT replaces files that REQ also delivered
(its `src/` or `test/` files, compared with the canonical copy), CLike names them on the failing
check, with a short diff: `[CLike EvalRunner] Shared files changed: …`. It works on files, so in
any language: a file the candidate **adds** in a test directory of that REQ or one of its parents
(not a test of its own: a package marker such as `__init__.py`, a conftest, a runner config: it changes how those tests are
collected and import their helpers), a test runner config whose selectors no longer match the earlier tests ("No tests
found"), a compose file or manifest an earlier check pins, a component whose behaviour changed.
The repair is told to keep what the promoted REQ put there and add its own part, or to put it in a
separate file (a compose override, an extra test config or project) when an earlier check pins the
content; the repair notes list the replaced files. The KIT rules say the same up front: test runner
configs, infrastructure and build manifests are shared files (test selectors never depend on which
test files exist: after promotion they all do), and checks assert what their REQ
contributes, never that a shared file contains only that.

In the regression a promoted REQ runs the promoted version of its tests: each test file of its KIT
is replaced by its copy in the canonical test tree when that copy differs and was committed later
(a later REQ reconciled it and promotion delivered it), so a reconciliation is done once, not by
every following REQ. The promoted version gets the support files it imports from the canonical
test tree (a helper at the test root, a package marker beside it), with the same rule as a
reconciled test. The test root's `conftest.py` is shared by every REQ and merged at promotion, so
the REQ keeps its own and the canonical one is not brought.

A service of another promoted REQ (`services[].req` in the LTC) runs that REQ's promoted code with
the candidate's source over it, as in its regression, not the original source of its KIT.

When the candidate changes a promoted REQ's behaviour on purpose, it reconciles that REQ's test in
its own test root, at the same path (`runs/kit/<candidate>/test/...`). The regression runs that
version, since promotion delivers it: the candidate's copy replaces the test files the promoted
REQ already has, and the candidate's new support files that version needs come with it: the
modules it imports, directly or through another copied helper, from anywhere in the candidate's
test tree (a helper at the test root for a test in `test/v2/`; for JS/TS its relative imports,
`from './v2/x.fixtures'`, `require('../y')`, `import('./z')`, with or without extension), and a package marker
(`__init__.py`) or a `conftest` in the same directory as a reconciled test. Nothing else comes: a
`conftest` in another directory would be loaded by the test runner into that REQ's own tests, a
module that exists in the sources is never taken from the test tree, and the candidate's tests run
in its own checks. A candidate file identical to the promoted one reconciles nothing (promotion
does not change it) and is not overlaid. The candidate's own tests are not added to
that REQ's checks. The change is never silent:
the report carries the warning `regression::<REQ>::reconciled-tests` with the replaced files, for
review before the gate. It is not sent to a repair.

The eval workspace is composed from the KIT and the canonical tree without installs, caches and
scratch (`node_modules`, `.tmp`, `.cache`, `.npm-cache`, `.next`, `local-eval-workspaces`…); a
file removed while it is copied is skipped. If CLike still cannot compose it, the preparation is
retried once, then `env::prepare-workspace` is environment-blocked: no check ran, `--fix` stops
instead of sending it to a repair.

A promoted dependency is already in the canonical tree, merged with what later REQs changed, so its
KIT copy must not bring old files back. With a gate auto-merge record
(`runs/kit/<REQ>/promotion/*/report.json`) its KIT is not overlaid at all. A REQ that is done
without that record (promoted before the records existed, by an overwrite, or kept beside the tree
by a folder/suffix strategy) is overlaid file by file: a KIT file wins unless its canonical copy
differs and was committed later (git history of the project); without history the KIT wins, as
before. This also applies to a promoted REQ's own run in the regression.

Repository-root deliverables of a KIT (`runs/kit/<REQ>/root/<path>`: `scripts/`, `deploy/`, root
manifests) are at the eval workspace root, after the canonical ones and those of dependency KITs
not promoted yet, so a check runs `./scripts/…` as it will after promotion; in the regression the
candidate's root files are overlaid too, and a promoted check failing on one names it.

A KIT's root `test/conftest.py` (or `tests/conftest.py`) is promoted over the canonical one that
every delivered REQ shares: the eval fails it (`structure::shared-conftest::<root>`, blocking) when it
drops a fixture or helper the canonical one defines, so the repair keeps them or moves the REQ's
fixtures into its own package conftest — instead of a promotion conflict after a passing gate.
Removing that root conftest is the one deletion the acceptance governance accepts: a test-support
file that defines no test and that the eval named is taken out of the lock (audited); a deleted test
file is always restored.

The same holds for every other **shared test-support file**, in any language CLike reads: a KIT that
replaces a helper or fixture module of the promoted tree (not a test: `test/fixtures.ts`, a
`*_support.py`, a `TestBase.java`, a Go helper) must keep the public names the promoted REQs' tests
use — functions, classes and module names in Python; `export`s in JS/TS; public members in Java/C#;
declarations in Kotlin; exported names in Go. A dropped one fails the eval
(`structure::shared-test-support::<root>/<file>`, blocking) with the names and the tests that use
them, before the regression would fail late (a suite that does not load, an e2e that times out). A
name counts as used when a test names it and refers to the module (or sits in the same directory, as
Go and Java packages do), in the version after promotion: a test the candidate reconciled is read in
its version. A changed behaviour behind the same names is the regression's to find; a file in a
language CLike does not read is left to the regression as before.

A KIT also must not **add a test-layout file** in a test directory of the promoted tree (or one of
its parents): a file that changes how the tests already there are collected or import their helpers
— a package marker (`__init__.py`), a `conftest.py`, a pytest / Jest / Vitest / Playwright / Mocha /
Babel / TypeScript config, a `go.mod`, `pom.xml`, `build.gradle`, `.csproj`. The eval fails
(`structure::test-layout::<root>`, blocking, no run needed) with the files, at the first eval: the
regression would show it only once the REQ's own checks pass. The REQ's own tests, helpers and
directories are not concerned.

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
  ENOENT`, `No such file or directory: 'kcat'`, `Cannot run program "mvn"`), or whose own wording
  says a catalog program is missing (`shellcheck missing`, `aws is not installed`, `requires aws`)
  when that program is indeed absent from the sandbox: it is environment-blocked (`missing_tools`
  in the report), never sent to a repair.

The script linters `shellcheck` and `powershell` (`pwsh`) are default tools: the eval-tools service
installs them at its start, for every project, without asking (`CLIKE_EVAL_TOOLS_DEFAULTS=0` turns
this off). What else is missing is installed after the developer's confirmation (VS Code: *Install*, *Always for
this project*, *No*; `clike.evalTools.install`: `ask` | `always` | `never`); tools listed in
`.clike/eval-tools.yaml` (`tools:`) install without asking, so a team shares the same tools. A
check that stopped on a missing tool runs again once it is installed; without an answer within 5
minutes the eval runs without it, and `--fix` stops saying how to install it. A project can add
other conda-forge packages under `custom:` in the same file. Libraries of a language (psycopg,
ojdbc, kafka-python…) are not tools: the project's manifests install them.

`/tools` lists the catalog and what is installed with versions, `/tools search <text>` finds an
entry, `/tools add <tool>[@version]…` installs and approves for the project, `/tools update
[tool…]` rebuilds them at the latest versions and shows what changed, `/tools remove <tool>`
withdraws the approval.

How the tools are installed (the `eval-tools` service: only the orchestrator reaches it, its own
network, no credentials):

- **One environment per tool** (`/opt/clike-tools/envs/<tool>`): installing Maven never changes
  the `jdk@17` already there; micromamba's package cache keeps the copies small.
- **Three kinds of catalog entry**: conda-forge `packages`; `pip` for CLIs distributed on PyPI
  (e.g. `azure-cli`, whose conda-forge package does not resolve), installed in the tool's own
  Python; `download` for a vendor archive — an `https` URL per platform (`linux-64`,
  `linux-aarch64`) with its **sha256**, verified before it is unpacked (tar/zip, no paths outside
  the tool directory), never executed by CLike. A project adds its own entries of any kind under
  `custom:` in `.clike/eval-tools.yaml`.
- **Versions are locked.** Each tool records its top-level versions and an exact lock (micromamba
  explicit spec with md5, `pip freeze`, archive digest); the orchestrator keeps a copy outside
  the volume (`<state>/eval-tools/lock.json`). On a new volume `docker/rebuild.sh` rebuilds the
  same tools with the same versions (`restore`).
- **Updates are deliberate.** A rebuild does not change versions, so two gates on the same code
  give the same result. `/tools update` or `./rebuild.sh --update-tools` rebuilds every tool at
  its latest version (the image's PostgreSQL client too) and prints `old → new`; a tool whose
  rebuild fails keeps its previous version. `/tools` and the rebuild remind you when the tools
  are older than 30 days (`CLIKE_EVAL_TOOLS_STALE_DAYS`).
- **Evidence.** Every eval and gate report records the versions of the installed tools
  (`tools`), next to `missing_tools`.

Verified on conda-forge for both architectures (dry-run resolution, 2026-10): every catalog entry
except `kafkacat` on `linux-aarch64` (not published there).

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

## The whole solution (`/finalize`)

The solution started as a whole is verified at `/finalize` (see `commands.md`): CLike installs,
builds, configures and starts every component together in the sandbox and smoke-checks it while it
runs. It does not run the REQs' tests again: the regression of each gate already did.
