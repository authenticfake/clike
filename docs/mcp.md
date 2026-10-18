# MCP

> Step by step, from setup to a delivered project: [howto-mcp-project.md](howto-mcp-project.md).

## Overview

The orchestrator currently exposes a **read-only MCP server** based on FastMCP.

Relevant file:
- `orchestrator/mcp_server.py`

Mount logic:
- mounted at `/mcp`
- mounted only when `CLIKE_MCP_SERVER_ENABLED=true`
- mounted from the orchestrator app
- protected by the service token like every orchestrator endpoint: clients must send
  `Authorization: Bearer <CLIKE_API_TOKEN>` (HTTP 401 otherwise)

## Current MCP characteristics

The current MCP server should be documented as:

- **read-only**
- **streamable HTTP**
- **JSON responses**
- **stateless HTTP mode**
- **repository-aware**
- **Harper-aware**
- **RAG-aware**
- **run-artifact aware**

## What MCP is intentionally not

The current code explicitly excludes:
- phase execution
- Git mutation
- arbitrary shell
- arbitrary filesystem writes
- MCP write tools
- raw provider proxying
- UI or session mutation

This restriction is important and should remain explicit in official docs.

BMAD-aware methodology profiles do not change this boundary. Future MCP write tools are documented only as roadmap material in `docs/integrations/bmad/FUTURE_MCP_WRITE_TOOLS.md`.

## Current exposed MCP tools

Current tool inventory from `mcp_server.py`:

### Capability and health
- `clike_capabilities_list`
- `clike_health_get`

### Catalog and routing
- `clike_models_list`
- `clike_profiles_list`
- `clike_routing_resolve`

### Product / workflow explanation
- `clike_about`
- `clike_harper_workflow_explain`
- `clike_artifacts_explain`

### Harper docs and plan state
- `harper_project_read_core`
- `harper_doc_read`
- `harper_plan_read`
- `harper_req_list`
- `harper_req_get`
- `harper_req_next`
- `harper_kit_prepare`
- `harper_status_read`

### RAG
- `rag_search`
- `rag_docs_status`
- `rag_reindex_docs`, `rag_reindex_docs_if_empty` (index the project's `docs/` into RAG; they
  write the vector store, never the workspace)

### Run artifacts
- `runs_list`
- `runs_read`
- `eval_read_summary`
- `gate_read_decision`

### Operating model
- `clike_operational_model_explain`

## Authentication

The orchestrator MCP endpoint is protected by the service token like every orchestrator endpoint.
It uses streamable HTTP semantics, so manual calls need both `content-type` and `accept` headers
(otherwise HTTP `406`); without the token the response is `401`.

```bash
curl -s http://127.0.0.1:8080/mcp/ \
  -H "authorization: Bearer $CLIKE_API_TOKEN" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | jq
```

Registering it in an MCP client:

The token must reach the client as a header. With Claude Code, prefer a project `.mcp.json` that
reads it from the environment (safe to commit: no secret inside) and export `CLIKE_API_TOKEN` in
your shell before starting `claude`:

```json
{
  "mcpServers": {
    "clike": {
      "type": "http",
      "url": "http://localhost:8080/mcp/",
      "headers": { "Authorization": "Bearer ${CLIKE_API_TOKEN}" }
    }
  }
}
```

`claude mcp add --transport http clike http://localhost:8080/mcp/ --header "Authorization: Bearer $CLIKE_API_TOKEN"`
also works, but the shell expands the token when you add the server: with the variable unset it
stores an empty bearer, otherwise it writes the token into `~/.claude.json`. Use `localhost`, not
`127.0.0.1` (managed policies often allow only `http://localhost*`), and keep the trailing `/`.

**"Dynamic Client Registration rejected (HTTP 401)"** means the client reached CLike without the
header and tried OAuth: CLike has no OAuth (its `/.well-known/oauth-*` and `/register` answer 404) —
add the `Authorization` header as above.

## Extension operational MCP server

The VS Code extension can expose a second, **operational** MCP-compatible server that lets agents
operate CLike through the same slash commands available in chat (see
[agent-operating-model.md](agent-operating-model.md), Model 2). Typical tools:
`clike_extension_status`, `harper_next_action`, `harper_run_phase`, `harper_run_status`,
`cancel_run`, `eval_run`, `gate_check`, `harper_kit_next`, `harper_continue_loop`, `rag_reindex`,
`rag_docs_status`, `rag_docs_reindex_if_empty`.
It runs normal commands (`/kit REQ-001`, `/eval REQ-001 --fix`, `/gate REQ-001`, `/finalize`, …)
through the chat's governed handlers and does not duplicate Harper logic:

- `harper_run_phase {phase, req_id?, text?, attachments?, methodology?, agent?, extend?, release?, dry_run?,
  confirm?, wait_seconds?, await?}` covers `idea`, `spec`, `plan`, `kit`, `eval`, `gate`,
  `finalize`; `phase: "idea", extend: true` is `/idea --extend` (release inputs from
  `docs/inputs/vN/`).
- Every run gets a `run_id`; a run longer than `wait_seconds` (default 50, max 600 — keep it under
  your client's tool timeout, e.g. Codex `tool_timeout_sec`) returns `status: running`, then
  `harper_run_status` tells its end and `cancel_run` stops it. Only one phase runs at a time.
- Nobody answers the chat's confirmations during an MCP run: `/finalize` with REQs not promoted,
  or `/idea --extend` on an undelivered baseline, stop with the reason unless `confirm: true`. A run
  that stops before doing anything says why (`reason`, last chat `messages`).
- `harper_next_action` returns the in-progress REQ, else the first open REQ whose dependencies are
  done, `blocked` when every open REQ waits for one, `finalize_only` when all are done.
- Streamable HTTP: notifications get `202`, `GET /mcp` is `405`, `ping` answers, the protocol
  version is negotiated; `/.well-known/oauth-*` and `/register` are `404` (no OAuth).

Because it can trigger phases that make local agents write files, it is locked down:

- **disabled by default** (`clike.mcp.extensionServerEnabled`);
- listens on `127.0.0.1` (`clike.mcp.extensionServerPort`, default `55742`);
- **always requires** `Authorization: Bearer <token>`: a random token is generated and kept in
  SecretStorage (copy it with *CLike: Copy Extension MCP Token*); `clike.mcp.extensionServerToken`
  is an optional legacy override;
- rejects any request carrying an `Origin` header (browsers), non-loopback `Host` headers or a
  different port, and non-JSON `POST` bodies.

## Current MCP usage model

The current MCP server is intended for:
- repository exploration
- Harper contract inspection
- artifact lookup
- RAG-backed contextual lookup
- run-state visibility
- plan and REQ inspection

It is **not** intended to replace the orchestrator HTTP APIs for:
- phase execution
- apply flows
- Git mutation
- chat UI control

## `harper_kit_prepare`

One of the most important MCP tools is `harper_kit_prepare(req_id)`.

It currently returns a read-only preparation bundle containing:
- target contract
- file requirements
- promotion manifest
- repo access manifest
- repo structure evidence
- repo composition manifest
- available core docs

This makes MCP useful as an informational surface for external agents or tools without granting mutation capability.

## Security posture

- Token-protected: orchestrator with the service token, extension with its own token; no OAuth
  (discovery paths answer 404 so clients report a missing header).
- Orchestrator server: read tools, except `rag_reindex_docs` / `rag_reindex_docs_if_empty`, which
  write the project's RAG index; no phase execution, no git, no file writes.
- Path-safe reads: `project_root` confined to `CLIKE_PROJECTS_DIR`; a `run_id` is a run directory
  name, never a path (`..`, `/`, CLike's `state/` are refused); `eval_read_summary` /
  `gate_read_decision` with `project_root` + `req_id` read that project's latest report.
- Extension server: loopback only, no browser origins, phases through the chat's governance
  (locked tests, gate, write rules, no overrides from MCP), one phase at a time.
- CLike's own Harper agent runs load no MCP server (Claude: `--strict-mcp-config`): the eval checks
  they need go through the file bridge, without token or network.


## Using CLike from Claude Code and Codex (H2)

- **Orchestrator MCP** (read-only, `http://localhost:8080/mcp/`): the `harper_*` read tools accept
  `project_root` (a project under `CLIKE_PROJECTS_DIR`).
- **Extension MCP** (operational, `http://localhost:55742/mcp`, VS Code open):
  `harper_run_phase{phase, req_id?, wait_seconds?, await?}`, `eval_run{req_id, fix?, hint?}`,
  `gate_check{req_id}`, `harper_run_status{run_id}`, plus status/next-action/RAG tools. Phases run
  through the chat's governed handlers and the tools return their outcome; a run longer than
  `wait_seconds` (default 50) returns `status: running` and a `run_id`. `eval_run` with `fix`
  returns the report of the **last** eval (after the repairs) plus
  `auto_eval {outcome: pass|stopped, cycles, reason}`.
- **Approvals:** Codex asks to approve each MCP call; set `default_tools_approval_mode = "approve"`
  for the CLike servers (they are governed by CLike), see INSTALL §6.

Setup commands: [INSTALL §6](INSTALL.md#6-use-clike-from-claude-code-or-codex-mcp).
