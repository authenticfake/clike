# orchestrator/routes/rag.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

from services.rag_store import RagStore

log = logging.getLogger("rag")

router = APIRouter()

class RagIndexItem(BaseModel):
    path: str
    text: str

class RagIndexRequest(BaseModel):
    project_id: str
    items: List[RagIndexItem]  # file già letti lato estensione/BE

class RagSearchRequest(BaseModel):
    project_id: str
    query: str
    top_k: int = 6

class RagPurgeRequest(BaseModel):
    project_id: str
    path_prefix: Optional[str] = None

@router.post("/v1/rag/index")
async def rag_index(req: RagIndexRequest):
    store = RagStore(project_id=req.project_id)
    out = await store.index_texts([it.dict() for it in req.items])
    if not out.get("ok"):
        raise HTTPException(500, detail=out.get("error","index failed"))
    return out

@router.post("/v1/rag/search")
async def rag_search(req: RagSearchRequest):
    store = RagStore(project_id=req.project_id)
    hits = await store.search(req.query, top_k=req.top_k)
    return {"hits": hits}

@router.post("/v1/rag/purge")
async def rag_purge(req: RagPurgeRequest):
    store = RagStore(project_id=req.project_id)
    out = await store.purge(req.path_prefix)
    if not out.get("ok"):
        raise HTTPException(500, detail=out.get("error","purge failed"))
    return out

# --- RAG merging: client chunks + server search (Qdrant) --------------------

def _chunk_map_from_client(rag_chunks: dict) -> dict:
    """Crea un dizionario {(name, idx) -> text} dai rag_chunks client."""
    cmap = {}
    for ch in (rag_chunks or []):
        name = (ch.get("name") or "").strip()
        idx  = ch.get("idx")
        txt  = (ch.get("text") or "").strip()
        if not name or idx is None or not txt:
            continue
        cmap[(name, int(idx))] = txt
    return cmap
