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

The result is still canonical `SPEC.md`. BMAD PM guidance should make requirements clearer and more testable, not create an alternate PRD pipeline.

### Spec With UX

Use the UX role when user journeys, interaction states, accessibility, terminology, empty states, and error states need first-class attention.

```text
/spec --methodology bmad --agent ux
```

UX guidance may refer to controlled companion artifacts such as `docs/harper/ux/DESIGN.md` and `docs/harper/ux/EXPERIENCE.md` when present. It does not override CLike output contracts or eval/gate policy.

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
