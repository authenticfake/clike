from __future__ import annotations
import os, re, json, time, hashlib, logging, uuid
import traceback
from typing import List, Dict, Any, Optional, Tuple
import httpx


def _rag_base_url(base_url: str | None = None) -> str:
    return (base_url or os.getenv("RAG_BASE_URL", "http://localhost:8080/v1/rag")).rstrip("/")


log = logging.getLogger("rag.store")

# Config base (env + default)
QDRANT_URL  = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QCOLLECTION = os.getenv("QDRANT_COLLECTION", "clike_rag")
EMB_DIM     = int(os.getenv("EMBEDDING_DIM", "1536"))
CHUNK_TOKENS   = int(os.getenv("RAG_CHUNK_TOKENS", "800"))
CHUNK_OVERLAP  = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))
TOP_K          = int(os.getenv("RAG_TOP_K", "12"))
MAX_CTX_TOKENS = int(os.getenv("RAG_MAX_CTX_TOKENS", "1800"))
MAX_EMBED_TEXT_CHARS = int(os.getenv("RAG_MAX_EMBED_TEXT_CHARS", "12000"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.30"))
def _default_embed_family() -> str:
    explicit = (os.getenv("RAG_EMBED_FAMILY") or "").strip()
    if explicit:
        return explicit

    model_name = (os.getenv("RAG_EMBED_MODEL") or "").strip().lower()
    if model_name.startswith("openai:") or "text-embedding-3" in model_name:
        return f"openai_{EMB_DIM}"
    if model_name.startswith("ollama:"):
        return f"ollama_{EMB_DIM}"
    if model_name.startswith("vllm:"):
        return f"vllm_{EMB_DIM}"
    if model_name.startswith("deepseek:"):
        return f"deepseek_{EMB_DIM}"

    # conservative fallback, but no longer preferred
    return f"emb_{EMB_DIM}"

EMB_FAMILY = _default_embed_family()

# Alcune estensioni testuali
TEXT_EXTS = {".md",".txt",".rst",".adoc",".py",".js",".ts",".tsx",".jsx",".java",".go",".rs",".cpp",".c",".h",".sql",".yml",".yaml",".json",".toml",".ini",".proto",".sh",".ps1",".rb",".php",".cs",".kt"}

def _norm_path(p: str) -> str:
    return re.sub(r"[\\]+", "/", (p or "").strip())

def _point_id(embed_family: str, path: str, sha: str, chunk_idx: int) -> str:
    raw = f"{embed_family}|{path}|{sha}|{chunk_idx}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

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
    Gateway-only embedding client.
    No direct-provider fallback.
    No fake vectors.
    Fail fast on provider failure or dimension mismatch.
    """

    def __init__(self, gateway_base: str = "http://gateway:8000/v1"):
        self.base = gateway_base.rstrip("/")
        self.model_name = (os.getenv("RAG_EMBED_MODEL") or "").strip()

    async def _embed_one_gateway(self, text: str) -> List[float]:
        payload: Dict[str, Any] = {"input": text}
        if self.model_name:
            payload["model"] = self.model_name

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/embeddings", json=payload)
            r.raise_for_status()
            data = r.json() or {}

        vecs = [
            d["embedding"]
            for d in (data.get("data") or [])
            if isinstance(d, dict) and "embedding" in d
        ]
        if not vecs:
            raise RuntimeError("gateway embeddings returned no vectors")

        vec = vecs[0]
        if not isinstance(vec, list) or not vec:
            raise RuntimeError("gateway embeddings returned an empty vector")

        if len(vec) != EMB_DIM:
            raise RuntimeError(
                f"embedding dimension mismatch: expected={EMB_DIM} got={len(vec)}"
            )

        return vec

    async def embed(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []

        for text in texts:
            payload: Dict[str, Any] = {"input": text}
            model_name = (os.getenv("RAG_EMBED_MODEL") or "").strip()
            if model_name:
                payload["model"] = model_name

            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(f"{self.base}/embeddings", json=payload)
                r.raise_for_status()
                data = r.json() or {}

            vecs = [
                d["embedding"]
                for d in (data.get("data") or [])
                if isinstance(d, dict) and "embedding" in d
            ]
            if not vecs:
                raise RuntimeError("gateway embeddings returned no vectors")

            vec = vecs[0]
            if not isinstance(vec, list) or len(vec) != EMB_DIM:
                raise RuntimeError(
                    f"embedding dimension mismatch: expected={EMB_DIM} got={len(vec) if isinstance(vec, list) else 'invalid'}"
                )

            results.append(vec)

        return results

class RagStore:
    
    def __init__(self, project_id: str):
        """
        Initialize store for a specific project namespace.
        Collection naming MUST include embedding family to avoid mixing
        incompatible vector spaces across index/search callers.
        """
        self.project_id = (project_id or "default")
        self.namespace = ("proj_" + re.sub(r"[^a-zA-Z0-9_]+", "_", self.project_id)).lower()
        self.q = QDRANT_URL
        self.c = f"{QCOLLECTION}__{self.namespace}__{EMB_FAMILY}"
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

    async def get_by_path(
        self,
        path: str,
        *,
        max_chars_per_doc: int = 200000,
        search_top_k: int = 100,
        base_url: Optional[str] = None,
        timeout_sec: int = 30,
    ) -> dict:
        """
        Call orchestrator RAG API to aggregate a single document by exact path.

        Returns:
            dict -> {"path": str, "text": str, "chunks": int} or {} on not found/error.
        """
        if not path:
            return {}

        payload = {
            "project_id": self.project_id,
            "paths": [path],
            "max_chars_per_doc": max(500, int(max_chars_per_doc)),
            "search_top_k": int(search_top_k),
        }
        # ⚠️ importante: usa _rag_base_url(base_url) per evitare "localhost" nel container gateway
        url = f"{_rag_base_url(base_url)}/fetch_by_paths"
        log.info("rag.store rag get_by_path %s %s", url, payload)

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                docs = data.get("docs") or []

                if docs:
                    first = docs[0] or {}
                    log.info(
                        "rag.store get_by_path found path=%s chunks=%s text_len=%s",
                        first.get("path"),
                        first.get("chunks"),
                        len(first.get("text") or ""),
                    )
                    return first

                log.info("rag.store get_by_path found nothing for path=%s", path)
                return {}
        except Exception as e:
            log.warning("get_by_path failed: %s", e)
            return {}


    async def fetch_docs(
        self,
        *,
        paths: Optional[List[str]] = None,
        path_prefix: Optional[str] = None,
        limit_docs: int = 20,
        max_chars_per_doc: int = 4000,
        search_top_k: int = 100,
        base_url: Optional[str] = None,
        timeout_sec: int = 30,
    ) -> List[dict]:
        """
        Call orchestrator RAG API to fetch multiple aggregated documents.

        Returns:
            list[dict] -> [{"path": str, "text": str, "chunks": int}, ...] or [] on error.
        """
        payload = {
            "project_id": self.project_id,
            "paths": paths or None,
            "path_prefix": path_prefix or None,
            "limit_docs": max(1, int(limit_docs)),
            "max_chars_per_doc": max(500, int(max_chars_per_doc)),
            "search_top_k": int(search_top_k),
        }
        url = f"{_rag_base_url(base_url)}/fetch"
        log.info("rag fetch_docs %s %s", url, payload)

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                return data.get("docs") or []
        except Exception as e:
            log.warning("fetch_docs failed: %s", e)
            return []

        
    async def index_texts(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        await self.ensure()

        texts: List[str] = []
        metas: List[Dict[str, Any]] = []
        paths_to_replace: set[str] = set()

        for it in items:
            p = _norm_path(it.get("path") or "unknown")
            t = it.get("text") or ""
            if not p or not isinstance(t, str) or not t.strip():
                continue

            paths_to_replace.add(p)
            file_sha = _sha1(t)

            chunks = _split_chunks(t)
            for idx, ch in enumerate(chunks):
                if not ch.strip():
                    continue
                texts.append(ch)
                metas.append(
                    {
                        "path": p,
                        "sha": file_sha,
                        "chunk": idx,
                    }
                )

        if not texts:
            return {"ok": True, "upserts": 0, "indexed_paths": 0}

        vecs = await self.emb.embed(texts)
        if len(vecs) != len(metas):
            raise RuntimeError(
                f"embedding count mismatch: vecs={len(vecs)} metas={len(metas)}"
            )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                if paths_to_replace:
                    delete_body = {
                        "filter": {
                            "should": [
                                {"key": "path", "match": {"value": p}}
                                for p in sorted(paths_to_replace)
                            ]
                        }
                    }
                    r_del = await client.post(
                        f"{self.q}/collections/{self.c}/points/delete?wait=true",
                        json=delete_body,
                    )
                    if r_del.status_code >= 400:
                        log.error("RAG delete failed status=%s body=%s", r_del.status_code, r_del.text)
                        r_del.raise_for_status()

                points = []
                for i, (v, m) in enumerate(zip(vecs, metas)):
                    chunk_text = texts[i]
                    points.append(
                        {
                            "id": _point_id(EMB_FAMILY, m["path"], m["sha"], int(m["chunk"])),
                            "vector": v,
                            "payload": {
                                "path": m["path"],
                                "sha": m["sha"],
                                "chunk": int(m["chunk"]),
                                "text": chunk_text,
                                "text_len": len(chunk_text),
                                "embed_family": EMB_FAMILY,
                            },
                        }
                    )

                r_up = await client.put(
                    f"{self.q}/collections/{self.c}/points?wait=true",
                    json={"points": points},
                )

                if r_up.status_code >= 400:
                    log.error("RAG upsert failed status=%s body=%s", r_up.status_code, r_up.text)
                    r_up.raise_for_status()

        except Exception as e:
            log.error("RAG upsert failed: %s", e)
            raise

        return {
            "ok": True,
            "upserts": len(points),
            "indexed_paths": len(paths_to_replace),
        }

    async def search(self, query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
        await self.ensure()

        query_text = (query or "").strip()
        if not query_text:
            return []

        vec = (await self.emb.embed([query_text]))[0]

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                limit_as_int = int(top_k)
                body = {
                    "vector": vec,
                    "limit": limit_as_int,
                    "with_payload": True,
                    "score_threshold": RAG_SCORE_THRESHOLD,
                }
                r = await client.post(f"{self.q}/collections/{self.c}/points/search", json=body)
                r.raise_for_status()
                data = r.json() or {}

                raw_results = data.get("result") or []
                out: List[Dict[str, Any]] = []
                unique_paths = set()
                max_score = None
                min_score = None

                for it in raw_results:
                    pl = it.get("payload") or {}
                    score = float(it.get("score", 0.0))
                    path = pl.get("path", "") or ""
                    chunk = pl.get("chunk", 0)
                    text = pl.get("text", "") or ""

                    if path:
                        unique_paths.add(path)

                    if max_score is None or score > max_score:
                        max_score = score
                    if min_score is None or score < min_score:
                        min_score = score

                    out.append({
                        "path": path,
                        "chunk": chunk,
                        "score": score,
                        "text": text,
                    })

                log.info(
                    "RAG search raw_hits=%d unique_paths=%d max_score=%.4f min_score=%.4f query=%r collection=%s",
                    len(raw_results),
                    len(unique_paths),
                    max_score or 0.0,
                    min_score or 0.0,
                    query_text,
                    self.c,
                )

                try:
                    ranked_paths = []
                    for item in sorted(out, key=lambda x: float(x.get("score", 0.0)), reverse=True):
                        p = (item.get("path") or "").strip()
                        if not p:
                            continue
                        ranked_paths.append(f"{p} (chunk={item.get('chunk', 0)} score={float(item.get('score', 0.0)):.3f})")

                    if ranked_paths:
                        log.info("RAG search files for query=%r -> %s", query_text, " | ".join(ranked_paths[:20]))
                    else:
                        log.info("RAG search files for query=%r -> none", query_text)
                except Exception as log_err:
                    log.warning("RAG search path logging failed for query=%r: %s", query_text, log_err)

                return out

        except httpx.HTTPStatusError as e:
            error_details = e.response.text[:400] if e.response else "N/A"
            log.error(
                "RAG search failed (HTTP %s). URL=%s details=%s",
                e.response.status_code if e.response else "N/A",
                e.request.url if e.request else "N/A",
                error_details,
            )
            return []

        except Exception as e:
            full_traceback = traceback.format_exc()
            log.error("RAG search failed: %s", e)
            log.error("RAG search traceback: %s", full_traceback)
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
        

