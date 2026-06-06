# BMAD Integration

BMAD support in CLike is implemented as a governed methodology profile. It gives Harper phases a richer role-driven working style, while CLike remains the runtime that owns lifecycle control, artifact contracts, execution boundaries, eval, gate, telemetry, audit, and promotion.

The integration exists because methodology and execution are different concerns. A methodology can tell the system how to reason about a phase: an analyst can frame the idea, a product manager can tighten acceptance criteria, an architect can make implementation slices more precise, a developer can focus a candidate KIT run, and QA can explain likely repair paths. None of those roles become executors, and none of them receive governance authority.

CLike remains responsible for canonical Harper artifacts, orchestration and phase state, eval, gate, telemetry, audit, promotion, cloud/local execution policy, candidate-first isolation, allowed write roots, and forbidden paths. BMAD contributes methodology identity with `--methodology bmad`, role identity with `--agent <role>`, phase-to-role defaults, cloud prompt guidance when Gateway is used, local-agent guidance when Claude Code or Codex CLI is used, and QA advisory guidance after canonical eval.

BMAD is not a hard dependency. CLike does not invoke the official BMAD package-runner command, does not vendor BMAD code, and does not create a parallel BMAD pipeline.

## Current Documents

- [Methodology Profile](METHODOLOGY_PROFILE.md)
- [Governance Model](GOVERNANCE_MODEL.md)
- [Commands](COMMANDS.md)
- [Agents](AGENTS.md)
- [UX Profile](UX_PROFILE.md)
- [Provenance](PROVENANCE.md)
- [Profile Sync Report](PROFILE_SYNC_REPORT.md)
- [Scorecard](SCORECARD.md)
- [Verification](VERIFICATION.md)
- [Future Importer](FUTURE_IMPORTER.md)
- [Future TEA](FUTURE_TEA.md)
- [Future Party Mode](FUTURE_PARTY_MODE.md)
- [Future MCP Write Tools](FUTURE_MCP_WRITE_TOOLS.md)
- [Test Plan](TEST_PLAN.md)

## Execution Boundaries

For cloud Harper runs, the orchestrator resolves the methodology context and sends it to Gateway. Gateway is cloud-only prompt composition. It renders the resolved methodology context into the cloud LLM prompt, but it does not resolve methodology identity and it is not a universal methodology prompt builder.

```text
VS Code -> Orchestrator -> methodology resolver -> Gateway -> cloud LLM prompt
```

For local-agent runs, the orchestrator resolves the same methodology context and injects it into the local-agent package. The package is the boundary that creates `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md` for Claude Code or Codex CLI. Local-agent prompt construction is not routed through Gateway.

```text
VS Code -> Orchestrator -> methodology resolver -> local_agent_package -> AGENT_*_CONTEXT / AGENT_*_PROMPT -> Claude Code or Codex CLI
```

EvalRunner remains authoritative for eval. BMAD QA can attach operational advisory guidance after canonical eval, but it cannot decide pass/fail, change promotability, promote code, or affect gate. Gate is CLike-only and does not accept methodology authority in the current MVP.

## Roadmap Boundaries

The current MVP does not implement BMAD runtime execution, `npx bmad-method` runtime invocation, the BMAD importer, TEA/Test Architect, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, or automatic latest BMAD tracking at runtime. Those topics are documented as future roadmap areas only. Any future implementation must preserve CLike governance, controlled roots, auditability, dry-run or approval behavior where relevant, and the existing eval/gate authority model.
