# Test idioms: payments

A fake provider records charges and idempotency keys; webhooks are signed in the test with a test secret.

## Python

- Money as `int` minor units or `decimal.Decimal` with explicit quantize; hypothesis property tests for totals and refunds.
- Webhooks: build the signed payload with the test secret, post it with `TestClient`, assert state; post twice, assert once.

## TypeScript / web

- Money as integer minor units (or a decimal library with an explicit scale, never `number` arithmetic on amounts); fast-check property tests; supertest for webhook endpoints with signed bodies.

## Java

- `BigDecimal` with explicit scale and `RoundingMode`, or `long` minor units; jqwik for property tests; MockMvc for webhooks.

## .NET

- `decimal` with explicit rounding, or `long` minor units; FsCheck for property tests; `WebApplicationFactory` for webhooks.

## Go

- `int64` minor units; table and fuzz tests (`testing.F`) for totals; `httptest` for signed webhooks.

## Rust

- Integer minor units or `rust_decimal`; `proptest` for totals and refunds; axum `oneshot` for signed webhooks.
