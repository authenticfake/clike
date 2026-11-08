---
name: industrial-solution
description: Industrial solution scenario: safe states, controlled commands, operational reliability.
obligations:
  - Model safe states and controlled command flows
  - Prioritize operational reliability and observability
eval_checks:
  - safe-state-default
  - controlled-command-flow
  - operational-observability-present
gate_implications:
  - block-if-unsafe-default-state
  - block-if-uncontrolled-critical-commands
evidence_required:
  - Safety/operational tests
---

# Pack: Industrial Solution

## Intent

Guide CLike generation for industrial, manufacturing, shop-floor, MES, SCADA, PLC, edge, and control-room scenarios.

This pack prioritizes safety boundaries, simulator-first validation, operational clarity, stale-data handling, and explicit separation between monitoring and control actions.

## Scenario signals

- Industrial, manufacturing, plant, factory, shop floor, production line, MES, SCADA, PLC, HMI, OPC UA, Modbus, MQTT, edge gateway, sensor, actuator, alarm, downtime, maintenance, operator, or control room.
- Requirements involving equipment state, telemetry, alarms, operator workflows, physical-world processes, or edge/on-prem runtime.
- Design profile industrial-control-room is selected.

## Use when

Use this pack when software interacts with industrial data, equipment, operators, plant systems, machine telemetry, or production workflows.

## Do not use when

Do not use this pack for generic enterprise CRUD applications with no industrial runtime, equipment, operator, telemetry, or safety implication.

## Required capabilities

Recommended skills:

- journey-industrial-control
- journey-runtime-config
- backend-contract-boundary
- eval-contract-writer
- gate-risk-reviewer
- journey-ui-states when operator UI is involved

Recommended design profiles:

- industrial-control-room for control-room and operator dashboards
- mobile-operator-app for field/tablet workflows

## Runtime assumptions

- Local simulator/fake-device mode is required for deterministic validation.
- Real equipment integration must be opt-in and never required for unit tests.
- Edge/on-prem/hybrid runtime may be required.
- Network connectivity may be intermittent or restricted.
- Telemetry can be stale, missing, delayed, duplicated, or degraded.

## Security/compliance assumptions

- Industrial endpoints, credentials, equipment identifiers, and plant topology must not be hardcoded.
- Write/control actions are high risk and must be disabled, dry-run, approval-gated, or simulator-only unless explicitly scoped.
- Operator-facing behavior must reveal stale/degraded/unknown states.
- Auditability is required for operationally significant actions.

## Architecture constraints

- Separate read-only monitoring from write/control actions.
- Keep industrial protocols behind adapters.
- Model safety states explicitly where relevant.
- Prefer deterministic simulator tests over real plant dependencies.
- Avoid visual novelty that reduces operator clarity.
- Avoid claiming plant readiness from simulator-only evidence.

## Eval expectations

- Simulator-based tests for telemetry and failure states.
- Adapter boundary tests for industrial protocols or system connectors.
- UI evidence for alarm readability, stale telemetry, and status hierarchy when UI is involved.
- HOWTO must separate simulator/local checks from real plant validation.
- Real equipment validation must be external and explicitly documented.

## Gate implications

Gate should block promotion when:

- Tests can affect real equipment.
- Industrial write/control behavior lacks a safety boundary.
- Simulator evidence is missing.
- Stale/degraded telemetry is hidden.
- Real plant readiness is claimed without external evidence.
- Required checks fail.

Gate may allow non-blocking warnings when:

- Real plant validation is unavailable but simulator checks pass.
- Latency/performance checks require dedicated industrial infrastructure.

---

# CLike Pack Overlay

## Skills

Select only the skills the REQ, lane, runtime profile and acceptance justify: the journeys whose
scenarios the REQ owns (`journey-*`), `eval-contract-writer` for every REQ that ships code,
`backend-contract-boundary` for backend contracts, `e2e-slice-runnability` for user or service
flows, plus the scenario-specific skills listed by this pack.

## Gate

The gate promotes on PASS and on PASS_WITH_WARNINGS (non-blocking checks failed or
environment-blocked, reported and tracked), unless the project enables strict warnings. A check
belongs in the blocking set when it proves an acceptance criterion or scenario in the sandbox; it is
non-blocking only when it needs infrastructure the sandbox does not have, with the reason stated.
