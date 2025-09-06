# HARPER_GUIDE — IDEA → SPEC → PLAN → KIT

Operate CLike in **Harper mode** with HITL and eval-driven quality.

## Stages
1. IDEA — create `IDEA.md`.
2. SPEC — generate and **approve** `SPEC.md` (scope, stack, UAT, security tests, KPIs).
3. PLAN — generate and **approve** `PROMPT_PLAN.md` (checklist of micro-tasks).
4. KIT — generate `kit/` and run evals. Review **Diff | Files | Evals | Sources** and approve.

## Governance
- Strict: next stage locked until previous approved and evals passed.
- Advisory: override allowed with rationale (stored in audit).

## Git
- Branches: `clike/spec/*`, `clike/plan/*`, `clike/kit/*`, `clike/fix/*`.
- PR includes eval report + `audit_id`.

## RAG
- Index SPEC/PLAN/KIT/src/docs; require citations; enforce groundedness in strict policy.
