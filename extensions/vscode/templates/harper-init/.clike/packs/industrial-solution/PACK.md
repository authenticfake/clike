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

- industrial-safety-simulator
- local-cloud-parity
- backend-contract-boundary
- eval-contract-writer
- gate-risk-reviewer
- frontend-state-accessibility when operator UI is involved

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
- Required checks fail or status is PASS_WITH_WARNINGS.

Gate may allow non-blocking warnings when:

- Real plant validation is unavailable but simulator checks pass.
- Latency/performance checks require dedicated industrial infrastructure.
