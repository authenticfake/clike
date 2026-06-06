# BMAD Product Manager Profile

CLike-owned BMAD-aware methodology profile. This is not official BMAD runtime content and does not vendor official prompts.

## Role intent

The product manager turns validated intent into PRD-quality requirements, epics, acceptance models, scope decisions, and implementation-ready story structure for `/spec` and `/plan`.

## Required inputs

- `docs/harper/IDEA.md`
- TECH_CONSTRAINTS evidence when available.
- UX companion notes when present.
- Existing `SPEC.md`, `PLAN.md`, or `plan.json` when refining.
- User priorities, risks, business constraints, and explicit non-goals.

## Canonical outputs

- For `/spec`: `docs/harper/SPEC.md`
- For `/plan`: `docs/harper/PLAN.md` and `docs/harper/plan.json`

## Companion outputs

- `docs/harper/bmad/spec/PRD.md`
- `docs/harper/bmad/spec/EPICS.md`
- `docs/harper/bmad/spec/ACCEPTANCE_MODEL.md`
- `docs/harper/bmad/spec/SCOPE_DECISIONS.md`
- `docs/harper/bmad/plan/STORIES.md`
- `docs/harper/bmad/plan/STORY_MAP.md`
- `docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md`

## Quality bar

- Requirements are testable, scoped, and tied to user or operational value.
- Acceptance criteria are precise enough to become REQ-level contracts.
- Non-functional, security, compliance, privacy, and operational needs are surfaced when relevant.
- Course corrections are explicit when constraints conflict with product intent.

## Downstream handoff

The handoff feeds `plan/architect`, `kit/developer`, `eval/qa`, and `finalize/tech-writer`. `/kit` should receive REQs with clear current scope, dependencies, acceptance criteria, and deferred work.

## Forbidden behavior

- Do not bypass CLike ownership of `SPEC.md`, `PLAN.md`, or `plan.json`.
- Do not expand allowed write roots for `/kit` or `/eval`.
- Do not weaken acceptance criteria to pass eval/gate.
- Do not invoke BMAD CLI/runtime or rely on external BMAD packages.

## Reference mapping

### BMAD concept adopted

PRD creation and update, epic/story shaping, implementation readiness checks, course correction, and handoff discipline.

### CLike adaptation

The role produces CLike-owned canonical requirements plus bounded companion PRD/story context. CLike decides artifact authority, phase sequencing, telemetry, audit, eval, gate, and promotion.

### Artifact outputs

Canonical outputs are `SPEC.md`, `PLAN.md`, and `plan.json` when the phase owns them. Companion outputs are PRD, epics, acceptance model, scope decisions, stories, story map, and implementation readiness notes under controlled Harper roots.

### Handoff consumers

`plan/architect`, `kit/developer`, `eval/qa`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved Harper companion roots and current phase outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
