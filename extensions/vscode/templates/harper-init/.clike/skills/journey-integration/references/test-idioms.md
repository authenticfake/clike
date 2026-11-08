# Test idioms: integration

Fake the external system at the network or protocol boundary and make it misbehave on demand.

## Python

- pytest + `respx` (httpx) or `responses` (requests) to return 500, 429 with `Retry-After`, malformed JSON, truncated pages; `httpx.TimeoutException` via a delayed route or side effect.
- Schema validation at the boundary (for example pydantic models); assert the rejection and that nothing was stored.
- Webhooks: compute the HMAC with a test secret; assert 401/400 for bad signature, stale timestamp, repeated event ID.
- Time / backoff: `freezegun` or an injected clock; circuit breaker state asserted after N failures.
- Contract fixtures checked into the test root; optional live checks marked and excluded from blocking runs.

## TypeScript / web

- vitest + MSW (`http.get(..., () => HttpResponse.json(..., { status: 429, headers: { "Retry-After": "30" } }))`) or nock.
- Timeouts: fake timers plus a never-resolving handler; assert abort via `AbortController`.
- Schema checks (for example zod) asserted on malformed payloads.
- UI: Testing Library asserts the degraded or waiting message; Playwright `page.route()` simulates provider outages end to end.

## Java

- JUnit 5 + WireMock (faults, `withFixedDelay`, 429 stubs) or MockWebServer; Testcontainers for brokers.
- Resilience4j circuit breaker and retry asserted with a fake clock.
- Contract tests (for example Pact or Spring Cloud Contract) for the response schema.

## .NET

- xUnit + WireMock.Net or a custom `HttpMessageHandler`; Polly / resilience pipelines asserted with `FakeTimeProvider`.
- `WebApplicationFactory` to replace the typed client base address with the fake.

## Go

- `testing` + `httptest.NewServer` handlers that delay, fail or return bad bodies; `context.WithTimeout` asserted.
- Table-driven cases per failure mode; fake store counting side effects.

## Mobile

- Fake backend (for example MockWebServer, URLProtocol stubs) for offline, slow, 429 and malformed responses; UI tests assert the user message.

## IaC

- Policy tests that outbound endpoints use TLS, secrets come from the secret store, and alarms exist for integration error rates.

## PLC / SCADA / industrial

- OPC UA / Modbus / MQTT simulator to drop connections, return bad quality codes or stale timestamps; assert alarm raise and safe handling (see journey-industrial-control for safety scenarios).
