# Commands

## Chat modes

The extension currently exposes three main chat modes:
- `free` (Q&A)
- `coding`
- `harper`

The webview keeps separate attachment buckets per mode.

All three modes can run via the cloud or via a local agent (Claude Code / Codex
CLI), selected with the Execution preference (see below). In `free`, the local
agent answers read-only and the reply is badged with the agent used
(`agent-claude` / `agent-codex`); in `coding`, the local agent writes the
generated files under `generated/<id>/` in the workspace root.

## Slash commands

The current webview parser supports the following slash commands.

### Project / workspace commands
- `/help`
- `/init <name> [--path <abs>] [--force]` — `--force` adds CLike to a folder that already has files: only missing template files are created, existing ones are kept, `.gitignore` gets only the CLike rules it lacks
- `/status`
- `/where`
- `/switch <name|path>`

### Harper commands
- `/idea`
- `/idea --extend [--from attachment] [--release vN] [--dry-run]` — the next release of a delivered project (see below)
- `/spec`
- `/plan`
- `/kit`
- `/agent-model list` — list the models you can set for Claude Code and Codex (CLike model catalog; aliases opus/sonnet/haiku)
- `/agent-model [claude|codex] [model]` — without arguments: show the execution preference (cloud / agent), the default agent and the models in use; with arguments: set the local agent model (e.g. `/agent-model claude sonnet`); applies to chat and Harper phases, saved in the workspace settings
- `/eval <REQ-ID>`
- `/eval <REQ-ID> --fix ["hint"]` — auto-eval: repair from the real failures and re-evaluate (see `auto-eval.md`)
- `/gate <REQ-ID>`
- `/eval <REQ-ID> --accept "reason"` — accept a deliberate edit of the REQ's locked tests / `ci/` (audited)
- `/gate <REQ-ID> --fix ["hint"]` — auto-gate: on a failing gate, the same repair as `/eval --fix`, then a full gate again (see `auto-eval.md`)
- `/gate <REQ-ID> manual pass` — developer override **without executing checks**: asks for a reason
  (≥ 10 characters), is recorded by the orchestrator in an audit log with a digest of the REQ
  artifacts, and is reported as `OVERRIDE`, never as `PASS`. Use only when the gate cannot run
  (e.g. environment-blocked checks).
- `/tools [search <text> | add <tool[@version]>… | remove <tool>…]` — native tools of the eval
  sandbox (kcat, mysqldump, aws, kubectl, terraform, jdk@17…). CLike installs what an eval needs on
  its own after asking; `/tools` shows the catalog and what is installed, `add` installs and
  approves for the project (`.clike/eval-tools.yaml`). See `auto-eval.md`.
- `/autopilot [N] | stop | status` — the REQs of the plan unattended: `/kit` → `/eval --fix` → `/gate` each, a REQ that needs you parked with its reason (see below)
- `/finalize`
- `/extend` — appends REQs to the existing plan, plan only (see `CLike_Harper_Extend_Feature.md`); for a new release use `/idea --extend`

### Local agent selection
- `/agent-default auto` — let CLike choose the local executor
- `/agent-default claude` — prefer Claude Code
- `/agent-default codex` — prefer Codex CLI

Optional governed methodology flags are supported on Harper phase commands:
- `--methodology bmad`
- `--methodology=bmad`
- `--agent developer`
- `--agent=developer`

`--agent` requires `--methodology`. Methodology identity is separate from `profileHint` and local agent executor selection.

Full BMAD command semantics are documented in `docs/integrations/bmad/COMMANDS.md`.

### RAG commands
- `/rag <query>`
- `/rag +<N>`
- `/rag list`
- `/rag clear`
- `/ragIndex [glob]`
- `/ragSearch <query>`

## Harper command semantics

### `/idea`
Formalizes or updates `docs/harper/IDEA.md`.

**Attachments are the source of truth.** `/idea` requires **at least one attached
file** (use `📎 Attach → + Workspace files` or `+ External files`). You can attach
**multiple files at once**.

Attachment handling (via local agent):
- Each file up to **10 MB** is inlined and **materialized** into
  `runs/idea/attachments/<name>` so the agent reads a workspace-local copy
  (no external-path access).
- Files **larger than 10 MB** are referenced by path only and are **not**
  materialized (a warning is shown) — split or shrink them if their content
  must be used.
- External files are also copied into `.clike/uploads/<name>` for portability;
  the agent always reads the run-local copy under `runs/idea/attachments/`.
- Supported content:
  - **Text** (`.md`, `.txt`, `.json`, `.csv`, code, …) — read directly.
  - **PDF** — text is extracted and used as evidence.
  - **Images** (`.png`, `.jpg`, `.gif`, `.webp`, …) — described via **vision**
    (UI screens, layouts, diagrams, visible text) and used as evidence.
  - **Office** (`.docx`, `.xlsx`, `.pptx`) — materialized and read when the
    executor can parse them.
- PDF text and image vision rely on **Claude Code**'s native multimodal reader.
  With the **Codex** executor, image/PDF understanding may be limited.

> Non-text binaries are intentionally **not** sent to the RAG index (only their
> materialized copy reaches the agent), so attaching many images/PDFs no longer
> blocks the run.

### `/idea --extend [--from attachment] [--release vN] [--dry-run] [text]`
The next release of a project whose REQs are delivered. One command runs the cascade
IDEA → SPEC → PLAN in continuity with what exists:

- **Inputs, by release folder.** Put the new requirements of release N in `docs/inputs/vN/`
  (for example `docs/inputs/v2/`, then `docs/inputs/v3/` for the release after) and background
  material in `docs/reference/vN/`. With files in `docs/inputs/vN/` no attachment is needed,
  and you can still attach more files (notes, documents, examples): they add to the folder, both
  are inputs of the release. With `docs/inputs/vN/` empty or missing an attachment is required
  (as for `/idea`). Text after the command adds to them. The targeted release
  is `--release vN`, else the highest folder above what the plan already holds, else the next one.
  Inputs of earlier releases (and unversioned files in `docs/inputs/`) are read as history, never as
  new requirements. The folders of the targeted release are read even when `.clike/context.yaml`
  does not declare them.
- **Baseline.** CLike checks that the REQs of the current release are delivered (it asks before
  going on when some are not) and tags the delivered state `harper/v<N-1>` before changing the
  documents.
- **Merge, never regenerate.** IDEA.md and SPEC.md keep every section of earlier releases; the new
  release is added inside the sections it belongs to, plus a `## Release vN` section.
  TECH_CONSTRAINTS.yaml changes only by addition. A document that drops a section of the earlier
  release is restored and the run says so.
- **PLAN delta.** Delivered REQs are read-only (CLike restores any change). New REQs continue the
  sequence with `release`, `origin` and `change`:
  - `ADDED` — a new capability (prefer extending an existing seam);
  - `MODIFIED` — changes behavior a delivered REQ verifies: `amends: ["REQ-x"]`, the changed
    criteria restated in full, `supersedes: [{"check": "REQ-x#<LTC check id>", "reason": …}]`,
    `unchanged: [...]`;
  - `REMOVED` — retires a capability: `retires: ["REQ-x"]`.
  Targets must exist and be delivered; a superseded check must exist in the REQ's LTC. A plan that
  breaks these rules is rejected and nothing is kept.
  The PLAN.md sections that index every REQ (REQ-IDs table, dependency graph, test strategy, KIT
  readiness) list the new REQs too: CLike adds any the agent left out.
- **BMAD.** `--methodology bmad --agent analyst|pm|architect|ux` works on the cascade (default role
  `pm`): the role leads the angle, CLike's rules and checks stay in charge (see
  `integrations/bmad/COMMANDS.md`).
- **Report.** `docs/harper/EXTEND_<date>_<first>_<last>.md` with the changes and why, the delta
  table, impact, unchanged behavior and open questions, plus a **CLike verification** section CLike
  writes itself. `--dry-run` keeps only the report.
- **Then as usual:** `/kit`, `/eval --fix` and `/gate` for each new REQ, `/finalize` at the end of the
  release. In the regression, the checks a `MODIFIED` REQ supersedes leave the amended REQ's
  regression (reported as `superseded`), and a REQ retired by a `REMOVED` REQ leaves the regression
  set; every other check of delivered REQs keeps running.

Projects not built with CLike: put their documentation in `docs/reference/` and the new needs in
`docs/inputs/v2/`; taking over the existing code base inside `/idea --extend` is the next step
(see `architecture/ADOPT_AND_IDEA_EXTEND.md`). Until then `/idea --extend` needs a plan with REQs.

### `/spec`
Generates or updates `SPEC.md` from current Harper context. It also writes `TECH_CONSTRAINTS.yaml`
from the *Technology Constraints* block of IDEA.md — except with `--methodology bmad --agent ux`
(companion-only: UX documents in `docs/harper/ux/` only) and once the project has releases
(`/idea --extend` owns TECH_CONSTRAINTS from then on, by addition).

### `/plan`
Generates or updates `PLAN.md` and `plan.json`.

### `/kit`
Runs the base KIT flow by default or explicit follow-up KIT phases. The candidate lives in
`runs/kit/<REQ>/` (`src/`, `test/`, `ci/`, `docs/`, and `root/<path>` for repository-root files such
as `scripts/` or `deploy/`, promoted to `<path>` — see `git-and-promotion.md`).

Supported patterns in current parser:
```text
/kit
/kit REQ-001
/kit REQ-001 --integrity
/kit REQ-001 --hardener
/kit REQ-001 --promotion-eval
/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval
```

Normalized follow-up phase names currently used by the sources:
- `kit`
- `integrity_eval`
- `promotion_hardener`
- `promotion_eval`

### `/kit <REQ-ID>` with `clike.kit.acceptanceFirst`
Acceptance-first KIT: first the acceptance tests and eval profile (from SPEC/PLAN), locked; then
the code against them. See `harper-workflow.md`.

### `/eval <REQ-ID>`
Runs eval for the target REQ using candidate artifacts and `LTC.json`. With
`clike.eval.regression` (default on) it also re-runs the acceptance checks of every
promoted REQ (plan status `done`) against the new code (`regression::<REQ>::<check>`).

### `/eval <REQ-ID> --fix ["hint"]`
Auto-eval: eval, then on failure a KIT repair built from the failed checks and the current
candidate files, then eval again, up to `clike.autoEval.maxCycles` (default 2). Tests stay
locked; LTC command fixes are audited. Re-run to continue. The hint is optional: CLike flags
failures that passed in earlier runs as nondeterministic, and writes what each repair received
in `runs/eval/<REQ>/repair_<REQ>_<ts>.md`. See `auto-eval.md`.

### `/eval <REQ-ID> --accept "reason"`
The tests and `ci/` of a REQ are locked at its first eval; an edit made afterwards blocks the
eval and the gate of that REQ and of every later REQ whose regression runs it (*the acceptance
surface of REQ-002 changed after the lock*). When you changed them on purpose — e.g. you
completed a promoted REQ's `ci/LTC.json` by hand — this accepts the edit without a new `/kit`:
the orchestrator records the files, your `git config user.name` and the reason (at least 10
characters; asked when missing) in the lock and in the audit log. Only edits that weaken nothing
are accepted: a removed file, an LTC check removed, made non-blocking or with another command,
or an added skip marker still needs the files restored or `/kit <REQ-ID>`. It runs no eval:
run `/eval` again afterwards.

### `/gate <REQ-ID>`
Runs gate checks for the target REQ using eval output and gate policy. Warnings (failed
non-blocking checks) do not block unless `clike.gate.strictWarnings`; regression failures
block with `GATE_BLOCKED_REGRESSION`. When nothing changed since a passing `/eval` (same files,
LTCs and REQ statuses), the gate reuses that verdict instead of running everything again; the
acceptance integrity and required outputs are still checked (see `auto-eval.md`, *Speed*).

### `/gate <REQ-ID> --fix ["hint"]`
Auto-gate: when the gate fails (checks, regression, required outputs), a KIT repair with the same
rules as `/eval --fix`, then a full gate again; only a gate run on the repaired candidate
promotes it. It stops on a tampered acceptance surface and does not try to resolve promotion
conflicts. Notes per cycle in `runs/gate/<REQ>/repair_<REQ>_<ts>.md`.

`/eval --fix` and `/gate --fix` stop, instead of repairing code, when the failure is not the code:
the sandbox ran out of resources (`EVAL_SANDBOX_EXHAUSTED`), a native tool is still missing
(`missing_tools`), or CLike could not prepare the eval workspace. A promoted REQ's test that fails
and then passes on a re-run is a nondeterministic warning, not a regression. A regression caused by
files the candidate replaced names those files, with a short diff, for the repair.

### `/autopilot [N] | stop | status`
The REQs of the plan one after the other, unattended, in dependency order: `/kit`, `/eval --fix`,
`/gate` for each, through the same chat handlers — same executor (cloud model, Codex or Claude
Code, as configured), same locks, gate, promotion and audit as when you type them. No model decides
the loop: a fixed rule picks the next REQ (`harper_next_action`: an in-progress REQ first — resumed
from the eval when its KIT is there — then the first open REQ whose dependencies are done).

- A REQ that needs you is **parked** with its reason (eval `--fix` stopped, gate not passing,
  promotion not done, an acceptance edit to `--accept`, a value only you have, a native tool to
  approve: nobody answers the prompts, so they count as *no*). The REQs that do not depend on it go
  on; the loop ends when none can.
- A provider quota or rate limit (429, usage limit) is not a failure: the step waits
  `clike.autopilot.quotaWaitMinutes` (30) and retries, at most `clike.autopilot.quotaRetries` (8).
- `N` stops after N promoted REQs; `stop` after the current step; Cancel stops it now.
- A gate that promoted test fixes made by a repair is listed for your review (gate *REVIEW*).
- It stops before `/finalize`, which stays yours. Needs `clike.gate.autoPromote` `merge` (or `off`).

Report (rewritten at every step, not committed): `runs/autopilot/report.md` — promoted REQs with
repair cycles and duration, parked REQs with the step, the reason and the last messages, quota
waits, what to do next. Do not run other Harper phases while it runs.

### `/tools [search <text> | add <tool[@version]>… | remove <tool>…]`
Native tools of the eval sandbox. CLike installs what an eval needs on its own: before an eval or
gate it finds the programs the REQ declares (`environment.tools` in `ci/LTC.json`) or runs, and
asks *Install / Always for this project / No* (`clike.evalTools.install`: `ask` | `always` |
`never`). `/tools` lists the catalog by group and what is installed; `search` matches name,
description or program; `add` accepts a catalog name or the program (`mysqldump`, `kcat`), with
an optional version (`jdk@17`), installs it and approves it for the project in
`.clike/eval-tools.yaml`; `update [tool…]` rebuilds them at the latest versions and prints
`old → new` (a failed rebuild keeps the previous version); `remove` withdraws the approval (the
installed files stay in the shared tools volume). `/tools` shows the installed versions and reminds
you after 30 days. Libraries of a language belong to the project manifest. See `auto-eval.md`.

### `/finalize`
Brings the promoted solution to **running and configured**: it wires what is missing, writes the
run docs and scripts and `ci/SOLUTION_LTC.json`, the eval profile of the **whole solution
running**. If some REQs are not promoted yet, CLike lists them and asks before it starts.

The REQs' tests are **not run again**: each REQ passed them at its gate. With no flag
(`clike.finalize.verify`, default on) CLike runs `ci/SOLUTION_LTC.json` in the eval sandbox
against the canonical tree (`runs/`, `.git`, `.clike/` are not copied):

1. `setup`: install of every component and build of what needs one to run, before anything
starts, 2. the solution configured and started as services (migrations, backend, workers,
frontend, with readiness), 3. smoke checks of the running solution (`ci/solution/`): health, one
real request per main capability, the main UI pages answering with their content.

When it fails, `/finalize` runs again with all its errors (same loop rules as `/eval --fix`:
`clike.finalize.verifyMaxCycles`, default 3, plus extra cycles while the failures decrease). The
repair looks for the cause in order: configuration (variables, URLs, ports, services, migrations),
missing native tools, wiring, then code; a missing variable is provisioned and documented, never
hardcoded. A local agent (Codex, Claude Code) re-runs the profile's checks in the sandbox itself
while it works (`node .clike/bin/eval-check.mjs`) and runs `scripts/check_solution_local.sh` /
`.ps1` on your machine. A repair cycle that cannot run says so and stops.

What you get:

- `README.md` — the project README, marked as a CLike project: CLike, Harper and Finalize badges
  (linked to the [CLike repository](https://github.com/authenticfake/clike), its Harper lifecycle
  and `FINALIZE_REPORT.md`) and a closing **Made with CLike** section with links to the Harper
  documents, the report and the solution evidence. A README without it fails the verification
  and the next repair cycle adds it.
- `docs/harper/FINALIZE_REPORT.md` — the report for you: how to start the solution and see each
  main capability, every configuration variable (purpose, value or how it is generated, who sets
  it), **missing information** only you can give (what, why, where to get it, where to put it),
  everything `/finalize` changed file by file and why, the problems met and how they were solved,
  the limitations left. If `/finalize` does not write it, the verification fails and the next
  repair cycle writes it.
- `scripts/setup_local.sh` / `.ps1` (creates the local, git-ignored configuration from
  `.env.example`: local URLs, generated secrets, local database; never overwrites a value) and
  `scripts/start_solution_local.sh` / `.ps1` (starts everything and prints the URLs). Published
  host ports come from that configuration: setup picks a free port when the default is taken on
  your machine (for example by the CLike gateway on 8000), start names the port and the variable
  to change when one is busy. After a
  passing verification CLike offers **Configure locally** or **Configure and start**, in a
  terminal you see.
- `docs/harper/SOLUTION_EVAL.md` — what CLike verified: the checks, the verification cycles and the
  last gate of every REQ (the acceptance tests, not run again).

The profile, its smoke scripts, the evidence and the report are committed when the verification
ends; changes you had in the working tree before `/finalize` and that it did not touch are left
out of its commits (recorded by content in `runs/finalize/DIRTY_BEFORE.json` until a finalize
commit succeeds, so the work of an earlier run that ended before its commit is still committed).

Deployment target from `TECH_CONSTRAINTS.yaml`: **on-premises/local** — the local run is the
target and must work on the developer's machine; **cloud** — guarded deploy scripts too (mutating
only with `CLIKE_ALLOW_CLOUD_MUTATION=1`), checked non-mutating (validate/plan); the deploy itself
is always an explicit action.

## KIT follow-up phases

The current sources support follow-up KIT phases, but they are not equivalent to base KIT generation.

### Base phase
- `kit`

### Follow-up phases
- `integrity_eval`
- `promotion_hardener`
- `promotion_eval`

The extension performs preflight checks for required candidate artifacts before allowing follow-up phases.

## RAG slash semantics

### `/rag <query>`
Searches RAG and displays top results.

### `/rag +<N>`
Attaches a result from the last RAG search to the next call.

### `/rag list`
Lists current inline and RAG attachments.

### `/rag clear`
Clears current attachments.

### `/ragIndex [glob]`
Triggers manual indexing into the orchestrator RAG.

### `/ragSearch <query>`
Explicitly searches RAG through the orchestrator search path.

## Extension commands

The extension also contributes direct VS Code commands.

### Service authentication
- `clike.setServiceToken` — *CLike: Set Service Token*: paste the stack `CLIKE_API_TOKEN`, or generate
  one (the `.env` line is copied to the clipboard). Stored in SecretStorage.
- `clike.clearServiceToken` — *CLike: Clear Service Token*
- `clike.copyExtensionMcpToken` — *CLike: Copy Extension MCP Token*: token for clients of the
  extension's operational MCP server

### Chat / session
- `clike.openChat`
- `clike.chat.clearSession`
- `clike.chat.openSessionFile`

### Harper / project
- `clike.harper.init`

### Code actions / generation
- `clike.codeAction`
- `clike.addDocstring`
- `clike.refactor`
- `clike.generateTests`
- `clike.fixErrors`
- `clike.applyUnifiedDiffHardened`
- `clike.applyUnifiedDiff`
- `clike.applyNewContent`
- `clike.applyLastPatch`

### Models / services
- `clike.listModels`
- `clike.checkServices`

### RAG
- `clike.ragReindex`
- `clike.ragSearch`

### Git / promotion
- `clike.gitCreateBranch`
- `clike.gitCommitPatch`
- `clike.gitOpenPR`
- `clike.gitSmartPR`
- `clike.promoteReqSources`
- `clike.promoteReqSourcesQuick`

## Code-action intent surface

The orchestrator agent endpoint currently supports at least these intent families from the code-action path:
- `docstring`
- `refactor`
- `tests`
- `fix`

These flows are repository-file oriented and not Harper-phase oriented.

## Execution preference

The extension passes an execution preference with every chat request.

Execution-agent (local-agent) execution is available for the Harper phases
`/idea`, `/spec`, `/plan`, `/kit`, `/eval`, `/finalize`, and `/extend`, and for
the standalone `free` (Q&A) and `coding` modes. With `prefer_local_agent` or
`local_agent_only`, supported flows run through the local-agent path;
`cloud_only` and `auto` keep using the cloud path. For the early Harper document
phases the local agent writes only the canonical Harper outputs
(`docs/harper/IDEA.md`, `docs/harper/SPEC.md`, and `docs/harper/PLAN.md` +
`docs/harper/plan.json` with lane guides), and all other `docs/harper/` paths
stay protected. For standalone coding, the local agent writes under
`generated/<id>/` in the workspace root. Cloud and local execution remain
semantically equivalent and CLike governance stays canonical.

`agent only` (`local_agent_only`) is the default Execution preference. Provider
availability is computed at the gateway from configured API keys: when no cloud
provider key is set, the cloud-dependent Execution options are disabled and only
`agent only` remains selectable; the model list also hides models whose provider
has no configured key. A provider/key mismatch is reported in the chat **Text**
panel.

## Methodology Profile

BMAD is a CLike-owned methodology profile. BMAD is not an executor and does not create a parallel pipeline. It enriches Harper phase behavior with role guidance while CLike keeps authority over canonical artifacts, companion artifacts, local-agent packages, eval, gate, telemetry, audit, and promotion.

Supported BMAD roles:
- `analyst`
- `pm`
- `architect`
- `developer`
- `ux`
- `qa`
- `tech-writer`

Phase defaults:
- `idea` -> `analyst`
- `spec` -> `pm`
- `plan` -> `architect`
- `kit` -> `developer`
- `eval` -> `qa` advisory only
- `gate` -> CLike-only, no BMAD authority
- `finalize` -> `tech-writer`

Common command forms:

```text
/idea --methodology bmad --agent analyst
/spec --methodology bmad --agent pm
/spec --methodology bmad --agent ux
/plan --methodology bmad --agent architect
/plan --methodology bmad --agent pm
/kit REQ-001 --methodology bmad --agent developer
/kit REQ-001 --repair --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/eval REQ-001 --methodology bmad --agent developer
/finalize --methodology bmad --agent tech-writer
```

SPEC has an explicit PM/UX ownership split:

- `/spec --methodology bmad --agent pm` may produce canonical `docs/harper/SPEC.md` through normal CLike SPEC governance and companion PM artifacts under `docs/harper/bmad/spec/**`.
- `/spec --methodology bmad --agent ux` is companion-only in the current MVP. It may produce UX artifacts under `docs/harper/ux/**`, including `SPEC_UX_APPENDIX.md`, but must not overwrite canonical `docs/harper/SPEC.md`.

Gate remains CLike-owned. `/gate REQ-001 --methodology bmad` and `/gate REQ-001 --methodology bmad --agent qa` are rejected by the slash parser in the current MVP.

Injection boundaries:
- Cloud Harper runs receive resolved `methodology_context` only through Gateway cloud prompt composition.
- Local-agent runs receive resolved `methodology_context` through `local_agent_package` in `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`.
- Gateway is not used as a local-agent prompt builder.
- Methodology guidance cannot expand `allowed_write_roots` or override `forbidden_paths`.

For the complete governance model, see `docs/integrations/bmad/GOVERNANCE_MODEL.md`.

### Current normalized values
- `auto`
- `cloud_only`
- `prefer_local_agent`
- `local_agent_only`
- `hybrid`

### Backward compatibility
Legacy values are normalized:
- `prefer_claude_code` → `prefer_local_agent`
- `claude_code_only` → `local_agent_only`

## Local executor selection

Current executor choices:
- `auto`
- `claude_code`
- `gpt_codex`

There is no current slash command in the inspected sources that changes the default local executor from chat. Executor choice is currently configuration-driven and state-driven, not command-driven.
