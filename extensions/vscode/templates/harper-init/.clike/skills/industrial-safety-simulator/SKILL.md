# Skill: Industrial Safety Simulator

## Intent

Ensure industrial, manufacturing, edge, shop-floor, PLC, SCADA, MES, and control-room requirements are validated through safe simulation boundaries before any real-world integration.

This skill prevents generated software from treating industrial operations as ordinary CRUD workflows.

## Use when

Use this skill when a REQ touches manufacturing, industrial systems, shop-floor workflows, PLC, SCADA, MES, HMI, OPC UA, Modbus, MQTT, edge gateways, sensors, actuators, alarms, safety states, production lines, maintenance workflows, or control-room UI.

## Do not use when

Do not use this skill for generic enterprise software with no industrial runtime, physical process, equipment, sensor, actuator, operator, or safety implication.

## Signals

- The REQ mentions industrial, manufacturing, plant, factory, shop floor, PLC, SCADA, MES, HMI, OPC UA, Modbus, MQTT, edge, sensor, actuator, alarm, maintenance, downtime, line status, operator, or control room.
- The selected pack is industrial-manufacturing or industrial-solution.
- The selected design profile is industrial-control-room.
- Acceptance criteria include real-time status, equipment state, alarms, or operator actions.

## Required behavior

- Keep real equipment integration behind explicit adapters.
- Provide simulator/fake device paths for local tests.
- Treat write/control actions as high-risk and require explicit approval or simulation-only behavior unless the REQ explicitly provides a safe runtime.
- Model safety states explicitly where relevant: unknown, stale, degraded, alarm, stopped, manual override, and emergency.
- Show stale data and telemetry age in operator-facing UI when relevant.
- Document polling, latency, retry, and failure assumptions.
- Separate read-only monitoring from write/control operations.
- Mark real plant/equipment integration as external and non-blocking unless a safe test environment is provided.

## Forbidden behavior

- Do not send commands to real equipment from generated tests.
- Do not hide stale, missing, or degraded telemetry.
- Do not assume all equipment states are safe or reachable.
- Do not hardcode PLC/SCADA/MES endpoints, credentials, station IDs, or equipment identifiers.
- Do not implement write/control actions without safety boundary and approval semantics.
- Do not claim production plant readiness from simulator-only evidence.
- Do not optimize for visual novelty over operator clarity and alarm readability.

## Evidence required

- Simulator or fake adapter tests for industrial data and failure states.
- Explicit adapter boundary for real industrial protocols or systems.
- HOWTO explaining simulator/local mode and external validation mode.
- Safety-state handling evidence when physical process impact exists.
- Control-room UI evidence for alarm visibility, stale data, and operator readability when UI is involved.
- Gate notes distinguishing simulation evidence from real integration evidence.

## Repair guidance

- If code connects directly to industrial endpoints, introduce a simulator-compatible adapter.
- If stale data is invisible, add timestamp/age/degraded indicators.
- If write actions exist, add dry-run, approval, or disabled-by-default controls.
- If tests require real equipment, replace with simulator tests and document external validation.
- If UI is unclear, prioritize operator scanning, status grouping, contrast, and alarm hierarchy.

## Gate implications

Gate should block promotion when:
- Industrial write/control behavior lacks safety boundary.
- Tests can affect real equipment.
- Required simulator evidence is missing.
- Stale/degraded telemetry is hidden for operator-facing requirements.
- Real integration is claimed without external evidence.

Gate may allow non-blocking warnings when:
- Real plant validation is unavailable but simulator checks pass.
- Latency/performance checks require a dedicated industrial test environment.

## Examples

- A SCADA monitoring REQ uses a fake OPC UA adapter in tests and documents real endpoint configuration separately.
- A control-room dashboard shows stale telemetry age, alarm severity, and degraded state.
- A MES integration REQ has read-only local simulator tests and marks production connectivity as external validation.

## Non-examples

- A test that writes directly to a PLC endpoint.
- A dashboard that always shows green status when telemetry is missing.
- A generated control action with no dry-run or approval boundary.
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
