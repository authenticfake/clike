# BMAD Commands

Existing Harper commands remain unchanged. BMAD support is added through optional methodology flags that enrich phase behavior without changing who owns the phase.

The important distinction is that methodology is not execution. `--methodology bmad --agent developer` asks CLike to use BMAD-style developer guidance for the phase. It does not select Claude Code, Codex CLI, a cloud model, or any other executor.

## Flags

Supported forms:

```text
--methodology bmad
--methodology=bmad
--agent developer
--agent=developer
```

`--agent` requires `--methodology`.

## Command Examples

### Idea

Use the analyst role when the idea needs sharper framing, assumptions, constraints, or opportunity analysis before requirements are written.

```text
/idea --methodology bmad --agent analyst
```

The output remains CLike-governed `IDEA.md`. The analyst role may improve discovery quality, but it cannot bypass the Harper lifecycle.

### Spec With Product Management

Use the product manager role when the specification needs stronger product intent, acceptance criteria, readiness checks, or story framing.

```text
/spec --methodology bmad --agent pm
```

The result is still canonical `docs/harper/SPEC.md`. BMAD PM guidance should make requirements clearer and more testable, not create an alternate PRD pipeline. PM may also produce companion context under `docs/harper/bmad/spec/**`, including `PRD.md`, `EPICS.md`, `ACCEPTANCE_MODEL.md`, and `SCOPE_DECISIONS.md`.

### Spec With UX

Use the UX role when user journeys, interaction states, accessibility, terminology, empty states, and error states need first-class attention.

```text
/spec --methodology bmad --agent ux
```

UX is companion-only in the MVP. It must not overwrite `docs/harper/SPEC.md`; PM-owned canonical SPEC remains authoritative. UX output belongs under `docs/harper/ux/**`, such as `DESIGN.md`, `EXPERIENCE.md`, `USER_JOURNEYS.md`, `INTERACTION_STATES.md`, and `SPEC_UX_APPENDIX.md`. These artifacts are consumed by `/plan` as bounded context and do not override CLike output contracts or eval/gate policy.

### Plan With Architecture

Use the architect role when `PLAN.md` and `plan.json` need stronger implementation boundaries, dependencies, integration contracts, data contracts, runtime constraints, and security or operational implications.

```text
/plan --methodology bmad --agent architect
```

`/plan --methodology bmad --agent architect` and `/plan --methodology bmad --agent pm` keep CLike ownership of `docs/harper/PLAN.md` and `docs/harper/plan.json`.

BMAD guidance enriches planning so each REQ is implementation-ready for `/kit`. Each REQ should make functional scope, technical scope, non-functional requirements, security requirements, compliance and privacy requirements when applicable, observability and operations, integration contracts, data contracts, dependencies, acceptance criteria, test strategy, risk and mitigation, TECH_CONSTRAINTS obligations, the main module boundary, current build scope, deferred scope, and downstream assumptions clear.

`plan.json` remains the machine-readable source for `/kit`. It should preserve fields such as `functional_scope`, `technical_scope`, `non_functional_requirements`, `security_requirements`, `compliance_requirements`, `operational_requirements`, `integration_contracts`, `data_contracts`, `test_strategy`, `risk_notes`, `main_module_boundary`, `runtime_profile` when known, and `gate_expectations` when relevant.

BMAD planning does not hardcode Python, Node, cloud-only delivery, or any other stack. TECH_CONSTRAINTS, SPEC, repository evidence, and explicit user input decide technology and runtime obligations.

### Plan With Product Management

Use the PM role during planning when scope slicing, acceptance criteria, implementation readiness, or dependency sequencing need product-focused scrutiny.

```text
/plan --methodology bmad --agent pm
```

The PM role should help clarify what each REQ builds now, what it intentionally defers, and what downstream REQs may assume.

### KIT Development

Use the developer role for candidate-first implementation guidance.

```text
/kit REQ-001 --methodology bmad --agent developer
```

The candidate remains isolated under `runs/kit/<REQ-ID>/...`. BMAD developer guidance cannot expand allowed write roots, write directly to canonical `src/` or canonical tests, mutate `PLAN.md`, mutate `plan.json`, promote code, or bypass CLike governance.

### KIT Repair

Use repair mode when canonical eval has produced failures and the next KIT run should focus on repair rather than broad unrelated rewriting.

```text
/kit REQ-001 --repair --methodology bmad --agent developer
```

Repair is still the existing KIT path with repair intent. It does not create a separate repair pipeline and it does not bypass candidate-first generation.

### Eval With QA Advisory

Use QA advisory when canonical eval should be followed by operational repair guidance.

```text
/eval REQ-001 --methodology bmad --agent qa
```

The canonical path remains `handleEval -> /v1/eval/run -> EvalRunner.run_profile`. BMAD QA may summarize likely root causes, files to inspect, missing tests, contract gaps, risk notes, repair strategy, suggested next command, and checks to rerun. It does not decide pass/fail and does not change promotability.

### Eval With Developer Repair Advisory

Use the developer role during eval when the advisory should be written for the next repair implementer.

```text
/eval REQ-001 --methodology bmad --agent developer
```

This still runs canonical eval first. The developer-oriented advisory remains advisory-only.

### Finalize

Use the tech-writer role when finalization needs clearer release notes, documentation validation, or explanatory material.

```text
/finalize --methodology bmad --agent tech-writer
```

Finalize artifacts remain CLike-owned.

## KIT Flags Remain Compatible

Existing KIT options remain valid:

```text
/kit REQ-001 --integrity
/kit REQ-001 --hardener
/kit REQ-001 --promotion-eval
/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval
/kit REQ-001 --methodology bmad --agent developer
/kit REQ-001 --repair --methodology bmad --agent developer
```

## Eval Behavior

`/eval REQ-001 --methodology bmad --agent qa` still runs canonical CLike eval:

```text
handleEval -> /v1/eval/run -> EvalRunner.run_profile
```

BMAD QA may add advisory guidance after canonical eval. It does not decide pass/fail and does not change promotability.

## Gate Behavior

Gate remains CLike-only.

The current MVP does not accept methodology flags for `/gate`. The parser returns a clear error for:

```text
/gate REQ-001 --methodology bmad --agent qa
```

This prevents BMAD from entering gate authority.

## Output Contract Summary

Every Harper run now has an internal Active Output Contract. There is no user-facing `--methodology clike` flag; when methodology is omitted, CLike treats the run as `native_clike` internally and applies the native phase contract.

Native CLike runs use native active output contracts. For example, native `/idea` requires exactly `docs/harper/IDEA.md`, native `/spec` requires `docs/harper/SPEC.md`, and native `/plan` requires `docs/harper/PLAN.md`, `docs/harper/plan.json`, and lane guides when the PLAN contract requires them.

BMAD runs extend the active output contract with mandatory companion artifacts. Required outputs are exact path obligations, not a minimum file count. If the contract requires four BMAD IDEA companion files, the cloud model must emit or update those four paths; producing one extra file is not a substitute.

Optional BMAD artifacts are allowed only under controlled roots declared by the artifact policy. Companion artifacts are additive, non-authoritative, and bounded to controlled roots. Open-ended companion generation is allowed only inside those roots and must improve downstream SPEC, PLAN, KIT, EVAL, or FINALIZE work. If a companion artifact would not be useful downstream, the run should avoid producing it or explain why it is not needed.

Cloud and local-agent runners use the same contract model with different enforcement mechanisms. Gateway validates cloud file outputs after file-block parsing. Local-agent KIT and EVAL packages receive the active contract in `AGENT_EXECUTION_CONTEXT.json` or `AGENT_EVAL_CONTEXT.json`; local agents remain limited to currently supported local phases and candidate roots.

| Command | Canonical outputs | Companion outputs |
| --- | --- | --- |
| `/idea --methodology bmad --agent analyst` | `docs/harper/IDEA.md` | `docs/harper/bmad/idea/BRIEF.md`, `PRFAQ_NOTES.md`, `ASSUMPTIONS.md`, `RESEARCH_QUESTIONS.md`, and other useful files under `docs/harper/bmad/idea/**` |
| `/spec --methodology bmad --agent pm` | `docs/harper/SPEC.md` | `docs/harper/bmad/spec/PRD.md`, `EPICS.md`, `ACCEPTANCE_MODEL.md`, `SCOPE_DECISIONS.md`, and other useful files under `docs/harper/bmad/spec/**` |
| `/spec --methodology bmad --agent ux` | none in the current MVP | `docs/harper/ux/DESIGN.md`, `EXPERIENCE.md`, `USER_JOURNEYS.md`, `INTERACTION_STATES.md`, `SPEC_UX_APPENDIX.md`, and other useful files under `docs/harper/ux/**` |
| `/plan --methodology bmad --agent architect` | `docs/harper/PLAN.md`, `docs/harper/plan.json`, `docs/harper/lane-guides/**` | `docs/harper/bmad/architecture/ARCHITECTURE.md`, `DECISIONS.md`, `INTEGRATION_BOUNDARIES.md`, `RISKS.md`, and other useful files under `docs/harper/bmad/architecture/**` |
| `/plan --methodology bmad --agent pm` | `docs/harper/PLAN.md`, `docs/harper/plan.json`, `docs/harper/lane-guides/**` | `docs/harper/bmad/plan/STORIES.md`, `STORY_MAP.md`, `IMPLEMENTATION_READINESS.md`, and other useful files under `docs/harper/bmad/plan/**` |
| `/kit REQ-001 --methodology bmad --agent developer` | Candidate files under `runs/kit/REQ-001/src`, `test`, `ci`, and contract docs | `runs/kit/REQ-001/docs/BMAD_DEV_STORY.md`, `IMPLEMENTATION_NOTES.md`, `SELF_REVIEW.md`, `RUNBOOK.md`, and other useful candidate docs under `runs/kit/REQ-001/docs/**` |
| `/eval REQ-001 --methodology bmad --agent qa` | none; canonical eval remains EvalRunner-owned | `runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md`, `FIX_GUIDANCE.md`, `MISSING_TESTS.md`, `RISK_REVIEW.md`, and other useful advisory docs under `runs/kit/REQ-001/docs/**` |
| `/finalize --methodology bmad --agent tech-writer` | CLike finalize outputs such as `README.md` and `docs/harper/FINALIZE_NOTES.md` | `docs/harper/bmad/finalize/DOC_REVIEW.md`, `RELEASE_NARRATIVE.md`, `STAKEHOLDER_SUMMARY.md`, and other useful files under `docs/harper/bmad/finalize/**` |

Canonical artifacts win on conflict. Companion artifacts are valid context for downstream phases, but they cannot expand write permissions, change eval/gate authority, mutate promotion state, or override `TECH_CONSTRAINTS.yaml`.

## Current Out Of Scope

The current MVP does not implement BMAD runtime execution, `npx bmad-method` runtime invocation, the BMAD importer, TEA, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, or automatic latest BMAD tracking at runtime.
