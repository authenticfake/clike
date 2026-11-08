---
name: backend-contract-boundary
description: Use when a REQ adds or changes backend services, APIs, events, workers or persistence, to keep contracts explicit and stable at the boundary — validated input, typed errors, transport and providers out of the domain — so that later REQs extend them instead of breaking them. The error and status scenarios are in journey-api-contract, journey-data-lifecycle and journey-integration.
phases: ["plan", "kit", "eval"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "backend"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
obligations:
  - Explicit request, response, event and adapter contracts, validated at the boundary
  - Domain logic free of transport, framework and provider types
  - Stable, typed errors mapped once at the edge
eval_checks:
  - contract-tests-present
gate_implications:
  - block-if-public-contract-changed-without-tests
evidence_required:
  - Contract tests on success and failure behaviour
---

# Backend Contract Boundary

## Intent

Contracts are what later REQs build on. Keep them explicit at the boundary so that each REQ extends
them instead of breaking them.

## Use when

Backend services, APIs, events, workers, persistence and adapters.

## Do not use when

Frontend-only visual work, documentation, scripts with no contract.

## Shape

- Edge (route, consumer, CLI) → validates and maps → service (domain rules) → ports → adapters
  (database, queue, provider SDK). Follow the repository's existing layout; add the layer only where
  the REQ needs it.
- Request, response and event shapes are typed schemas; the published schema (OpenAPI, event schema)
  is generated from or checked against the code.
- Errors: domain errors are typed; the edge maps them once to the documented error body and status
  (journey-api-contract API-07). Tests read error metadata through the language's safe narrowing
  (type guard, `isinstance`, pattern match, `errors.As`), never by disabling type checks.
- Persistence: one migration per REQ through the project's migration chain; a change to existing
  tables preserves data (journey-data-lifecycle DAT-14).

## Compatibility

- Additive by default: new optional fields, new endpoints or a new version. A breaking change only
  when the REQ says so, with the acceptance and docs updated.
- A promoted contract is extended, not redefined: reuse its schemas and types.

## Forbidden

- Provider SDKs or framework objects inside domain services.
- Swallowing errors (`except Exception: pass`, a log line "failed") instead of a typed error.
- Silent changes to response or event shapes.
- Hardcoded endpoints, regions, tenants, queue or table names (journey-runtime-config).
