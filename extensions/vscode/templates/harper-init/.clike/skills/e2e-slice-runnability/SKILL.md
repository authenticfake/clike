---
name: e2e-slice-runnability
description: Use when a REQ delivers a user or service flow (API, page, workflow, integration), to make it a complete, wired, runnable slice — reusing what exists, reachable from a real entrypoint and proved end to end — instead of an isolated module or a decorative screen; at FINALIZE, to compose the promoted slices into one runnable solution.
phases: ["plan", "kit", "eval", "finalize"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "frontend", "backend", "ai-native", "iac"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - The REQ's primary flow is reachable from a real entrypoint (route, page, command, consumer) and proved by a test that goes through it
  - Reuse and register through existing composition; never a parallel app, launcher or router
  - Every frontend call has its backend route; no flow completed only in client state
eval_checks:
  - end-to-end-flow-tested
gate_implications:
  - block-if-flow-not-reachable-from-an-entrypoint
evidence_required:
  - The test that drives the primary flow through the entrypoint
---

# E2E Slice Runnability

## Intent

A REQ is useful when someone can run it: the route answers, the page loads real data, the job is
consumed, the flow ends in persisted state. Plausible modules with no entrypoint, screens that fake
completion in local state, and a second launcher next to the first are the typical ways a generated
slice looks done and is not.

## Use when

The REQ delivers a user or service flow (API, page, workflow, job, integration), or FINALIZE
composes the promoted REQs.

## Do not use when

Documentation-only REQs, deliberate spikes declared non-promotable, pure libraries.

## KIT rules

- Start from what exists: the plan's shared seams (router registration, module registry, one
  migration per REQ). Add files and register them; do not rewrite composition files.
- Wire the whole flow of the REQ: entrypoint → service → persistence or adapter → response or
  visible result. A REQ with UI calls the real backend route (or the plan says which REQ provides
  it); the UI shows the loading, empty, error and success states the journeys require.
- Prove it through the entrypoint: one test per primary flow drives the route, page, command or
  consumer and asserts the persisted or visible outcome, plus its main failure path.
- Business rules and authorization live in the backend; the frontend reflects them and handles
  denials.
- Out of scope stays out: say it in `docs/KIT_<REQ-ID>.md`, do not stub it as if done.

## Forbidden

- A single decorative page where the REQ implies operational capabilities.
- "Completed" flows that only change component state when a backend API is required.
- A new launcher, app factory or router per feature; rewriting working modules when wiring them is enough.
- Tests that import internals but never touch the entrypoint for the primary flow.

## FINALIZE

Close the gap between promoted slices and one runnable solution: composition root, settings loader
(journey-runtime-config), dependency and session factories, a local profile, run and check scripts,
frontend/backend route parity, README/HOWTO that match the real commands, no junk artifacts, valid
manifests. Each item is verified by a command, not described.
