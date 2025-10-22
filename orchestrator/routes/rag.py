# orchestrator/routes/rag.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic import BaseModel

from typing import List, Dict, Any, Optional
import logging
import io, os, base64
from pdfminer.high_level import extract_text  # import INSIDE to avoid import warning at module load

import docx
import pydantic
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
# --- ADD: extraction helpers ---
def _extract_text_from_pdf_bytes(raw: bytes) -> str:
    # pdfminer.six
    try:
        return extract_text(io.BytesIO(raw)) or ""
    except Exception as e:
        log.warning("PDF extract failed: %s", e)
        return ""
    


def _extract_text_from_docx_bytes(raw: bytes) -> str:
    # python-docx
    try:
        doc = docx.Document(io.BytesIO(raw))
        parts = []
        # paragraphs
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if t:
                parts.append(t)
        # tables (cells)
        for tbl in getattr(doc, "tables", []):
            for row in tbl.rows:
                for cell in row.cells:
                    t = (cell.text or "").strip()
                    if t:
                        parts.append(t)
        return "\n".join(parts)
    except Exception as e:
        log.warning("DOCX extract failed: %s", e)
        return ""

@router.post("/v1/rag/reindex")
async def rag_index(req: RagIndexRequest):
    return rag_index(req)

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
    log.info("RAG Store %s", store)
    log.info("RAG index %d items", len(req.items))

    # Costruisci docs normalizzati: sempre {"path":..., "text":...}
    docs = []
    for it in (req.items or []):
        p = (it.path or "").strip()
        txt = (it.text or "") if isinstance(it.text, str) else ""
        b64 = it.bytes_b64 or ""  # opzionale

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
                else:
                    # binari non supportati qui -> salta
                    txt = ""
                log.info("RAG file %s -> %d chars", p, len(txt))

        if isinstance(txt, str) and txt.strip():
            docs.append({"path": p or "doc", "text": txt.strip()})

    if not docs:
        # nessun testo estraibile -> ok a vuoto (oppure alza 400 se preferisci)
        log.info("RAG index: no indexable docs")
        return {"ok": True, "count": 0}

    out = await store.index_texts(docs)
    log.info("RAG out %s", out)
    if not out.get("ok"):
        raise HTTPException(500, detail=out.get("error", "index failed"))
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
