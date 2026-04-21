---
name: gate-risk-reviewer
description: Use when promotion must consider quality, safety, runtime, capability adherence, and future compatibility risks.
phases: ["eval", "gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "ai-native"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
---

# Gate Risk Reviewer Skill

## Intent

Promotion decisions must be based on evidence, not on generated prose or optimistic assumptions.

## Use when

Use this skill for every EVAL, GATE, FINALIZE, and any REQ that may affect promotion, runtime safety, public contracts, security posture, domain behavior, or future compatibility.

## Do not use when

Do not use this skill as a stylistic reviewer. It is not a code beautifier and must not block promotion for subjective preferences without policy or evidence.

## Signals

- Gate expectations include tests, lint, types, security, build, runtime profile adherence, skill adherence, design adherence, domain safety, or future compatibility.
- The REQ modifies public APIs, persistence contracts, authentication/authorization, external integrations, infra, AI behavior, industrial workflows, mobile offline behavior, or release artifacts.
- Eval produced warnings, blocked checks, missing reports, missing HOWTO/LTC, or partial evidence.

## Required behavior

- Gate must check functional acceptance criteria.
- Gate must check technical acceptance criteria.
- Gate must check runtime profile adherence when applicable.
- Gate must check selected skills and packs when applicable.
- Gate must block promotion when required tests, docs, or runtime paths are missing.
- Gate must call out future compatibility risks that would block later REQs.
- Gate must not promote a REQ just because code was generated.

## Evaluation

The REQ satisfies this skill only if:
- gate decisions cite concrete pass/fail reasons;
- missing evidence causes deferral or blocking;
- capability adherence is considered when capability hints are present;
- unresolved runtime or domain safety risks are surfaced explicitly.