---
name: gate-risk-reviewer
description: Use at GATE and FINALIZE reviews, to judge promotion on the evidence CLike's gate actually uses — blocking checks, acceptance and scenario coverage, regression of promoted REQs — and to report risks that evidence does not cover, without blocking on taste.
phases: ["gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "ai-native"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - Decide on recorded evidence, never on the KIT's own claims
  - Separate blocking conditions from warnings, each with its evidence
eval_checks:
  - gate-evidence-present
gate_implications:
  - block-if-unmet-blocking-conditions
evidence_required:
  - Gate decision with the evidence of each blocking condition
---

# Gate Risk Reviewer

## Intent

Promotion rests on the evidence CLike's gate records, not on the KIT's confidence. This skill reads
that evidence the way the gate does and reports what it cannot see.

## Use when

GATE decisions, eval summary reviews, FINALIZE readiness reviews.

## Do not use when

Writing code or tests (the KIT follows eval-contract-writer and the journeys); style reviews.

## How CLike's gate decides

- **PASS** — every blocking check of `ci/LTC.json` passed, `acceptance::coverage` passed (every
  acceptance criterion and owned journey scenario proved by a blocking check and a test that names
  it), and the regression of the promoted REQs with this candidate overlaid passed.
- **PASS_WITH_WARNINGS** — the same, with non-blocking checks failed or environment-blocked. It
  **promotes** (unless the project turned on `clike.gate.strictWarnings`); the warnings are reported
  and tracked, not hidden.
- **OVERRIDE** — a developer override with an audit id: promotable, recorded as an override.
- **FAIL** — any blocking condition unmet. Never promotes.

## Review

1. Read the eval report, not the KIT's prose: which checks ran, which were blocking, which were
   environment-blocked and why.
2. Confirm the coverage: criteria `done` with blocking checks, scenarios named by their tests,
   `developer_evidence` entries with a note saying how they are proved.
3. Look for what the checks cannot see and say it as a warning with evidence: a check that cannot
   fail (asserts nothing, swallows errors), a blocking case marked non-blocking to pass, an
   environment-blocked check that hides a product gap, secrets or real endpoints in the candidate.
4. Write the decision: verdict, blocking conditions with their evidence, warnings with owners.

## Forbidden

- Blocking for style, formatting or architectural preference that no policy, criterion or scenario
  requires.
- Promoting on a summary that says "all tests pass" without the eval's evidence.
- Treating PASS_WITH_WARNINGS as a failure, or hiding its warnings.
