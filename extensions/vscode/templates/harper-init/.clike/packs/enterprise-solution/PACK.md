---
name: enterprise-solution
description: Use for enterprise-grade applications requiring governance, auditability, integration safety, runtime configurability, security posture, MVP promotability, and release evidence.
domains: ["enterprise", "developer-tooling", "ai-native"]
default_runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
recommended_skills:
  - enterprise-solution-architecture
  - mvp-e2e-promotability
  - backend-contract-boundary
  - local-cloud-parity
  - secure-config-secrets
  - eval-contract-writer
  - gate-risk-reviewer
recommended_design_profiles:
  - enterprise-console
gate_required: true
obligations:
  - Enforce governance, audit, and secure configuration
  - Keep the solution promotable and reviewable
eval_checks:
  - secure-config-present
  - audit-trail-present
  - promotion-evidence-present
gate_implications:
  - block-if-missing-audit-or-secure-config
  - block-if-not-promotable
evidence_required:
  - Audit/config docs
  - Promotion evidence
---

# Enterprise Solution Pack

## Intent

Guide CLike generation for enterprise-grade applications that require governance, auditability, integration safety, runtime configurability, security posture, local runnability, and release evidence.

This pack is scenario-level guidance. It selects constraints and capabilities; it does not replace SPEC, PLAN, TECH_CONSTRAINTS, repository evidence, or explicit user instructions.

## Scenario signals

Use this pack when the requirement mentions:

- enterprise users;
- departments;
- operators;
- administrators;
- compliance teams;
- internal business platforms;
- document/workflow systems;
- identity providers;
- RBAC;
- queues;
- databases;
- object storage;
- SSO;
- audit logs;
- CI/CD;
- on-prem;
- hybrid;
- private network;
- policy;
- approvals;
- regulated data;
- AI assistance in business workflows.

## Required capabilities

Recommended skills:

- `enterprise-solution-architecture` for coherent enterprise slicing and integration;
- `mvp-e2e-promotability` for runnable MVP slices;
- `backend-contract-boundary` for backend/API/service work;
- `frontend-state-accessibility` when UI/UX is involved;
- `backoffice-workflow-ux` when operator/backoffice workflows are involved;
- `local-cloud-parity` for runtime or external dependencies;
- `secure-config-secrets` for configuration, secrets, auth, providers, or deployment;
- `ai-rag-eval-guardrails` when AI/LLM/RAG is involved;
- `eval-contract-writer` for executable validation;
- `gate-risk-reviewer` for promotion safety.

Recommended design profiles:

- `enterprise-console` for dashboards, admin panels, workflow consoles, and operator-facing enterprise UI;
- `developer-tooling-console` for developer-facing enterprise tooling.

Do not select every skill automatically. Select only those justified by the REQ, lane, runtime profile, design profile, and acceptance criteria.

## Requirement shaping

When this pack is selected, SPEC and PLAN should avoid vague enterprise mega-REQs.

Prefer dependency-aware MVP slices such as:

1. canonical contracts and persistence;
2. runtime profile/adapters;
3. primary backend capability;
4. workflow, RBAC, and audit;
5. archive/search/export/reporting;
6. frontend shell/navigation;
7. configuration/admin capability;
8. AI assistant or automation;
9. solution finalize/integration.

Each REQ should be independently promotable and should contribute to a coherent E2E solution.

## Runtime assumptions

- Local execution must remain possible through fakes, simulators, embedded stores, in-memory adapters, or local services when external systems are unavailable.
- Production runtime may be cloud, on-prem, hybrid, or air-gapped.
- Runtime configuration must be explicit and environment-driven.
- External checks may be non-blocking locally when enterprise infrastructure is unavailable, but they must be documented.
- A set of promoted modules without an entrypoint/composition root is not a complete enterprise solution.

## Security/compliance assumptions

- Least privilege is mandatory.
- Secrets must never be hardcoded.
- Audit-relevant actions must be observable.
- Identity and authorization boundaries must be explicit when touched by a REQ.
- Generated artifacts must avoid leaking proprietary or sensitive data.
- Security checks should be included when tooling is available or required by TECH_CONSTRAINTS.
- Local-dev auth must not be presented as production auth.

## Architecture constraints

- Keep public contracts stable and documented.
- Keep infrastructure-specific code behind adapters.
- Avoid provider lock-in unless the REQ explicitly requires it.
- Prefer small, testable modules with clear boundaries.
- Avoid decorative architecture and unnecessary abstractions.
- Preserve backward compatibility unless the REQ explicitly authorizes a breaking change.
- Reuse existing code before creating new layers.
- Patch existing composition before creating parallel composition.
- Avoid one launcher per feature when a project-level launcher is required.

## KIT expectations

When this pack is selected, KIT generation must:

- keep the implementation slice narrow and promotable;
- obey repository conventions before adding new layers;
- generate executable evidence;
- separate deterministic local validation from optional external validation;
- document runtime assumptions;
- preserve future compatibility for dependent REQs;
- avoid fake completeness and broad speculative architecture;
- produce capability adherence notes when skills/design profiles are selected.

## FINALIZE expectations

FINALIZE should close the gap between promoted slices and runnable solution.

When applicable, FINALIZE should create or validate:

- solution composition root;
- settings/env loader;
- dependency/repository factory;
- DB/session factory;
- local-dev profile;
- Linux/macOS scripts;
- Windows PowerShell scripts;
- route/API parity checks;
- manifest validity checks;
- README/HOWTO/SANITY/RELEASE/TODO/PR_BODY;
- junk artifact cleanup;
- truthful out-of-scope and next-step documentation.

## Eval expectations

- Unit tests for deterministic logic.
- Boundary tests for APIs, adapters, queues, persistence, or auth behavior when touched.
- Lint/type/build checks according to the project lane.
- Frontend route/page/build checks when UI exists.
- Route parity checks when backend and frontend exist.
- External integration checks must be marked opt-in or non-blocking unless infrastructure is available.
- HOWTO must document local and enterprise execution separately.

## Gate implications

Gate should block promotion when:

- required checks fail;
- required evidence is missing;
- public contracts changed without tests or documentation;
- secrets or environment-specific values are hardcoded;
- runtime parity is not represented for infra-facing REQs;
- a selected enterprise/backoffice/design skill is ignored;
- local run path is missing for runnable code;
- frontend/backend route parity is broken;
- FINALIZE claims runnability without executable scripts/checks;
- `PASS_WITH_WARNINGS` is the final status.

Gate may allow non-blocking warnings when:

- enterprise-only external runners are unavailable locally;
- full security/compliance tooling is documented but outside the current local environment;
- production hardening is explicitly deferred and local MVP evidence is complete.

## Use when

Use for enterprise solutions requiring governance, auditability, secure configuration, and controlled promotion.

## Do not use when

Do not use for throwaway consumer prototypes with no governance, audit, or promotion requirement.
