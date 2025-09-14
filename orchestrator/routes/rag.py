from fastapi import APIRouter, HTTPException
from services.utils import maybe_qdrant, RAG_COLL, simple_embed
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from qdrant_client import QdrantClient
from config import settings
from typing import Any, Dict, List


import os
# fallback robusto: prova prima embed_texts, poi embed_text
try:
    from embeddings import embed_texts as _embed_batch
except Exception:
    _embed_batch = None
try:
    from embeddings import embed_text as _embed_one
except Exception:
    _embed_one = None


router = APIRouter()

async def _ensure_vectors(texts: List[str], embed_model: str) -> List[List[float]]:
    if not texts:
        return []
    if "embed" not in embed_model.lower():
        raise HTTPException(400, f"embed_model '{embed_model}' does not look like an embedding model")
    if _embed_batch:
        return await _embed_batch(texts, model=embed_model)
    elif _embed_one:
        return [await _embed_one(t, model=embed_model) for t in texts]
    else:
        raise HTTPException(500, "embeddings backend not available")

async def index_path(client, path: str, pid_start: int, dims: int = 768) -> int:
    """Legge un file, lo spezza in chunk e lo inserisce in Qdrant."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return 0

    # chunk semplice riga per riga
    chunks = []
    buf, total = [], 0
    for line in text.splitlines():
        if total + len(line) > 800 and buf:
            chunks.append("\n".join(buf))
            buf, total = [line], len(line)
        else:
            buf.append(line)
            total += len(line)
    if buf:
        chunks.append("\n".join(buf))

    points, pid = [], pid_start
    
    for chunk in chunks:
        vec = await _embed_one(chunk)   # chiama Ollama embeddings
        if len(vec) != dims:
            # safety: se cambia modello a runtime, falliamo esplicitamente
            raise HTTPException(500, f"Embedding dims mismatch: expected {dims}, got {len(vec)}")
        points.append(PointStruct(id=pid, vector=vec, payload={"path": path, "snippet": chunk[:200]}))
        pid += 1

    if points:
        client.upsert(collection_name="clike_rag", points=points)
    return len(points)


def embed(text):
    dims=128; import numpy as np, hashlib
    v = np.zeros(dims, dtype=np.float32)
    for tok in text.split():
        h=int(hashlib.md5(tok.encode()).hexdigest(),16)%dims; v[h]+=1
    n=np.linalg.norm(v); 
    return (v/n).tolist() if n>0 else v.tolist()



async def reindex(body: Dict[str, Any]):
    base = body.get("base_dir",".")
    exts = body.get("exts", [".md",".ts",".tsx",".py",".go",".java"])
    
    docs: List[str] = body.get("documents") or body.get("docs") or []
    if not docs:
        raise HTTPException(400, "missing documents[]")

    embed_model = body.get("embed_model") or getattr(settings, "EMBED_MODEL", "nomic-embed-text")
    if "embed" not in embed_model.lower():
        raise HTTPException(400, f"embed_model '{embed_model}' does not look like an embedding model")

    client = maybe_qdrant()
    vectors = await _ensure_vectors(docs, embed_model)
    # 1) Rileva la dimensione direttamente dal modello embedding
    DIMS = len(vectors) if isinstance(vectors, list) else 768
    if DIMS <= 0:
        raise HTTPException(500, "Embedding provider returned empty vector")

    # 2) Ricrea SEMPRE la collezione con la dimensione corretta (idempotente)
    try:
        client.recreate_collection(
            collection_name=RAG_COLL,
            vectors_config=VectorParams(size=DIMS, distance=Distance.COSINE)
        )
    except Exception:
        pass
    pid = 1
    count = 0
    for dirpath, _, filenames in os.walk(base):
        for fn in filenames:
            if any(fn.endswith(e) for e in exts):
                p = os.path.join(dirpath, fn)
                count += await index_path(client, p, pid)  # usa embed_text(…) interno
                pid += 1000
    # >>> aggiungi provider e dims qui <<<
    return {
        "indexed": count,
        "provider": "ollama:nomic-embed-text",
        "dims": DIMS
    }

async def search(body: Dict[str, Any]):
    queries: List[str] = body.get("queries") or body.get("q") or []
    if not queries:
        raise HTTPException(400, "missing queries[]")

    embed_model = body.get("embed_model") or getattr(settings, "EMBED_MODEL", "nomic-embed-text")
    if "embed" not in embed_model.lower():
        raise HTTPException(400, f"embed_model '{embed_model}' does not look like an embedding model")

    qvecs = await _ensure_vectors(queries, embed_model)
    
    client = maybe_qdrant()
    if not client:
        return {"ok": False, "error": "qdrant not available"}
    res = client.search(RAG_COLL, query_vector=qvecs, limit=15)
    hits = [{"id": r.id, "score": r.score, "payload": r.payload} for r in res]
    return {"ok": True, "hits": hits}
