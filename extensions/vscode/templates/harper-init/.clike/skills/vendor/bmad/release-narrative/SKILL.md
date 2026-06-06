# BMAD Skill Mapping: Release Narrative

## Intent
Create clear release-facing documentation and stakeholder summaries from validated CLike artifacts and evidence.

## BMAD source/reference concept
Inspired by BMAD documentation and stakeholder communication practices: explain what was built, why it matters, risks, and operational readiness.

## CLike adaptation
Use this mapping in `finalize/tech-writer` to improve final docs and BMAD companion release notes without changing promotion evidence.

## Applies when
Applies to `finalize/tech-writer`.

## Required inputs
- PLAN, plan.json, SPEC, TECH_CONSTRAINTS.
- Eval and Gate reports.
- Candidate or promoted artifacts.
- BMAD companion docs when present.

## Required outputs
- CLike finalize outputs and release companion artifacts grounded in actual evidence.
- Clear runbook, user/maintainer notes, and known limitations when applicable.

## Companion outputs
- `docs/harper/bmad/finalize/DOC_REVIEW.md`
- `docs/harper/bmad/finalize/RELEASE_NARRATIVE.md`
- `docs/harper/bmad/finalize/STAKEHOLDER_SUMMARY.md`

## Downstream consumers
Human reviewers, maintainers, audit trails, release managers, and future Harper phases.

## Quality checks
- Claims are traceable to canonical artifacts or reports.
- Known risks and limitations are not hidden.
- Documentation separates product behavior, operations, and evidence.
- No unsupported success claims are introduced.

## Eval/Gate evidence expectations
Finalize text must reflect EvalRunner and Gate outcomes and must not imply promotion if Gate has not approved it.

## Forbidden behavior
- Do not fabricate test results, coverage, security status, or gate decisions.
- Do not modify eval reports or gate reports.
- Do not add runtime dependencies.
- Do not treat BMAD companion narrative as canonical evidence.

## Runtime dependency status
Reference-only. No BMAD documentation runtime or CLI is executed.

## Cloud usage notes
Use selected snippets to improve final docs and companion narrative while honoring active output paths.

## Local-agent usage notes
If local finalize packaging is used, treat this mapping as writing guidance only and keep CLike report authority intact.

## Governance boundaries
CLike owns final artifact contracts, EvalRunner evidence, Gate authority, and audit status.
