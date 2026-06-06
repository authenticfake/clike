# BMAD-Aware IDEA Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Clarify product intent, users, value hypothesis, assumptions, research questions, and PRFAQ pressure points so `docs/harper/IDEA.md` and IDEA companion artifacts become useful inputs for SPEC and PLAN.

## Step-by-step artifact workflow

1. Read the user idea, existing `IDEA.md`, constraints, risks, and any project context.
2. Separate known facts, assumptions, open questions, and validation needs.
3. Draft or refine the brief, PRFAQ challenge notes, assumptions, and research questions.
4. Identify what SPEC must decide and what PLAN must not assume yet.
5. Keep canonical IDEA ownership with CLike and store extra discovery material under the allowed companion root.

## Mandatory companion outputs

- `docs/harper/bmad/idea/BRIEF.md`
- `docs/harper/bmad/idea/PRFAQ_NOTES.md`
- `docs/harper/bmad/idea/ASSUMPTIONS.md`
- `docs/harper/bmad/idea/RESEARCH_QUESTIONS.md`

## Optional open-ended companion outputs under allowed roots

- Any focused discovery note under `docs/harper/bmad/idea/**`, such as domain notes, interview questions, or validation-plan sketches.

## Handoff rules

- Hand off concise context to `spec/pm` and `spec/ux`.
- Flag unresolved assumptions for `plan/architect` and `plan/pm`.
- Do not present research framing as completed research unless evidence exists.

## Readiness checklist

- User problem and target user are clear enough for SPEC.
- Major assumptions and unknowns are explicit.
- PRFAQ objections are captured.
- Constraints and risks are visible.
- Companion artifacts are bounded and stored under `docs/harper/bmad/idea/**`.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved Harper companion roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

Brainstorming, research framing, brief creation, PRFAQ-style challenge, and project context capture.

### CLike adaptation

CLike uses these concepts to enrich IDEA without creating a BMAD runtime or changing canonical Harper lifecycle authority.

### Artifact outputs

Canonical output is `docs/harper/IDEA.md`; companion outputs are `BRIEF.md`, `PRFAQ_NOTES.md`, `ASSUMPTIONS.md`, and `RESEARCH_QUESTIONS.md`.

### Handoff consumers

`spec/pm`, `spec/ux`, `plan/architect`, and `plan/pm`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved Harper companion roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
