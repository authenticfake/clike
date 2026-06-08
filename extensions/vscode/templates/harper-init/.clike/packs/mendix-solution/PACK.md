---
name: mendix-solution
description: Mendix solution scenario: respect platform/runtime boundaries and supported extension seams.
obligations:
  - Respect Mendix platform/runtime boundaries
  - Keep extensions within supported seams
eval_checks:
  - platform-boundary-respected
  - supported-seams-only
gate_implications:
  - block-if-unsupported-platform-mutation
evidence_required:
  - Boundary docs/tests
---

# Pack: Mendix Solution

## Intent

Guide CLike generation for Mendix-based solutions while respecting low-code platform boundaries, Studio Pro workflows, generated/custom code separation, and enterprise deployment constraints.

This pack prevents generic code generation from blindly editing Mendix-owned artifacts.

## Scenario signals

- Mendix, Studio Pro, module, microflow, nanoflow, entity, domain model, Java action, custom widget, marketplace module, OData, REST service, deployment package, runtime, on-prem Mendix, or hybrid Mendix deployment.
- Requirements involving Mendix extensions, integrations, custom code, or platform deployment.
- TECH_CONSTRAINTS references Mendix runtime or enterprise low-code governance.

## Use when

Use this pack when the target solution is a Mendix app, Mendix module, Mendix extension, or integration around a Mendix runtime.

## Do not use when

Do not use this pack for unrelated backend/frontend work that does not interact with Mendix platform artifacts or runtime assumptions.

## Required capabilities

Recommended skills:

- mendix-extension-boundary
- backend-contract-boundary for APIs/integrations
- frontend-state-accessibility for custom widgets/UI
- local-cloud-parity for runtime/deployment integration
- eval-contract-writer
- gate-risk-reviewer

Recommended design profiles:

- enterprise-console for admin/operator enterprise UI
- startup-product-app only for product-led Mendix frontends

## Runtime assumptions

- Mendix validation may require Studio Pro or platform runtime and may not be available locally.
- Generated code must stay inside safe extension points.
- Platform-owned artifacts must not be blindly rewritten.
- Local validation should focus on generated Java/custom widget/helper code when possible.
- Deployment checks may be external/non-blocking unless infrastructure is available.

## Security/compliance assumptions

- Environment-specific values and secrets must be externalized.
- Enterprise identity, deployment, and data boundaries must be documented when touched.
- Marketplace/module dependency assumptions must be explicit.
- Platform governance may require manual review or import steps.

## Architecture constraints

- Separate generated helper code from Mendix-owned artifacts.
- Document any Studio Pro/manual configuration steps.
- Do not invent Mendix internal file formats.
- Preserve runtime/version compatibility assumptions.
- Avoid pretending that ordinary code tests validate full Mendix deployability.

## Eval expectations

- Local checks for generated Java/custom widget/helper code when tooling exists.
- Static validation and documentation for platform integration steps.
- HOWTO must separate local code validation from Mendix Studio Pro/runtime validation.
- LTC must mark platform validation external/non-blocking unless the runtime is available.
- Compatibility notes must identify the assumed Mendix version/runtime when known.

## Gate implications

Gate should block promotion when:

- Generated output blindly modifies Mendix-owned artifacts.
- Required custom code checks fail.
- Manual platform steps are required but undocumented.
- Mendix runtime/version assumptions are missing.
- Secrets or production endpoints are hardcoded.
- PASS_WITH_WARNINGS is the final status.

Gate may allow non-blocking warnings when:

- Studio Pro or runtime validation is unavailable locally.
- Deployment package validation is external and documented.
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
