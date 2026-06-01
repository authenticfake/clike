# BMAD Test Plan

The BMAD integration is tested as methodology metadata and guidance, not as an execution backend. The tests should prove that CLike remains the governed runtime while BMAD enriches phase behavior.

## Local Commands

Run Python compilation for touched orchestrator and gateway modules:

```text
python -m compileall orchestrator gateway
```

Run orchestrator unit tests:

```text
cd orchestrator
../.venv/bin/python -m unittest tests.test_methodology_resolver tests.test_methodology_injection tests.test_eval_canonical_bmad tests.test_harper_schema tests.test_plan_prompt_content
```

Run pytest when the local environment has the project test dependencies installed:

```text
pytest orchestrator/tests
```

Run VS Code extension tests:

```text
node --test extensions/vscode/test/slash-parser.test.js extensions/vscode/test/bmad-advisory.test.js
```

Run safety grep checks from the repository root:

```text
rg -n "npx bmad-method|bmad-method|from bmad|import bmad|require\\(['\\\"]bmad" .
rg -n "methodology_context" orchestrator gateway extensions/vscode
rg -n "Roun[d] [0-9]" README.md docs extensions/vscode
```

The first grep should not reveal a runtime dependency or CLI invocation. The second grep is a review aid for ownership and injection boundaries. The third grep helps keep internal implementation-round wording out of user-facing docs.

## Manual VS Code Smoke Tests

Run these commands from the CLike chat UI in a test workspace:

```text
/idea --methodology bmad --agent analyst
/spec --methodology bmad --agent pm
/spec --methodology bmad --agent ux
/plan --methodology bmad --agent architect
/plan --methodology bmad --agent pm
/kit REQ-001 --methodology bmad --agent developer
/kit REQ-001 --repair --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/eval REQ-001 --methodology bmad --agent developer
/finalize --methodology bmad --agent tech-writer
```

Also verify that `/gate REQ-001 --methodology bmad --agent qa` is rejected with a clear MVP gate ownership message.

## Parser Coverage

Parser tests should cover legacy slash parsing without methodology flags, both `--methodology bmad` and `--methodology=bmad`, both `--agent developer` and `--agent=developer`, `--agent` without `--methodology`, unsupported methodology, unsupported agent, invalid phase-to-agent mapping, KIT repair, KIT phases, and gate override rejection.

## Resolver Coverage

Resolver tests should cover default agent per phase, allowed explicit agents, eval advisory-only context, gate CLike-only context, invalid methodology errors, invalid agent errors, and enriched workflow metadata.

## Injection Coverage

Injection tests should prove that cloud runs receive methodology context only through Gateway prompt composition, local-agent packages receive methodology context through `local_agent_package`, methodology context is absent when omitted, allowed write roots are unchanged when BMAD is enabled, and forbidden paths are unchanged when BMAD is enabled.

## Eval And Gate Coverage

Eval and gate tests should prove that `/v1/eval/run` remains canonical through `EvalRunner.run_profile`, `/eval --methodology bmad --agent qa` still invokes canonical eval before advisory handling, BMAD advisory does not change eval status, pass/fail, or promotable fields, and gate cannot be overridden by BMAD flags.

## Non-Goals

The current test plan does not cover BMAD artifact importing, TEA, Party Mode, MCP write tools, external BMAD CLI execution, or `npx bmad-method` because those features are not implemented.
