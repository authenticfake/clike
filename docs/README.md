# CLike Documentation

CLike is an AI-native development pipeline built around three runtime surfaces:

- **VS Code extension** for chat, Harper commands, code actions, local agent execution, RAG attachment handling, and Git-assisted promotion.
- **Orchestrator** for workflow control, repository-aware preparation, RAG APIs, eval/gate orchestration, MCP exposure, and gateway delegation.
- **Gateway** for model catalog resolution, provider abstraction, Harper prompt execution, embeddings, and telemetry APIs.

This documentation reflects the current source tree in the inspected package and treats code as the source of truth.

## Documentation map

- `architecture.md` — system structure and runtime boundaries
- `setup-and-runtime.md` — local services, ports, configs, and startup model
- `commands.md` — current slash commands, code actions, and extension commands
- `harper-workflow.md` — IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
- `artifacts.md` — canonical docs, run artifacts, candidate artifacts, and promotion files
- `local-agents.md` — current local execution path, GPT Codex / Claude Code integration, and restrictions
- `rag.md` — indexing, search, fetch, attachment strategy, and repository grounding
- `git-and-promotion.md` — current Git behavior, branch strategy, promotion, and merge flow
- `mcp.md` — current read-only MCP server and exposed tools
- `api-reference.md` — endpoint census for orchestrator, gateway, and agent surfaces

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
- Legacy `/v1/chat`, `/v1/generate`, and `/v1/apply`
- Harper workflow APIs under `/v1/harper/*`
- RAG APIs under `/v1/rag/*`
- Eval/Gate endpoints
- Agent endpoint for code-action style tasks
- Router resolution endpoint
- Optional **read-only MCP server** mounted at `/mcp`

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
- MCP server mounted by orchestrator when enabled
- Gateway model routing and provider abstraction
- Telemetry endpoints for Harper metrics

### Present but restricted
The following are implemented with explicit guardrails:
- Local agent execution is intended for **base `/kit`** flows first
- `/eval` local path is a **pre-pass**, not the canonical decision authority
- Follow-up KIT phases are restricted when `clike.localAgent.restrictToKitPhases=true`
- MCP is **read-only** and does not execute phases or mutate Git

### Not documented as current product guarantees
The inspected codebase does **not** justify treating these as stable user-facing guarantees:
- A slash command to dynamically change the default local agent from chat
- Writable or phase-executing MCP tools
- Remote external agent orchestration as a production contract

## Naming and compatibility notes

The sources currently show both legacy and normalized naming in the local-agent area.

### Execution preference
The extension normalizes legacy values:
- `prefer_claude_code` → `prefer_local_agent`
- `claude_code_only` → `local_agent_only`

Current normalized execution preference values are:
- `auto`
- `cloud_only`
- `prefer_local_agent`
- `local_agent_only`
- `hybrid`

### Local executors
Current supported local executors are:
- `claude_code`
- `gpt_codex`

Both are exposed as local agent executors behind the same extension workflow.

## Recommended reading order

For onboarding, read in this order:
1. `architecture.md`
2. `setup-and-runtime.md`
3. `commands.md`
4. `harper-workflow.md`
5. `artifacts.md`
6. `api-reference.md`
