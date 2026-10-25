"""RAG indexing: batched embeddings, unchanged files skipped. No network, no LLM."""
import asyncio

from services import rag_store
from services.rag_store import EMB_DIM, EmbeddingClient, RagStore


def test_embed_sends_batches_and_keeps_the_order(monkeypatch):
    monkeypatch.setenv("RAG_EMBED_BATCH_SIZE", "3")
    calls = []

    async def fake_batch(self, client, texts):
        calls.append(list(texts))
        return [[float(int(t))] * EMB_DIM for t in texts]

    monkeypatch.setattr(EmbeddingClient, "_embed_batch_gateway", fake_batch)
    vecs = asyncio.run(EmbeddingClient().embed([str(i) for i in range(7)] + ["  "]))
    assert [len(c) for c in calls] == [3, 3, 1]
    assert [v[0] for v in vecs] == [float(i) for i in range(7)]


def test_unchanged_files_are_not_embedded_again(monkeypatch):
    store = RagStore("p")
    embedded, deleted_paths, upserted = [], [], []

    async def ensure(self):
        return None

    async def unchanged(self, per_path):
        return {"docs/same.md"}

    async def embed(self, texts):
        embedded.extend(texts)
        return [[0.0] * EMB_DIM for _ in texts]

    class Resp:
        status_code = 200
        is_success = True
        text = ""

        def raise_for_status(self):
            return None

    async def request(client, method, url, json_body=None, attempts=1):
        if url.endswith("/points/delete?wait=true"):
            deleted_paths.extend(c["match"]["value"] for c in json_body["filter"]["should"])
        else:
            upserted.extend(json_body["points"])
        return Resp()

    monkeypatch.setattr(RagStore, "ensure", ensure)
    monkeypatch.setattr(RagStore, "_unchanged_paths", unchanged)
    monkeypatch.setattr(EmbeddingClient, "embed", embed)
    monkeypatch.setattr(rag_store, "_request_with_retry", request)
    out = asyncio.run(store.index_texts([
        {"path": "docs/same.md", "text": "unchanged content"},
        {"path": "docs/new.md", "text": "new content"},
    ]))
    assert embedded == ["new content"]
    assert deleted_paths == ["docs/new.md"]
    assert {p["payload"]["path"] for p in upserted} == {"docs/new.md"}
    assert out["unchanged_paths"] == 1 and out["indexed_paths"] == 1


def test_sources_lists_every_indexed_path_with_its_chunks(monkeypatch):
    # the Memory panel lists what the project and the CLike guide hold
    pages = [
        {"points": [{"payload": {"path": "docs/harper/SPEC.md"}}, {"payload": {"path": "docs/harper/SPEC.md"}}], "next_page_offset": "p2"},
        {"points": [{"payload": {"path": "runs/kit/REQ-001/src/a.py"}}, {"payload": {}}], "next_page_offset": None},
    ]
    bodies = []

    async def ensure(self):
        return None

    class Resp:
        def __init__(self, result):
            self._result = result

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": self._result}

    async def request(client, method, url, json_body=None, attempts=1):
        assert url.endswith("/points/scroll") and json_body["with_vector"] is False
        bodies.append(dict(json_body))
        return Resp(pages[len(bodies) - 1])

    monkeypatch.setattr(RagStore, "ensure", ensure)
    monkeypatch.setattr(rag_store, "_request_with_retry", request)
    out = asyncio.run(RagStore("p").sources())
    assert out == {
        "sources": [{"path": "docs/harper/SPEC.md", "chunks": 2}, {"path": "runs/kit/REQ-001/src/a.py", "chunks": 1}],
        "total_chunks": 3,
    }
    assert "offset" not in bodies[0] and bodies[1]["offset"] == "p2"
