# Future Party Mode

Party Mode is a future roadmap item. It is not implemented in the current BMAD integration.

The possible value of Party Mode is structured discussion between roles. An analyst, PM, architect, developer, UX role, QA role, or tech writer may contribute different perspectives before a Harper phase is finalized. That discussion can improve clarity, but it cannot become a second workflow authority.

Party discussion artifacts are governed by CLike and cannot overwrite canonical `PLAN.md` or `plan.json` directly.

## Possible Direction

Example future discussions:

```text
analyst + pm + architect review a plan before KIT
developer + qa review a repair strategy after eval
ux + pm clarify user-facing acceptance criteria during SPEC
architect + qa inspect contract and operational risk before KIT
```

The output of a future discussion should be a controlled companion artifact or a proposed phase input. CLike would still decide whether and how canonical artifacts are updated.

## Governance Requirements

Any future Party Mode must keep CLike as workflow owner, preserve one canonical phase output, avoid parallel pipelines, maintain auditability, keep eval and gate authoritative, and prevent role discussions from expanding write permissions.

Party Mode must not let role consensus override CLike gate decisions, directly mutate canonical Harper artifacts, promote code, or bypass candidate-first generation.
