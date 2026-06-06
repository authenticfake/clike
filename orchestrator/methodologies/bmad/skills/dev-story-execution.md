# BMAD Skill Mapping: Dev Story Execution

## Intent
Guide local-agent implementation of one target REQ as a promotable candidate slice with source, tests, CI, docs, and self-review.

## BMAD source/reference concept
Inspired by BMAD developer story execution and self-review practices: implement against a ready story, preserve traceability, and document evidence.

## CLike adaptation
Use this mapping only inside CLike KIT packages for `kit/developer`. It improves implementation discipline but never changes candidate write roots or promotion authority.

## Applies when
Applies to `kit/developer`.

## Required inputs
- `AGENT_EXECUTION_CONTEXT.json`.
- SPEC, PLAN, `plan.json`, TECH_CONSTRAINTS, target contract, file requirements.
- Dependency KIT roots and promoted source/test roots as read-only context.
- Selected capability context and BMAD companion docs when present.

## Required outputs
- Candidate source, tests, CI, docs, LTC, HOWTO, and required BMAD developer companion notes under the target KIT root.
- Summary of files changed, commands run, evidence, and unresolved gaps.

## Companion outputs
- `runs/kit/<REQ-ID>/docs/BMAD_DEV_STORY.md`
- `runs/kit/<REQ-ID>/docs/IMPLEMENTATION_NOTES.md`
- `runs/kit/<REQ-ID>/docs/SELF_REVIEW.md`
- `runs/kit/<REQ-ID>/docs/RUNBOOK.md`

## Downstream consumers
EvalRunner, Gate, promotion, FINALIZE, and later REQs consume candidate artifacts and evidence.

## Quality checks
- Implements exactly the target REQ.
- Reuses existing contracts and dependency KITs when available.
- Provides tests and executable validation contracts.
- Keeps runtime choices grounded in evidence.
- Documents assumptions and unresolved blockers.

## Eval/Gate evidence expectations
EvalRunner should find runnable checks, meaningful tests, and traceability to acceptance. Gate should find no weakened security, coverage, or policy evidence.

## Forbidden behavior
- Do not write outside `runs/kit/<REQ-ID>/**`.
- Do not modify canonical `src/`, `test/`, `tests/`, `docs/harper/PLAN.md`, or `plan.json`.
- Do not call `npx bmad-method`.
- Do not decide eval or gate results.
- Do not weaken tests to pass.

## Runtime dependency status
Reference-only. BMAD execution is disabled; only CLike local-agent execution is active.

## Cloud usage notes
For cloud KIT prompts, keep guidance bounded to implementation readiness and candidate output expectations.

## Local-agent usage notes
Read selected skill context before implementation or repair. Treat it as methodology guidance under `AGENT_EXECUTION_CONTEXT.json`.

## Governance boundaries
CLike owns local-agent packaging, write roots, EvalRunner, Gate, and promotion.
