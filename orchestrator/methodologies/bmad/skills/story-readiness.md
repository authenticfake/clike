# BMAD Skill Mapping: Story Readiness

## Intent
Ensure each planned story or REQ is ready for implementation with scope, dependencies, acceptance, files, tests, and risks clearly stated.

## BMAD source/reference concept
Inspired by BMAD story readiness and backlog refinement practices: stories should be actionable, bounded, and testable.

## CLike adaptation
Use this mapping to improve PLAN REQs, plan companion story maps, and KIT handoff notes while preserving CLike REQ identity and candidate boundaries.

## Applies when
Applies to `plan/architect`, `plan/pm`, and `kit/developer`.

## Required inputs
- PLAN and `plan.json`.
- Target REQ and dependencies.
- Lane guides, TECH_CONSTRAINTS, and architecture or PM companion docs.

## Required outputs
- Stories or REQs with clear functional scope, technical scope, acceptance, dependencies, and expected files/tests.
- Implementation readiness notes that identify blockers before KIT.

## Companion outputs
- `docs/harper/bmad/plan/STORIES.md`
- `docs/harper/bmad/plan/STORY_MAP.md`
- `docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md`
- `runs/kit/<REQ-ID>/docs/BMAD_DEV_STORY.md`

## Downstream consumers
KIT, EVAL, and FINALIZE use story readiness to avoid guessing and to report traceable implementation evidence.

## Quality checks
- The target slice is coherent and not a thin technical fragment.
- Dependencies and downstream assumptions are explicit.
- Expected files, tests, and boundaries are named.
- Open questions are blockers or assumptions, not hidden implementation choices.

## Eval/Gate evidence expectations
Eval/Gate should see acceptance coverage, dependency compatibility, and evidence that forbidden shortcuts were avoided.

## Forbidden behavior
- Do not implement multiple REQs in one KIT run.
- Do not modify canonical `PLAN.md` or `plan.json` from local-agent packages.
- Do not treat companion story docs as authoritative over canonical REQs.
- Do not expand allowed write roots.

## Runtime dependency status
Reference-only. No external BMAD runtime is available.

## Cloud usage notes
Use this mapping to make PLAN and companion story outputs implementation-ready.

## Local-agent usage notes
Use this mapping before implementation to understand the current REQ, then write only candidate files under allowed roots.

## Governance boundaries
CLike owns REQ selection, active output contracts, write policy, EvalRunner, and Gate.
