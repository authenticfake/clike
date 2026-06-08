---
name: local-cloud-parity
description: Enforce deterministic local execution while preserving cloud/on-prem/edge/hybrid production paths.
phases: ["plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "ai-native", "industrial"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - Provide config-driven endpoints
  - Keep a working local run path
  - Document parity notes between local and cloud
eval_checks:
  - local-run-path-present
  - config-driven-endpoints
  - parity-smoke-tested
gate_implications:
  - block-if-hidden-environment-assumptions
  - block-if-no-local-run-path
evidence_required:
  - Local smoke instructions
  - Parity notes
---

# Local/Cloud Parity Skill

## Intent

Generated software must remain executable, diagnosable, and testable locally while preserving a clear path to production, cloud, on-prem, edge, or hybrid execution.

This skill prevents cloud-only code, hidden production dependencies, fake local success paths, and integrations that cannot be validated by EVAL.

## Use when

Use this skill when a REQ touches external APIs, cloud services, databases, queues, object storage, identity providers, webhooks, SaaS integrations, LLM providers, MCP tools, industrial systems, deployment behavior, runtime behavior, or local/cloud/on-prem/edge/hybrid constraints.

## Do not use when

Do not use this skill for pure local computation, documentation-only changes, static UI copy, or isolated domain logic with no external runtime dependency.

## Signals

Apply this skill when the REQ, PLAN, TARGET_CONTRACT, TECH_CONSTRAINTS, or repository context mentions AWS, Azure, GCP, Kubernetes, Docker, ECS, Lambda, queues, storage, database, identity, webhook, SaaS, API gateway, proxy, private network, PLC, SCADA, MES, ERP, edge runtime, on-prem, hybrid, air-gapped, local simulator, runtime profile requirements, local validation requirements, or external service assumptions.

## KIT Generation Rules

The KIT must:

- keep business/domain logic independent from runtime-specific implementation;
- use a small adapter/port boundary for external systems;
- provide a deterministic local implementation when the REQ must be locally testable;
- use explicit configuration for runtime selection;
- default local tests to local/fake/in-memory adapters;
- keep production/cloud/on-prem adapters isolated and documented;
- never require real credentials for blocking local validation;
- never hide missing external infrastructure behind fake success;
- never claim production readiness when only local fake validation exists.

## Preferred Code Shape

When the language/framework allows it, prefer this shape while respecting repository conventions:

```text
src/
  <module>/
    service_or_use_case.*
    ports_or_contracts.*
    adapters/
      local_or_fake_adapter.*
      production_adapter.*
    config.*
test/
  test_<module>_local.*
  test_<module>_contracts.*
ci/
  LTC.json
  HOWTO.md
```

The exact paths must follow `main_module_boundary`, TARGET_CONTRACT, FILE_REQUIREMENTS, and repository conventions.

## Required Evidence

The KIT must produce:

- source code showing the runtime boundary;
- local deterministic tests using fake/in-memory/simulator behavior;
- configuration documentation;
- HOWTO section for local execution;
- HOWTO section for production/cloud/on-prem assumptions when applicable;
- LTC command that can run without production credentials;
- external integration checks marked as opt-in, non-blocking, or environment-blocked when infrastructure is unavailable.

## Forbidden Behavior

- Do not call real cloud, SaaS, or industrial services from unit tests.
- Do not hardcode credentials, tenants, endpoints, regions, queue names, bucket names, table names, device identifiers, or production URLs.
- Do not make local tests depend on internet access.
- Do not select production runtime by default.
- Do not instantiate provider SDKs directly inside core domain logic.
- Do not log secrets or full sensitive payloads.
- Do not treat a fake adapter as proof of production readiness.
- Do not create broad infrastructure abstractions unless required by the REQ.

## LTC Expectations

When this skill applies, `ci/LTC.json` must include at least one local deterministic validation command.

External checks should be represented separately with explicit metadata such as:

```json
{
  "id": "external-cloud-smoke",
  "blocking": false,
  "requires_external_infra": true,
  "status_if_missing": "environment_blocked",
  "reason": "Requires configured cloud/on-prem service not available in local eval."
}
```

Use the repository's existing LTC schema if available.

## HOWTO Expectations

`ci/HOWTO.md` must explain:

- how to run the local deterministic path;
- required environment variables;
- safe defaults;
- how to enable the real adapter;
- what external infrastructure is required;
- what is validated locally;
- what is not validated locally;
- how an operator should run optional external checks.

## Repair Guidance

If generated code directly instantiates an external SDK inside domain logic:

- extract a minimal port/interface;
- move provider code into an adapter;
- inject the adapter into the use case;
- add local fake tests.

If tests require real infrastructure:

- replace unit tests with local fake/simulator tests;
- document opt-in integration checks;
- update LTC so local checks remain blocking and external checks are non-blocking unless configured.

If configuration is implicit:

- introduce explicit runtime profile selection;
- document defaults;
- add tests for local default behavior.

If docs overclaim readiness:

- downgrade claims;
- list missing external evidence;
- document the promotion risk.

## Gate Impact

Gate must BLOCK promotion when:

- local validation requires production credentials;
- external services are called by blocking unit tests;
- production endpoints or secrets are hardcoded;
- no local deterministic path exists for an externally dependent REQ;
- missing infrastructure is hidden behind fake success;
- runtime selection is implicit and unsafe.

Gate may WARN when:

- production/cloud/on-prem integration is not executed locally but the local contract path passes;
- external runner instructions are present and clearly non-blocking;
- future hardening is documented without pretending it is complete.

## Success Definition

This skill is satisfied when the generated candidate can be evaluated locally without real external infrastructure and still preserves a clear, documented, testable path to production/cloud/on-prem execution.

