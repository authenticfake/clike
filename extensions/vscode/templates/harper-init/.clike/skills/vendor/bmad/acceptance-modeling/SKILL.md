# BMAD Skill Mapping: Acceptance Modeling

## Intent
Turn requirements into verifiable acceptance criteria, test obligations, and evidence expectations that support KIT, EVAL, and Gate.

## BMAD source/reference concept
Inspired by BMAD acceptance and validation practices: make requirements concrete enough for downstream implementation and review.

## CLike adaptation
Use this mapping to strengthen SPEC acceptance criteria, PLAN test strategy, lane guides, and companion acceptance models without changing validator authority.

## Applies when
Applies to `spec/pm`.

## Required inputs
- IDEA/SPEC product behavior.
- TECH_CONSTRAINTS and known runtime constraints.
- Existing tests, repository conventions, or capability manifest when present.

## Required outputs
- Acceptance criteria that are observable, testable, and tied to requirements.
- Negative-path and boundary expectations where risk is material.
- Evidence expectations suitable for EvalRunner and Gate.

## Companion outputs
- `docs/harper/bmad/spec/ACCEPTANCE_MODEL.md`
- `docs/harper/bmad/spec/SCOPE_DECISIONS.md`

## Downstream consumers
PLAN derives REQ acceptance and test strategy; KIT uses it for candidate tests; EVAL and Gate use it for evidence review.

## Quality checks
- Criteria avoid vague terms such as fast, secure, or robust without measurable detail.
- Failure modes and denied behavior are included when relevant.
- Each criterion can be tested or inspected.
- Acceptance does not assume unselected frameworks or providers.

## Eval/Gate evidence expectations
EvalRunner should be able to map generated tests and reports to acceptance criteria. Gate should see coverage, security, and operational evidence appropriate to risk.

## Forbidden behavior
- Do not lower acceptance criteria to match weak implementation.
- Do not mark test gaps as future work when they are part of the active slice.
- Do not replace EvalRunner or Gate decisions.
- Do not create provider-specific obligations without evidence.

## Runtime dependency status
Reference-only. No BMAD executable dependency is used.

## Cloud usage notes
Render concise acceptance guidance and required evidence. Do not dump vendor files.

## Local-agent usage notes
Local agents should read this mapping as quality guidance and keep repairs tied to candidate-owned files.

## Governance boundaries
CLike canonical validators, EvalRunner, Gate, and output contracts remain authoritative.
