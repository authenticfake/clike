# BMAD Skill Mapping: Architecture Readiness

## Intent
Strengthen PLAN architecture, dependencies, integration boundaries, security, operations, and implementation readiness before KIT.

## BMAD source/reference concept
Inspired by BMAD architecture review and technical readiness practices: define boundaries, decisions, risks, and platform obligations clearly.

## CLike adaptation
Use this mapping for `plan/architect` to improve canonical PLAN artifacts and architecture companion outputs. CLike owns `PLAN.md`, `plan.json`, lane guides, and active write policy.

## Applies when
Applies to `plan/architect`.

## Required inputs
- SPEC, TECH_CONSTRAINTS, PLAN, and `plan.json` when present.
- Repository structure and any existing companion product/UX artifacts.
- Security, operations, identity, deployment, data, and integration evidence.

## Required outputs
- Implementation-ready REQs with clear module boundaries, dependencies, constraints, test strategy, and gate expectations.
- Architecture companion artifacts describing decisions, boundaries, and risks.

## Companion outputs
- `docs/harper/bmad/architecture/ARCHITECTURE.md`
- `docs/harper/bmad/architecture/DECISIONS.md`
- `docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md`
- `docs/harper/bmad/architecture/RISKS.md`

## Downstream consumers
KIT uses architecture readiness to generate candidate code; EVAL and Gate use it to inspect risk and evidence.

## Quality checks
- Boundaries are explicit for modules, services, data, events, identity, secrets, deployment, and observability.
- Decisions include rationale and consequences.
- Risks have mitigation and evidence expectations.
- TECH_CONSTRAINTS obligations are not deferred as future hardening.

## Eval/Gate evidence expectations
Eval/Gate should see tests and artifacts proving contract boundaries, security behavior, runtime profile adherence, and operational readiness.

## Forbidden behavior
- Do not create source/test/infra outputs from PLAN.
- Do not loosen lane-guide requirements.
- Do not permit BMAD companion artifacts to replace canonical PLAN.
- Do not infer cloud-only or language-specific architecture without evidence.

## Runtime dependency status
Reference-only. No BMAD runtime, CLI, or network sync is used.

## Cloud usage notes
Render concise architecture guidance and selected snippets only. Keep output paths within the active contract.

## Local-agent usage notes
Local agents may use architecture companion context as read-only guidance and must not modify canonical architecture docs.

## Governance boundaries
CLike owns canonical PLAN validation, candidate isolation, EvalRunner, Gate, and promotion.
