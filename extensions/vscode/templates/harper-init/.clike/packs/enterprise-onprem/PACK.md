---
name: enterprise-onprem
description: Use for enterprise, regulated, on-prem, hybrid, air-gapped, or internal platform scenarios requiring parity, secure config, local runnability, and promotion evidence.
domains: ["enterprise"]
default_runtime_profiles: ["local", "on-prem", "hybrid", "air-gapped", "local-cloud"]
recommended_skills:
  - enterprise-solution-architecture
  - mvp-e2e-promotability
  - local-cloud-parity
  - secure-config-secrets
  - eval-contract-writer
  - gate-risk-reviewer
gate_required: true
obligations:
  - Keep solutions runnable on-prem/local without mandatory public-SaaS dependencies unless SPEC requires them
  - Treat secrets/credentials/endpoints as external configuration with restricted egress where applicable
  - Provide deterministic local run evidence and promotion artifacts
implementation_directives:
  - Use explicit adapters and configuration seams for external systems
  - Keep business contracts provider-independent; isolate provider SDKs behind infrastructure boundaries
eval_checks:
  - local-run-evidence-present
  - no-public-saas-hard-dependency-unless-specified
  - secrets-externalized
gate_implications:
  - block-if-cloud-only-when-onprem-required
  - block-if-restricted-egress-ignored
  - block-if-missing-local-run-evidence
evidence_required:
  - Local/on-prem run instructions and smoke evidence
  - Configuration docs for required secrets/endpoints
---

# Enterprise On-Prem Pack

## Intent

This pack guides CLike when generating software for enterprise environments where governance, auditability, controlled deployment, reproducibility, local runnability, on-prem support, and runtime constraints matter.

It should keep solutions AWS/cloud-capable when required, but never cloud-only unless the SPEC explicitly requires it.

## Use when

Use this pack when the project targets enterprise, regulated, on-prem, hybrid, air-gapped, or internal-platform scenarios that require parity, secure configuration, local runnability, and promotion evidence.

## Do not use when

Do not use this pack for cloud-only consumer prototypes with no on-prem, regulatory, air-gap, or internal-platform requirement.

## Planning Constraints

- Do not assume public SaaS availability unless explicitly allowed.
- Prefer explicit adapters and configuration seams.
- Keep local execution possible when external systems are unavailable.
- Treat secrets, credentials, tokens, certificates, and endpoints as external configuration.
- Do not hardcode credentials or endpoint-specific assumptions.
- Document runtime assumptions clearly.
- Keep generated implementation promotable and reviewable.
- Preserve business API and lifecycle parity across runtime profiles.
- Split broad enterprise requirements into dependency-aware MVP slices.

## KIT Constraints

Generated code must:

- be modular but not over-engineered;
- expose runtime profile behavior explicitly;
- provide local deterministic validation when external systems are unavailable;
- keep provider SDKs behind adapters when profiles require portability;
- avoid cloud/on-prem differences in business logic;
- keep local tests free from real credentials and production endpoints;
- provide HOWTO instructions for local and external/runtime-profile validation;
- produce executable evidence, not only architecture prose;
- avoid fake production readiness when only local fake adapters are implemented.

## Required Local Run Evidence

For runnable code, the candidate should provide or preserve:

- local run command;
- local check command;
- `.env.example` or equivalent;
- safe local defaults;
- fake/in-memory/local adapters where infrastructure is unavailable;
- optional external validation steps;
- clear statement of what is validated locally.

## FINALIZE Expectations

For code projects, FINALIZE should create or validate:

- composition root;
- settings/env loader;
- runtime profile loader;
- dependency/repository factory;
- DB/session factory when applicable;
- local-dev profile;
- Linux/macOS scripts;
- Windows PowerShell scripts;
- route/API parity check when backend/frontend exist;
- manifest parse checks;
- HOWTO_RUN and SANITY_CHECKS aligned with actual scripts;
- junk artifact cleanup.

## Security Expectations

- Use `secure-config-secrets` when configuration, secrets, auth, provider SDKs, DB, storage, queues, AI, or deployment are touched.
- Local-dev credentials must be sample-only and documented.
- Production config must fail fast when required values are missing.
- Logs and audit payloads must redact secrets and sensitive content.
- Restricted egress assumptions must be documented and, where practical, tested.

## Gate Expectations

Gate should require:

- tests;
- lint where applicable;
- types where applicable;
- security where applicable;
- manifest validity;
- local deterministic validation;
- runtime_profile_adherence;
- skill_adherence;
- documentation completeness;
- future compatibility safety.

Gate should BLOCK promotion when:

- local validation requires production infrastructure;
- provider/runtime-specific logic leaks into business code;
- secrets or endpoints are hardcoded;
- runtime profile assumptions are implicit;
- local run commands are missing for runnable code;
- selected capabilities are ignored;
- `PASS_WITH_WARNINGS` is final status.

Gate may WARN when:

- external enterprise runners are unavailable but local deterministic checks pass;
- full production hardening is documented as future work;
- optional runtime profile smoke checks are environment-blocked with a clear reason.