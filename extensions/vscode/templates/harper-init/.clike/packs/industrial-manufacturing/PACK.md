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
