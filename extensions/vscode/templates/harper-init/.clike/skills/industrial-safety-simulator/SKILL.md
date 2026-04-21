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
