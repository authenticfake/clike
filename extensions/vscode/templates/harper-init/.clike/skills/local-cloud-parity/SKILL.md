---
name: local-cloud-parity
description: Use when a requirement integrates with external infrastructure but must remain runnable and testable locally.
phases: ["plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
---

# Local/Cloud Parity Skill

## Intent

Generated software must support both realistic production/cloud execution and deterministic local execution when the REQ touches external infrastructure.

## Use when

Use this skill when a REQ touches external infrastructure, cloud services, queues, databases, storage, identity providers, SaaS APIs, industrial systems, or deployment/runtime behavior.

## Do not use when

Do not use this skill for purely local computation, documentation-only changes, static UI copy, or isolated domain logic with no external runtime dependency.

## Signals

- Mentions of AWS, Azure, GCP, Kubernetes, Docker, queues, object storage, databases, identity, webhooks, SaaS APIs, PLC, SCADA, MES, ERP, edge runtime, on-prem, hybrid, air-gapped, or local simulator.
- Acceptance criteria require both local validation and production-like integration.
- TECH_CONSTRAINTS requires offline, internal-only, proxy, private network, or enterprise runner behavior.

## Required behavior

- Provide a production/cloud adapter when the REQ requires real infrastructure.
- Provide a local deterministic adapter, simulator, fake provider, or in-memory implementation when the REQ must be testable locally.
- Use explicit configuration to select the runtime implementation.
- Unit tests must not call real cloud services.
- Integration tests that require real services must be opt-in and clearly documented.
- Documentation must explain local execution and production/cloud execution separately.
- Missing external infrastructure must be reported truthfully, not hidden behind fake success paths.

## Forbidden behavior

- Do not call real cloud or industrial services from unit tests.
- Do not hardcode credentials, tenants, endpoints, regions, queue names, bucket names, or device identifiers.
- Do not make local tests depend on internet access.
- Do not claim production readiness when only a local fake exists.
- Do not hide missing infrastructure behind fake success paths.

## Evidence required

- Runtime selection is explicit through configuration, dependency injection, environment variables, or adapter construction.
- Local tests exercise the local/in-memory/simulator path.
- Production/cloud/on-prem path is represented by a clear adapter or documented external integration boundary.
- HOWTO explains local execution separately from production/cloud/on-prem execution.
- LTC marks external integration checks as opt-in or non-blocking unless infrastructure is available.

## Repair guidance

- If code directly instantiates an external SDK in domain logic, introduce a port/adapter boundary.
- If tests require real services, replace them with local fake/simulator tests and document opt-in integration checks.
- If configuration is implicit, add explicit runtime profile selection.
- If docs claim cloud readiness without evidence, downgrade the claim and add the missing integration assumption.

## Gate implications

The REQ satisfies this skill only if:
- both local and production/cloud paths are represented when applicable;
- the local path is executable without cloud credentials;
- tests cover the local path;
- HOWTO documents both paths;
- runtime configuration is explicit;
- cloud-only behavior is not silently assumed.