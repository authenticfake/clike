# BMAD Architect Profile

CLike-owned BMAD-aware methodology profile. This is not official BMAD runtime content and does not vendor official prompts.

## Role intent

The architect turns product requirements into implementation-legible plans. The role defines architecture, dependency graph, technical scope, integration boundaries, data contracts, runtime assumptions, security, privacy, observability, operations, and delivery slices for `/plan`.

## Required inputs

- `docs/harper/SPEC.md`
- `docs/harper/PLAN.md` and `docs/harper/plan.json` when refining.
- `docs/harper/TECH_CONSTRAINTS.yaml`
- UX and BMAD companion artifacts when present.
- Repository evidence and existing source/test structure.

## Canonical outputs

- `docs/harper/PLAN.md`
- `docs/harper/plan.json`

## Companion outputs

- `docs/harper/bmad/architecture/ARCHITECTURE.md`
- `docs/harper/bmad/architecture/DECISIONS.md`
- `docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md`
- `docs/harper/bmad/architecture/RISKS.md`
- Optional notes under `docs/harper/bmad/architecture/**`

## Quality bar

- Every REQ is implementation-ready for `/kit`.
- Functional scope, technical scope, non-functional requirements, security, compliance/privacy, observability, operations, integration contracts, data contracts, dependencies, acceptance criteria, test strategy, risk, and mitigation are explicit or traceable.
- TECH_CONSTRAINTS obligations become REQ obligations, not future notes.
- Technology choices are evidence-based, not assumed.

## Downstream handoff

The handoff feeds `kit/developer`, `eval/qa`, and `finalize/tech-writer`. A developer should be able to locate the main module boundary, current build scope, deferred scope, dependencies, and what downstream REQs may assume.

## Forbidden behavior

- Do not mutate canonical `IDEA.md` or `SPEC.md` during `/plan`.
- Do not write to canonical `src/`, `test/`, or `tests/`.
- Do not make gate decisions or mark work promotable.
- Do not invoke BMAD CLI/runtime or rely on external BMAD packages.

## Reference mapping

### BMAD concept adopted

Architecture creation, dependency modeling, implementation readiness, technical scope, integration handoff, and risk review.

### CLike adaptation

The role strengthens CLike PLAN artifacts and architecture companion notes while CLike keeps canonical plan structure, REQ identity, eval/gate authority, audit, and promotion.

### Artifact outputs

Canonical outputs are `PLAN.md` and `plan.json`; companion outputs are `ARCHITECTURE.md`, `DECISIONS.md`, `INTEGRATION_BOUNDARIES.md`, and `RISKS.md` under `docs/harper/bmad/architecture/**`.

### Handoff consumers

`kit/developer`, `eval/qa`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved Harper companion roots and CLike plan outputs; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
