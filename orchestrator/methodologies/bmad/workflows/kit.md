# BMAD-Aware KIT Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Build candidate-first source, tests, CI, docs, and implementation notes for exactly one current REQ under CLike write boundaries.

## Step-by-step artifact workflow

1. Read `AGENT_EXECUTION_CONTEXT.json`, current REQ, TECH_CONSTRAINTS, SPEC, PLAN, `plan.json`, target contract, file requirements, companion artifacts, dependency KITs, and promoted roots as read-only evidence.
2. Create a focused dev story for the current REQ.
3. Implement only the current REQ under candidate roots.
4. Add tests, LTC/HOWTO, implementation notes, self-review, and runbook evidence.
5. When repair is requested, inspect failed checks and repair the smallest candidate-owned surface.

## Mandatory companion outputs

- `runs/kit/<REQ-ID>/docs/BMAD_DEV_STORY.md`
- `runs/kit/<REQ-ID>/docs/IMPLEMENTATION_NOTES.md`
- `runs/kit/<REQ-ID>/docs/SELF_REVIEW.md`
- `runs/kit/<REQ-ID>/docs/RUNBOOK.md`

## Optional open-ended companion outputs under allowed roots

- Focused implementation notes under `runs/kit/<REQ-ID>/docs/**`.

## Handoff rules

- Hand off candidate source, tests, CI, HOWTO, LTC, target contract, file requirements, and BMAD dev notes to `eval/qa`.
- Make repair context legible for `eval/developer`.
- Do not write anything that assumes promotion has happened.

## Readiness checklist

- Current REQ only.
- Acceptance criteria and file requirements satisfied.
- TECH_CONSTRAINTS respected.
- Promoted roots inspected read-only.
- Dependency KIT outputs considered when relevant.
- Candidate outputs stay under allowed write roots.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to `runs/kit/<REQ-ID>/src`, `test`, `ci`, and `docs`; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

Developer story execution, quick dev, QA test generation, code review, sprint/story support, and forensic repair workflow.

### CLike adaptation

CLike adapts developer guidance into candidate-first implementation packages. CLike controls candidate roots, forbidden paths, eval, gate, and promotion.

### Artifact outputs

Canonical candidate outputs are under `runs/kit/<REQ-ID>/src`, `test`, `ci`, and governed docs. Companion outputs are `BMAD_DEV_STORY.md`, `IMPLEMENTATION_NOTES.md`, `SELF_REVIEW.md`, and `RUNBOOK.md`.

### Handoff consumers

`eval/qa`, `eval/developer`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to `runs/kit/<REQ-ID>/src`, `test`, `ci`, and `docs`; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
