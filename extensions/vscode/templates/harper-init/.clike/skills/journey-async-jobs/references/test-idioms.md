# Test idioms: async jobs

Step the worker deterministically, inject failures, assert state transitions and visible status.

## Python

- pytest; run the worker function directly or with an eager/in-memory broker mode; use a containerized broker for redelivery and restart tests.
- Time and backoff: `freezegun` or an injected clock; assert the computed delays and the attempt count.
- Failures: a fake dependency raising N times (`side_effect=[Err, Err, ok]`) only at the external boundary.
- Idempotency: submit twice with the same key, assert one row and one call on the fake.
- Restart: start a job, abort the worker mid-step, run a fresh worker, assert final state.
- Async code: `pytest-asyncio` / `anyio` with `asyncio.wait_for` bounds instead of sleeps.

## TypeScript / web

- vitest with `vi.useFakeTimers()` and `vi.advanceTimersByTimeAsync()` for backoff and timeouts.
- Queue libraries: local broker or in-memory mode; assert retry counts and failed-queue entries.
- UI: Testing Library asserts the status labels (Queued, Running 40%, Failed: reason) and the cancel and retry controls.
- Journeys: Playwright submits work, polls the status UI with `expect.poll` / `toHaveText` with timeout, cancels, and checks the failed job view.

## Java

- JUnit 5 + Awaitility for bounded waits; Testcontainers for the broker.
- Spring Retry / Resilience4j: assert attempts and backoff with a fake clock.
- Assert dead-letter queue content and the operator API.

## .NET

- xUnit; hosted services run with `WebApplicationFactory` or directly; `FakeTimeProvider` for backoff and timeouts.
- Testcontainers for the broker; assert retry and dead-letter behaviour.

## Go

- `testing` with context deadlines; inject a clock; run the worker loop for a fixed number of iterations.
- Assert idempotency with a fake store counting writes; use `-race` for concurrency limits.

## Mobile

- Background work (WorkManager test helpers, BGTask simulation): assert constraints, retry and cancellation; UI tests show sync status and failure messages.

## IaC

- Policy tests that queues have dead-letter targets, max receive counts, visibility timeouts and alarms on dead-letter depth.

## PLC / SCADA / industrial

- Batch or sequence steps tested (for example TcUnit) with simulated I/O: step timeout raises an alarm, abort returns to a safe idle, power-loss restart resumes per the defined recovery mode.
