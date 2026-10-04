# Agent Operating Model

CLike supports two complementary ways of working with coding agents. In both, CLike owns the
Harper lifecycle and its governance; agents and models are executors.

## Model 1 — Developer activates an agent through CLike

This is the local-agent (execution-agent) path. It covers the Harper phases `/idea`, `/spec`,
`/plan`, `/kit`, `/eval`, `/finalize` and `/extend`. All phases reuse the same execution-agent
architecture; only the expected output files, allowed write paths, phase prompt and phase
validation differ.

```text
Developer
→ VS Code extension
→ Orchestrator builds an execution package (prompt, contract, write roots, expected outputs)
→ Extension runs the local agent (Claude Code, Codex CLI, …)
→ Orchestrator normalizes the result
→ RAG / Git / Eval / Gate continue through CLike
```

For the document phases the local agent writes `docs/harper/IDEA.md` (idea),
`docs/harper/SPEC.md` (spec), and `docs/harper/PLAN.md` plus `docs/harper/plan.json` (plan); all
other `docs/harper/` paths stay protected. Cloud and local execution remain semantically
equivalent and CLike governance stays canonical.

### Responsibilities

| Orchestrator | Extension |
|---|---|
| Harper phase semantics | UI |
| Execution strategy and local-agent eligibility | Workspace access |
| Executor hints | Confined local filesystem writes |
| Prompt contracts, allowed write roots, expected outputs | Local CLI execution (argv, no shell; prompt on stdin on Windows) |
| Fallback policy | stdout/stderr/exit-code and generated-file collection |
| Result normalization | Git integration |

Local agents are executors only. They must not promote files, run Git operations, or write
directly to canonical `src/`, `test/` or `tests/` roots. They authenticate through their own CLI
session: cloud API keys are removed from their environment.

### Free chat (Q&A) and Coding via local agent

The same execution-agent path serves the standalone chat modes. The **Execution** selector lets a
request run via the local agent instead of the cloud:

- **Free chat (Q&A)** runs the local agent read-only and renders its answer as a chat bubble,
  badged with the agent used (`agent-claude` / `agent-codex`). A short execution synthesis is shown
  in the **Text** panel.
- **Coding** lets the local agent write the requested artifacts under a `generated/<id>/` folder in
  the workspace root, mirroring the cloud generation layout. Generated files are listed and
  clickable in the **Files** tab.

Model availability is computed by the gateway from the configured provider keys. With at least one
cloud key all execution options are available (`agent only` is the default); without cloud keys
only `agent only` remains selectable. Provider/key mismatches surface as a clear message in the
**Text** panel.

## Model 2 — Agent interacts with CLike

This is the MCP-driven operating model.

```text
External / local agent
→ CLike extension operational MCP server (opt-in, token-protected)
→ Extension dispatches the normal slash commands
→ Normal CLike flow: Orchestrator → Gateway / local agent / RAG / Git / Eval / Gate
```

The agent does not call the orchestrator with invented Harper payloads: it asks the extension to
dispatch the same slash commands a developer would type (`/kit REQ-001`, `/eval REQ-001`,
`/gate REQ-001`, `/finalize`, `/ragIndex docs/**/*`, `/agent-default codex`, …). This keeps the
workflow simple, auditable and aligned with the developer path. When there are no open or
in-progress REQs, Model 2 tools report `finalize_only`.

See [mcp.md](mcp.md) for the tool list and authentication.

## Methodology profiles

Methodology profiles (for example BMAD) can enrich how phases reason with role-aware guidance, but
they never replace Harper governance:

- companion artifacts are additive and non-authoritative; canonical Harper artifacts win on conflict;
- methodology is not an executor: cloud models and local agents remain execution choices governed by CLike;
- eval and gate remain CLike-owned; methodology QA is advisory only;
- there is no runtime dependency (no `npx bmad-method`, no vendored runtime code).

See [integrations/bmad/README.md](integrations/bmad/README.md).
