# Harper Workflow

## Overview

The current codebase implements Harper as an iterative, repository-aware pipeline:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
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
semantically equivalent: the cloud system prompts under
`gateway/prompts/harper/` remain the canonical source of phase behavior, CLike
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

## GATE model

Current gate characteristics:
- REQ-oriented
- fed by eval results and gate policy
- can update REQ status
- participates in promotion decisions
- may be linked with Git merge behavior through extension settings

The current docs should treat GATE as a policy-and-promotion decision phase, not merely a test status wrapper.

## FINALIZE model

Finalize is present as a first-class Harper phase in both the extension and orchestrator/gateway APIs.

Current intent:
- prepare release notes
- close the workflow
- optionally integrate with broader governance or Git release behavior

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
