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
---

# CLike Promotable KIT Pack Overlay

## Purpose

This pack is a scenario-level orchestrator for CLike `/kit`.

It should help the model choose the right constraints, not generate decorative architecture.

## Default Promotable Skills

For code-producing REQs, prefer selecting relevant skills from:

- `promotable-code-boundary` when available;
- `backend-contract-boundary` for backend/API/service work;
- `frontend-state-accessibility` for UI work;
- `local-cloud-parity` for runtime or external dependencies;
- `eval-contract-writer` for executable validation;
- `gate-risk-reviewer` for promotion safety;
- `secure-config-secrets` when available for credentials/config/runtime;
- `observability-diagnostics` when available for supportability;
- scenario-specific skills already listed by this pack.

Do not select every skill automatically. Select only those justified by the REQ, lane, runtime profile, and acceptance criteria.

## KIT Behavior

When this pack is selected, KIT generation must:

- keep the implementation slice narrow and promotable;
- obey repository conventions before adding new layers;
- generate executable evidence;
- separate local deterministic validation from optional external validation;
- document runtime assumptions;
- preserve future compatibility for dependent REQs;
- avoid fake completeness and broad speculative architecture.

## Required Evidence

The KIT should provide:

- source mapped to the REQ;
- tests mapped to acceptance criteria;
- `ci/LTC.json`;
- `ci/HOWTO.md`;
- capability adherence notes in KIT documentation;
- external infrastructure assumptions when relevant.

## Gate Bias

This pack biases GATE toward safe promotion.

Promotion should require full `PASS`.

`PASS_WITH_WARNINGS` must not promote.

Warnings are acceptable only when the missing evidence is explicitly non-blocking, external, and documented with a deterministic local fallback.
