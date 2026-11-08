---
name: journey-integration
description: Use when a capability calls or is called by an external system, to enumerate and prove the integration scenarios (provider down, timeout, rate limit, bad response, expired credentials, partial data, safe retries, webhooks) beyond a provider that always answers.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: INT
scenarios:
  - INT-01 | required | Successful exchange | When the external system answers correctly, the system shall map the response into domain data and complete the user or service flow.
  - INT-02 | required | Provider down | If the external system is unreachable or returns a server error, then the system shall fail the dependent operation with a readable message and keep the rest of the product working.
  - INT-03 | required | Timeout | If the external system does not answer within the configured timeout, then the system shall abort the call, report a timeout and never wait indefinitely.
  - INT-04 | required | Rate limited | If the external system answers with a rate-limit response (for example 429 with retry-after), then the system shall back off as instructed and tell the caller the operation is delayed or must be retried.
  - INT-05 | required | Malformed or unexpected response | If a response lacks required fields or has invalid values, then the system shall reject it at the boundary, log the mismatch and not store or show corrupted data; unknown extra fields shall be ignored.
  - INT-06 | required | Expired or invalid credentials | If the external system rejects the credentials, then the system shall refresh them when possible, otherwise stop retrying and alert an operator with a clear reason.
  - INT-07 | required | Partial data | If the external system returns incomplete data (missing fields, truncated pages), then the system shall handle the gaps explicitly and show which data is missing instead of presenting it as complete.
  - INT-08 | required | Retries without duplicate side effects | If a call with side effects is retried after an ambiguous failure, then the system shall not create the side effect twice on either side.
  - INT-09 | conditional | [Repeated failures possible] Circuit breaker and degraded mode | If failures exceed the configured threshold, then the system shall stop calling the provider for a cool-down period and run in a stated degraded mode visible to users.
  - INT-10 | conditional | [Inbound webhooks exist] Webhook signature and replay | If an inbound webhook has an invalid signature, an old timestamp or a repeated event identifier, then the system shall reject it without side effects.
  - INT-11 | conditional | [The system sends webhooks or events to subscribers] Outbound delivery | When the system delivers an event to a subscriber, it shall sign it, retry failures with backoff, and move events still undelivered after the retry limit to a dead-letter state visible to an operator.
  - INT-12 | conditional | [Calls with side effects can fail ambiguously] Reconciliation | If the outcome of a call with side effects is unknown (timeout after sending), then the system shall query the provider for the real outcome before retrying or reporting it.
  - INT-13 | conditional | [The provider publishes a schema or contract] Contract pinned | When the provider contract changes, a consumer contract test pinned to the provider version shall fail before the change reaches production.
obligations:
  - Enumerate every INT scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Put every external system behind an adapter with explicit timeout, retry and schema validation
  - Keep blocking checks local with a fake or simulator; real-provider checks are optional
eval_checks:
  - scenario-coverage
  - failure-message-asserted
  - adapter-fake-or-simulator-present
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-external-call-without-timeout
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Integration

## Intent

External systems are slow, down, throttled, wrong or changed without notice. This skill turns each of those behaviours into a scenario the adapter must handle visibly and safely, proven locally with a fake or simulator.

## Use when

- Use cases or REQs mention API, integration, provider, third-party, ERP, CRM, payment, email, SMS, storage service, identity provider, webhook, callback, sync, connector, MES, historian, OPC UA, MQTT, model or inference endpoint.
- The KIT introduces an HTTP, gRPC, message or SDK client.

## Do not use when

The REQ calls no external system (no third-party API, registry, provider, message broker or device gateway).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios` per external system; include each `required` one or exclude it with a reason.
- **PLAN**: assign each included scenario ID to the REQ owning the adapter in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `INT-04: a 429 with retry-after 30 delays the sync and the status shows "Waiting for provider"`).
- **KIT**: one blocking check per included scenario recorded in docs/ACCEPTANCE.json with the scenario ID; the fake or simulator lives in the test root.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- Read-only call with no side effects: INT-08 reduced to "retry is safe", with that reason.
- Provider has no rate limiting by contract: INT-04 excluded, citing the contract.
- Static credential that cannot expire (rare): INT-06 excluded with the reason; rotation still documented.
- Not a valid reason: "the SDK handles retries" without a test of the configured behaviour.

## Proof per scenario

- Use a local fake server, recorded contract fixtures or a simulator that can return errors, delays, 429, malformed bodies and partial pages on demand.
- Assert the domain outcome and the message shown or returned to the caller, plus what was stored (nothing corrupted, nothing duplicated).
- Timeouts use short configured values and a fake that delays beyond them; no real waits of seconds.
- Duplicate protection: fail after the provider applied the effect, retry, assert one effect on the fake.
- Webhooks: sign with a test secret; assert rejection for bad signature, stale timestamp and repeated event ID.

## Forbidden

- Tests that only cover a successful provider response.
- Blocking checks that need real provider credentials or network.
- Mocking the adapter itself in the test that claims to prove its error handling.
- External calls without a timeout.
- Retrying non-idempotent calls without an idempotency key.
- Leaking provider error bodies or credentials into user messages or logs.

## References

- references/test-idioms.md
