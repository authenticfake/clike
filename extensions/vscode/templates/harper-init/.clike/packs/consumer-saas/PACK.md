---
name: consumer-saas
description: Use for consumer, startup, product-led SaaS, onboarding, dashboards, subscription, and customer-facing scenarios.
domains: ["consumer", "startup"]
default_runtime_profiles: ["local", "cloud", "local-cloud"]
recommended_skills: ["local-cloud-parity", "eval-contract-writer", "gate-risk-reviewer"]
gate_required: true
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