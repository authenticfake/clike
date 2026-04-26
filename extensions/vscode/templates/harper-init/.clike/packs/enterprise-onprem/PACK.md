---
name: enterprise-onprem
description: Use for enterprise, regulated, on-prem, hybrid, air-gapped, or internal platform scenarios.
domains: ["enterprise"]
default_runtime_profiles: ["local", "on-prem", "hybrid", "air-gapped", "local-cloud"]
recommended_skills: ["local-cloud-parity", "eval-contract-writer", "gate-risk-reviewer"]
gate_required: true
---

# Enterprise On-Prem Pack

## Intent

This pack guides CLike when generating software for enterprise environments where governance, auditability, controlled deployment, reproducibility, and runtime constraints matter.

## Planning Constraints

- Do not assume public SaaS availability unless explicitly allowed.
- Prefer explicit adapters and configuration seams.
- Keep local execution possible when external systems are unavailable.
- Treat secrets, credentials, tokens, certificates, and endpoints as external configuration.
- Do not hardcode credentials or endpoint-specific assumptions.
- Document runtime assumptions clearly.
- Keep generated implementation promotable and reviewable.

## KIT Constraints

- Generated code must be modular but not over-engineered.
- Runtime profile behavior must be explicit.
- Unit tests must avoid real external calls.
- Integration tests must be opt-in when external systems are required.
- HOWTO must include local execution steps and enterprise/runtime notes.
- If an enterprise runner such as Jenkins, GitLab CI, Azure DevOps, or SonarQube is required, document how artifacts are expected to be collected.

## Gate Expectations

- tests
- lint
- types where applicable
- security where applicable
- runtime_profile_adherence
- skill_adherence
- documentation completeness
- future compatibility safety
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
