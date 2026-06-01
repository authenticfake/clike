# BMAD UX Profile

The BMAD UX role can be used during `spec` to enrich user-facing requirements.

Supported command:

```text
/spec --methodology bmad --agent ux
```

## Purpose

The UX role focuses on:

- user journeys
- interaction states
- accessibility expectations
- user-visible acceptance criteria
- content and terminology clarity
- error and empty states
- workflow ergonomics

## Governance

UX guidance is methodology context. It does not override:

- CLike output contracts
- canonical artifacts
- eval/gate policy
- project constraints
- implementation write policy

UX guidance should make acceptance criteria more testable and product behavior clearer. It should not introduce speculative UI scope outside the current requirement intent.

