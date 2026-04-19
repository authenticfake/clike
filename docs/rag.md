# RAG

## Overview

CLike currently supports repository-grounded RAG for Harper, coding, and free-mode use cases.

Main goals:
- reduce prompt bloat
- ground generation in project artifacts
- support large-file attachment workflows
- keep repository context searchable without pasting entire docs

## Main surfaces

### Extension
The extension supports:
- manual RAG commands
- inline vs RAG attachment strategy
- per-mode attachment buckets
- attachment reuse from search results

Relevant files:
- `extensions/vscode/chat-ui.js`
- `extensions/vscode/rag.js`

### Orchestrator
The orchestrator exposes RAG APIs under `/v1/rag/*`.

Relevant files:
- `orchestrator/routes/rag.py`
- `orchestrator/services/rag_store.py`

### Gateway
The gateway can consume RAG materials during Harper execution and also references RAG store utilities.

Relevant files:
- `gateway/routes/harper.py`
- `gateway/utils/rag_store.py`

## Current APIs

Current orchestrator RAG endpoints:
- `POST /v1/rag/fetch`
- `POST /v1/rag/fetch_by_paths`
- `POST /v1/rag/reindex`
- `POST /v1/rag/index`
- `POST /v1/rag/search`
- `POST /v1/rag/purge`

## Current extension commands

### Manual indexing
- `/ragIndex [glob]`

### Search
- `/ragSearch <query>`
- `/rag <query>`

### Attachment management
- `/rag +<N>`
- `/rag list`
- `/rag clear`

## Inline vs RAG attachments

The current codebase keeps a clear conceptual distinction.

### Inline attachments
Used when the extension decides to send raw content directly.

Best suited for:
- small files
- snippets
- compact prompt context

### RAG attachments
Used when files are indexed and passed by reference.

Best suited for:
- large documents
- multiple documents
- long-running Harper flows
- repository-grounded context reuse

## Extension-side RAG behavior

The extension-side helper `gatherRagChunks` currently reads from:
- `docs/harper/IDEA.md`
- `docs/harper/SPEC.md`

It chunks text heuristically by:
- headings
- bounded text size

This helper is lightweight and does not replace orchestrator/gateway RAG APIs.

## Current RAG decision parameters in runtime config

The runtime stack currently exposes threshold-style RAG tuning such as:
- `INLINE_MAX_FILE_KB`
- `INLINE_MAX_TOTAL_KB`
- `RAG_SIZE_THRESHOLD_KB`
- `RAG_TOP_K`
- `RAG_SCORE_THRESHOLD`

These values influence the boundary between:
- direct inline context
- retrieval-grounded context

## RAG project identity

The code uses project-aware or workspace-aware IDs for RAG namespaces.

Common concepts in current sources:
- `project_id`
- `project_name`
- `rag_namespace`
- workspace-derived defaults

## RAG in Harper flows

Harper requests can carry:
- `rag_strategy`
- `rag_chunks`
- `rag_queries`
- `rag_top_k`
- `rag_files`
- `in_line_files`
- attachments

This means RAG is not bolted on after the fact. It is part of the Harper request model.

## Fetch and search patterns

### Search
Search returns scored matches by path and chunk content.

### Fetch
Fetch endpoints support:
- generic retrieval
- targeted retrieval by paths
- reindex flows
- purge

## Current documentation rule

The current sources support documenting RAG as:
- implemented
- repository-grounded
- manually indexable
- used by Harper, coding, and free modes

The current sources do **not** justify documenting it as:
- fully automatic repo-wide continuous indexing by default
- a replacement for all inline attachments
- a guarantee that every attached file is automatically persisted in RAG
