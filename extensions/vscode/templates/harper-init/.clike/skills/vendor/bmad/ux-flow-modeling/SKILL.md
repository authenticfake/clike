# BMAD Skill Mapping: UX Flow Modeling

## Intent
Capture user journeys, interaction states, accessibility expectations, and UX risks as companion context without taking ownership of canonical SPEC.

## BMAD source/reference concept
Inspired by BMAD UX flow and front-end specification practices: make journeys, states, and user-facing constraints explicit before implementation.

## CLike adaptation
Use this mapping only for BMAD UX companion outputs. In MVP, `spec/ux` is companion-only and must not emit `docs/harper/SPEC.md`.

## Applies when
Applies to `spec/ux`.

## Required inputs
- IDEA and current SPEC context.
- User personas or workflow descriptions.
- TECH_CONSTRAINTS and design profile evidence when present.

## Required outputs
- UX companion artifacts describing journeys, screens, states, content, accessibility, and handoff notes.
- Clear separation between UX advice and canonical SPEC authority.

## Companion outputs
- `docs/harper/ux/DESIGN.md`
- `docs/harper/ux/EXPERIENCE.md`
- `docs/harper/ux/USER_JOURNEYS.md`
- `docs/harper/ux/INTERACTION_STATES.md`
- `docs/harper/ux/SPEC_UX_APPENDIX.md`

## Downstream consumers
SPEC PM, PLAN, KIT, EVAL, and FINALIZE may use UX companion artifacts as bounded context.

## Quality checks
- Primary flows, empty states, error states, loading states, and accessibility expectations are explicit.
- UX guidance matches the selected domain and design profile when evidenced.
- Interaction states are testable and not decorative.

## Eval/Gate evidence expectations
Eval/Gate may look for accessibility tests, interaction state coverage, and user-facing acceptance evidence when UI scope is active.

## Forbidden behavior
- Do not emit canonical SPEC in `spec/ux`.
- Do not expand write roots or add implementation files.
- Do not invent UI scope when product context is backend-only.
- Do not override PM-owned canonical requirements.

## Runtime dependency status
Reference-only. No BMAD UX runtime, generator, or external CLI is executed.

## Cloud usage notes
Render companion-only UX context and state that canonical SPEC remains PM/CLike-owned.

## Local-agent usage notes
KIT may read UX companion files for UI REQs, but must implement only the target REQ under candidate roots.

## Governance boundaries
CLike owns canonical SPEC, PLAN, EvalRunner, Gate, and all write policy.
