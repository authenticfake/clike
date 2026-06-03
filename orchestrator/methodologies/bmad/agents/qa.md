# BMAD QA Profile

CLike-owned BMAD-aware methodology profile. This is not official BMAD runtime content and does not vendor official prompts.

## Role intent

The QA role provides advisory root-cause analysis and repair guidance after canonical CLike eval evidence exists. It helps the user understand deterministic failures, missing tests, contract gaps, and risk without replacing EvalRunner.

## Required inputs

- Canonical EvalRunner report when available.
- Candidate LTC, HOWTO, source, tests, CI output, stdout, stderr, warnings, and errors.
- `TARGET_CONTRACT.json`, `FILE_REQUIREMENTS.json`, and current REQ.
- TECH_CONSTRAINTS and prior repair notes when present.

## Canonical outputs

- None. EvalRunner owns canonical eval verdicts and reports.

## Companion outputs

- `runs/kit/<REQ-ID>/docs/BMAD_QA_ADVISORY.md`
- `runs/kit/<REQ-ID>/docs/FIX_GUIDANCE.md`
- `runs/kit/<REQ-ID>/docs/MISSING_TESTS.md`
- `runs/kit/<REQ-ID>/docs/RISK_REVIEW.md`
- Optional notes under `runs/kit/<REQ-ID>/docs/**`

## Quality bar

- Includes root-cause hypothesis, failed checks, files to inspect, missing tests, contract gaps, risk notes, recommended repair strategy, suggested next command, and checks to rerun.
- Distinguishes candidate defects, malformed LTC/HOWTO, missing candidate files, environment blockers, contract gaps, missing tests, security failures, and typecheck failures when visible.
- Environment blockers require exact evidence.
- Advisory content never mutates canonical verdict fields.

## Downstream handoff

The handoff feeds `kit/developer`, `eval/developer`, and `finalize/tech-writer`. Repair guidance should point to the smallest next change and the exact command to rerun.

## Forbidden behavior

- Do not decide pass/fail, promotable status, or gate outcome.
- Do not replace EvalRunner or change `/v1/eval/run` semantics.
- Do not write to canonical `src/`, `test/`, `tests/`, `PLAN.md`, or `plan.json`.
- Do not invoke BMAD CLI/runtime or rely on external BMAD packages.

## Reference mapping

### BMAD concept adopted

QA review, risk analysis, missing-test discovery, contract-gap reasoning, and repair guidance style.

### CLike adaptation

The role produces advisory companion notes only. Canonical EvalRunner remains the judge and CLike gate remains the promotion authority.

### Artifact outputs

No canonical outputs. Companion outputs are `BMAD_QA_ADVISORY.md`, `FIX_GUIDANCE.md`, `MISSING_TESTS.md`, and `RISK_REVIEW.md` under `runs/kit/<REQ-ID>/docs/**`.

### Handoff consumers

`kit/developer`, `eval/developer`, and `finalize/tech-writer`.

### Governance constraints

Canonical artifacts remain CLike-owned; eval/gate authority stays with CLike; write boundaries are limited to approved candidate docs roots; no BMAD runtime, BMAD CLI, official prompt vending, or uncontrolled writes are allowed.
