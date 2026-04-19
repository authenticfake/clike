# Setup and Runtime

## Default local topology

The inspected `docker/docker-compose.yml` defines these services:

- `gateway` on port `8000`
- `orchestrator` on port `8080`
- `ollama` on port `11434`
- `qdrant` on port `6333`

## Service startup model

### Gateway
Default command:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Orchestrator
Default command:
```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### Ollama
Runs as a sidecar local model service and is initialized with a bootstrap container that ensures `nomic-embed-text` is present.

### Qdrant
Runs as the vector store backing RAG persistence.

## Main environment variables

### Orchestrator
Important environment variables in compose:
- `GATEWAY_URL=http://gateway:8000`
- `RUNS_DIR=/runs`
- `WORKSPACE_ROOT=/workspace/`
- `CODE_ROOT_BASE=src`
- `TEST_ROOT_BASE=tests`
- `GENERATED_ROOT=/generated`
- `RAG_BASE_URL=http://localhost:8080/v1/rag`
- `RAG_TOP_K=12`
- `INLINE_MAX_FILE_KB=64`
- `INLINE_MAX_TOTAL_KB=256`
- `RAG_SIZE_THRESHOLD_KB=64`
- `PREFER_FRONTIER_FOR_REASONING=true`
- `OPTIMIZE_FOR=capability`
- `CLIKE_MCP_SERVER_ENABLED=true`

### Gateway
Important environment variables in compose:
- `MODELS_CONFIG=/workspace/configs/models.yaml`
- `HARPER_TELEMETRY_DIR=/workspace/telemetry`
- `HARPER_STUB_DIR=/workspace/gateway/stub`
- `GATEWAY_DUMP_DIR=/app/runs/gateway_dumps`
- `RAG_BASE_URL=http://orchestrator:8080/v1/rag`
- `RAG_TOP_K=12`
- `EMBEDDING_DIM=1536`
- `RAG_EMBED_MODEL=openai:text-embedding-3-small`
- `RAG_SCORE_THRESHOLD=0.30`

## Model catalog

The current model catalog is stored in:
- `configs/models.yaml`

It defines:
- defaults
- models
- profiles
- routing
- scoring weights

### Default model choices
Current defaults:
- `chat_model: gpt-5.4-mini`
- `embedding_model: openai:text-embedding-3-small`

### Example profile routing
Current examples include:
- `plan.fast`
- `code.strict`
- `chat.cheap`
- `local.codegen`
- `cloud.codegen`

Current routing map includes:
- `idea -> plan.fast`
- `spec -> plan.fast`
- `plan -> plan.fast`
- `kit -> code.strict`
- `build -> code.strict`
- `finalize -> local.codegen`
- `chat -> chat.cheap`

## VS Code extension runtime settings

Current extension settings include:

### Core service URLs
- `clike.orchestratorUrl`
- `clike.gatewayUrl`

### Harper and chat
- `clike.docRoot`
- `clike.harperTimeout`
- `clike.optimizeFor`
- `clike.chat.persistDir`
- `clike.chat.never_send_source_to_cloud`
- `clike.chat.autoWriteGeneratedFiles`

### Execution
- `clike.execution.defaultPreference`
- `clike.execution.showInChat`

### Local agents
- `clike.localAgent.enabled`
- `clike.localAgent.preferredExecutor`
- `clike.localAgent.allowEval`
- `clike.localAgent.restrictToKitPhases`
- `clike.localAgent.timeoutMinutes`

### Claude Code
- `clike.claudeCode.enabled`
- `clike.claudeCode.command`
- `clike.claudeCode.printModeFlag`
- `clike.claudeCode.permissionMode`

### GPT Codex
- `clike.localAgent.codex.enabled`
- `clike.localAgent.codex.command`
- `clike.localAgent.codex.approvalMode`
- `clike.localAgent.codex.printModeFlag`

### Git
- `clike.git.autoCommit`
- `clike.git.gitMergeOnGate`
- `clike.git.gitDeleteBranchOnMerge`
- `clike.git.gitReturnToFeatureAfterMerge`
- `clike.git.remote`
- `clike.git.defaultBranch`
- `clike.git.branchPrefix`
- `clike.git.prBodyPath`

### MCP
- `clike.mcp.clientEnabled`
- `clike.mcp.serverEnabled`

## Local workspace assumptions

The current source tree assumes:
- repository root mounted under `/workspace`
- run artifacts under `/runs`
- docs under `docs/harper`
- source roots normally under `src`
- test roots normally under `tests`

The extension also expects:
- `.clike/project.json` for project metadata where present
- session persistence under `.clike/sessions` by default

## Health endpoints

Useful runtime checks:
- gateway: `GET /health`
- orchestrator: `GET /health`
- orchestrator Harper namespace: `GET /v1/harper/health`

## Startup guidance

A normal local startup sequence is:
1. start Qdrant
2. start Ollama
3. start Gateway
4. start Orchestrator
5. open the VS Code extension
6. fetch models and verify health from the extension
7. initialize or switch Harper project if needed

## Operational cautions

- The inspected package includes local absolute-volume assumptions for the author environment. Treat them as development-specific.
- Candidate artifacts are stored under `runs/kit/<REQ-ID>/...`; do not confuse them with promoted canonical roots.
- MCP is optional and mounted only when orchestrator-side enablement is active.
