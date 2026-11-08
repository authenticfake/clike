---
name: journey-api-contract
description: Use when a capability exposes an API (REST, GraphQL, gRPC, messages, CLI contract), to enumerate and prove the contract scenarios (invalid input, 401, 403, 404, 409, versioning, limits, idempotency, consistent error schema) beyond a 200 response.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: API
scenarios:
  - API-01 | required | Valid request | When a client sends a valid, authorized request, the system shall return the documented success status and a body that matches the published schema.
  - API-02 | required | Invalid input | If a request has missing, malformed or out-of-range fields, then the system shall return a 4xx (or the protocol equivalent) with a readable error body that names each invalid field.
  - API-03 | required | Unauthenticated | If a request has no credentials or invalid credentials, then the system shall return 401 (or the protocol equivalent) without executing the operation or leaking data.
  - API-04 | required | Unauthorized | If an authenticated client requests an operation or resource outside its permissions, then the system shall return 403 (or the protocol equivalent) and leave state unchanged.
  - API-05 | required | Not found | If a request targets a resource that does not exist, then the system shall return 404 (or the protocol equivalent) with the standard error body.
  - API-06 | required | Conflict | If a request conflicts with current state (duplicate, stale version, invalid transition), then the system shall return 409 (or the protocol equivalent) with a message explaining the conflict; precondition headers are API-15.
  - API-07 | required | Consistent error schema | When any error is returned, the system shall use one documented error schema (code, message, details, correlation id) and never expose stack traces or internal identifiers.
  - API-08 | required | Versioning and backward compatibility | When the contract changes, the system shall keep existing clients working (additive changes or a new version) and the published schema shall match the implementation.
  - API-09 | required | Pagination | When a client requests a collection, the system shall return pages with documented parameters, a stable order and a capped page size.
  - API-10 | conditional | [Unsafe operations may be retried] Idempotency keys | If a client retries an unsafe request with the same idempotency key, then the system shall return the original result and not repeat the side effect.
  - API-11 | required | Request size and media type | If a request body exceeds the size limit or has an unsupported media type, then the system shall reject it before processing with 413 or 415 (or the protocol equivalent) and a readable message stating the limit or the accepted types.
  - API-12 | conditional | [Public, partner or shared API] Rate limit | If a client exceeds its rate limit, then the system shall answer 429 (or the protocol equivalent) with Retry-After and execute nothing.
  - API-13 | required | Object-level authorization | If an authenticated client requests an object it does not own or may not see, by guessing or changing its identifier, then the system shall answer as not found or forbidden and return no data of that object.
  - API-14 | required | Server-owned fields protected | If a request body sets fields the server owns (identifier, owner, role, status, timestamps, prices), then the system shall reject or ignore them and never apply them.
  - API-15 | conditional | [Clients cache or edit concurrently] Entity tags | When a client sends If-None-Match with the current tag, the system shall answer 304; when it sends If-Match with a stale tag, the system shall answer 412 and change nothing.
  - API-16 | conditional | [Browser clients on other origins] Cross-origin policy | If a browser request comes from an origin not in the configured list, then the system shall not grant it cross-origin access.
  - API-17 | conditional | [Endpoints are being retired] Deprecation signalled | When a client calls a deprecated endpoint, the system shall still answer and signal the deprecation and its sunset date in the response headers and the published schema.
obligations:
  - Enumerate every API scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Publish the contract (OpenAPI, GraphQL schema, protobuf, message schema) and test the implementation against it
  - Assert error body content, not only status codes
eval_checks:
  - scenario-coverage
  - error-body-asserted
  - contract-matches-implementation
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-breaking-change-without-version
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: API Contract

## Intent

An API is a promise to clients. Clients depend as much on how it fails (status, error body, limits) as on how it succeeds. This skill makes every contract outcome an explicit scenario, proven against the published schema. It complements backend-contract-boundary with traceable scenario IDs.

## Use when

- Use cases or REQs mention API, endpoint, route, resource, REST, GraphQL, gRPC, webhook provider, SDK, public interface, message contract, event schema, CLI with machine-readable output.
- A frontend, mobile app, device or partner system consumes the service.

## Do not use when

The REQ exposes no API to other programs (a UI-only change, a batch script, embedded logic without a service interface).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason; reference the contract file.
- **PLAN**: assign each included scenario ID to the REQ owning the endpoint group in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `API-06: POST /orders with a duplicate reference returns 409 {code: "duplicate_reference"}`).
- **KIT**: one blocking check per included scenario recorded in docs/ACCEPTANCE.json with the scenario ID, plus a schema conformance check.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- Public anonymous read-only API: API-03 and API-04 excluded with that reason; API-09 limits still apply.
- No mutable state: API-06 and API-10 excluded.
- Internal API with a single consumer deployed together: API-08 reduced to "schema matches implementation".
- Not a valid reason: "the framework returns 422 automatically" without asserting the body.

## Proof per scenario

- Call the real routing, middleware and handlers in-process or against a started service; fake only external dependencies.
- For each error scenario assert status, error code, message and details per field, and that state is unchanged.
- Validate every response (success and error) against the published schema.
- Backward compatibility: run the previous contract's tests or a schema diff and fail on breaking changes without a version bump.
- Pagination: assert page size caps, cursors or offsets and stable ordering.
- Idempotency: same key twice returns the same body and one side effect; same key with a different payload is rejected.

## Forbidden

- Asserting only status codes without the error body.
- Tests that call handler functions directly and skip authentication or validation middleware.
- Different error shapes per endpoint.
- Stack traces, SQL or internal IDs in error responses.
- Breaking contract changes without a version or deprecation path.
- A published schema that is not checked against the implementation.

## References

- references/test-idioms.md
