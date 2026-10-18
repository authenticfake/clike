# CLike Documentation

CLike is an AI-native development pipeline built around three runtime surfaces:

- **VS Code extension** for chat, Harper commands, code actions, local agent execution, RAG attachment handling, and Git-assisted promotion.
- **Orchestrator** for workflow control, repository-aware preparation, RAG APIs, eval/gate orchestration, MCP exposure, and gateway delegation.
- **Gateway** for model catalog resolution, provider abstraction, Harper prompt execution, embeddings, and telemetry APIs.

This documentation reflects the current source tree in the inspected package and treats code as the source of truth.

## Documentation map

- `INSTALL.md` — requirements, configuration, services, extension, local agents, MCP for Claude Code / Codex
- `GET_STARTED.md` — first project, agent chat, auto-eval, acceptance-first, CLike from Claude Code / Codex, troubleshooting
- `architecture.md` — system structure and runtime boundaries
- `setup-and-runtime.md` — local services, ports, configs, and startup model
- `commands.md` — current slash commands, code actions, and extension commands
- `harper-workflow.md` — IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE, then `/idea --extend` for the next release
- `auto-eval.md` — `/eval REQ --fix`: governed KIT ⇄ EVAL repair loop, regression of promoted REQs, gate warnings policy, extra cycles while improving
- `artifacts.md` — canonical docs, run artifacts, candidate artifacts, and promotion files
- `local-agents.md` — current local execution path, GPT Codex / Claude Code integration, and restrictions
- `context-sources.md` — `.clike/context.yaml`: project files (requirements, UI references, data, ...) read by the phases, release folders (`docs/inputs/vN/`, `docs/reference/vN/`), formats and rules
- `rag.md` — indexing, search, fetch, attachment strategy, and repository grounding
- `git-and-promotion.md` — current Git behavior, stacked REQ branches, gate auto-merge promotion (3-way, conflicts, report), merge flow
- `mcp.md` — MCP servers (orchestrator, extension), tools and authentication
- `howto-mcp-project.md` — run a whole project from Claude Code or Codex through MCP (setup, the phase loop, next release, troubleshooting)
- `images/clike-overview.svg` (and `.png`) — CLike at a glance
- `api-reference.md` — endpoint census for orchestrator, gateway, and agent surfaces
- `agent-operating-model.md` — developer→agent and agent→CLike operating models, methodology profiles
- `architecture/ADOPT_AND_IDEA_EXTEND.md` — `/idea --extend` (implemented: release cascade of a delivered project with ADDED/MODIFIED/REMOVED requirements) and the `/adopt` proposal for brownfield repositories (not implemented)
- `development.md` — developer guide: local runs, tests, golden snapshots, lint baseline, hygiene, CI, rebuild, eval sandbox and **eval environment** (`docker/eval.env`, provisioned variables, test databases, services of other REQs)
- `../SECURITY.md` — security model, known limitations, vulnerability reporting
- `../CHANGELOG.md` — release notes

## Current product shape

### Extension
The VS Code extension currently provides:
- Chat modes: **free**, **coding**, **harper**
- Harper slash commands and webview-based execution
- AI code actions for docstrings, refactoring, tests, and fix flows
- File attachments with **inline** vs **RAG** paths
- Local agent execution for compatible Harper flows
- Git helpers for branch, commit, PR, and promotion
- Eval/Gate integration from the chat UI and commands

### Orchestrator
The orchestrator currently provides:
- Legacy `/v1/chat` and `/v1/generate` (`/v1/apply` was removed in the 2026-10 hardening)
- Harper workflow APIs under `/v1/harper/*`
- RAG APIs under `/v1/rag/*`
- Eval/Gate endpoints
- Agent endpoint for code-action style tasks
- Router resolution endpoint
- Optional **read-only MCP server** mounted at `/mcp`
- Eval sandbox (isolated container), eval environment provisioning, eval tools catalog (`/v1/eval/tools`)

### Gateway
The gateway currently provides:
- Model catalog and validation
- Provider-routed chat completions
- Embeddings
- Harper phase execution via `/v1/harper/run`
- Telemetry APIs and telemetry UI

## What is current vs experimental

### Current
The following are implemented in the inspected sources:
- Harper phases and slash-command entrypoints
- Candidate artifact generation under `runs/kit/<REQ-ID>/...`
- RAG index/search/fetch APIs
- Local agent integration with **Claude Code** and **GPT Codex**
- `AGENT_EXECUTION_CONTEXT.json`
- Eval pre-pass support for local agents
- `/eval --fix` / `/gate --fix` repair loops, regression of promoted REQs, gate auto-merge promotion, merge-on-gate
- `/finalize` solution verification (`ci/SOLUTION_LTC.json`, `FINALIZE_REPORT.md`, local run scripts)
- `/idea --extend` release cascade of a delivered project
- MCP server mounted by orchestrator when enabled; extension MCP server for Claude Code / Codex
- Gateway model routing and provider abstraction
- Telemetry endpoints for Harper metrics

### Present but restricted
The following are implemented with explicit guardrails:
- Local agents run every Harper phase (IDEA … FINALIZE, `/extend`, `/idea --extend`) under the phase write policy; the verdict of `/eval` and `/gate` is always the canonical sandbox eval, the local `/eval` path is a **pre-pass**
- The orchestrator MCP server is **read-only**; the extension MCP server runs phases, `eval_run` and `gate_check` through the governed chat flow, without overrides, promotion or Git

### Not documented as current product guarantees
The inspected codebase does **not** justify treating these as stable user-facing guarantees:
- MCP tools that write files, promote or run Git
- Remote external agent orchestration as a production contract

## Naming and compatibility notes

The sources currently show both legacy and normalized naming in the local-agent area.

### Execution preference
The extension normalizes legacy values:
- `prefer_claude_code` → `prefer_local_agent`
- `claude_code_only` → `local_agent_only`
- `auto` → `cloud_only`
- `hybrid` → `prefer_local_agent`

Current normalized execution preference values are:
- `cloud_only`
- `prefer_local_agent`
- `local_agent_only` (default of `clike.execution.defaultPreference`)

### Local executors
Current supported local executors are:
- `claude_code`
- `gpt_codex`

Both are exposed as local agent executors behind the same extension workflow.

## Recommended reading order

For onboarding, read in this order:
1. `architecture.md`
2. `agent-operating-model.md`
3. `setup-and-runtime.md`
4. `commands.md`
5. `harper-workflow.md`
6. `artifacts.md`
7. `api-reference.md`
8. `development.md` (contributors)
