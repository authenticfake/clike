# API Reference

This document inventories the currently exposed HTTP API surfaces found in the inspected sources.

It is organized by runtime:
- Orchestrator
- Gateway
- Agent / code-action surface
- MCP informational surface

## Authentication

All orchestrator and gateway endpoints except `GET /health` require
`Authorization: Bearer <CLIKE_API_TOKEN>`. Missing or wrong token → `401`; token not configured on
the server → `503`; unexpected `Host` header → `403`. No CORS headers are emitted. The gateway
telemetry API also accepts the `clike_token` cookie set by `POST /v1/metrics/login` (GET only).

## Orchestrator API

Base runtime:
- FastAPI app in `orchestrator/app.py`
- default local port `8080`

### Health
#### `GET /health`
Basic orchestrator health endpoint.

#### `GET /v1/harper/health`
Harper namespace health endpoint.

### Harper control plane
Prefix:
- `/v1/harper`

#### `GET /v1/harper/version`
Returns orchestrator version info.

#### `GET /v1/harper/models`
Returns model list from loaded config.

#### `GET /v1/harper/models/defaults`
Returns default model/profile values for Harper UX.

#### `GET /v1/harper/profiles`
Returns available profile names.

#### `GET /v1/harper/routing/resolve`
Returns routing choice for a Harper task.

Query parameters used by current code:
- `task`
- `hint`
- `model`
- `provider`

#### `POST /v1/harper/session/clear`
Clears Harper chat session state by scope.

Current request model:
- `scope`: `singleModel | allModels`

#### `GET /v1/harper/runs/{run_id}`
Returns run bundle information for a given run ID.

#### `POST /v1/harper/idea`
Runs IDEA phase.

#### `POST /v1/harper/spec`
Runs SPEC phase.

#### `POST /v1/harper/plan`
Runs PLAN phase.

#### `POST /v1/harper/kit`
Runs KIT phase.

#### `POST /v1/harper/finalize`
Runs FINALIZE phase.

Current request model used by these phase endpoints:
- `cmd`
- `phase`
- `mode`
- `model`
- `profileHint`
- `executionPreference`
- `docRoot`
- `core`
- `attachments`
- `messages`
- `runId`
- `historyScope`
- `repository_context`
- `localAgentExecutor`
- `idea_md`
- `spec_md`
- `plan_md`
- `kit_md`
- `release_notes_md`
- `telemetry`
- `core_blobs`
- `workspace`
- `kit`
- `rag_strategy`
- `context_hard_limit`
- `project_id`
- `project_name`
- `rag_chunks`
- `rag_queries`
- `rag_top_k`
- `files`

### Legacy / generic orchestrator APIs

#### `GET /v1/models`
Lists models from legacy orchestrator surface.

#### `POST /v1/chat`
Legacy chat endpoint used by extension and helper flows.

#### `POST /v1/generate`
Legacy generation endpoint for coding / harper style generation.

#### ~~`POST /v1/apply`~~ (removed)
Removed in the 2026-10 hardening: it wrote request-supplied files to arbitrary paths.
The VS Code extension applies generated files locally (it is the only workspace writer).

### Router API

#### `GET /v1/router/resolve`
Shared routing resolution endpoint.

Current query parameters:
- `task`
- `hint`
- `model`
- `provider`

### RAG API
Prefix:
- `/v1/rag`

#### `POST /v1/rag/fetch`
Fetches RAG materials by query/path strategy.

#### `POST /v1/rag/fetch_by_paths`
Fetches docs directly by paths.

#### `POST /v1/rag/reindex`
Reindexes repository materials.

#### `POST /v1/rag/index`
Indexes repository or provided files into RAG.

#### `POST /v1/rag/search`
Searches indexed RAG materials.

#### `POST /v1/rag/purge`
Purges RAG documents by project and path prefix.

### Eval / gate API

#### `POST /v1/eval/run`
Runs eval against REQ-scoped candidate artifacts.

Current request fields accepted by the request model and query merge logic include:
- `profile`
- `project_root`
- `req_id`
- `mode`
- `verdict`
- `ltc`
- `project_name`

Confinement rules (also for `/v1/gate/check`):
- `project_root` must lie under `DEV_FOLDER` (the host projects dir, `CLIKE_PROJECTS_DIR` in compose)
  or under one of `CLIKE_EVAL_ALLOWED_ROOTS` (path-separator list); otherwise `403`.
  With neither configured, eval/gate are disabled.
- The LTC is read from the `profile` file under the project root, which is authoritative.
  An inline `ltc` is accepted only if identical to that file (`409` otherwise). An inline-only
  LTC (no file) is refused (`403`) unless `CLIKE_ALLOW_INLINE_LTC=1`.
- `profile` must stay inside the project root (`400` on traversal).
- Eval commands run without credentials in their environment (API keys, `CLIKE_API_TOKEN`
  and any `*KEY*`/`*TOKEN*`/`*SECRET*`/`*PASSWORD*`-style variables are removed).
- In containers the profile is executed by the `eval-sandbox` service (`CLIKE_EVAL_SANDBOX_URL`);
  responses carry `executor: "sandbox" | "local"`.
- **Acceptance integrity**: the REQ acceptance surface (`runs/kit/<REQ>/test/**` and `ci/**`) is
  locked server-side the first time it is evaluated after a KIT generation. If files were removed
  or modified, LTC checks removed/made non-blocking/changed, or skip markers added, eval and gate
  do not run (`reason_code` `ACCEPTANCE_TAMPERED` / `GATE_BLOCKED_ACCEPTANCE_TAMPERED`). Responses
  include an `integrity` object (`ok`, `anomalies`, `added`, `lock_digest`). A new `/kit`
  re-baselines the lock.
- `/v1/gate/check` rejects `mode=manual` (`400`): use `/v1/gate/override`.

#### `POST /v1/gate/override`
Developer override of a gate. Body: `project_root`, `project_name`, `req_id`, `reason`
(≥ 10 characters), `author`. The project root is confined like eval/gate. The override is appended
to an audit log (`CLIKE_STATE_DIR/audit/gate_overrides.jsonl`) with a digest of the REQ artifacts
and returned with `status: "OVERRIDE"` (never `PASS`), `gate: "pass"` (promotable) and an
`override` object (`audit_id`, `author`, `reason`, `at`, `artifacts`).

#### `POST /v1/gate/check`
Runs gate checks and promotion decisions.

Current request fields include:
- `profile`
- `project_root`
- `mode`
- `verdict`
- `req_id`
- `promote`
- `ltc`
- `project_name`

### Agent code-action API

#### `POST /agent/code`
Repository-file oriented AI action endpoint.

Current intent families visible in the route implementation:
- `docstring`
- `refactor`
- `tests`
- `fix`

Common request fields used by current implementation:
- `intent`
- `path`
- `text`
- `selection`
- `prompt`
- `language`
- `temperature`
- `max_tokens`
- `model`

## Gateway API

Base runtime:
- FastAPI app in `gateway/app.py`
- default local port `8000`

### Health

#### `GET /health`
Basic gateway health endpoint.

### Model catalog

#### `GET /v1/models`
Returns model catalog with alias-aware information.

#### `GET /v1/models/validate`
Returns model catalog validation information.

### Chat and completions

#### `POST /v1/chat/completions`
Main provider-routed chat endpoint.

Current request model includes:
- `model`
- `messages`
- `temperature`
- `max_tokens`
- `response_format`
- `tools`
- `tool_choice`
- `profile`
- `timeout`
- `provider`
- `base_url`
- `remote_name`
- `max_completion_tokens`
- `mode_contract`

### Embeddings

#### `POST /v1/embeddings`
Embeddings endpoint for provider-routed embedding requests.

Current request body is request-json driven and includes:
- `model`
- `input`

The route enforces:
- non-empty input
- size guard on oversized embedding input

### Harper execution

Prefix:
- `/v1/harper`

#### `POST /v1/harper/run`
Main Harper execution endpoint on the gateway.

Current request model includes:
- `project_id`
- `project_name`
- `cmd`
- `phase`
- `mode`
- `model`
- `profile`
- `profileHint`
- `docRoot`
- `core`
- `attachments`
- `messages`
- `flags`
- `runId`
- `historyScope`
- `idea_md`
- `spec_md`
- `plan_md`
- `todo_ids`
- `core_blobs`
- `gen`
- `workspace`
- `kit`
- `rag_strategy`
- `context_hard_limit`
- `rag_chunks`
- `rag_queries`
- `rag_top_k`
- `in_line_files`
- `rag_files`

The gateway route also contains logic for:
- Harper prompt composition
- plan JSON derivation
- candidate path enforcement
- RAG retrieval and injection
- telemetry writing
- provider-specific execution

### Telemetry API

Prefix:
- `/v1/metrics`

#### `GET /v1/metrics/harper/files`
Lists telemetry files.

#### `GET /v1/metrics/harper/projects`
Lists projects found in telemetry data.

#### `GET /v1/metrics/harper/aggregate`
Aggregate telemetry view.

#### `GET /v1/metrics/harper/series`
Series telemetry view.

#### `GET /v1/metrics/harper/top`
Top-file or top-project style telemetry view.

#### `GET /v1/metrics/harper/raw`
Raw telemetry view.

#### `GET /v1/metrics/harper/aggregate_file`
Aggregate-by-file view.

#### `GET /v1/metrics/harper/series_file`
Series-by-file view.

#### `GET /v1/metrics/harper/top_file`
Top-by-file view.

#### `GET /v1/metrics/harper/raw_file`
Raw-by-file view.

### Telemetry UI

#### `GET /v1/metrics/harper/ui`
Serves HTML telemetry UI.

## Agent surface summary

Although the agent route lives in the orchestrator runtime, it is conceptually its own file-oriented API surface.

Current characteristics:
- single endpoint: `POST /agent/code`
- file/path oriented
- code-action oriented
- not Harper-phase oriented
- uses gateway chat under the hood for compatible intents

## MCP informational surface

The orchestrator mounts MCP separately from REST.

Mount path:
- `/mcp`

Current exposed tools include:
- capability listing
- health
- model and profile listing
- route resolution
- Harper workflow explanation
- artifact explanation
- document reads
- plan reads
- REQ listing and retrieval
- kit preparation
- RAG search
- run listing and reading
- eval summary reading
- gate decision reading
- status reading

MCP is currently read-only and should not be treated as a writable or phase-executing API.
