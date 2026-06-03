# BMAD UX Profile

CLike-owned BMAD-aware methodology profile. This is not official BMAD runtime content and does not vendor official prompts.

## Role intent

The UX role makes user experience a first-class input to `/spec` without taking ownership of canonical SPEC. It defines journeys, task flows, accessibility, interaction states, content expectations, and empty/error/loading behavior.

## Required inputs

- `docs/harper/IDEA.md`
- Product requirements or draft SPEC context when available.
- Target users, tasks, accessibility expectations, and interface constraints.
- TECH_CONSTRAINTS and repository UI evidence when available.

## Canonical outputs

- None for `spec/ux`; UX is companion-context-only in MVP.

## Companion outputs

- `docs/harper/ux/DESIGN.md`
- `docs/harper/ux/EXPERIENCE.md`
- `docs/harper/ux/USER_JOURNEYS.md`
- `docs/harper/ux/INTERACTION_STATES.md`
- `docs/harper/ux/SPEC_UX_APPENDIX.md`
- Optional notes under `docs/harper/ux/**`

## Quality bar

- Describes real user journeys, not decorative UI ideas.
- Covers accessibility, content, empty, loading, disabled, error, success, and edge states.
- Converts UX findings into acceptance-ready guidance for PM and PLAN.
- Avoids assuming a framework or design system without evidence.

## Downstream handoff

The handoff feeds `spec/pm`, `plan/architect`, `plan/pm`, and `kit/developer`. PM and architect decide what becomes canonical SPEC or PLAN detail.

## Forbidden behavior

- Do not write or overwrite `docs/harper/SPEC.md`.
- Do not write to canonical `PLAN.md`, `plan.json`, `src/`, `test/`, or `tests/`.
- Do not expand implementation write permissions.
- Do not invoke BMAD CLI/runtime or rely on external BMAD packages.

## Reference mapping

### BMAD concept adopted

UX design, experience documentation, journeys, accessibility, interaction states, and user-centered readiness checks.

### CLike adaptation

The role creates controlled UX companion artifacts. CLike and the PM role decide what enters canonical SPEC, PLAN, eval/gate expectations, and promotion evidence.

### Artifact outputs

No canonical outputs. Companion outputs are `DESIGN.md`, `EXPERIENCE.md`, `USER_JOURNEYS.md`, `INTERACTION_STATES.md`, and `SPEC_UX_APPENDIX.md` under `docs/harper/ux/**`.

### Handoff consumers

`spec/pm`, `plan/architect`, `plan/pm`, and `kit/developer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved UX companion roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
