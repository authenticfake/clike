# RAG_GUIDE — Retrieval-Augmented Generation

## Indexing
- Per-branch indexing; hybrid retrieval (BM25 + vectors); MD/code-aware chunking.
- Auto-refresh on commit; manual `/v1/rag/index`.

## Querying
- `/v1/rag/search` returns `hits[]` with `file`, `line`, `score`, `snippet`.
- Orchestrator passes `sources[]` back to UI for transparency.

## Quality
- Track groundedness/faithfulness; block Apply under thresholds (strict).
