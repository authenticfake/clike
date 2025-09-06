from fastapi import APIRouter, Request, HTTPException
from services.utils import maybe_qdrant, RAG_COLL, simple_embed
from qdrant_client.http.models import VectorParams, Distance, PointStruct
import os

router = APIRouter()

@router.post("/rag/reindex")
async def rag_reindex(req: Request):
    b = await req.json()
    path = b.get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(400, "valid path required")
    client = maybe_qdrant()
    if not client:
        return {"ok": False, "error": "qdrant not available"}

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    step = 600
    chunks = [(i//step, text[i:i+step]) for i in range(0, len(text), step)]
    try:
        client.get_collection(RAG_COLL)
    except Exception:
        client.recreate_collection(RAG_COLL, vectors_config=VectorParams(size=256, distance=Distance.COSINE))
    points = []
    for idx, chunk in chunks:
        vec = simple_embed(chunk)
        points.append(PointStruct(id=idx, vector=vec, payload={"path": path, "offset": idx, "text": chunk}))
    client.upsert(RAG_COLL, points=points)
    return {"ok": True, "chunks": len(points)}

@router.post("/rag/search")
async def rag_search(req: Request):
    b = await req.json()
    query = b.get("q") or b.get("query") or ""
    if not query:
        raise HTTPException(400, "q required")
    client = maybe_qdrant()
    if not client:
        return {"ok": False, "error": "qdrant not available"}
    vec = simple_embed(query)
    res = client.search(RAG_COLL, query_vector=vec, limit=5)
    hits = [{"id": r.id, "score": r.score, "payload": r.payload} for r in res]
    return {"ok": True, "hits": hits}
