# BMAD Integration

BMAD support in CLike is implemented as a governed methodology profile. It enriches Harper phase behavior with role-aware guidance, but it does not replace CLike workflow ownership.

CLike remains responsible for:
- canonical Harper artifacts
- orchestration and phase state
- eval, gate, telemetry, audit, and promotion
- cloud/local execution policy
- candidate-first isolation and write-root governance

BMAD contributes:
- methodology identity with `--methodology bmad`
- role identity with `--agent <role>`
- phase-to-role defaults
- cloud prompt guidance through Gateway when a cloud Harper run is used
- local-agent guidance through `local_agent_package` when Claude Code or Codex CLI is used
- QA advisory guidance after canonical eval

BMAD is not a hard dependency. CLike does not call `npx bmad-method`, does not vendor BMAD code, and does not create a parallel BMAD pipeline.

## Current Documents

- [Methodology Profile](METHODOLOGY_PROFILE.md)
- [Governance Model](GOVERNANCE_MODEL.md)
- [Commands](COMMANDS.md)
- [Agents](AGENTS.md)
- [UX Profile](UX_PROFILE.md)
- [Future Importer](FUTURE_IMPORTER.md)
- [Future TEA](FUTURE_TEA.md)
- [Future Party Mode](FUTURE_PARTY_MODE.md)
- [Future MCP Write Tools](FUTURE_MCP_WRITE_TOOLS.md)
- [Test Plan](TEST_PLAN.md)

## Execution Boundaries

Cloud path:

```text
Orchestrator -> Gateway -> cloud LLM prompt
```

Local-agent path:

```text
Orchestrator -> local_agent_package -> AGENT_*_CONTEXT / AGENT_*_PROMPT -> Claude Code or Codex CLI
```

Gateway is only for cloud LLM prompt composition. Gateway is not a universal methodology prompt builder and is not used to construct local-agent prompts.

