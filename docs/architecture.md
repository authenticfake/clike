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
  ├─ legacy chat/generate APIs
  ├─ agent code-action API
  ├─ routing APIs
  └─ optional read-only MCP server
        │            │
        │            └─▶ eval-sandbox (runs eval/gate checks, no credentials)
        │                 └─ eval-tools (installs catalog tools into a read-only volume)
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
  ├─ OpenAI-compatible endpoints (Ollama, ...)
  └─ Qdrant (RAG store, used by the orchestrator)
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
- `extensions/vscode/utility.js`
- `extensions/vscode/auto-eval.js` (`/eval --fix`, `/gate --fix`), `promote-merge.js` (gate auto-merge),
  `finalize-verify.js` (solution verification), `release-extend.js` (`/idea --extend`),
  `eval-tools.js` (`/tools`)

### Orchestrator
The orchestrator is the control plane.

Responsibilities:
- receives extension workflow requests
- prepares Harper payloads and repository context as a typed `PhaseContext` (v1)
- composes the cloud phase messages from the phase definitions (`orchestrator/phases/`)
- delegates the model call to the gateway with the composed messages
- exposes repository-grounded RAG services
- runs eval/gate services (in the `eval-sandbox` container), provisions the eval environment and
  the eval tools, runs the regression of promoted REQs
- resolves the project context sources (`.clike/context.yaml`, release folders)
- exposes legacy generation APIs
- exposes read-only MCP tools
- builds execution packages for local agents (`services/local_agent/`)

Key implementation files:
- `orchestrator/app.py`
- `orchestrator/routes/harper.py`
- `orchestrator/routes/rag.py`
- `orchestrator/routes/routes_eval.py`
- `orchestrator/eval_runner.py`, `orchestrator/eval_environment.py`, `orchestrator/eval_sandbox_app.py`,
  `orchestrator/eval_tools_app.py`
- `orchestrator/services/context_sources.py`, `orchestrator/services/extend_cascade.py`
- `orchestrator/routes/agent.py`
- `orchestrator/mcp_server.py`
- `orchestrator/services/harper.py`
- `orchestrator/services/phase_context.py`, `orchestrator/services/cloud_prompt/`
- `orchestrator/phases/<phase>/` (phase.yaml, text.yaml, cloud_*.md)

### Gateway
The gateway is the model and provider execution layer.

Responsibilities:
- loads and validates the model catalog
- resolves model aliases and route selection
- abstracts provider differences
- runs Harper model calls on the messages composed by the orchestrator, adding RAG material and chat history, then extracts and validates the produced files
- executes embeddings
- records telemetry (cloud and local-agent runs) and exposes telemetry views
- retrieves RAG materials through the orchestrator's `/v1/rag` when requested by Harper flow

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

A delivered project evolves by releases: `/idea --extend` (EXTEND phase, cascade mode) merges the
release inputs into IDEA, SPEC and TECH_CONSTRAINTS and appends a PLAN delta of ADDED / MODIFIED /
REMOVED REQs, which then go through KIT → EVAL → GATE → FINALIZE. `/extend` only appends REQs.

### Operational split
- The extension provides UX, command parsing, local execution, and candidate file handling.
- The orchestrator owns the Harper domain: phase definitions, context, prompt composition, local-agent packages, RAG APIs, eval/gate control, and MCP exposure.
- The gateway owns provider interaction for Harper runs: model call, RAG material, output extraction and validation.

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
- canonical authority for eval/gate outcomes (the eval always runs in the CLike sandbox)

### Local agent path
- extension builds `AGENT_EXECUTION_CONTEXT.json`
- extension invokes a local executor (`claude_code` or `gpt_codex`)
- local executor writes within the write roots of its phase: Harper documents for IDEA … PLAN and
  EXTEND, candidate files under `runs/kit/<REQ-ID>/...` for KIT, the solution for FINALIZE
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

The VS Code extension runs a second, operational MCP server (off by default, loopback, token): it
runs Harper phases, `eval_run` and `gate_check` through the same governed chat flow, without
overrides, promotion choices or Git.

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
- is a client of the orchestrator's `/v1/rag` (no store of its own); embeddings are computed through
  its `/v1/embeddings`

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
- the orchestrator MCP is intentionally read-only
- the extension remains the orchestration UX surface for day-to-day developer interaction
