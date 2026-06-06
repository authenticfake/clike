# BMAD Skill Mapping: Epic Framing

## Intent
Organize broad product behavior into coherent epics, slices, dependencies, and downstream planning units that remain implementation-legible.

## BMAD source/reference concept
Inspired by BMAD epic and story decomposition practices: group work by meaningful outcomes, dependencies, readiness, and handoff clarity.

## CLike adaptation
Use this mapping to improve SPEC companion epics and PLAN REQ structure. CLike still owns canonical REQ IDs, dependency modeling, `PLAN.md`, and `plan.json`.

## Applies when
Applies to `spec/pm` and `plan/pm` BMAD runs.

## Required inputs
- Valid IDEA and SPEC context.
- Existing `PLAN.md` and `plan.json` when present.
- TECH_CONSTRAINTS and repository evidence.
- Prior companion PRD, epics, and story map artifacts.

## Required outputs
- Implementation-sized REQs or story map entries with stable dependencies.
- Explicit in-scope and out-of-scope behavior for each slice.
- Handoff notes that later KIT runs can use without inventing behavior.

## Companion outputs
- `docs/harper/bmad/spec/EPICS.md`
- `docs/harper/bmad/plan/STORY_MAP.md`
- `docs/harper/bmad/plan/STORIES.md`

## Downstream consumers
PLAN, KIT, EVAL, and FINALIZE consume the epic framing to understand sequencing and story intent.

## Quality checks
- Each epic or story maps to a user/system outcome.
- Dependencies are explicit and acyclic where possible.
- Slices are large enough to be meaningful and small enough for focused KIT.
- Deferred scope is named and does not block the promoted slice.

## Eval/Gate evidence expectations
Eval/Gate evidence should connect tests, acceptance, and implementation artifacts back to the planned slice and its dependencies.

## Forbidden behavior
- Do not create REQs that require KIT to guess business behavior.
- Do not split work solely by technical layers when a vertical slice is required.
- Do not bypass canonical `plan.json` structure.
- Do not add BMAD companion files to native Harper runs.

## Runtime dependency status
Reference-only. No BMAD runtime execution or external CLI is enabled.

## Cloud usage notes
Use the mapping to improve REQ clarity, story maps, and companion context while preserving the active output contract.

## Local-agent usage notes
Local agents may use story framing to interpret the target REQ, but must implement only that REQ under candidate roots.

## Governance boundaries
CLike owns REQ identity, phase contracts, candidate isolation, EvalRunner, and Gate.
