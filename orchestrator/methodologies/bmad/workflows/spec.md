# BMAD-Aware SPEC Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Convert IDEA context into PRD-grade behavior, UX expectations, acceptance criteria, scope decisions, and implementation-readiness inputs while preserving CLike ownership of canonical `SPEC.md`.

## Step-by-step artifact workflow

1. Read `IDEA.md`, TECH_CONSTRAINTS, BMAD idea notes, and UX notes when present.
2. For `pm`, produce PRD, epics, acceptance model, and scope decisions.
3. For `ux`, produce design, experience, journeys, interaction states, and SPEC UX appendix.
4. Translate companion context into canonical SPEC only through CLike-owned SPEC generation.
5. Mark unresolved decisions and constraints that PLAN must handle.

## Mandatory companion outputs

- `docs/harper/bmad/spec/PRD.md`
- `docs/harper/bmad/spec/EPICS.md`
- `docs/harper/bmad/spec/ACCEPTANCE_MODEL.md`
- `docs/harper/bmad/spec/SCOPE_DECISIONS.md`
- `docs/harper/ux/DESIGN.md`
- `docs/harper/ux/EXPERIENCE.md`
- `docs/harper/ux/USER_JOURNEYS.md`
- `docs/harper/ux/INTERACTION_STATES.md`
- `docs/harper/ux/SPEC_UX_APPENDIX.md`

## Optional open-ended companion outputs under allowed roots

- Product notes under `docs/harper/bmad/spec/**`.
- UX notes, wireframes, accessibility notes, or journey maps under `docs/harper/ux/**`.

## Handoff rules

- PM companion output feeds `plan/architect`, `plan/pm`, `kit/developer`, and `eval/qa`.
- UX companion output feeds PM and PLAN, but `spec/ux` does not own canonical `SPEC.md`.
- Acceptance criteria must be precise enough for PLAN REQs and later EvalRunner evidence.

## Readiness checklist

- Scope, non-scope, risks, dependencies, and assumptions are visible.
- Acceptance model is testable.
- UX states and accessibility needs are captured when relevant.
- TECH_CONSTRAINTS implications are not deferred silently.
- Canonical SPEC remains CLike-owned.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved SPEC/UX companion roots and CLike SPEC outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

PRD creation/update/validation, epics, stories, UX positioning, acceptance modeling, and course correction.

### CLike adaptation

CLike adapts these concepts into canonical SPEC plus bounded PRD and UX companion artifacts. The UX role remains companion-only in MVP.

### Artifact outputs

Canonical output is `docs/harper/SPEC.md` for PM-led SPEC. Companion outputs include `PRD.md`, `EPICS.md`, `ACCEPTANCE_MODEL.md`, `SCOPE_DECISIONS.md`, `DESIGN.md`, `EXPERIENCE.md`, `USER_JOURNEYS.md`, `INTERACTION_STATES.md`, and `SPEC_UX_APPENDIX.md`.

### Handoff consumers

`plan/architect`, `plan/pm`, `kit/developer`, and `eval/qa`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved SPEC/UX companion roots and CLike SPEC outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
