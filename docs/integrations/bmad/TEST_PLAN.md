# BMAD Test Plan

The BMAD integration is tested as methodology metadata and guidance, not as an execution backend.

## Parser Tests

Coverage:

- legacy slash parsing without methodology flags
- `--methodology bmad`
- `--methodology=bmad`
- `--agent developer`
- `--agent=developer`
- `--agent` without `--methodology`
- unsupported methodology
- unsupported agent
- invalid phase-to-agent mapping
- gate override rejection

## Resolver Tests

Coverage:

- default agent per phase
- allowed explicit agents
- eval advisory-only context
- gate CLike-only context
- invalid methodology and agent errors

## Injection Tests

Coverage:

- cloud runs receive methodology context through Gateway prompt composition
- local-agent packages receive methodology context through `local_agent_package`
- methodology context is absent when omitted
- allowed write roots are unchanged when BMAD is enabled
- forbidden paths are unchanged when BMAD is enabled

## Eval/Gate Tests

Coverage:

- `/v1/eval/run` remains canonical through `EvalRunner.run_profile`
- `/eval --methodology bmad --agent qa` still invokes canonical eval before advisory handling
- BMAD advisory does not change eval status, pass/fail, or promotable fields
- gate cannot be overridden by BMAD flags

## Non-Goals

The current test plan does not cover:

- BMAD artifact importing
- TEA
- Party Mode
- MCP write tools
- external BMAD CLI execution
- `npx bmad-method`

These features are not implemented.
