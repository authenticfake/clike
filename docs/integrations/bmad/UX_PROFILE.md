# BMAD UX Profile

UX is first-class in the BMAD-aware methodology profile because many implementation failures begin as unclear user behavior. A feature can satisfy an API contract and still fail the user if journeys, interaction states, accessibility, content, or recovery paths were never specified.

The UX role is available during `spec`:

```text
/spec --methodology bmad --agent ux
```

This command keeps CLike ownership of `SPEC.md` while asking the methodology profile to emphasize user experience. The role should help express who the user is, what journey they are completing, what states they encounter, what feedback they receive, and how errors or empty states should behave.

## Companion UX Artifacts

Controlled companion artifacts may live under `docs/harper/ux/**`. Two common future-facing examples are:

- `docs/harper/ux/DESIGN.md`
- `docs/harper/ux/EXPERIENCE.md`

These files can provide design rationale, journey notes, state inventories, accessibility expectations, terminology decisions, and interaction details. They are companion context, not replacements for canonical Harper artifacts.

`SPEC.md`, `PLAN.md`, and `plan.json` remain the artifacts that CLike uses for downstream phase authority. Companion UX documents can inform them, but they do not override them.

## UX Expectations

UX guidance should make acceptance criteria more observable. It should call out journeys, primary and secondary users, entry and exit states, loading states, empty states, error states, disabled states, accessibility needs, keyboard or assistive technology expectations, copy tone, and user-visible recovery behavior when relevant.

The UX role should avoid speculative product expansion. If a design idea is not grounded in IDEA, SPEC, TECH_CONSTRAINTS, repository evidence, or explicit user input, it should be framed as a question or deferred companion note rather than treated as mandatory scope.

## Governance

UX guidance is methodology context. It does not override CLike output contracts, canonical artifacts, eval/gate policy, project constraints, allowed write roots, forbidden paths, or promotion rules.
