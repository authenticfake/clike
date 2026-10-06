# MCP

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

### Run artifacts
- `runs_list`
- `runs_read`
- `eval_read_summary`
- `gate_read_decision`

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

Registering it in an MCP client, e.g. Claude Code:

```bash
claude mcp add --transport http clike http://127.0.0.1:8080/mcp/ --header "Authorization: Bearer $CLIKE_API_TOKEN"
```

## Extension operational MCP server

The VS Code extension can expose a second, **operational** MCP-compatible server that lets agents
operate CLike through the same slash commands available in chat (see
[agent-operating-model.md](agent-operating-model.md), Model 2). Typical tools:
`clike_extension_status`, `harper_next_action`, `harper_run_phase`, `harper_kit_next`,
`harper_continue_loop`, `rag_reindex`, `rag_docs_status`, `rag_docs_reindex_if_empty`.
It dispatches normal commands (`/kit REQ-001`, `/eval REQ-001`, `/gate REQ-001`, `/finalize`, …) and
does not duplicate Harper logic.

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

The current code is aligned with a conservative MCP posture:
- token-protected (orchestrator: service token; extension: dedicated token)
- read-only tool exposure (orchestrator server)
- path-safe reads
- explicit exclusions
- no execution side effects

Official docs should preserve this conservative positioning until the codebase intentionally expands the MCP contract.


## Using CLike from Claude Code and Codex (H2)

- **Orchestrator MCP** (read-only, `http://127.0.0.1:8080/mcp/`): the `harper_*` read tools accept
  `project_root` (a project under `CLIKE_PROJECTS_DIR`).
- **Extension MCP** (operational, `http://127.0.0.1:55742/mcp`, VS Code open):
  `harper_run_phase{phase, req_id?, wait_seconds?, await?}`, `eval_run{req_id, fix?, hint?}`,
  `gate_check{req_id}`, `harper_run_status{run_id}`, plus status/next-action/RAG tools. Phases run
  through the chat's governed handlers and the tools return their outcome; a run longer than
  `wait_seconds` (default 50) returns `status: running` and a `run_id`.

Setup commands: [INSTALL §6](INSTALL.md#6-use-clike-from-claude-code-or-codex-mcp).
