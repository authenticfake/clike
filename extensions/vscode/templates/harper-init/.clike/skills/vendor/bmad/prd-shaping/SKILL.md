# BMAD Skill Mapping: PRD Shaping

## Intent
Convert product intent into a clear, testable requirements narrative that improves IDEA and SPEC quality without replacing Harper canonical schemas.

## BMAD source/reference concept
Inspired by BMAD product brief and PRD shaping practices: clarify users, problems, outcomes, scope, assumptions, risks, and handoff questions before implementation planning.

## CLike adaptation
Use this mapping to improve `docs/harper/IDEA.md`, `docs/harper/SPEC.md`, and BMAD companion product artifacts. Canonical IDEA/SPEC headings stay Harper-owned. Extra discovery material belongs in BMAD companion files.

## Applies when
Applies to `idea/analyst` and `spec/pm` BMAD runs.

## Required inputs
- User request and chat context.
- Existing `docs/harper/IDEA.md` when present.
- `docs/harper/TECH_CONSTRAINTS.yaml` when present.
- Prior BMAD idea/spec companion artifacts when present.

## Required outputs
- Canonical IDEA or SPEC content appropriate to the active phase.
- Clear goals, non-goals, users, assumptions, constraints, and testable acceptance direction.
- No BMAD-only sections inside canonical Harper artifacts.

## Companion outputs
- `docs/harper/bmad/idea/BRIEF.md`
- `docs/harper/bmad/idea/PRFAQ_NOTES.md`
- `docs/harper/bmad/idea/ASSUMPTIONS.md`
- `docs/harper/bmad/idea/RESEARCH_QUESTIONS.md`
- `docs/harper/bmad/spec/PRD.md`
- `docs/harper/bmad/spec/SCOPE_DECISIONS.md`

## Downstream consumers
SPEC, PLAN, KIT, EVAL, and FINALIZE use the clarified product intent as bounded context.

## Quality checks
- Problem, users, value, scope, and assumptions are explicit.
- Acceptance direction is testable.
- Constraints are grounded in evidence.
- Ambiguous product claims are captured as assumptions or research questions.

## Eval/Gate evidence expectations
Eval and Gate should see traceable acceptance criteria, no hidden scope expansion, and no unevidenced runtime assumptions.

## Forbidden behavior
- Do not add BMAD-only headings to canonical IDEA/SPEC.
- Do not emit source code, tests, or infrastructure.
- Do not invent market facts or operational requirements.
- Do not override TECH_CONSTRAINTS or active output contracts.

## Runtime dependency status
Reference-only. No BMAD runtime, CLI, network fetch, MCP write tool, or executable prompt is enabled.

## Cloud usage notes
Render only bounded snippets and summaries. Use the mapping to improve canonical and companion outputs, not to create arbitrary files.

## Local-agent usage notes
For KIT/EVAL, this mapping may explain product intent but must not expand write roots or change the target REQ.

## Governance boundaries
CLike canonical schemas, write boundaries, EvalRunner, and Gate remain authoritative.
