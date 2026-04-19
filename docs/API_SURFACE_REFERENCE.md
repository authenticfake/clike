# CLike — API Surface Reference

**Scope:** current API census for the CLike VS Code extension, Orchestrator, Gateway, RAG, Eval/Gate, Git, local-agent, and MCP surfaces.

---

## 1) Orchestrator HTTP APIs

### Health and metadata

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Basic orchestrator health. |
| `GET` | `/version` | Harper route version metadata. |
| `GET` | `/models` | Models visible through orchestrator/gateway integration. |
| `GET` | `/models/defaults` | Default model/profile metadata. |
| `GET` | `/profiles` | Available model routing profiles. |
| `GET` | `/routing/resolve` | Resolve a routing request. |
| `GET` | `/resolve` | Router compatibility endpoint. |
| `POST` | `/session/clear` | Clear a session scope. |
| `GET` | `/runs/{run_id}` | Read a run bundle or run metadata. |

### General chat/code actions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/models` | v1 model list compatibility route. |
| `POST` | `/chat` | Chat route through orchestrator service layer. |
| `POST` | `/generate` | Coding/file-generation route. |
| `POST` | `/apply` | Apply generated patch/content. |
| `POST` | `/agent/code` | Editor code actions: docstring, refactor, tests, fix errors, new file style actions. |

### Harper phases

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/idea` | Generate/update `docs/harper/IDEA.md`. |
| `POST` | `/spec` | Generate/update `docs/harper/SPEC.md`. |
| `POST` | `/plan` | Generate/update `PLAN.md` and `plan.json`. |
| `POST` | `/kit` | Generate or harden REQ candidate artifacts; supports staged KIT phases. |
| `POST` | `/eval` | Harper eval pre-pass / local-agent diagnostic package route. |
| `POST` | `/finalize` | Generate final release/PR artifacts. |
| `POST` | `/local-agent/complete` | Normalize local-agent execution result and returned candidate artifacts. |

### Canonical eval/gate

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/eval/run` | Run canonical eval and produce normalized eval evidence. |
| `POST` | `/v1/gate/check` | Apply gate policy and produce gate decisions. |

### RAG

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/rag/index` | Index provided files or workspace path content into RAG. |
| `POST` | `/v1/rag/reindex` | Reindex workspace/project content. |
| `POST` | `/v1/rag/search` | Semantic search. |
| `POST` | `/v1/rag/fetch` | Fetch indexed docs by prefix/query constraints. |
| `POST` | `/v1/rag/fetch_by_paths` | Fetch indexed docs by explicit paths. |
| `POST` | `/v1/rag/purge` | Purge indexed RAG content. |

### Git helper routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/git/branch` | Branch helper. |
| `POST` | `/git/commit` | Commit helper. |
| `POST` | `/git/pr` | PR helper. |

### MCP

| Method | Path | Purpose |
|---|---|---|
| `MCP` | `/mcp` | Streamable HTTP MCP server mounted by the Orchestrator when enabled. |

---

## 2) Gateway HTTP APIs

### Health and models

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Gateway health. |
| `GET` | `/v1/models` | Model catalog. |
| `GET` | `/v1/models/validate` | Validate configured model catalog. |

### Model IO

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat completions with provider routing. |
| `POST` | `/v1/embeddings` | Embeddings endpoint. |
| `POST` | `/run` | Gateway Harper run route; mounted prefix may expose this as `/v1/harper/run` through client configuration. |

### Telemetry

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/harper/ui` | Telemetry UI. |
| `GET` | `/harper/files` | Harper telemetry files. |
| `GET` | `/harper/projects` | Harper projects telemetry. |
| `GET` | `/harper/aggregate` | Aggregate telemetry. |
| `GET` | `/harper/series` | Time-series telemetry. |
| `GET` | `/harper/top` | Top telemetry dimensions. |
| `GET` | `/harper/raw` | Raw telemetry. |
| `GET` | `/harper/aggregate_file` | File-backed aggregate telemetry. |
| `GET` | `/harper/series_file` | File-backed series telemetry. |
| `GET` | `/harper/top_file` | File-backed top telemetry. |
| `GET` | `/harper/raw_file` | File-backed raw telemetry. |

---

## 3) VS Code Extension Commands

| Command | Purpose |
|---|---|
| `clike.openChat` | Open CLike chat. |
| `clike.harper.init` | Initialize Harper workspace docs/templates. |
| `clike.chat.clearSession` | Clear current model chat session. |
| `clike.chat.openSessionFile` | Open current model session JSONL. |
| `clike.ping` | Ping services. |
| `clike.codeAction` | Generic code action entrypoint. |
| `clike.addDocstring` | Generate docstring via Orchestrator. |
| `clike.refactor` | Refactor selected/current code. |
| `clike.generateTests` | Generate tests. |
| `clike.fixErrors` | Fix errors using AI. |
| `clike.applyUnifiedDiffHardened` | Apply unified diff with hardened path. |
| `clike.applyUnifiedDiff` | Apply unified diff. |
| `clike.applyNewContent` | Apply new content. |
| `clike.applyLastPatch` | Apply last patch. |
| `clike.listModels` | List models through Gateway. |
| `clike.checkServices` | Check service connectivity. |
| `clike.ragReindex` | RAG reindex through Orchestrator. |
| `clike.ragSearch` | RAG search through Orchestrator. |
| `clike.gitCreateBranch` | Create Git branch. |
| `clike.gitCommitPatch` | Commit patch. |
| `clike.gitOpenPR` | Open PR. |
| `clike.gitSmartPR` | Smart PR helper. |
| `clike.eval.runAll` | Run all evals. |
| `clike.gate.checkPhase` | Gate check for current phase. |
| `clike.constraints.sync` | Sync constraints from IDEA/SPEC. |
| `clike.plan.updateChecklist` | Update PLAN checklist from eval. |
| `clike.promoteReqSources` | Promote REQ source code. |
| `clike.promoteReqSourcesQuick` | Quick promote REQ source code. |

---

## 4) Chat Slash Commands

| Slash command | Purpose |
|---|---|
| `/idea` | Generate/update IDEA. |
| `/spec` | Generate/update SPEC. |
| `/plan` | Generate/update PLAN and plan JSON. |
| `/kit [REQ-ID]` | Generate/harden candidate artifacts for a REQ. |
| `/eval [REQ-ID]` | Run/prepare eval for a REQ. |
| `/gate [REQ-ID]` | Gate and promote a REQ when evidence passes. |
| `/finalize` | Generate final release artifacts. |
| `/ragIndex <glob-or-path>` | Index workspace content into RAG. |
| `/ragSearch <query>` | Search indexed RAG context. |
| `/agent-default codex|claude|auto` | Set preferred local-agent executor. |

---

## 5) Orchestrator MCP Tools

Mounted at `/mcp` when `CLIKE_MCP_SERVER_ENABLED=true`.

| Tool | Purpose |
|---|---|
| `clike_capabilities_list` | List Orchestrator MCP capabilities and non-exposed operations. |
| `clike_health_get` | Read orchestrator health/workspace roots. |
| `clike_models_list` | Read configured models. |
| `clike_profiles_list` | Read routing profiles. |
| `clike_routing_resolve` | Resolve model routing. |
| `clike_about` | Explain CLike. |
| `clike_harper_workflow_explain` | Explain Harper workflow. |
| `clike_artifacts_explain` | Explain canonical artifacts. |
| `harper_project_read_core` | Read core Harper docs. |
| `harper_doc_read` | Read a Harper doc. |
| `harper_plan_read` | Read plan JSON/plan state. |
| `harper_req_list` | List REQs. |
| `harper_req_get` | Get one REQ. |
| `harper_req_next` | Resolve next eligible REQ. |
| `harper_kit_prepare` | Prepare target contract, file requirements, and promotion manifests for a REQ. |
| `rag_search` | Search RAG. |
| `runs_list` | List run directories. |
| `runs_read` | Read a run bundle. |
| `eval_read_summary` | Read latest or selected eval summary. |
| `gate_read_decision` | Read latest or selected gate decision. |
| `harper_status_read` | Summarize Harper status. |
| `clike_operational_model_explain` | Explain Model 2: external agent interacts with extension MCP. |
| `rag_docs_status` | Check docs RAG availability. |
| `rag_reindex_docs` | Reindex docs into RAG. |
| `rag_reindex_docs_if_empty` | Reindex docs only if missing. |

---

## 6) Extension Operational MCP Tools

Default URL:

```text
http://127.0.0.1:55742/mcp
```

Supported JSON-RPC methods:

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

| Tool | Purpose |
|---|---|
| `clike_extension_status` | Read extension state, workspace, chat status, and next Harper action. |
| `harper_next_action` | Return next REQ or `finalize_only`. |
| `harper_run_phase` | Dispatch `/idea`, `/spec`, `/plan`, `/kit`, `/eval`, `/gate`, or `/finalize`. |
| `harper_kit_next` | Dispatch `/kit <next-REQ>`. |
| `harper_continue_loop` | Dispatch next `kit`, `eval`, or `gate`, or `/finalize` when all REQs are done. |
| `rag_reindex` | Reindex workspace files through extension collector. |
| `rag_docs_status` | Check docs RAG status. |
| `rag_docs_reindex_if_empty` | Reindex docs when missing. |

---

## 7) Security and Boundaries

- Orchestrator MCP is service/read-only and does not expose arbitrary shell, Git mutation, raw provider proxying, or direct phase execution.
- Extension MCP is operational but only dispatches normal CLike slash commands.
- Local agents are constrained by `AGENT_EXECUTION_CONTEXT.json`.
- Local agents must not run Git, promote files, or write outside allowed candidate roots.
- Canonical eval/gate remain CLike-owned.
