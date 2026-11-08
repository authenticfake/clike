---
name: enterprise-solution-architecture
description: Use when planning or finalizing an enterprise solution (several REQs, integrations, runtime profiles, audit), to keep module boundaries, contracts, audit and diagnosability coherent across REQs.
phases: ["spec", "plan", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "iac", "ai-native"]
domains: ["enterprise", "developer-tooling", "ai-native", "industrial"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - One owner per module and per contract; later REQs extend, they do not redefine
  - Business-relevant actions carry actor, correlation id and a redacted audit record
eval_checks:
  - contracts-explicit
gate_implications:
  - block-if-a-req-redefines-a-promoted-contract
evidence_required:
  - Module and contract ownership in PLAN
---

# Enterprise Solution Architecture

## Intent

An enterprise solution is built by many REQs over time. It stays coherent when each module and
contract has one owner, runtime specifics stay in adapters, and every business action can be traced.
This skill shapes SPEC, PLAN and FINALIZE; the KIT follows the plan it produced.

## Use when

Enterprise solutions with several REQs, integrations, runtime profiles, RBAC, audit or regulated data.

## Do not use when

Single-REQ tools, throwaway prototypes, static sites.

## SPEC and PLAN

- Name the bounded modules, their owners and the contracts between them (API, events, data).
- Slice by capability, never by technical layer (see the capacity profile of the plan): each REQ
  delivers a usable outcome; the first REQ of an application owns its seams (registration by
  convention, one migration per REQ, adapter registry).
- Runtime profiles (local, cloud, on-prem, hybrid, air-gapped) are configuration plus adapters, not
  forks of business logic (journey-runtime-config).
- Integrations: provider SDKs behind adapters with local fakes; real-system checks are opt-in.
- Audit and diagnosability for business actions: actor, correlation id, before/after state
  (redacted), structured logs; state which REQ owns them (journey-data-lifecycle DAT-11).

## FINALIZE

The promoted REQs compose into one runnable solution (see e2e-slice-runnability, FINALIZE), and the
docs state what was validated locally and what needs the target environment.

## Forbidden

- Duplicate domain models or a second definition of a promoted contract.
- Provider or runtime code inside business services.
- Docs that claim production readiness from local evidence.
