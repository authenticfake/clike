# Architecture

## Runtime topology

CLike is split into three main runtime components.

```text
VS Code extension
  ├─ chat UI
  ├─ slash commands
  ├─ code actions
  ├─ attachment handling
  ├─ local agent execution
  └─ Git integration
        │
        ▼
Orchestrator (FastAPI, default port 8080)
  ├─ Harper workflow control
  ├─ RAG APIs
  ├─ eval/gate endpoints
  ├─ legacy chat/generate/apply APIs
  ├─ agent code-action API
  ├─ routing APIs
  └─ optional read-only MCP server
        │
        ▼
Gateway (FastAPI, default port 8000)
  ├─ model catalog
  ├─ model validation
  ├─ provider-routed chat completions
  ├─ embeddings
  ├─ Harper phase execution
  └─ telemetry APIs / UI
        │
        ▼
Providers / infra
  ├─ OpenAI
  ├─ Anthropic
  ├─ DeepSeek
  ├─ Ollama
  ├─ vLLM
  └─ Qdrant
```

## Component responsibilities

### VS Code extension
The extension is the primary user entrypoint.

Responsibilities:
- hosts the chat webview and mode switching
- parses Harper slash commands
- manages session state and history scope
- resolves inline vs RAG attachments
- invokes orchestrator and gateway routes
- writes local candidate artifacts in compatible flows
- optionally invokes local agent executors
- runs Git helper flows and promotion helpers

Key implementation files:
- `extensions/vscode/extension.js`
- `extensions/vscode/chat-ui.js`
- `extensions/vscode/local-agent-executors.js`
- `extensions/vscode/git.js`
- `extensions/vscode/rag.js`
- `extensions/vscode/utility.js`

### Orchestrator
The orchestrator is the control plane.

Responsibilities:
- receives extension workflow requests
- prepares Harper payloads and repository context
- proxies or delegates Harper execution to gateway
- exposes repository-grounded RAG services
- runs eval/gate services
- exposes legacy generation APIs
- exposes read-only MCP tools
- builds execution contracts for local agents

Key implementation files:
- `orchestrator/app.py`
- `orchestrator/routes/harper.py`
- `orchestrator/routes/rag.py`
- `orchestrator/routes/routes_eval.py`
- `orchestrator/routes/agent.py`
- `orchestrator/mcp_server.py`
- `orchestrator/services/harper.py`

### Gateway
The gateway is the model and provider execution layer.

Responsibilities:
- loads and validates the model catalog
- resolves model aliases and route selection
- abstracts provider differences
- runs Harper prompt pipelines
- executes embeddings
- records telemetry and exposes telemetry views
- stores or retrieves RAG materials when requested by Harper flow

Key implementation files:
- `gateway/app.py`
- `gateway/routes/models.py`
- `gateway/routes/chat.py`
- `gateway/routes/embeddings.py`
- `gateway/routes/harper.py`
- `gateway/routes/telemetry_api.py`
- `gateway/routes/telemetry_ui.py`

## Harper architecture

Harper is implemented as a repository-aware iterative pipeline, not as a single monolithic generation step.

### Canonical flow
- `IDEA`
- `SPEC`
- `PLAN`
- `KIT`
- `EVAL`
- `GATE`
- `FINALIZE`

### Operational split
- The extension provides UX, command parsing, local execution, and candidate file handling.
- The orchestrator owns workflow preparation, RAG APIs, eval/gate control, and MCP exposure.
- The gateway owns the actual Harper phase execution and provider interaction.

## Candidate-first design

A core architectural rule in current sources is that generated implementation artifacts are first written under candidate roots, not promoted directly.

Primary candidate root:
- `runs/kit/<REQ-ID>/`

Common subtrees:
- `runs/kit/<REQ-ID>/src/`
- `runs/kit/<REQ-ID>/test/`
- `runs/kit/<REQ-ID>/ci/`
- `runs/kit/<REQ-ID>/docs/`

This separation is foundational for:
- local agent execution
- canonical eval/gate decisions
- Git promotion
- safe review before promotion

## Local vs cloud execution paths

The current architecture supports two execution paths for compatible Harper work:

### Cloud path
- extension → orchestrator → gateway → provider
- canonical path for Harper workflow execution
- canonical authority for eval/gate outcomes

### Local agent path
- extension builds `AGENT_EXECUTION_CONTEXT.json`
- extension invokes a local executor (`claude_code` or `gpt_codex`)
- local executor writes candidate files under `runs/kit/<REQ-ID>/...`
- extension may still fall back to cloud path if local execution is unavailable or restricted

## MCP position in architecture

The orchestrator mounts a FastMCP server at `/mcp` when enabled.

Current MCP characteristics:
- read-only
- streamable HTTP transport
- contract-first
- no phase execution
- no Git mutation
- no arbitrary shell
- no arbitrary filesystem writes

## RAG position in architecture

RAG spans extension, orchestrator, gateway, and Qdrant-backed storage.

### Extension
- chooses inline vs RAG attachment strategy
- offers `/rag`, `/ragIndex`, `/ragSearch`

### Orchestrator
- exposes `/v1/rag/*` APIs
- builds repository-aware RAG requests
- fetches or prepares RAG context for Harper workflows

### Gateway
- can consume RAG materials during Harper execution
- stores or retrieves chunks as part of Harper context preparation

## Telemetry position in architecture

Telemetry is currently gateway-centric for Harper execution visibility.

Main telemetry surfaces:
- `GET /v1/metrics/harper/files`
- `GET /v1/metrics/harper/projects`
- aggregate / series / top / raw endpoints
- `GET /v1/metrics/harper/ui`

The orchestrator also keeps run-oriented artifacts under `runs/<runId>/...`.

## Current architectural constraints

The current sources imply the following constraints:
- candidate artifacts must remain isolated before promotion
- local agent execution must not mutate canonical workspace roots directly
- eval/gate remain contract-driven and artifact-driven
- MCP is intentionally read-only
- the extension remains the orchestration UX surface for day-to-day developer interaction
