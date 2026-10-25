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

### Orchestrator
The orchestrator exposes RAG APIs under `/v1/rag/*`.

Relevant files:
- `orchestrator/routes/rag.py`
- `orchestrator/services/rag_store.py` (Qdrant store, embeddings through the gateway)
- `orchestrator/services/document_text.py` (office/PDF text extraction, shared with the context sources)

Indexing is batched and incremental: chunks are embedded in batches (`RAG_EMBED_BATCH_SIZE`,
default 64, `RAG_EMBED_CONCURRENCY` 4 calls at a time) and files whose content is already indexed
are skipped (point ids derive from path + content).

### Gateway
The gateway can consume RAG materials during Harper execution. It is a client of the orchestrator
`/v1/rag` API (no store of its own); its `/v1/embeddings` accepts a list input and returns one
vector per item.

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
- `POST /v1/rag/sources` — every indexed path with its chunk count (the Memory panel lists)

## Memory panel

**CLike: Memory** (or **🧠 Memory** in the chat, every layout) opens a panel of its own next to the
chat. It holds two memories:

- **Project**: what CLike indexed for the workspace — Harper documents, the KITs of the REQs (after
  `/kit` and `/eval`), eval and gate reports, files attached in the chat.
- **CLike Guide**: CLike's own documentation, shipped inside the extension in its own collection
  (`clike-guide`). At every start CLike checks what the memory holds: a guide missing (e.g. an
  emptied store) or changed by a new version is indexed; a guide already there is left alone.

Ask in natural language, in any language (the search is semantic): each result is a file with the
lines that answer — the question's words highlighted — and a link to open it. The semantic ranking is
refined by the question's exact words, weighted by how rare they are among the candidates (`--accept`
counts, `how` does not); words no candidate contains, e.g. of another language, change nothing. On the left, **Contents** lists what each memory holds
(by group, with a filter) and **Recent searches** repeats a search with a click.

The chat and the Memory panel do not exchange anything: **💬 Chat** in the panel and **🧠 Memory** in
the chat only open the other panel, or bring it to the front. Files reach the memory from the chat
(📎 Attach); the panel lists them.

### The project memory follows the KITs

The KIT of a REQ is indexed after `/kit` and after `/eval`, without hidden folders (`ci/.tmp`
copies of the workspace, caches). Right after, the memory drops that REQ's files the KIT no longer
has, and files in hidden folders of any KIT indexed by earlier versions (unless the KIT reached the
indexing cap, when the files past it are still in the KIT).

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

The extension no longer chunks Harper documents itself (its `rag.js` helper was removed in 1.0.0):
indexing and retrieval go through the orchestrator `/v1/rag/*` APIs.

Project inputs that every phase should read (requirements, UI references, release folders
`docs/inputs/vN/`, `docs/reference/vN/`) can be declared as context sources instead
(`.clike/context.yaml`, see `context-sources.md`): they are delivered whole to the phases that
read them, not retrieved by similarity.

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
