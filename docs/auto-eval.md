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
| Run it automatically after every `/kit` | `clike.autoEval.afterKit: true` (default `false`) |
| Number of repair cycles | `clike.autoEval.maxCycles` (default `2`, max `5`) |
| Re-check the promoted REQs | `clike.eval.regression` (default `true`) |
| Make warnings block the gate | `clike.gate.strictWarnings` (default `false`) |

Then promote as usual with `/gate REQ-002`.

## When the loop stops

| Outcome | Message | What to do |
|---|---|---|
| Eval passes | `✔ AUTO-EVAL REQ-002: eval PASS after N repair cycle(s)` | `/gate REQ-002` |
| Cycles exhausted | `still failing after N repair cycle(s)` and the failing checks | read the eval report, re-run with a hint, or fix manually |
| No progress | `no progress: the same checks still fail` | a hint usually helps; or the failure is environmental |
| Repair request failed | `the KIT repair request failed` | see the error in the chat (provider, validation) |
| Acceptance surface changed | `the acceptance surface (test/ or ci/) changed after the lock` | tests/LTC were edited outside the governed path: re-run `/kit` to re-baseline |
| Nothing to repair | `eval failed without failing checks` | see the eval report (e.g. integrity or setup errors) |

## What the repair may change (governance)

The repair prompt (cloud) and the orchestrator enforce the same rules:

- **Source and docs** (`runs/kit/<REQ>/src/**`, `docs/**`): free to change. Only the changed files
  are returned; the others stay as they are.
- **Tests** (`runs/kit/<REQ>/test/**`): **locked**. They are the acceptance criteria taken at the
  first eval. Any change is rejected (`repair_change_rejected:...`) and never written. Single
  exception: a Python test may drop unused imports (lint failures); the orchestrator verifies via
  the AST that nothing else changed and no import was added, and audits the amendment.
- **`ci/LTC.json`**: only the *command* of a check that cannot run may be fixed (wrong path,
  module or flag). Removing a check, making it non-blocking or weakening it is rejected. Accepted
  changes are recorded as audited amendments of the acceptance lock
  (`audit/acceptance_amendments.jsonl` in the CLike state directory) and reported as
  `repair_amendment_accepted:...`.
- **Other `ci/**`** (e.g. `ci/requirements.txt`): accepted and audited, so the repair can upgrade
  vulnerable dependencies. Vulnerable dependencies keep blocking the gate until upgraded.
- **Environment failures** (network, missing system tool) are not "fixed" in code: the model
  documents them in `docs/KIT_<REQ>.md`.

With a local agent (Claude Code, Codex) the same `kit.repair` request reaches the agent package;
files the agent edits under `test/` are caught by the acceptance lock at the next eval, which
stops the loop.

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
