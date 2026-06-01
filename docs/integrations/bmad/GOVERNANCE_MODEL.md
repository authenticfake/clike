# BMAD Governance Model

CLike owns governance. BMAD enriches phase behavior.

This is the core rule for the integration.

## CLike-Owned Authority

CLike remains authoritative for:

- canonical Harper documents such as `IDEA.md`, `SPEC.md`, `PLAN.md`, and `plan.json`
- candidate KIT roots under `runs/kit/<REQ-ID>/`
- local-agent execution contracts
- allowed write roots and forbidden paths
- canonical eval execution through EvalRunner
- gate decisions
- telemetry and audit records
- promotion and Git-related flows
- MCP read/write policy

BMAD guidance cannot override any of these.

## Cloud Path

For cloud Harper runs, the orchestrator resolves `methodology_context` and sends it to Gateway. Gateway injects the resolved context into the cloud LLM prompt.

Gateway remains a cloud prompt composition and provider abstraction layer. Gateway does not resolve methodology identity and does not build local-agent prompts.

## Local-Agent Path

For Claude Code or Codex local execution, the orchestrator resolves `methodology_context` and injects it through `local_agent_package`.

The package writes methodology guidance into:

- `AGENT_*_CONTEXT.json`
- `AGENT_*_PROMPT.md`

This preserves the local-agent execution boundary:

```text
Orchestrator -> local_agent_package -> local CLI actuator
```

Local-agent methodology guidance must not expand `allowed_write_roots`, relax `forbidden_paths`, or bypass CLike candidate isolation.

## Eval And Gate

EvalRunner remains authoritative for eval. BMAD QA can add advisory guidance only after canonical eval has run.

BMAD QA cannot:

- replace EvalRunner
- decide pass/fail
- change `promotable`
- change REQ status
- affect gate

Gate is CLike-only. BMAD flags are unsupported for gate in the current MVP.

