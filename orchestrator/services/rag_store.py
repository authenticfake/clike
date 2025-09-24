# orchestrator/services/rag_store.py
# Lightweight RAG service: chunk, embed, upsert/search su Qdrant
# Riusa models.yaml per scegliere il modello embeddings preferito

from __future__ import annotations
import os, re, json, time, hashlib, logging
from typing import List, Dict, Any, Optional, Tuple
import httpx

log = logging.getLogger("rag")

# Config base (env + default)
QDRANT_URL  = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QCOLLECTION = os.getenv("QDRANT_COLLECTION", "clike_rag")
EMB_DIM     = int(os.getenv("EMBEDDING_DIM", "1536"))  # default openai small
CHUNK_TOKENS   = int(os.getenv("RAG_CHUNK_TOKENS", "800"))
CHUNK_OVERLAP  = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))
TOP_K          = int(os.getenv("RAG_TOP_K", "6"))
MAX_CTX_TOKENS = int(os.getenv("RAG_MAX_CTX_TOKENS", "1800"))

# Alcune estensioni testuali
TEXT_EXTS = {".md",".txt",".rst",".adoc",".py",".js",".ts",".tsx",".jsx",".java",".go",".rs",".cpp",".c",".h",".sql",".yml",".yaml",".json",".toml",".ini",".proto",".sh",".ps1",".rb",".php",".cs",".kt"}

def _norm_path(p: str) -> str:
    return re.sub(r"[\\]+", "/", (p or "").strip())

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def _split_chunks(text: str, tokens:int=CHUNK_TOKENS, overlap:int=CHUNK_OVERLAP) -> List[str]:
    # Grezzo: spezza per paragrafi/righe con overlap su caratteri
    if not text: return []
    unit = max(500, tokens*4)  # approx char per token
    step = max(256, overlap*4)
    out = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i+unit)
        out.append(text[i:j])
        if j == n: break
        i = max(i + unit - step, i+1)
    return out

class EmbeddingClient:
    """
    Cliente embeddings “compatibile”. Sceglie provider dal gateway se presente
    o cade su OpenAI text-embedding-3-small (se OPENAI_API_KEY è disponibile).
    Altrimenti usa un fallback grezzo (hash) per non bloccare.
    """
    def __init__(self, gateway_base: str = "http://gateway:8000/v1"):
        self.base = gateway_base.rstrip("/")
        self.openai_key = os.getenv("OPENAI_API_KEY")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        # 1) prova via gateway /v1/embeddings (se presente)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(f"{self.base}/embeddings", json={"input": texts})
                if r.is_success:
                    data = r.json()
                    vecs = [d["embedding"] for d in (data.get("data") or []) if "embedding" in d]
                    if vecs: return vecs
        except Exception:
            pass
        # 2) prova OpenAI diretto se key presente
        if self.openai_key:
            try:
                headers = {"Authorization": f"Bearer {self.openai_key}"}
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post("https://api.openai.com/v1/embeddings",
                        headers=headers,
                        json={"model":"text-embedding-3-small","input":texts})
                    r.raise_for_status()
                    data = r.json()
                    return [d["embedding"] for d in data.get("data") or []]
            except Exception:
                pass
        # 3) fallback dummy (hash → sparse float) per non bloccare
        log.warning("RAG embeddings fallback: using hash-based embeddings")
        out = []
        for t in texts:
            h = hashlib.sha256((t or "").encode("utf-8","ignore")).digest()
            vec = [x/255.0 for x in h[:128]]  # finto vettore
            # pad a EMB_DIM
            if len(vec) < EMB_DIM:
                vec = vec + [0.0]*(EMB_DIM - len(vec))
            out.append(vec[:EMB_DIM])
        return out

class RagStore:
    def __init__(self, project_id: str):
        # project_id → namespace: multi-progetto nello stesso Qdrant
        self.namespace = ("proj_" + re.sub(r"[^a-zA-Z0-9_]+","_", project_id or "default")).lower()
        self.q = QDRANT_URL
        self.c = f"{QCOLLECTION}__{self.namespace}"
        self.emb = EmbeddingClient()

    async def ensure(self) -> None:
        # crea collection se non esiste
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{self.q}/collections/{self.c}")
                if r.is_success:
                    return
                # create
                body = {
                    "vectors": {"size": EMB_DIM, "distance": "Cosine"},
                    "on_disk_payload": True,
                }
                r = await client.put(f"{self.q}/collections/{self.c}", json=body)
                r.raise_for_status()
                log.info("RAG created collection %s", self.c)
        except Exception as e:
            log.error("RAG ensure failed: %s", e)
            raise

    async def index_texts(self, items: List[Dict[str,Any]]) -> Dict[str,Any]:
        """
        items: [{path, text}]  (contenuti già estratti)
        """
        await self.ensure()
        points = []
        id_auto = int(time.time()*1000)
        texts = []
        metas = []
        # chunk → embed
        for it in items:
            p = _norm_path(it.get("path") or "unknown")
            t = it.get("text") or ""
            chunks = _split_chunks(t)
            for idx, ch in enumerate(chunks):
                meta = {"path": p, "sha": _sha1(t), "chunk": idx}
                texts.append(ch)
                metas.append(meta)
        if not texts:
            return {"ok": True, "upserts": 0}

        vecs = await self.emb.embed(texts)
        # compose points
        for i,(v,m) in enumerate(zip(vecs, metas)):
            points.append({
                "id": id_auto + i,
                "vector": v,
                "payload": m
            })
        # upsert
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                body = {"points": points}
                r = await client.put(f"{self.q}/collections/{self.c}/points", json=body)
                r.raise_for_status()
            return {"ok": True, "upserts": len(points)}
        except Exception as e:
            log.error("RAG upsert failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def search(self, query: str, top_k:int=TOP_K) -> List[Dict[str,Any]]:
        await self.ensure()
        # embed query
        vec = (await self.emb.embed([query]))[0]
        # search
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                body = {"vector": vec, "limit": top_k, "with_payload": True}
                r = await client.post(f"{self.q}/collections/{self.c}/points/search", json=body)
                r.raise_for_status()
                data = r.json()
                out = []
                for it in (data.get("result") or []):
                    pl = it.get("payload") or {}
                    out.append({
                        "path": pl.get("path",""),
                        "chunk": pl.get("chunk",0),
                        "score": it.get("score",0.0)
                    })
                return out
        except Exception as e:
            log.error("RAG search failed: %s", e)
            return []

    async def purge(self, path_prefix: Optional[str]=None) -> Dict[str,Any]:
        await self.ensure()
        # delete by filter
        payload_filter = {}
        if path_prefix:
            payload_filter = {"must": [{"key":"path","match":{"value":path_prefix}}]}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                body = {"filter": payload_filter} if payload_filter else {}
                r = await client.post(f"{self.q}/collections/{self.c}/points/delete", json=body)
                r.raise_for_status()
            return {"ok": True}
        except Exception as e:
            log.error("RAG purge failed: %s", e)
            return {"ok": False, "error": str(e)}
