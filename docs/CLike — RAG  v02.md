# CLike — Retrieval Augmented Generation (RAG)

CLike uses RAG to give models trustworthy, up-to-date context without pasting huge files into prompts. With RAG you can:

- **Index** files and folders on demand (manual, opt-in).
- **Search** and fetch relevant chunks at runtime (Free, Coding, Harper).
- **Attach** RAG references to requests without hitting token limits.
- **Reduce hallucinations** by grounding generations in your repository.

> Current status: **Manual indexing** via the `/ragIndex …` chat command and the Orchestrator APIs `POST /v1/rag/index` and `POST /v1/rag/search`.

---

## 1) Core concepts

- **Inline vs RAG attachments**  
  - *Inline attachments*: you send the full file content in the request (good for small files/snippets).  
  - *RAG attachments*: you send **references** to content you already indexed (best for large and/or many files).
- **Chunking**: indexed files are split into overlapping chunks and stored in a **collection** (Qdrant).
- **Tags**: free labels (e.g., `spec`, `plan`, `sdk`, `api`, `design`) to filter retrieval.
- **Namespace / project**: documents are associated with the current CLike workspace (data isolation).
- **Dedupe / Upsert**: re-indexing updates existing entries instead of creating duplicates.

---

## 2) When to use RAG

- **Harper**: IDEA/SPEC with long attachments (architecture PDFs, internal standards, API docs).
- **Coding**: codegen guided by references (SDKs, style guides, endpoint examples).
- **Free**: Q&A grounded on private documentation.

**Rule of thumb:** small files → *inline*; large / many files → **/ragIndex** then attach via RAG.

---

## 3) Supported flows

### 3.1 Manual indexing from chat
```

/ragIndex --path docs/harper
/ragIndex --path path/to/folder --glob "\*\*/\*.md" --tags "spec,plan"

````
The extension shows a bubble summary (file and chunk counts, issues if any).

### 3.2 Attaching in chat
- In the **Files** panel you can attach files **Inline** (content) or **RAG** (reference).  
- In **Coding** / **Harper**, the Orchestrator retrieves relevant chunks and injects them into the prompt in a controlled way.

---

## 4) Orchestrator APIs (RAG)

> Default base URL: `http://localhost:8080`  
> Endpoints are implemented in `orchestrator/routes/rag.py` and `services/rag_store.py`.

### 4.1 `POST /rag/index`
Index or update documents.

**Request (JSON)**
```json
{
  "path": "docs/harper",
  "glob": "**/*.md",
  "tags": ["spec", "plan"],
  "namespace": "auto",
  "max_chunk_tokens": 800,
  "overlap_tokens": 120,
  "upsert": true,
  "dedupe": true
}
````

* `path`: file or directory (required if `files` is not provided).
* `glob`: optional glob (active when `path` is a directory).
* `tags`: array of labels to reuse in `search`.
* `namespace`: if `auto`, resolved from the current workspace/project.
* `max_chunk_tokens` / `overlap_tokens`: chunking parameters.
* `upsert`, `dedupe`: replace/update instead of duplicating.
* **Alternative (inline files):**

  ```json
  {
    "files": [
      { "path": "README.md", "content": "…", "tags": ["docs"] }
    ]
  }
  ```

**Response (200)**

```json
{
  "ok": true,
  "indexed_files": 12,
  "indexed_chunks": 94,
  "collection": "clike_default",
  "namespace": "my-project"
}
```

### 4.2 `POST /v1/rag/search`

Retrieve relevant chunks.

**Request (JSON)**

```json
{
  "query": "recurring payments and webhooks",
  "top_k": 8,
  "min_score": 0.25,
  "tags": ["api", "payments"],
  "namespace": "auto"
}
```

**Response (200)**

```json
{
  "ok": true,
  "matches": [
    {
      "path": "docs/payments/webhooks.md",
      "text": "…chunk text…",
      "score": 0.78,
      "tags": ["api", "payments"],
      "metadata": { "sha256": "…", "line_from": 220, "line_to": 320 }
    }
  ]
}
```

> The Orchestrator also calls `search` internally for Free/Coding/Harper when you attach **RAG files** (automatic, controlled injection).

---

## 5) Chat slash command: `/v1/index`

**Syntax**

```
/ragIndex --path <p> [--glob "<g>"] [--tags "<t1,t2>"]
```

* Shows a result bubble in the chat.
* Common errors: missing path, empty glob, chunker failures.

---

## 6) Integration with other features

* **Coding (tool-calls → files)**: when RAG context is attached, concise citations are added to the system prompt.
* **Harper**: RAG docs tagged `spec/plan` are prioritized during `/spec` and `/plan`.
* **History Scope**: affects which bubbles are shown (Model/All models) but does **not** change RAG state.

---

## 7) Limits & performance

* Prefer **/ragIndex** for files > \~200KB; keep *inline* for small MD/snippets.
* Keep **top\_k** between **5–12**; scores < 0.2 are rarely useful.
* Re-index after refactors/renames/major edits.

---

## 8) Security & privacy

* **Store**: Qdrant (local for dev; remote optional).
* **Redaction**: when using cloud models you can enable flags to avoid sending proprietary source; RAG chunks are already a curated subset.
* **Isolation**: project namespace prevents cross-leaks between workspaces.

---

## 9) Troubleshooting

* `404 path not found`: verify `path` and `glob`.
* `0 matches`: increase `top_k` or lower `min_score`; check your `tags`.
* Irrelevant matches: clean generated artifacts, exclude binaries/logs from the index.

---

## 10) Test plan

* **Index 01**: `POST /rag/index` on `docs/harper` (`*.md`) → `indexed_files > 0`.
* **Index 02**: re-index same path with `upsert:true` → no duplicates; stable `indexed_files`.
* **Search 01**: query with `tags:["spec"]` → `matches[].tags` contains `spec`.
* **Chat (Free)**: attach 1 RAG file, ask a question → answer quotes correct portions.
* **Coding**: attach 2 RAG files, ask “generate Go client for these endpoints” → files align with the docs.
* **Harper**: `/spec` with RAG (API docs) → SPEC uses the correct terminology.

---

## 11) FAQ

**Q: Can I automate indexing?**
A: Yes, but we currently recommend **manual** via `/ragIndex` for maximum control.

**Q: Can I index PDFs?**
A: Yes, provided the Orchestrator has a text extractor; scanned PDFs need OCR first.
