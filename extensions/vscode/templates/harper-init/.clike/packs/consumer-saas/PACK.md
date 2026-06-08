---
name: consumer-saas
description: Use for consumer, startup, product-led SaaS, onboarding, dashboards, subscription, and customer-facing scenarios.
domains: ["consumer", "startup"]
default_runtime_profiles: ["local", "cloud", "local-cloud"]
recommended_skills: ["local-cloud-parity", "eval-contract-writer", "gate-risk-reviewer"]
gate_required: true
obligations:
  - Provide onboarding and account/project boundaries
  - Surface user-facing error states
  - Track product analytics where relevant
eval_checks:
  - onboarding-flow-tested
  - account-boundaries-enforced
  - user-error-states-present
gate_implications:
  - block-if-broken-account-isolation
  - block-if-missing-user-error-states
evidence_required:
  - Onboarding/account tests
---

# Consumer SaaS Pack

## Intent

This pack guides CLike when generating product-led software for consumer, startup, SaaS, or customer-facing scenarios.

## Planning Constraints

- Prioritize user value and clear interaction flows.
- Include empty, loading, error, and success states when UI is involved.
- Keep onboarding and first-run behavior explicit when applicable.
- Prefer simple, composable architecture over premature enterprise layering.
- Preserve local execution and developer experience.
- Make analytics, billing, auth, or notification assumptions explicit when relevant.

## KIT Constraints

- Generated code must be easy to run locally.
- External services must have clear adapters or opt-in integration tests.
- UI work should follow a selected design profile when present.
- Documentation must include setup, local run, tests, and known limitations.
- Avoid fake production claims when infrastructure is not implemented.

## Gate Expectations

- tests
- lint
- types where applicable
- design_adherence when UI is involved
- runtime_profile_adherence
- skill_adherence
- documentation completeness
---

# CLike Promotable KIT Pack Overlay

## Purpose

This pack is a scenario-level orchestrator for CLike `/kit`.

It should help the model choose the right constraints, not generate decorative architecture.

## Default Promotable Skills

For code-producing REQs, prefer selecting relevant skills from:

- `promotable-code-boundary` when available;
- `backend-contract-boundary` for backend/API/service work;
- `frontend-state-accessibility` for UI work;
- `local-cloud-parity` for runtime or external dependencies;
- `eval-contract-writer` for executable validation;
- `gate-risk-reviewer` for promotion safety;
- `secure-config-secrets` when available for credentials/config/runtime;
- `observability-diagnostics` when available for supportability;
- scenario-specific skills already listed by this pack.

Do not select every skill automatically. Select only those justified by the REQ, lane, runtime profile, and acceptance criteria.

## KIT Behavior

When this pack is selected, KIT generation must:

- keep the implementation slice narrow and promotable;
- obey repository conventions before adding new layers;
- generate executable evidence;
- separate local deterministic validation from optional external validation;
- document runtime assumptions;
- preserve future compatibility for dependent REQs;
- avoid fake completeness and broad speculative architecture.

## Required Evidence

The KIT should provide:

- source mapped to the REQ;
- tests mapped to acceptance criteria;
- `ci/LTC.json`;
- `ci/HOWTO.md`;
- capability adherence notes in KIT documentation;
- external infrastructure assumptions when relevant.

## Gate Bias

This pack biases GATE toward safe promotion.

Promotion should require full `PASS`.

`PASS_WITH_WARNINGS` must not promote.

Warnings are acceptable only when the missing evidence is explicitly non-blocking, external, and documented with a deterministic local fallback.

## Use when

Use for consumer or B2B SaaS products with onboarding, multi-tenant account/project boundaries, and user-facing UI.

## Do not use when

Do not use for on-prem/air-gapped enterprise platforms or backend-only services with no user-facing surface.
