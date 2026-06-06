# BMAD Skill Mapping: QA Risk Review

## Intent
Provide advisory QA and repair guidance around candidate artifacts while preserving EvalRunner as the canonical judge.

## BMAD source/reference concept
Inspired by BMAD QA review, risk assessment, missing-test identification, and repair guidance practices.

## CLike adaptation
Use this mapping in `eval/qa` to improve pre-eval hardening and advisory companion docs. It must never alter canonical eval verdicts.

## Applies when
Applies to `eval/qa`.

## Required inputs
- `AGENT_EVAL_CONTEXT.json`.
- Candidate source, tests, CI, LTC, HOWTO, and reports.
- SPEC, PLAN, plan.json, TECH_CONSTRAINTS, lane guides, and companion docs.

## Required outputs
- Focused repair notes and QA advisory companion outputs under the target KIT root.
- Exact commands rerun and remaining blockers when repair is incomplete.

## Companion outputs
- `runs/kit/<REQ-ID>/docs/BMAD_QA_ADVISORY.md`
- `runs/kit/<REQ-ID>/docs/FIX_GUIDANCE.md`
- `runs/kit/<REQ-ID>/docs/MISSING_TESTS.md`
- `runs/kit/<REQ-ID>/docs/RISK_REVIEW.md`
- `runs/kit/<REQ-ID>/reports/BMAD_EVAL_REPAIR_NOTES.md`

## Downstream consumers
Canonical EvalRunner, Gate, KIT repair loops, and FINALIZE use the advisory output as context only.

## Quality checks
- Root cause is tied to exact files, checks, and evidence.
- Repairs are candidate-owned and minimal.
- Missing tests and risks are named without hiding failures.
- Environment blockers include concrete evidence.

## Eval/Gate evidence expectations
EvalRunner remains authoritative. Gate may consider advisory risk notes but must rely on CLike canonical reports and policy.

## Forbidden behavior
- Do not decide pass/fail.
- Do not mutate canonical eval verdict fields.
- Do not modify canonical roots or dependency KIT roots.
- Do not weaken LTC, tests, typecheck, lint, security checks, or gate policy.
- Do not call BMAD runtime or external CLI.

## Runtime dependency status
Reference-only. No BMAD QA runtime executes.

## Cloud usage notes
Use concise advisory framing and preserve canonical eval authority.

## Local-agent usage notes
Read selected skill context before repair. Patch only under allowed write roots and rerun the failing checks when possible.

## Governance boundaries
CLike owns EvalRunner, Gate, write policy, reports, and promotion status.
