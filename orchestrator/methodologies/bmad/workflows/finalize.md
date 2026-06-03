# BMAD-Aware FINALIZE Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Produce evidence-based final documentation, release narrative, stakeholder summary, and documentation review from CLike-owned artifacts.

## Step-by-step artifact workflow

1. Read PLAN, `plan.json`, eval reports, gate reports, candidate outputs, promoted artifacts, and companion notes.
2. Validate claims against actual artifacts and canonical eval/gate evidence.
3. Write or update final docs and companion release narrative.
4. Add Mermaid diagrams only when they clarify real architecture, flow, dependency, or operational behavior.
5. Preserve known gaps, risks, and follow-up work without implying promotion decisions.

## Mandatory companion outputs

- `docs/harper/bmad/finalize/DOC_REVIEW.md`
- `docs/harper/bmad/finalize/RELEASE_NARRATIVE.md`
- `docs/harper/bmad/finalize/STAKEHOLDER_SUMMARY.md`

## Optional open-ended companion outputs under allowed roots

- Focused finalization notes under `docs/harper/bmad/finalize/**`.

## Handoff rules

- Hand off final docs to human review, audit, release, and future planning.
- Trace claims back to canonical CLike artifacts.
- Do not treat companion notes as promotion evidence unless CLike canonical artifacts support them.

## Readiness checklist

- Documentation reflects real implemented and evaluated behavior.
- Eval and gate evidence are referenced accurately.
- Gaps and risks are not hidden.
- Diagrams are useful and evidence-based.
- Finalize outputs stay inside allowed roots.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved finalize outputs and companion roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

Project documentation, write-document workflow, Mermaid generation, doc validation, and concept explanation.

### CLike adaptation

CLike adapts documentation concepts into evidence-based final artifacts while lifecycle state, telemetry, audit, eval, gate, and promotion remain CLike-owned.

### Artifact outputs

Canonical outputs include `README.md` and `docs/harper/FINALIZE_NOTES.md`; companion outputs are `DOC_REVIEW.md`, `RELEASE_NARRATIVE.md`, and `STAKEHOLDER_SUMMARY.md`.

### Handoff consumers

Human review, audit, release, and future planning.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved finalize outputs and companion roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
