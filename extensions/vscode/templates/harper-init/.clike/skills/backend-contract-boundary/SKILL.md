---
name: backend-contract-boundary
description: Keep backend contracts explicit and stable; isolate internal types behind boundaries.
obligations:
  - Define explicit backend contracts for the REQ
  - Keep internal types behind service/adapter boundaries
eval_checks:
  - explicit-contract-defined
  - contract-tests-present
  - no-leaky-internal-types
gate_implications:
  - block-if-unstable-public-contract
  - block-if-missing-contract-tests
evidence_required:
  - Contract tests
  - Interface/contract docs
---

# Skill: Backend Contract Boundary

## Intent

Ensure backend requirements produce stable, testable contracts instead of ad-hoc implementation code.

This skill protects API boundaries, domain boundaries, persistence boundaries, adapter boundaries, and error semantics.

## Use when

Use this skill when a REQ touches backend services, APIs, controllers, routes, workers, domain logic, persistence, queues, webhooks, adapters, SDK integrations, authentication, authorization, or service contracts.

## Do not use when

Do not use this skill for purely frontend visual work, static documentation, or isolated scripts with no public or internal contract.

## Signals

- The REQ mentions API, endpoint, service, route, FastAPI, Flask, Django, Express, NestJS, worker, queue, database, repository, adapter, webhook, schema, DTO, OpenAPI, contract, persistence, auth, or domain boundary.
- Generated files include backend source, migrations, service classes, adapters, routers, validators, or integration tests.
- Acceptance criteria depend on request/response behavior, events, persistence effects, or external integration semantics.

## Required behavior

- Keep public contracts explicit: request schema, response schema, event payload, command shape, or adapter interface.
- Validate inputs at the boundary.
- Keep domain logic independent from transport details when practical.
- Keep external systems behind adapters or ports.
- Preserve backward compatibility unless the REQ explicitly allows a breaking change.
- Use typed errors or stable error responses where the stack supports them.
- When tests or CI scripts assert error semantics, access custom error metadata only through the active language's safe narrowing, casting, matching, downcast, typed-exception, or adapter mechanism.
- Include local deterministic tests for domain and boundary behavior.
- Mark real external service checks as opt-in unless infrastructure is available.

## Forbidden behavior

- Do not call external SDKs directly from core domain logic.
- Do not change public API shape silently.
- Do not swallow errors without observable behavior.
- Do not hardcode credentials, regions, tenants, URLs, queue names, or database identifiers.
- Do not create migrations or persistence changes without documenting compatibility and rollback assumptions.
- Do not use broad exception handling as a substitute for contract design.
- Do not claim integration readiness without a local test or documented external check.

## Evidence required

- Source code showing explicit boundaries.
- Tests covering success and failure contract behavior.
- HOWTO commands for backend tests, lint, type checks, and smoke checks when available.
- Contract documentation or generated schema notes when the REQ changes API/event behavior.
- External integration assumptions documented as blocking or non-blocking in LTC.

## Repair guidance

- If transport logic and domain logic are mixed, introduce a minimal service or adapter boundary.
- If contract behavior is implicit, add typed schema or validation.
- If errors are unstable, add deterministic error mapping.
- If tests require real services, replace with fake/local adapter tests and document opt-in integration checks.
- If the change breaks existing contracts, either restore compatibility or explicitly update acceptance criteria and docs.

## Gate implications

Gate should block promotion when:
- Public contract behavior changed without tests or documentation.
- Required backend checks fail.
- External calls are made from unit tests without local isolation.
- Auth, persistence, or webhook behavior lacks failure-path evidence.
- Boundary code hardcodes environment-specific values.

Gate may allow non-blocking warnings when:
- External smoke checks cannot run locally but are documented as opt-in.
- OpenAPI/schema export is unavailable but request/response tests provide evidence.

## Examples

- A FastAPI route delegates to a service, validates input with schemas, returns stable errors, and has route-level tests.
- A queue integration uses an adapter interface with in-memory tests and documented cloud runtime configuration.
- A webhook handler verifies payload shape, handles duplicate events, and has deterministic tests.

## Non-examples

- A route that directly instantiates a cloud client and writes to a database without tests.
- A worker that catches all exceptions and logs only "failed".
- A generated API that changes response fields without compatibility notes.
---

# CLike Promotable KIT Enforcement Layer

## Purpose

This layer makes the skill operational for CLike `/kit` generation.

The goal is not to produce plausible code. The goal is to produce candidate artifacts that can be evaluated, repaired, and promoted through EVAL and GATE with minimal human rework.

## Promotable Code Obligations

When this skill is selected for a REQ, the KIT must:

- respect `main_module_boundary`;
- respect `functional_scope` and `technical_scope`;
- generate the smallest complete implementation slice;
- prefer repository-native conventions over invented abstractions;
- produce source files only under the target KIT source root;
- produce tests only under the target KIT test root;
- keep canonical `src/`, `test/`, and `tests/` read-only during candidate generation;
- document any intentional limitation instead of pretending completeness;
- avoid broad rewrites unless explicitly required by the REQ.

## Required Candidate Artifacts

The KIT should produce or update:

```text
runs/kit/<REQ-ID>/src/
runs/kit/<REQ-ID>/test/
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md
```

If the REQ is documentation-only or policy-only, the KIT must explicitly state why source/test artifacts are not required.

## Code Shape Expectations

Generated code should favor:

- explicit boundaries;
- dependency injection or constructor/function injection where practical;
- small cohesive modules;
- deterministic local behavior;
- typed schemas/contracts when the stack supports them;
- error paths that are visible and testable;
- safe defaults;
- clear adapter seams for external systems.

Generated code must avoid:

- hidden global state;
- hardcoded environment assumptions;
- silent fallbacks;
- fake success;
- speculative framework layers;
- broad unrelated refactors;
- acceptance criteria implemented only in prose.

## Test Expectations

Tests must map to acceptance criteria.

Prefer:

- deterministic unit tests;
- contract tests around adapters and payloads;
- failure-path tests;
- local fake/simulator tests for external dependencies;
- smoke checks only when deeper tests are not possible.

Avoid:

- placeholder tests;
- tests that only import modules when behavior is required;
- tests that require production credentials;
- network-dependent blocking tests unless explicitly scoped.

## LTC Expectations

`ci/LTC.json` must be valid JSON and include enough information for EvalRunner or a local agent to execute checks.

It should include:

- target `req_id`;
- lane/runtime profile when known;
- blocking local commands;
- optional external commands;
- report paths when available;
- environment-blocked status for unavailable infrastructure;
- gate-relevant policy hints.

## HOWTO Expectations

`ci/HOWTO.md` must be clear enough for a developer to run without guessing.

It should include:

- where to run commands from;
- prerequisites;
- local commands;
- expected result;
- troubleshooting;
- required environment variables;
- optional external validation steps;
- limitations and non-goals.

## Gate Impact

GATE should BLOCK promotion when this selected skill is materially violated.

Blocking examples:

- source is not mapped to the target REQ;
- acceptance-critical behavior has no test or executable evidence;
- LTC/HOWTO are missing for runnable code;
- production services or credentials are required for local blocking checks;
- selected capability obligations are ignored;
- generated files modify forbidden canonical roots;
- code claims completeness without evidence.

GATE may WARN when:

- optional external validation is not available but a deterministic local contract check exists;
- documentation is thin but executable evidence is complete;
- future hardening is correctly documented as out of scope.
