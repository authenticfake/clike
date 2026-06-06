# BMAD-Aware PLAN Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Create implementation-legible REQs for `/kit` with functional, technical, non-functional, security, compliance, privacy, observability, operational, integration, data, dependency, acceptance, test, risk, and TECH_CONSTRAINTS obligations.

## Step-by-step artifact workflow

1. Read `SPEC.md`, existing `PLAN.md`, `plan.json`, TECH_CONSTRAINTS, repository evidence, BMAD spec notes, architecture notes, and UX notes.
2. Define architecture decisions, integration boundaries, risks, stories, story map, and implementation readiness notes.
3. Slice work into REQs with dependencies, main module boundary, current build scope, deferred scope, and downstream assumptions.
4. Preserve machine-readable detail in `plan.json` for `/kit`, including `integration_contracts`, `data_contracts`, `runtime_profile`, and `gate_expectations` when those fields are known or relevant.
5. Validate that each REQ can be implemented without hidden product, architecture, runtime, or test decisions.

## Mandatory companion outputs

- `docs/harper/bmad/architecture/ARCHITECTURE.md`
- `docs/harper/bmad/architecture/DECISIONS.md`
- `docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md`
- `docs/harper/bmad/architecture/RISKS.md`
- `docs/harper/bmad/plan/STORIES.md`
- `docs/harper/bmad/plan/STORY_MAP.md`
- `docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md`

## Optional open-ended companion outputs under allowed roots

- Architecture details under `docs/harper/bmad/architecture/**`.
- Planning notes under `docs/harper/bmad/plan/**`.

## Handoff rules

- `/kit` receives REQs that state what this REQ builds now, what this REQ intentionally defers, and what downstream REQs may assume.
- `eval/qa` receives acceptance, contract, risk, and test strategy context.
- `finalize/tech-writer` receives architecture and decision context for evidence-based docs.

## Readiness checklist

- Every REQ has Functional Scope, technical scope, Non-Functional Requirements, Security Requirements, compliance/privacy requirements when applicable, observability and operations, integration contracts, data contracts, dependencies, acceptance criteria, test strategy, risk notes, TECH_CONSTRAINTS obligations, main module boundary, current scope, deferred scope, and downstream assumptions.
- Every machine-readable REQ records `integration_contracts`, `data_contracts`, `runtime_profile`, and `gate_expectations` when applicable, so `/kit`, EvalRunner, and Gate can consume the same implementation-legible contract.
- Every REQ answers: what this REQ builds now; what this REQ intentionally defers; what downstream REQs may assume.
- `plan.json` carries machine-readable fields needed by `/kit`.
- Technology choices come from TECH_CONSTRAINTS, SPEC, repository evidence, or explicit user input.
- Cloud/on-prem parity, air-gapped mode, provider portability, internal registry, identity, or deployment requirements become REQ obligations when present.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved PLAN/architecture companion roots and CLike PLAN outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

Architecture creation, story mapping, implementation readiness, dependency graph, handoff rules, checklist patterns, and project-context modeling.

### CLike adaptation

CLike adapts these concepts into canonical `PLAN.md` and `plan.json` plus bounded architecture and planning companion artifacts.

### Artifact outputs

Canonical outputs are `PLAN.md` and `plan.json`. Companion outputs are `ARCHITECTURE.md`, `DECISIONS.md`, `INTEGRATION_BOUNDARIES.md`, `RISKS.md`, `STORIES.md`, `STORY_MAP.md`, and `IMPLEMENTATION_READINESS.md`.

### Handoff consumers

`kit/developer`, `eval/qa`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved PLAN/architecture companion roots and CLike PLAN outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
