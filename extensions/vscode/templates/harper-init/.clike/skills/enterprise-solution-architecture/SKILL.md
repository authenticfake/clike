---
name: enterprise-solution-architecture
description: Keep enterprise solutions coherent across requirements, runtime profiles, integration boundaries, observability, audit, and release readiness.
phases: ["idea", "spec", "plan", "kit", "eval", "gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "iac", "ai-native"]
domains: ["enterprise", "developer-tooling", "ai-native", "industrial"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - Define bounded modules and clear ownership
  - Make integration contracts explicit and stable
eval_checks:
  - bounded-modules-defined
  - integration-contracts-explicit
gate_implications:
  - block-if-uncontrolled-coupling
  - block-if-missing-integration-contracts
evidence_required:
  - Module/ownership map
  - Integration contracts
---

# Enterprise Solution Architecture Skill

## Intent

Enterprise systems must remain coherent as multiple REQs are generated, evaluated, promoted, and finalized.

This skill prevents fragmented slices, inconsistent contracts, duplicated composition roots, cloud-only assumptions, weak auditability, missing run paths, and business logic spread across unrelated modules.

## Use when

Use this skill when the solution involves:

- enterprise users or departments;
- backoffice or operator workflows;
- RBAC or identity;
- auditability;
- persistence;
- document/workflow platforms;
- integrations;
- multi-service runtime;
- on-prem/hybrid/cloud profiles;
- regulated data;
- AI features in an enterprise context.

## Do not use when

Do not use this skill for isolated scripts, throwaway demos, simple static sites, or non-enterprise prototypes without integration/runtime obligations.

## Required architecture behavior

Generated REQs and KITs must:

- preserve stable public contracts;
- respect existing module boundaries;
- avoid duplicate domain models;
- keep business APIs profile-independent;
- keep runtime-specific logic behind adapters;
- preserve audit semantics where actions are business-relevant;
- use explicit configuration for runtime/environment behavior;
- keep a local deterministic execution path;
- avoid broad speculative architecture;
- document production vs local-dev gaps honestly.

## Composition expectations

When multiple slices are promoted, FINALIZE or an integration REQ must provide:

- a solution composition root;
- entrypoints or launchers;
- settings/env loader;
- dependency/repository factory;
- local-dev profile;
- scripts for local run/check;
- route/API parity checks when frontend/backend exist;
- docs matching actual commands.

A set of modules without a runnable composition is not an enterprise solution.

## Requirement slicing guidance

When a user describes a broad enterprise capability, CLike should split it into REQs that are:

- independently understandable;
- dependency-aware;
- promotable;
- small enough to evaluate;
- large enough to deliver a usable slice.

Prefer this sequence:

1. data/contract backbone;
2. runtime/profile adapters;
3. primary backend capability;
4. workflow/authorization/audit;
5. search/export/reporting;
6. UI route/shell;
7. configuration/admin capability;
8. AI or automation capability;
9. solution finalize/integration.

Do not create REQs so thin that each one only adds a placeholder file.

## Integration safety

When integrating with external or enterprise systems:

- isolate SDK/provider code behind adapters;
- provide fake/local adapters for eval;
- document external infrastructure;
- keep credentials external;
- separate blocking local checks from optional external checks;
- avoid direct provider calls in business services unless the REQ explicitly requires it.

## Observability and audit

For business-relevant actions, generated code should consider:

- actor identity;
- correlation ID;
- before/after state;
- redacted audit payload;
- structured logs;
- operational errors that can be diagnosed.

Do not log secrets, raw confidential content, or raw prompts unless explicitly allowed by policy.

## Gate implications

Gate must BLOCK promotion when:

- generated code duplicates canonical enterprise contracts;
- runtime-specific code leaks into business logic;
- a promoted slice breaks a dependent REQ boundary;
- business-relevant actions have no audit or diagnosability when required;
- solution-level finalize lacks runnable composition for a code project;
- local execution is impossible without unsupported external infrastructure;
- generated docs overclaim production readiness.

Gate may WARN when:

- production hardening is explicitly out of scope;
- external integrations are documented but not locally available;
- observability is minimal but sufficient for the current MVP slice.

## Success definition

The skill is satisfied when each promoted slice contributes to a coherent enterprise solution that can be run locally, evaluated deterministically, and extended without hidden rewrites.

