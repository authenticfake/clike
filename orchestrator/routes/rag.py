# orchestrator/routes/rag.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from typing import List, Optional
import logging
import os, base64
import pydantic

from services.document_text import (  # shared with the project context sources
    _extract_text_from_docx_bytes,
    _extract_text_from_pdf_bytes,
    _extract_text_from_pptx_bytes,
    _extract_text_from_xls_bytes,
    _extract_text_from_xlsb_bytes,
    _extract_text_from_xlsx_bytes,
)
# Detect Pydantic major version once
try:
    _PYD_VER = int((getattr(pydantic, "__version__", "1.0.0").split(".")[0]) or "1")
except Exception:
    _PYD_VER = 1

# A small base that works on both Pydantic v1 and v2
if _PYD_VER >= 2:
    try:
        from pydantic import ConfigDict  # type: ignore
    except Exception:
        ConfigDict = dict  # fallback for type checkers
    class RagBase(BaseModel):
        model_config = ConfigDict(extra="ignore")  # v2 way
else:
    class RagBase(BaseModel):
        class Config:  # v1 way
            extra = "ignore"


from services.rag_store import RagStore

log = logging.getLogger("router.rag")

router = APIRouter()

class RagIndexItem(RagBase):
    path: str
    text: Optional[str] = None
    bytes_b64: Optional[str] = None

class RagIndexRequest(RagBase):
    project_id: str
    items: List[RagIndexItem]

class RagSearchRequest(RagBase):
    project_id: str
    query: str
    top_k: int = 8

class RagPurgeRequest(BaseModel):
    project_id: str
    path_prefix: Optional[str] = None
    # exact paths to delete (files gone from the workspace); used instead of path_prefix
    paths: Optional[List[str]] = None

# --- NEW: fetch models ---
class RagFetchRequest(RagBase):
    project_id: str
    # If given, restrict the fetch to these paths (case-insensitive "starts with" match)
    paths: Optional[List[str]] = None
    # Alternatively/additionally, filter by prefix
    path_prefix: Optional[str] = None
    # Maximum number of documents (paths) to return
    limit_docs: int = 20
    # Maximum characters per aggregated document (for prompt budget)
    max_chars_per_doc: int = 4000
    # How many chunks to pull from the store (overshoot: 5x documents)
    search_top_k: int = 100

class RagFetchByPathsRequest(RagBase):
    project_id: str
    paths: List[str]
    max_chars_per_doc: int = 4000
    search_top_k: int = 100
    


def _b64_to_bytes(b64: Optional[str]) -> Optional[bytes]:
    if not isinstance(b64, str) or not b64:
        return None
    try:
        # strip data URLs if present
        if b64.startswith("data:"):
            head, _, rest = b64.partition(",")
            b64 = rest
        return base64.b64decode(b64, validate=False)
    except Exception:
        return None

def _ext_from_path(p: str) -> str:
    try:
        return os.path.splitext((p or "").strip())[1].lower()
    except Exception:
        return ""
@router.post("/v1/rag/fetch")
async def rag_fetch(req: RagFetchRequest):
    store = RagStore(project_id=req.project_id)

    if req.paths:
        docs = await store.fetch_docs_by_paths(
            req.paths,
            max_chars_per_doc=max(500, req.max_chars_per_doc),
            limit_points=max(100, req.search_top_k),
        )
        docs = docs[: max(1, req.limit_docs)]
        return {"docs": docs, "count": len(docs)}

    if req.path_prefix:
        docs = await store.fetch_docs_by_prefix(
            req.path_prefix,
            max_chars_per_doc=max(500, req.max_chars_per_doc),
            limit_points=max(100, req.search_top_k),
            limit_docs=max(1, req.limit_docs),
        )
        return {"docs": docs, "count": len(docs)}

    raise HTTPException(400, detail="rag fetch requires explicit paths or path_prefix")

@router.post("/v1/rag/fetch_by_paths")
async def rag_fetch_by_paths(req: RagFetchByPathsRequest):
    store = RagStore(project_id=req.project_id)
    log.info("RAG fetch_by_paths project=%s paths=%d", req.project_id, len(req.paths or []))

    docs = await store.fetch_docs_by_paths(
        req.paths or [],
        max_chars_per_doc=max(500, req.max_chars_per_doc),
        limit_points=max(100, req.search_top_k),
    )
    return {"docs": docs, "count": len(docs)}


@router.post("/v1/rag/reindex")
async def rag_reindex(req: RagIndexRequest):
    return await rag_index(req)

@router.post("/v1/rag/index")
async def rag_index(req: RagIndexRequest):
    # store = RagStore(project_id=req.project_id)
    # log.info("RAG Store %s", store)
    # log.info("RAG index %d items", len(req.items))
    # out = await store.index_texts([it.dict() for it in req.items])
    # log.info("RAG out %s", out)
    # if not out.get("ok"):
    #     raise HTTPException(500, detail=out.get("error","index failed"))
    # return out
   
    store = RagStore(project_id=req.project_id)
    log.info("RAG Store for indexing - %d items", len(req.items))

    # Build normalized docs: always {"path":..., "text":...}
    docs = []
    for it in (req.items or []):
        p = (it.path or "").strip()
        txt = (it.text or "") if isinstance(it.text, str) else ""
        b64 = it.bytes_b64 or ""  # optional

        if not txt and b64:
            raw = _b64_to_bytes(b64)
            if raw:
                ext = _ext_from_path(p)
                if ext == ".pdf":
                    log.info("RAG index: PDF")
                    txt = _extract_text_from_pdf_bytes(raw)
                elif ext == ".docx":
                    log.info("RAG index: DOCX")
                    txt = _extract_text_from_docx_bytes(raw)
                elif ext == ".xlsx":
                    log.info("inline: XLSX")
                    txt = _extract_text_from_xlsx_bytes(raw)
                elif ext == ".xls":
                    log.info("inline: XLS (legacy)")
                    txt = _extract_text_from_xls_bytes(raw)
                elif ext == ".xlsb":
                    log.info("inline: XLSB")
                    txt = _extract_text_from_xlsb_bytes(raw)
                elif ext == ".pptx":
                    log.info("inline: PPTX")
                    txt = _extract_text_from_pptx_bytes(raw)
                else:
                    # fallback: if it is "raw" or unknown text, try decoding as utf-8
                    try:
                        txt = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        txt = ""
                
                log.info("RAG file %s -> %d chars", p, len(txt))

        if isinstance(txt, str) and txt.strip():
            docs.append({"path": p or "doc", "text": txt.strip()})

    if not docs:
        # no extractable text -> ok with empty (or raise 400 if preferred)
        log.info("RAG index: no indexable docs")
        return {"ok": True, "count": 0}

    try:
        out = await store.index_texts(docs)
    except Exception as e:
        log.warning(
            "RAG index skipped project=%s docs=%d error_type=%s error=%s",
            req.project_id,
            len(docs),
            type(e).__name__,
            str(e)[:500],
        )
        return {
            "ok": False,
            "skipped": True,
            "count": 0,
            "upserts": 0,
            "indexed_paths": 0,
            "error_type": type(e).__name__,
            "error": str(e)[:500],
        }

    log.info("RAG out %s", out)
    if not out.get("ok"):
        return {
            "ok": False,
            "skipped": True,
            "count": 0,
            "upserts": 0,
            "indexed_paths": 0,
            "error": out.get("error", "index failed"),
        }
    return out


@router.post("/v1/rag/search")
async def rag_search(req: RagSearchRequest):
    store = RagStore(project_id=req.project_id)
    hits = await store.search(req.query, top_k=req.top_k)
    return {"hits": hits}

class RagSourcesRequest(BaseModel):
    project_id: str


@router.post("/v1/rag/sources")
async def rag_sources(req: RagSourcesRequest):
    """Indexed paths with their chunk counts (Memory panel); an unreachable store is reported, not raised."""
    try:
        return {"ok": True, **(await RagStore(project_id=req.project_id).sources())}
    except Exception as e:
        log.warning("RAG sources failed project=%s error=%s", req.project_id, str(e)[:300])
        return {"ok": False, "sources": [], "total_chunks": 0, "error": str(e)[:300]}

@router.post("/v1/rag/purge")
async def rag_purge(req: RagPurgeRequest):
    store = RagStore(project_id=req.project_id)
    if req.paths:
        return await store.purge_paths(req.paths)
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
