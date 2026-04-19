# MCP

## Overview

The orchestrator currently exposes a **read-only MCP server** based on FastMCP.

Relevant file:
- `orchestrator/mcp_server.py`

Mount logic:
- mounted at `/mcp`
- mounted only when `CLIKE_MCP_SERVER_ENABLED=true`
- mounted from the orchestrator app

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
- raw provider proxying
- UI or session mutation

This restriction is important and should remain explicit in official docs.

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
- read-only tool exposure
- path-safe reads
- explicit exclusions
- no execution side effects

Official docs should preserve this conservative positioning until the codebase intentionally expands the MCP contract.
