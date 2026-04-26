# Pack: Enterprise Solution

## Intent

Guide CLike generation for enterprise-grade applications that require governance, auditability, integration safety, runtime configurability, security posture, and release evidence.

This pack is scenario-level guidance. It selects constraints and capabilities; it does not replace SPEC, PLAN, TECH_CONSTRAINTS, or Gate policy.

## Scenario signals

- Enterprise users, departments, operators, administrators, compliance teams, or internal business platforms.
- Integration with identity providers, enterprise APIs, queues, databases, storage, SSO, audit logs, or CI/CD.
- Requirements mentioning auditability, traceability, RBAC, least privilege, on-prem, hybrid, private network, internal gateway, policy, or approvals.
- Runtime profiles such as local, cloud, on-prem, hybrid, air-gapped, or enterprise runner.

## Use when

Use this pack when the product is intended for enterprise deployment, internal platforms, regulated environments, or multi-team business systems.

## Do not use when

Do not use this pack for quick throwaway prototypes, consumer-only landing pages, or isolated scripts with no enterprise runtime, compliance, or integration concerns.

## Required capabilities

Recommended skills:

- backend-contract-boundary
- local-cloud-parity
- eval-contract-writer
- gate-risk-reviewer
- ai-rag-eval-guardrails when AI/LLM/RAG is involved
- frontend-state-accessibility when UI/UX is involved

Recommended design profiles:

- enterprise-console for dashboards, admin panels, and operator-facing enterprise UI

## Runtime assumptions

- Local execution must remain possible through fakes, simulators, or in-memory adapters when external systems are unavailable.
- Production runtime may be cloud, on-prem, hybrid, or air-gapped.
- Runtime configuration must be explicit and environment-driven.
- External checks may be non-blocking locally when enterprise infrastructure is unavailable, but they must be documented.

## Security/compliance assumptions

- Least privilege is mandatory.
- Secrets must never be hardcoded.
- Audit-relevant actions must be observable.
- Identity and authorization boundaries must be explicit when touched by a REQ.
- Generated artifacts must avoid leaking proprietary or sensitive data.
- Security checks should be included when tooling is available or required by TECH_CONSTRAINTS.

## Architecture constraints

- Keep public contracts stable and documented.
- Keep infrastructure-specific code behind adapters.
- Avoid provider lock-in unless the REQ explicitly requires it.
- Prefer small, testable modules with clear boundaries.
- Avoid decorative architecture and unnecessary abstractions.
- Preserve backward compatibility unless the REQ explicitly authorizes a breaking change.

## Eval expectations

- Unit tests for deterministic logic.
- Boundary tests for APIs, adapters, queues, persistence, or auth behavior when touched.
- Lint/type/build checks according to the project lane.
- External integration checks must be marked opt-in or non-blocking unless infrastructure is available.
- HOWTO must document local and enterprise execution separately.

## Gate implications

Gate should block promotion when:

- Required checks fail.
- Required evidence is missing.
- Public contracts changed without tests or documentation.
- Secrets or environment-specific values are hardcoded.
- Runtime parity is not represented for infra-facing REQs.
- PASS_WITH_WARNINGS is the final status.

Gate may allow non-blocking warnings when:

- Enterprise-only external runners are unavailable locally.
- Full security/compliance tooling is documented but outside the current local environment.
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
