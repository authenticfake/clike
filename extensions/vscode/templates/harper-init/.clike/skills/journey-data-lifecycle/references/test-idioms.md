# Test idioms: data lifecycle

Prove each DAT scenario against a store with the real constraints and assert both the message and the unchanged data.

## Python

- pytest + `TestClient` / httpx against the app with a test database (SQLite in-memory only if constraints match; otherwise a containerized database).
- Validation: assert the error body lists each invalid field with its message, then query the store to confirm nothing was written.
- Concurrency: version column or ETag; send two updates with the same version, expect 409 on the second.
- Pagination: seed fixtures with factories, assert ordering and `next` cursor or page metadata.
- Audit: assert the audit row (actor, timestamp from a frozen clock, changed fields).

## TypeScript / web

- vitest + Testing Library: render the list with an empty fixture and assert the empty-state text and call to action; render with a filter that matches nothing and assert the distinct no-results text.
- Forms: submit invalid data, assert inline field messages (`getByText`, `toHaveAccessibleDescription`) and the error summary.
- API: supertest or the framework test client with a real test database.
- Journeys: Playwright for create, edit conflict (two browser contexts editing the same record), delete with confirmation dialog, not-found route.

## Java

- JUnit 5 + MockMvc or RestAssured with Testcontainers for the database.
- `@Version` optimistic locking: assert 409 and the message on stale update.
- Bean Validation: assert each field error in the response body.
- Journeys: Playwright for Java.

## .NET

- xUnit + `WebApplicationFactory` with a containerized or provider-equivalent database.
- Concurrency tokens (`rowversion` / `[ConcurrencyCheck]`): assert `DbUpdateConcurrencyException` maps to 409 with a readable message.
- ValidationProblemDetails: assert the `errors` dictionary per field.
- Journeys: Playwright .NET.

## Go

- `testing` + `httptest` with a real test database; table-driven validation cases.
- Assert the decoded error body per field and re-read the row to confirm no write.

## Mobile

- Component tests for list empty/no-results/not-found screens and inline form errors.
- Emulator E2E for create, edit, delete confirmation and offline save conflict if sync exists.

## IaC

- Policy tests that data stores enable deletion protection, backups and point-in-time recovery where the audit or restore scenarios are included.

## PLC / SCADA / industrial

- Recipe or setpoint storage: unit tests (for example TcUnit) that out-of-range values are rejected with an alarm text and the active recipe is unchanged.
- Recipe changes recorded in the audit or event log with operator identity, verified against a simulator.
