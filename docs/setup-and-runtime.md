# Setup and Runtime

## Default local topology

The inspected `docker/docker-compose.yml` defines these services:

- `gateway` on `127.0.0.1:8000`
- `orchestrator` on `127.0.0.1:8080`
- `qdrant` on `127.0.0.1:6333`
- `eval-sandbox` — not published; executes eval/gate commands (see below)
- `ollama` on `127.0.0.1:11434` — optional, only with `--profile ollama`

All ports are published on loopback only. Set `CLIKE_PROJECTS_DIR` in `docker/.env`
(see `docker/.env.example`): it is mounted read-only at the same path and exposed as `DEV_FOLDER`.
The stack runs with Podman (`podman-compose`) or Docker Compose.

## Service startup model

### Gateway
Image command (Python 3.12, dependencies installed from `gateway/uv.lock`):
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Orchestrator
Image command (Python 3.12, dependencies from `orchestrator/uv.lock`, plus the
`eval-toolchain` group used by KIT LTC commands while eval runs in this container):
```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

Both services have compose healthchecks; the orchestrator starts after the gateway is healthy.
Both run as the non-root user `clike` (uid 1000).

### Mounts
- orchestrator: the CLike repo read-only at `/workspace` (including `.git`), writable only
  `src/` and `tests/` (generated code), `docker/runs` at `/app/runs`, configs read-only,
  the projects dir read-only at its host path.
- gateway: `configs` read-only, `telemetry` read-write, `gateway/stub` read-only, the
  projects dir read-only.
There is no `--reload` in containers: rebuild the images after code changes.

### Eval sandbox
`eval-sandbox` runs the LTC commands of eval/gate (they are authored by models during `/kit`).
It holds no credentials (it refuses to start if any are present), lives only on the dedicated
`evalnet` network (it cannot reach the gateway or Qdrant), runs non-root on a read-only root
filesystem with a tmpfs `/tmp`, all capabilities dropped and resource limits, and sees the
projects directory read-only. Egress is allowed so that dependency installs work; for offline
evaluation (dependencies already available) start the stack with:

```bash
podman-compose -f docker-compose.yml -f compose.eval-offline.yml up -d
```

Gate integrity state (acceptance locks, override audit log) lives in `docker/runs/state`.

### Ollama (optional)
Started only with `podman-compose --profile ollama up -d`; an init container ensures `nomic-embed-text` is present.

### Qdrant
Runs as the vector store backing RAG persistence.

## Main environment variables

### Shared (root `.env`, loaded by both services)
- `CLIKE_API_TOKEN` — **required** service token (`openssl rand -hex 32`); every endpoint except
  `/health` requires `Authorization: Bearer <token>`. Without it the services answer `503`.
- `CLIKE_ALLOWED_HOSTS` — optional override of accepted `Host` names
  (default `localhost,127.0.0.1,::1,gateway,orchestrator`).
- provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …).

### Compose (`docker/.env`)
- `CLIKE_PROJECTS_DIR` — host folder containing your projects; mounted read-only at the same path
  and exposed to the services as `DEV_FOLDER`. Eval/gate only operate on projects under it.

### Eval / gate (orchestrator)
- `DEV_FOLDER` — allowed root for eval/gate project roots (set from `CLIKE_PROJECTS_DIR`).
- `CLIKE_EVAL_SANDBOX_URL` — eval sandbox endpoint (compose: `http://eval-sandbox:8090`; unset = in-process).
- `CLIKE_STATE_DIR` — gate integrity state (compose: `/app/runs/state`).
- `CLIKE_EVAL_ALLOWED_ROOTS` — additional allowed roots (path-separator list).
- `CLIKE_ALLOW_INLINE_LTC` — `1` to accept inline-only LTC profiles (default: the workspace profile
  file is authoritative).

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
Automation is **off by default** (see [git-and-promotion.md](git-and-promotion.md)):
- `clike.git.autoCommit` (`false`) — commit only the files of each phase
- `clike.git.autoPush` (`false`, machine) — push commits, tags and gate merges
- `clike.git.gitMergeOnGate` (`false`) — merge the REQ branch after a PASS gate
- `clike.git.openPR` (`false`) — open a PR on `/finalize`
- `clike.git.pushRebase` (`false`)
- `clike.git.gitDeleteBranchOnMerge`, `clike.git.gitReturnToFeatureAfterMerge`
- `clike.git.remote`, `clike.git.remoteUrl`, `clike.git.defaultBranch`, `clike.git.branchPrefix`,
  `clike.git.tagPrefix`, `clike.git.conventionalCommits`, `clike.git.prBodyPath`

### Service authentication
- the service token is not a setting: run **CLike: Set Service Token** (stored in SecretStorage)

### MCP (extension operational server)
- `clike.mcp.extensionServerEnabled` (`false`)
- `clike.mcp.extensionServerHost` (`127.0.0.1`), `clike.mcp.extensionServerPort` (`55742`)
- `clike.mcp.extensionServerToken` — optional legacy override; by default a generated token in
  SecretStorage (*CLike: Copy Extension MCP Token*)

Security-relevant settings (service URLs, agent binaries/flags/permission and sandbox modes, MCP
server, Git remote/push/auto-commit) are **machine-scoped**: a workspace cannot override them.

## Local workspace assumptions

The current source tree assumes:
- repository root mounted read-only under `/workspace` (only `src/` and `tests/` writable)
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
1. configure `.env` (provider keys, `CLIKE_API_TOKEN`) and `docker/.env` (`CLIKE_PROJECTS_DIR`)
2. `cd docker && podman-compose up -d --build` (Qdrant, gateway, then orchestrator once the gateway
   is healthy; add `--profile ollama` for local models)
3. in VS Code run *CLike: Set Service Token*
4. open the CLike chat, fetch models and verify health from the extension
5. initialize or switch the Harper project if needed

After code changes: `podman-compose build && podman-compose up -d --force-recreate`.

## Operational cautions

- Projects must live under `CLIKE_PROJECTS_DIR`: eval/gate refuse other project roots (`403`).
- Candidate artifacts are stored under `runs/kit/<REQ-ID>/...`; do not confuse them with promoted canonical roots.
- MCP is optional and mounted only when orchestrator-side enablement is active.
