---
name: journey-async-jobs
description: Use when work runs in the background (jobs, queues, workers, scheduled or long tasks), to enumerate and prove the async scenarios (status, retry, timeout, cancel, idempotency, crash recovery, failed jobs) beyond a job that simply succeeds.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: JOB
scenarios:
  - JOB-01 | required | Accepted and queued | When a user or system submits long-running work, the system shall accept it immediately, return a job identifier and record the job as queued.
  - JOB-02 | required | Progress and status visible | When a job is running, the system shall expose its status and progress so that the user or caller can see queued, running, succeeded or failed without guessing.
  - JOB-03 | required | Retry with backoff | If a job step fails with a transient error, then the system shall retry it with bounded backoff and record each attempt.
  - JOB-04 | required | Timeout | If a job exceeds its time limit, then the system shall stop it, mark it as timed out with a readable reason and release its resources.
  - JOB-05 | required | Cancel | When a user cancels a queued or running job, the system shall stop it at a safe point, mark it cancelled and leave no partial result presented as complete.
  - JOB-06 | required | Idempotent resubmit | If the same work is submitted again (retry, double click, redelivered message), then the system shall not duplicate its side effects and shall return the existing job or result.
  - JOB-07 | required | Resume after restart or crash | If the worker or host restarts while jobs are in flight, then the system shall resume or safely re-run them and never leave them stuck as running.
  - JOB-08 | required | Failed job surfaced to operator | If a job fails permanently or a message is poison, then the system shall move it to a failed or dead-letter state, keep the error detail and make it visible to an operator with a way to retry or discard.
  - JOB-09 | conditional | [Concurrency or quota limits apply] Concurrency limits | When the number of running jobs reaches the configured limit, the system shall queue further jobs and show that they are waiting instead of failing or overloading.
  - JOB-10 | conditional | [Scheduled jobs exist] Schedule and missed runs | When a scheduled run time is reached or was missed during downtime, the system shall run it once according to the stated catch-up policy and never run it twice concurrently.
obligations:
  - Enumerate every JOB scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Persist job state outside process memory when restart recovery is in scope
  - Make side effects idempotent with an explicit key
eval_checks:
  - scenario-coverage
  - failure-state-asserted
  - idempotency-tested
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-jobs-can-stay-running-forever
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Async Jobs

## Intent

Background work fails in ways a request-response flow never shows: it gets stuck, runs twice, is lost on restart, or fails where nobody looks. This skill makes each of those outcomes an explicit scenario with proof.

## Use when

- Use cases or REQs mention job, task, worker, queue, background, batch, scheduled, cron, nightly, import, export generation, report generation, processing, pipeline, ingestion, long-running, async, notification sending.
- Any operation that takes longer than a normal request or is triggered by a message or timer.
- Batch sequences or long cycles on an industrial controller.

## Do not use when

Everything the REQ does completes synchronously within the request, with no queue, scheduler or background worker.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason.
- **PLAN**: assign each included scenario ID to one owning REQ in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `JOB-06: resubmitting with the same key returns the existing job and sends one email`).
- **KIT**: one blocking check per included scenario recorded in docs/ACCEPTANCE.json with the scenario ID.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- Work completes within one request and is never queued: the whole skill is not applicable; say so once.
- Pure read-only computation with no side effects: JOB-06 may be reduced to "re-run returns the same result".
- Platform-managed queue with dead-lettering configured: JOB-08 remains, proven by a test that a failing message reaches the dead-letter target and is visible.
- Not a valid reason: "the queue library retries" without a test of the configured limits.

## Proof per scenario

- Run the worker in-process or with a local broker; drive time with a controlled clock and step the worker deterministically.
- Inject failures with a fake dependency that fails N times, then succeeds or fails permanently.
- Assert job state transitions and the visible status text or API payload, not only log lines.
- Idempotency: submit twice with the same key, assert one side effect (one row, one call on the fake).
- Restart: start a job, stop the worker mid-step, start a new worker, assert completion or safe re-run and no job stuck as running.
- Operator visibility: assert the failed job appears in the operator view or API with its error.

## Forbidden

- Tests that only check a job succeeds.
- Real sleeps to wait for completion; use polling with a timeout or deterministic stepping.
- Unbounded retries or retries without backoff.
- Job state only in memory when restart recovery is included.
- Swallowing errors so a failed job looks succeeded.

## References

- references/test-idioms.md
