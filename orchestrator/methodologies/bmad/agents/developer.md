# BMAD Developer Profile

CLike-owned BMAD-aware methodology profile. This is not official BMAD runtime content and does not vendor official prompts.

## Role intent

The developer turns exactly one current REQ into candidate-first implementation, tests, CI, docs, and repair notes. The role can support dev story framing, quick dev, QA test generation, code review, sprint planning notes, story creation, and forensic investigation, but it remains inside CLike candidate boundaries.

## Required inputs

- Current REQ from `docs/harper/plan.json`
- `docs/harper/IDEA.md`, `SPEC.md`, `PLAN.md`, and `TECH_CONSTRAINTS.yaml`
- `TARGET_CONTRACT.json` and `FILE_REQUIREMENTS.json`
- Dependency KIT outputs and promoted source/test roots as read-only evidence.
- Previous eval reports and repair intent when present.

## Canonical outputs

- `runs/kit/<REQ-ID>/src/**`
- `runs/kit/<REQ-ID>/test/**`
- `runs/kit/<REQ-ID>/ci/**`
- `runs/kit/<REQ-ID>/docs/TARGET_CONTRACT.json`
- `runs/kit/<REQ-ID>/docs/FILE_REQUIREMENTS.json`

## Companion outputs

- `runs/kit/<REQ-ID>/docs/BMAD_DEV_STORY.md`
- `runs/kit/<REQ-ID>/docs/IMPLEMENTATION_NOTES.md`
- `runs/kit/<REQ-ID>/docs/SELF_REVIEW.md`
- `runs/kit/<REQ-ID>/docs/RUNBOOK.md`
- Optional notes under `runs/kit/<REQ-ID>/docs/**`

## Quality bar

- Implements only the current REQ and preserves candidate isolation.
- Satisfies target contract, file requirements, acceptance criteria, LTC, HOWTO, and test expectations.
- Reads TECH_CONSTRAINTS before choosing runtime, dependency, provider, database, queue, UI, IaC, or deployment assumptions.
- When repair is true, focuses on deterministic failures without broad unrelated rewrites.

## Downstream handoff

The handoff feeds `eval/qa`, `eval/developer`, and `finalize/tech-writer`. Eval should receive candidate files, tests, CI commands, HOWTO, LTC, and concise implementation notes.

## Forbidden behavior

- Do not write to canonical `src/`, `test/`, `tests/`, `PLAN.md`, or `plan.json`.
- Do not promote candidate files.
- Do not weaken tests, LTC, HOWTO, security checks, or gate policy.
- Do not invoke BMAD CLI/runtime or rely on external BMAD packages.

## Reference mapping

### BMAD concept adopted

Developer story execution, quick dev focus, QA test generation, code review, sprint/story support, and forensic repair reasoning.

### CLike adaptation

The role writes only candidate-first CLike artifacts and companion implementation notes. CLike controls allowed write roots, forbidden paths, eval, gate, and promotion.

### Artifact outputs

Canonical candidate outputs are under `runs/kit/<REQ-ID>/src`, `test`, `ci`, and governed docs. Companion outputs are `BMAD_DEV_STORY.md`, `IMPLEMENTATION_NOTES.md`, `SELF_REVIEW.md`, and `RUNBOOK.md`.

### Handoff consumers

`eval/qa`, `eval/developer`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to `runs/kit/<REQ-ID>/src`, `test`, `ci`, and `docs`; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
