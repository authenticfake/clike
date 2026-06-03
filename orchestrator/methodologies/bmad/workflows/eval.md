# BMAD-Aware EVAL Workflow

CLike-owned workflow guidance. This is not official BMAD runtime content and does not create a parallel Harper pipeline.

## Phase goal

Provide advisory QA/developer repair guidance after canonical EvalRunner evidence exists, without deciding pass/fail, promotable status, or gate outcome.

## Step-by-step artifact workflow

1. Read canonical eval report, LTC, HOWTO, candidate files, target contract, file requirements, TECH_CONSTRAINTS, and prior repair notes.
2. Identify the first deterministic failure and classify it as candidate defect, malformed LTC/HOWTO, missing candidate file, environment blocker, contract gap, missing test, security failure, or typecheck failure when evidence supports it.
3. Produce advisory fix guidance, missing-test notes, and risk review under candidate docs.
4. Suggest `/kit <REQ-ID> --repair --methodology bmad --agent developer` when repair is appropriate.
5. List checks to rerun without mutating canonical eval verdict fields.

## Mandatory companion outputs

- `runs/kit/<REQ-ID>/docs/BMAD_QA_ADVISORY.md`
- `runs/kit/<REQ-ID>/docs/FIX_GUIDANCE.md`
- `runs/kit/<REQ-ID>/docs/MISSING_TESTS.md`
- `runs/kit/<REQ-ID>/docs/RISK_REVIEW.md`

## Optional open-ended companion outputs under allowed roots

- Focused advisory notes under `runs/kit/<REQ-ID>/docs/**`.

## Handoff rules

- Hand off concise repair guidance to `kit/developer` or `eval/developer`.
- Hand off risk and evidence notes to `finalize/tech-writer`.
- Do not pass BMAD context to gate authority.

## Readiness checklist

- Root-cause hypothesis is concise and evidence-based.
- Failed checks, files to inspect, missing tests, contract gaps, risks, repair strategy, suggested command, and checks to rerun are present.
- Candidate defects are not mislabeled as environment blockers.
- Canonical verdict fields remain unchanged.

## Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved candidate docs roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.

## Reference mapping

### BMAD concept adopted

QA risk/review/fix guidance style, missing-test analysis, contract-gap review, and checklist-driven rerun guidance.

### CLike adaptation

CLike adapts QA guidance into advisory companion artifacts only. EvalRunner stays authoritative and gate remains CLike-only.

### Artifact outputs

No canonical outputs. Companion outputs are `BMAD_QA_ADVISORY.md`, `FIX_GUIDANCE.md`, `MISSING_TESTS.md`, and `RISK_REVIEW.md`.

### Handoff consumers

`kit/developer`, `eval/developer`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved candidate docs roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
