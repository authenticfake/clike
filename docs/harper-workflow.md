# Harper Workflow

## Overview

The current codebase implements Harper as an iterative, repository-aware pipeline:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

A delivered project evolves release by release with `/idea --extend` (IDEA, SPEC and PLAN of the
next release merged in continuity, then the same KIT → EVAL → GATE → FINALIZE per new REQ):

```text
release v1: IDEA → SPEC → PLAN → (KIT → EVAL → GATE)* → FINALIZE
release v2: /idea --extend → (KIT → EVAL → GATE)* for the new REQs → FINALIZE
```

This is not a purely prompt-only flow. It is backed by:
- canonical docs in `docs/harper`
- machine-readable artifacts such as `plan.json`
- candidate build roots under `runs/kit/<REQ-ID>/...`
- run evidence under `runs/<runId>/...`
- optional local agent execution contracts
- eval and gate endpoints

## Phase-by-phase behavior

### IDEA
Purpose:
- capture business and technical intent
- describe users, value, constraints, and problem framing

Primary output:
- `docs/harper/IDEA.md`

Entry:
- `/idea`
- `POST /v1/harper/idea`
- `/idea --extend` for the next release of a delivered project: runs the `extend` phase in cascade
  mode (`POST /v1/harper/extend` with `extend.mode = "cascade"`), see "Evolving a delivered project"

### SPEC
Purpose:
- translate intent into testable requirements and acceptance criteria

Primary output:
- `docs/harper/SPEC.md`

Entry:
- `/spec`
- `POST /v1/harper/spec`

### PLAN
Purpose:
- break scope into dependency-aware REQs
- define machine-readable plan state

Primary outputs:
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`

Entry:
- `/plan`
- `POST /v1/harper/plan`

### KIT
Purpose:
- generate candidate implementation artifacts for one or more REQs

Primary output area:
- `runs/kit/<REQ-ID>/...`

Common outputs:
- candidate source files
- candidate tests
- `LTC.json`
- `HOWTO.md`
- candidate README / KIT docs
- `AGENT_EXECUTION_CONTEXT.json` in local-agent flows

Entry:
- `/kit`
- `POST /v1/harper/kit`

### EVAL
Purpose:
- execute or normalize checks against the candidate artifacts

Primary output:
- `runs/<runId>/eval.summary.json`

Entry:
- `/eval <REQ-ID>`
- `POST /v1/eval/run`

### GATE
Purpose:
- apply dependency policy and quality policy to decide promotion eligibility

Primary output:
- `runs/<runId>/gate.decisions.json`

Entry:
- `/gate <REQ-ID>`
- `POST /v1/gate/check`

### FINALIZE
Purpose:
- produce release-oriented summaries and closing artifacts

Typical output:
- `docs/harper/RELEASE_NOTES.md`

Entry:
- `/finalize`
- `POST /v1/harper/finalize`

## Current KIT model

KIT is candidate-first and REQ-oriented.

### Default target resolution
If the user does not specify a REQ, the extension resolves the next open eligible REQ from the plan.

### Candidate output roots
Current allowed candidate roots are:
- `runs/kit/<REQ-ID>/src`
- `runs/kit/<REQ-ID>/test`
- `runs/kit/<REQ-ID>/ci`
- `runs/kit/<REQ-ID>/docs`
- `runs/kit/<REQ-ID>/root` — repository-root deliverables (`scripts/`, `deploy/`, root manifests),
  promoted to the repository root (see `git-and-promotion.md`)

### Canonical protection
The current execution contract explicitly protects canonical roots from direct local-agent mutation:
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- `src`
- `test`

## Early document phases on the local agent

`/idea`, `/spec`, and `/plan` can also run through the same execution-agent
architecture used by `/kit`, `/eval`, `/finalize`, and `/extend`. They reuse the
orchestrator execution policy, `run_phase` dispatch, the local-agent package
envelope, `/local-agent/complete` normalization, and the extension actuator. The
only phase-specific differences are the expected outputs, allowed write paths,
phase prompt, and phase validation.

The write policy for these phases is narrow:
- `/idea` writes only `docs/harper/IDEA.md`.
- `/spec` writes only `docs/harper/SPEC.md`.
- `/plan` writes `docs/harper/PLAN.md` and `docs/harper/plan.json`, plus
  `docs/harper/lane-guides/<lane>.md` for each detected lane.

Every other `docs/harper/` path remains protected, and `src/`, `test/`,
`tests/`, and `.git/` stay forbidden. Cloud and local execution stay
semantically equivalent: the phase definitions under `orchestrator/phases/`
(cloud system prompts `cloud_*.md`, local-agent `phase.yaml` / `text.yaml`) are the
canonical source of phase behavior, CLike
governance remains canonical, and the agent only performs bounded document work
that CLike then validates and governs.

## Follow-up KIT phases

The inspected sources implement a multi-step KIT follow-up sequence:

```text
kit
integrity_eval
promotion_hardener
promotion_eval
```

These phases are treated as explicit follow-up work on an existing candidate slice, not as aliases for the base KIT phase.

## EVAL model

The current sources support two eval layers.

### Canonical eval
The canonical eval path is owned by CLike through `/v1/eval/run`.

### Optional local-agent eval pre-pass
If local-agent eval is enabled:
- the extension builds `AGENT_EXECUTION_CONTEXT.json`
- the local executor performs a pre-pass
- canonical eval still runs afterward unless the flow is explicitly blocked earlier

This means the current implementation should be documented as:
- **local eval pre-pass supported**
- **canonical eval remains authoritative**

### Acceptance-first KIT (`clike.kit.acceptanceFirst`, opt-in)
By default one KIT call writes both the code and the tests that judge it. With
`clike.kit.acceptanceFirst`, `/kit REQ` makes two calls:
1. **acceptance stage** (`kit.phases=["acceptance"]`): only `test/**`, `ci/LTC.json`,
   `ci/HOWTO.md`, test manifests and `docs/ACCEPTANCE_<REQ>.md` (criterion → test → LTC check),
   derived from SPEC.md, PLAN.md and the REQ in plan.json; `src/` outputs are dropped;
2. the extension writes them and locks them (`POST /v1/acceptance/lock`) — before any code exists;
3. **code KIT** (`kit.acceptance_first=true`): receives the locked files read-only and writes the
   code to pass them; test/LTC changes go through the same governance as an auto-eval repair
   (rejected, or restored when a local agent wrote them).

Works with the cloud and with local agents. Benchmark: `--acceptance-first`.

### Auto-eval and regression
`/eval <REQ-ID> --fix ["hint"]` runs a bounded, governed repair loop (KIT repair from the real
failures → eval) and, by default, eval and gate also re-run the acceptance checks of the promoted
REQs. `/gate <REQ-ID> --fix ["hint"]` runs the same loop from a failing gate. The hint is optional:
CLike flags failures that passed in earlier runs as nondeterministic. See `auto-eval.md`.

Native programs a check needs (database and messaging clients, cloud and IaC CLIs, a JDK…) are
installed in the eval sandbox from CLike's tools catalog when an eval needs them, after the
developer's confirmation; `/tools` shows and manages them. See `auto-eval.md`.

## GATE model

Current gate characteristics:
- REQ-oriented
- fed by eval results and gate policy
- warnings (failed non-blocking checks) are reported but do not block unless strict
  (`clike.gate.strictWarnings`, `CLIKE_GATE_STRICT_WARNINGS=1`)
- regression failures of promoted REQs block (`GATE_BLOCKED_REGRESSION`)
- can update REQ status
- participates in promotion decisions
- may be linked with Git merge behavior through extension settings

The current docs should treat GATE as a policy-and-promotion decision phase, not merely a test status wrapper.

## FINALIZE model

`/finalize` closes a release: it brings the promoted solution to running and configured. The REQ
test suites are not run again (each REQ passed them at its gate); CLike installs, builds,
configures, starts and smoke-checks the solution in the eval sandbox (`ci/SOLUTION_LTC.json`,
`ci/solution/`) and repairs it until it passes. It writes the README (marked as a CLike project),
`docs/harper/FINALIZE_REPORT.md` for the developer, `docs/harper/SOLUTION_EVAL.md`, and
`scripts/setup_local` / `start_solution_local` (Docker, Podman or native; free host ports), then
offers to configure and start the solution on the developer's machine. See `commands.md`.

## Evolving a delivered project (`/idea --extend`)

- Release inputs live in versioned folders: `docs/inputs/vN/` (requirements) and
  `docs/reference/vN/` (background). The targeted release is the delta; earlier releases are
  history (context role `previous_release`). Files attached to the command add to the folder; an
  attachment is required only when `docs/inputs/vN/` is empty.
- The cascade merges the release into IDEA.md, SPEC.md and TECH_CONSTRAINTS.yaml and appends a PLAN
  delta of REQs typed `ADDED` / `MODIFIED` / `REMOVED` (`amends`, `supersedes`, `retires`,
  `release`, `origin`). Delivered REQs stay read-only.
- The extension checks the result deterministically (`release-extend.js`): merged documents keep
  every earlier section, the delta rules hold, the EXTEND report gets a CLike verification section,
  and the delivered baseline is tagged `harper/v<N-1>`.
- The regression honors the declared changes: superseded checks of an amended REQ are not run
  (reported as `superseded`), a retired REQ leaves the regression set.
- Design and the next steps (taking over projects not built with CLike):
  `architecture/ADOPT_AND_IDEA_EXTEND.md`.

## Cloud and local agents get the same context

A local agent (Codex, Claude Code) reads the workspace; a cloud model sees only its prompt. CLike
puts in the prompt what the local agent would read, bounded:

- **KIT** (base, acceptance stage, follow-ups, repairs): TECH_CONSTRAINTS, IDEA, SPEC, the REQ and
  its dependencies from plan.json, **the REQ's slice of PLAN.md** (its table rows and sections and
  those of its dependencies), the repository and promotion manifests, the candidate files (the
  locked tests in acceptance-first), the REQ and BMAD companion documents, and the **dependency
  surface**: the code its dependencies delivered (from their promotion reports, read from the
  canonical tree; the KIT copy for a dependency not promoted yet), interfaces first, plus their
  `ci/HOWTO.md` — chosen by the extension, no RAG. A manual `/kit <REQ> --repair` carries the latest
  failures and the candidate files, like `/eval --fix`.
- **FINALIZE**: IDEA, SPEC, TECH_CONSTRAINTS, a digest of PLAN.md and an index of plan.json, and the
  **solution surface** (manifests, entry points and interfaces of every delivered REQ).
- **`/idea --extend`**: the IDEA it merges into, SPEC, PLAN and plan.json; **PLAN** gets IDEA too.
- Companion documents (BMAD, UX) go with their content in every phase, within a budget.
- Context sources (`.clike/context.yaml`) reach the acceptance stage too; attachments reach the
  local KIT and FINALIZE packages as workspace copies.
- A cloud run that cannot fit is refused with its size (`cloud_context_too_large`): see
  `CLIKE_CLOUD_MAX_PROMPT_CHARS` / `CLIKE_CLOUD_MAX_OUTPUT_CHARS` in `setup-and-runtime.md`; the
  local agents have no such limit.

## History scope and core context

Harper requests carry contextual state including:
- `messages`
- `historyScope`
- `core`
- `core_blobs`
- repository context
- attachments
- RAG hints
- execution preference
- local executor selection

This is one of the key differences between Harper and the legacy `/v1/generate` flow.

## What the current workflow is not

The current workflow should not be documented as:
- direct generation into canonical `src/` and `test/`
- local-agent-only without fallback and guardrails
- eval-free or gate-free
- writable MCP execution
