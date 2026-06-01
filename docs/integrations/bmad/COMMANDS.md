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
/kit REQ-001 --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/finalize --methodology bmad --agent tech-writer
```

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

