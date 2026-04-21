---
name: industrial-manufacturing
description: Use for industrial, manufacturing, shop-floor, MES, PLC/SCADA, MoM telemetry, control-room, and process automation scenarios.
domains: ["industrial", "manufacturing"]
default_runtime_profiles: ["local", "on-prem", "edge", "plant", "cloud", "hybrid", "air-gapped"]
recommended_skills: ["local-cloud-parity", "eval-contract-writer", "gate-risk-reviewer"]
gate_required: true
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