# Pack: Startup Solution

## Intent

Guide CLike generation for startup and product-led SaaS scenarios where speed matters, but generated software must still be testable, evolvable, and honest about limits.

This pack optimizes for lean implementation, clear user value, fast feedback, and minimal architecture that can survive the next iteration.

## Scenario signals

- MVP, SaaS, product-led, startup, beta, customer feedback, onboarding, billing, dashboard, analytics, landing-to-product flow, or growth loop.
- Requirements emphasizing speed, user validation, experimentation, feature slicing, or quick iteration.
- Consumer or small-team product contexts where scope must stay lean.

## Use when

Use this pack when building product increments for early-stage products, MVPs, SaaS applications, internal startup-style tools, or fast validation loops.

## Do not use when

Do not use this pack for regulated enterprise systems, industrial safety systems, air-gapped deployments, or heavy compliance scenarios unless combined with stronger packs and constraints.

## Required capabilities

Recommended skills:

- frontend-state-accessibility when UI/UX is involved
- backend-contract-boundary when APIs/services are involved
- eval-contract-writer
- gate-risk-reviewer
- ai-rag-eval-guardrails when AI/LLM/RAG is involved
- local-cloud-parity when infrastructure or third-party services are involved

Recommended design profiles:

- startup-product-app for product-facing UI
- enterprise-console only when the product is an internal/admin console

## Runtime assumptions

- Local-first development must be easy.
- Cloud deployment may exist but should not be required for unit tests.
- External SaaS integrations must be isolated behind adapters or documented opt-in checks.
- Configuration should support fast local setup without secrets for core tests.

## Security/compliance assumptions

- Do not skip basic security because the product is early-stage.
- Secrets must never be hardcoded.
- User data boundaries must be explicit.
- Auth and permissions must not be faked when acceptance criteria require them.
- Risky shortcuts must be documented as non-production limitations.

## Architecture constraints

- Prefer minimal, coherent modules over speculative architecture.
- Do not build generic frameworks unless the REQ clearly needs them.
- Keep the main user flow complete before adding optional abstractions.
- Keep APIs and state boundaries stable enough for frontend/backend iteration.
- Avoid fake completeness: partial MVP behavior must be declared honestly.

## Eval expectations

- Tests must cover the primary user value path.
- At least one failure/empty/error path should be covered for UI/API flows.
- Build/lint/type checks should run when project tooling exists.
- HOWTO must be short, practical, and copy-pasteable.
- Known MVP limits should be documented.

## Gate implications

Gate should block promotion when:

- The primary user flow is not implemented.
- Generated code is demo-only while claiming product readiness.
- Required checks fail.
- Critical local setup is missing or undocumented.
- External integrations are hardcoded or untestable.

Gate may allow non-blocking warnings when:

- Advanced scalability, observability, or compliance checks are intentionally future scope.
- Optional third-party integrations are documented but not locally runnable.
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
