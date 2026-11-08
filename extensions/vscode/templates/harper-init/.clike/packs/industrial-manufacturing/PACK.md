---
name: industrial-manufacturing
description: Use for industrial, manufacturing, shop-floor, MES, PLC/SCADA, MoM telemetry, control-room, and process automation scenarios.
domains: ["industrial", "manufacturing"]
default_runtime_profiles: ["local", "on-prem", "edge", "plant", "cloud", "hybrid", "air-gapped"]
recommended_skills: ["journey-industrial-control", "journey-runtime-config", "eval-contract-writer"]
gate_required: true
obligations:
  - Model safe states and operator confidence cues
  - Handle stale/disconnected states
eval_checks:
  - safe-state-default
  - stale-state-handled
  - operator-confirmation-on-critical-actions
gate_implications:
  - block-if-unsafe-default-state
  - block-if-no-disconnected-state-handling
evidence_required:
  - Safety/state tests
---

# Industrial Manufacturing Pack

## Intent

This pack guides CLike when generating software for industrial and manufacturing scenarios where safety, traceability, operator workflows, deterministic behavior, and system boundaries matter.

## Planning Constraints

- Treat industrial and manufacturing processes as safety-sensitive unless the SPEC says otherwise.
- Separate observation/read paths from command/write paths.
- Do not assume direct equipment control unless explicitly required.
- Prefer dry-run, simulator, or local deterministic execution paths for tests.
- Avoid hidden side effects in generated code.
- Preserve auditability for actions that affect process state.
- Make future integration with PLC, SCADA, MES, ERP, telemetry, or edge systems possible without rewriting the REQ.

## KIT Constraints

- Generated code must clearly separate adapters from domain logic.
- Unit tests must not command real equipment or external industrial systems.
- Simulators or fake adapters should be used for local validation.
- Configuration must make unsafe or write-capable behavior explicit.
- HOWTO must explain local/simulated execution first.
- Any missing industrial protocol dependency must be documented truthfully.

## Gate Expectations

- tests
- lint
- types where applicable
- domain_safety
- runtime_profile_adherence
- skill_adherence
- auditability when process actions exist
- no unsafe real-system dependency in unit tests

## Use when

Use for manufacturing/industrial systems with operator-facing control, safety states, and field/plant conditions.

## Do not use when

Do not use for pure web/consumer apps with no operational safety or control surface.

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
