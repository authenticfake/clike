# Test idioms: API contract

Exercise the full request pipeline and validate every response against the published contract.

## Python

- pytest + framework `TestClient` / httpx `AsyncClient` on the app factory (middleware included).
- Parametrize error cases: `(payload, status, code, field)`; assert `status_code`, `json()["code"]`, `json()["message"]`, `json()["details"]`.
- Schema conformance: validate responses against the OpenAPI document (for example `openapi-core`, `jsonschema`) or property-based checks with Schemathesis.
- Breaking changes: diff the generated OpenAPI against the committed one (for example `oasdiff`) as a blocking check.

## TypeScript / web

- vitest + supertest (or the framework inject API) against the real app.
- Validate responses with the shared schema (zod, ajv against OpenAPI).
- GraphQL: execute operations against the schema; assert `errors[].extensions.code` and messages.
- Client side: Testing Library / Playwright assert that API error messages surface as readable UI text.

## Java

- JUnit 5 + MockMvc (`jsonPath("$.code")`, `jsonPath("$.details[0].field")`) or RestAssured against a started app.
- Spring Security test support for 401/403; ProblemDetails or the project error schema asserted.
- Contract tests (Spring Cloud Contract, Pact) and OpenAPI validation (for example swagger-request-validator).

## .NET

- xUnit + `WebApplicationFactory<Program>`; assert ProblemDetails / ValidationProblemDetails fields.
- Snapshot the generated OpenAPI document and diff it in a blocking test.
- gRPC: in-process test server; assert `StatusCode` and status detail messages.

## Go

- `testing` + `httptest` on the real router with middleware; table-driven error cases decoding the error body.
- OpenAPI validation (for example kin-openapi) of responses; protobuf breaking-change checks (for example buf breaking).

## Mobile

- Contract tests that the app's API client parses every documented error shape and maps it to user-facing text; fake server returns 401/403/404/409/429.

## IaC

- Policy tests that API gateways enforce authentication, request size limits, throttling and TLS; plan-level tests for stage/version routing.

## PLC / SCADA / industrial

- OPC UA information model or MQTT topic/payload contracts validated against the published model; invalid writes return a defined status code and are logged.

## Rust

- axum `oneshot` / actix-web `test::call_service` against the real router; decode bodies with `serde_json` and assert the error schema fields.
- Schema parity: validate responses against the published OpenAPI document (generated with utoipa or checked with the `jsonschema` crate).
- Invalid input at scale: `proptest` strategies for out-of-range and malformed fields, asserting a 4xx with the field named.
