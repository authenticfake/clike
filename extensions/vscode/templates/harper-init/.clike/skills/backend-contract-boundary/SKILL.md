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
