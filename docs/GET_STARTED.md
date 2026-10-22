# GET STARTED

A first project end to end with CLike, then the everyday features: the agent chat, auto-eval,
acceptance-first, and CLike from Claude Code or Codex. Install first: [INSTALL](INSTALL.md).

## 1. The chat and its three modes

Open **CLike: Chat (Q&A / Harper / Coding)**.

| Mode | For | What happens |
|---|---|---|
| **Free (Q&A)** | questions about the project | answers only, nothing is written |
| **Coding** | quick code generation | files written under `generated/<id>/` |
| **Harper** | the governed delivery process | IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE |

**Execution** (selector in the chat): *cloud* (the model chosen in the model selector, through the
gateway) or *agent* (Claude Code / Codex on your machine). `/agent-model` shows what is in use.

### Talking to the agent directly

With execution = agent, the chat **is** a conversation with Claude Code or Codex:

- each mode keeps one agent session: the next message resumes it, so the agent remembers the
  conversation (`/agent-session` shows the sessions, `/agent-session new` starts a fresh one);
- the agent's answer and the tools it uses (files read or edited, commands) appear live;
- **Cancel** stops the agent, and a running `/eval`, `/gate` or `--fix` loop with it;
- Free is read-only (questions only). Coding and **Harper free text** let the agent also create
  files, only under `generated/<id>/` (e.g. in Harper: "create a script that computes N!"); the
  Harper artifacts (SPEC, PLAN, KIT, ...) change only through the phase commands;
- in **Coding** and **Harper**, every edit and command waits for your choice (**Allow**, **Allow all this turn**,
  **Deny**) and writes outside `generated/` are denied without asking. Claude Code asks through
  CLike, Codex runs through `codex app-server`. `clike.agentChat.approvals = auto` turns the
  questions off (edits under `generated/` then run without asking).

## 2. A first Harper project

The pilots in `benchmark/projects/` (`pingboard`: backend only; `shortlink`: frontend + backend)
are small IDEAs to start with.

1. Create a folder under `CLIKE_PROJECTS_DIR`, open it in VS Code, chat in **Harper** mode.
2. `/init pingboard`
3. Put the IDEA in `docs/harper/IDEA.md` (its *Technology Constraints* block becomes
   `TECH_CONSTRAINTS.yaml`), or write it with `/idea`.
4. `/spec` then `/plan` → `docs/harper/SPEC.md`, `PLAN.md`, `plan.json` (the REQs).
   Put requirement documents (docx, pdf, xlsx, pptx, md) in `docs/inputs/` and UI material (HTML
   prototypes, CSS, screenshots) in `docs/harper/ux/`: the phases read them as declared in
   `.clike/context.yaml` ([context sources](context-sources.md)).
5. For each REQ:
   ```text
   /kit REQ-001            # code, tests, eval profile under runs/kit/REQ-001/
   /eval REQ-001 --fix     # canonical eval; on failure a governed repair, then eval again
   /gate REQ-001           # promotion decision; on PASS auto-merge into src/ and test/ + report
   ```
   Or `/autopilot`: the same three steps for every REQ, unattended (a REQ that needs you is
   parked and the others go on; report in `runs/autopilot/report.md`).
6. `/finalize` when the REQs are done: it does not run the REQs' tests again (the gates did). It
   brings the solution to running and configured: CLike installs, builds, configures and starts it
   in the sandbox, checks that it answers and repairs it until it passes. Read
   `docs/harper/FINALIZE_REPORT.md` (how to start and see it, configuration, what you still have
   to provide, what changed and why); CLike then offers to configure and start it on your machine
   (`scripts/setup_local`, then `scripts/start_solution_local`; with Docker or Podman, or natively).
   A host port already taken on your machine is replaced by a free one in your local `.env`.
7. **Next release.** Put the new requirements in `docs/inputs/v2/` (background, blueprints in
   `docs/reference/v2/`; `v3/` for the release after) and run `/idea --extend` — or attach them
   to the command (an attachment is required when `docs/inputs/v2/` is empty; with files there you
   can still attach more, they add to them). CLike merges the
   release into IDEA, SPEC and TECH_CONSTRAINTS, adds the new REQs to the PLAN typed `ADDED`,
   `MODIFIED` (changes a delivered REQ, naming the checks it replaces) or `REMOVED`, keeps every
   delivered REQ as it is, tags the delivered state `harper/v1` and writes
   `docs/harper/EXTEND_<date>_<first>_<last>.md`. Review it (`--dry-run` writes only the report),
   then step 5 for each new REQ and step 6 at the end of the release.

`/help` lists every command; `/status` shows where you are.

## 3. What CLike guarantees

- **Tests are locked** at the first eval: a repair cannot weaken them. If a test is itself wrong
  (Python or JS/TS), the repair fixes the test (assertions unchanged) and the gate asks for your review.
- **The test environment is created for you**: sessions, ids, a disposable PostgreSQL database per
  REQ and the services of other REQs (e.g. the API of REQ-001 for the integration tests of
  REQ-002) are declared by the KIT and provisioned by CLike in the sandbox; you set only
  `CLIKE_EVAL_POSTGRES_URL` and the values only you have in `docker/eval.env` ([INSTALL §2](INSTALL.md#2-configuration)).
- **Promotion never overwrites your changes**: the gate merges file by file (base = what the KIT
  started from); a file changed on both sides at the same lines is left untouched with a
  `.conflict-<REQ>-<ts>` file next to it, and the REQ stays in progress until you resolve it;
  `conflicts.md` in the promotion report shows each spot with its diff.
- **Regression**: eval and gate also re-run the tests of the REQs already promoted.
- **Sandbox**: checks run in an isolated container without credentials.
- **Audit**: every amendment and override is recorded.

## 4. Options worth knowing

| Setting / command | Effect |
|---|---|
| `/eval REQ --accept "reason"` | accept, audited, a deliberate edit of the REQ's locked tests or `ci/LTC.json` (nothing weakened) without a new `/kit` |
| `/eval REQ --fix ["hint"]` | auto-eval: up to `clike.autoEval.maxCycles` (2) governed repairs, plus `clike.autoEval.extraCyclesOnProgress` (3) while the failures decrease; rerun to continue, the hint guides the fix |
| `clike.autoEval.afterKit` | auto-eval after every `/kit` |
| `/autopilot [N]`, `clike.autopilot.quotaWaitMinutes` (30), `clike.autopilot.quotaRetries` (8) | every REQ unattended (`/kit` → `/eval --fix` → `/gate`); parks a REQ that needs you, waits and retries on a provider quota; `/autopilot stop`, `/autopilot status` |
| `/tools`, `clike.evalTools.install` (`ask`) | native tools of the eval sandbox (kcat, mysqldump, aws, kubectl, jdk@17…): installed when an eval needs them, after asking; `/tools add <tool>[@version]` installs and approves for the project (`.clike/eval-tools.yaml`); `/tools update` or `./rebuild.sh --update-tools` updates them (versions are otherwise locked) |
| `clike.kit.acceptanceFirst` | tests written from SPEC/PLAN and locked **before** the code |
| `clike.eval.regression` (on) | regression of promoted REQs in eval and gate |
| `clike.gate.strictWarnings` | warnings block the gate |
| `clike.gate.autoPromote` (`merge`) | how `/gate` promotes: `merge` auto-merge + report, `ask` strategy list, `off`; `/gate REQ --auto-merge`, `--ask`, `--no-promote` for one run |
| `clike.git.autoCommit` | commit every phase on `feature/req-<n>` — **User settings only** (CLike warns if it is in the project) |
| `/agent-default`, `/agent-model`, `/agent-session` | choose the agent, its model, its session |

Details: [auto-eval](auto-eval.md) · [commands](commands.md) · [local agents](local-agents.md).

## 5. CLike from Claude Code or Codex

After the MCP setup in [INSTALL §6](INSTALL.md#6-use-clike-from-claude-code-or-codex-mcp), ask your
agent in plain words, for example:

```text
Use the clike tools: list the REQs of /path/to/pingboard, then run the KIT of the next open REQ,
evaluate it with fix=true and run the gate. Report the outcome of each step.
```

The operational tools (`harper_run_phase`, `eval_run`, `gate_check`, `harper_run_status`) run inside
VS Code through CLike's normal flow: same test lock, gate and write rules as the chat. Long phases
return `status: running` and a `run_id` to poll; `eval_run` with `fix` returns the final report after
the repairs. Overrides, promotion and git are not exposed. Codex: approve the CLike tools once
(INSTALL §6) or each call asks.

## 6. See what happened

- **Chat** and the **Files** / **Text** tabs for each run.
- **Telemetry portal** `http://127.0.0.1:8000/v1/metrics/harper/ui`: tokens (cached ones included),
  cost, model per phase, cloud and agent runs (agent cost is the API-equivalent cost).
- **Promotion reports** `runs/kit/<REQ>/promotion/<ts>/report.md` (per-file outcome) and `promotion.diff`.
- **Reports** under `runs/eval`, `runs/gate` and the KIT folders.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Eval returns 503 or the orchestrator restarts | container VM memory too low: raise it ([INSTALL §1](INSTALL.md#1-requirements)), lower `CLIKE_EVAL_SANDBOX_MEM_LIMIT` |
| "No local agent is available" | install/log in `claude` or `codex`, or switch execution to cloud |
| An answer from the agent seems to forget the conversation | `/agent-session` — a failed resume starts a new session |
| Browser (Playwright) checks are slow the first time | Chromium is downloaded on first use in the sandbox |
| `EVAL BLOCKED — missing in docker/eval.env` | set the named value in `docker/eval.env` and rebuild; `EVAL BLOCKED — CLike cannot create yet` → `/eval REQ --fix` declares it |
| Gate PASS but the REQ stays in progress | the promotion left conflicts: read `conflicts.md` in the promotion report, resolve the `.conflict-…` files, `/gate` again |
| Phases not committed although `autoCommit` is on | it is set in the project settings: apply it in User settings (CLike shows a warning) |
