# BMAD Commands

Existing Harper commands remain unchanged. BMAD support is added through optional flags.

## Flags

Supported forms:

```text
--methodology bmad
--methodology=bmad
--agent developer
--agent=developer
```

`--agent` requires `--methodology`.

## Examples

```text
/idea --methodology bmad
/spec --methodology bmad --agent pm
/spec --methodology=bmad --agent=ux
/plan --methodology bmad --agent architect
/plan --methodology bmad --agent pm
/kit REQ-001 --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/finalize --methodology bmad --agent tech-writer
```

## Plan Behavior

`/plan --methodology bmad --agent architect` and `/plan --methodology bmad --agent pm` keep CLike ownership of `docs/harper/PLAN.md` and `docs/harper/plan.json`.

BMAD guidance enriches planning so each REQ is implementation-ready for `/kit`. Each REQ should make functional scope, technical scope, non-functional requirements, security requirements, compliance and privacy requirements when applicable, observability and operations, integration contracts, data contracts, dependencies, acceptance criteria, test strategy, risk and mitigation, TECH_CONSTRAINTS obligations, the main module boundary, current build scope, deferred scope, and downstream assumptions clear.

`plan.json` remains the machine-readable source for `/kit`. It should preserve fields such as `functional_scope`, `technical_scope`, `non_functional_requirements`, `security_requirements`, `compliance_requirements`, `operational_requirements`, `integration_contracts`, `data_contracts`, `test_strategy`, `risk_notes`, `main_module_boundary`, `runtime_profile` when known, and `gate_expectations` when relevant.

BMAD planning does not hardcode Python, Node, cloud-only delivery, or any other stack. TECH_CONSTRAINTS, SPEC, repository evidence, and explicit user input decide technology and runtime obligations.

## KIT Flags Remain Compatible

Existing KIT options remain valid:

```text
/kit REQ-001 --integrity
/kit REQ-001 --hardener
/kit REQ-001 --promotion-eval
/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval
/kit REQ-001 --methodology bmad --agent developer
```

## Eval Behavior

`/eval REQ-001 --methodology bmad --agent qa` still runs canonical CLike eval:

```text
handleEval -> /v1/eval/run -> EvalRunner.run_profile
```

BMAD QA may add advisory guidance after canonical eval. It does not decide pass/fail and does not change promotability.

## Gate Behavior

Gate remains CLike-only.

The current MVP returns a clear command parsing error for:

```text
/gate REQ-001 --methodology bmad --agent qa
```

This prevents BMAD from entering gate authority.
