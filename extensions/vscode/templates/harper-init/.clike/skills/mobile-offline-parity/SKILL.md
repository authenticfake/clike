# Skill: Mobile Offline Parity

## Intent

Ensure mobile and mobile-like requirements handle offline, intermittent connectivity, device constraints, and synchronization explicitly.

This skill applies to native mobile, hybrid mobile, PWA, field apps, and operator apps running in constrained environments.

## Use when

Use this skill when a REQ touches mobile apps, PWA behavior, offline mode, local storage, synchronization, field operations, device APIs, push notifications, camera, location, poor connectivity, or mobile UX.

## Do not use when

Do not use this skill for desktop-only backend services, server-only APIs, or frontend pages with no mobile/offline/device behavior.

## Signals

- The REQ mentions mobile, iOS, Android, React Native, Flutter, PWA, offline, sync, local storage, cache, device, camera, geolocation, push notification, field operator, tablet, handheld, or intermittent network.
- Acceptance criteria include offline behavior or mobile responsiveness.
- Design profile mentions mobile operator app, field app, industrial operator UI, or consumer mobile app.

## Required behavior

- Define online, offline, reconnecting, synced, conflict, and failed-sync states when relevant.
- Keep offline data boundaries explicit.
- Avoid silent data loss.
- Make synchronization idempotent where practical.
- Document device permission assumptions.
- Keep mobile UI accessible and usable on constrained screens.
- Provide local tests for offline state transitions when the stack allows it.
- Mark real device/cloud push checks as opt-in unless infrastructure is available.

## Forbidden behavior

- Do not assume always-on connectivity.
- Do not silently discard local changes after reconnect.
- Do not hardcode device identifiers or production endpoints.
- Do not require real device hardware for unit tests unless explicitly scoped.
- Do not claim offline support if only cached static UI exists.
- Do not ignore permission-denied states for device capabilities.

## Evidence required

- Tests or documented checks for offline/reconnect behavior.
- Source code showing explicit local persistence or cache boundaries when offline behavior is required.
- HOWTO explaining local simulation and optional device checks.
- UI states for sync progress, sync failure, and conflict when relevant.
- Configuration separating local/dev/prod runtime endpoints.

## Repair guidance

- If connectivity assumptions are implicit, add explicit network state handling.
- If sync can duplicate operations, add idempotency keys or conflict handling.
- If offline data is unbounded, document retention and cleanup assumptions.
- If tests require hardware, introduce adapter boundaries and local fakes.
- If permissions are missing, add permission-denied behavior and documentation.

## Gate implications

Gate should block promotion when:
- Offline/mobile behavior is acceptance-critical but not implemented.
- Data loss is possible during reconnect without documented handling.
- Required mobile checks fail.
- Device permissions are used without denied-state behavior.
- Runtime endpoints are hardcoded.

Gate may allow non-blocking warnings when:
- Real-device validation is documented but unavailable.
- Push notification or app-store checks are outside current REQ scope.

## Examples

- A field app REQ stores inspections locally, retries sync, and shows conflict status.
- A PWA REQ handles offline read-only mode and documents cache invalidation.
- A mobile form REQ validates locally and queues submission until reconnect.

## Non-examples

- A responsive page that claims mobile readiness without touch, layout, or state evidence.
- An offline toggle that only hides API errors.
- A mobile feature that crashes when geolocation permission is denied.
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
