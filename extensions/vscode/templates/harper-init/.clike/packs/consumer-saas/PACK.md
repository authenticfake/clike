---
name: consumer-saas
description: Use for consumer, startup, product-led SaaS, onboarding, dashboards, subscription, and customer-facing scenarios.
domains: ["consumer", "startup"]
default_runtime_profiles: ["local", "cloud", "local-cloud"]
recommended_skills: ["journey-ui-states", "journey-identity-access", "journey-tenancy", "journey-runtime-config", "eval-contract-writer"]
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

## Use when

Use for consumer or B2B SaaS products with onboarding, multi-tenant account/project boundaries, and user-facing UI.

## Do not use when

Do not use for on-prem/air-gapped enterprise platforms or backend-only services with no user-facing surface.

---

# CLike Pack Overlay

## Skills

Select only the skills the REQ, lane, runtime profile and acceptance justify: the journeys whose
scenarios the REQ owns (`journey-*`), `eval-contract-writer` for every REQ that ships code,
`backend-contract-boundary` for backend contracts, `e2e-slice-runnability` for user or service
flows, plus the scenario-specific skills listed by this pack.

## Gate

The gate promotes on PASS and on PASS_WITH_WARNINGS (non-blocking checks failed or
environment-blocked, reported and tracked), unless the project enables strict warnings. A check
belongs in the blocking set when it proves an acceptance criterion or scenario in the sandbox; it is
non-blocking only when it needs infrastructure the sandbox does not have, with the reason stated.
