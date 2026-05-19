from __future__ import annotations
import os, re, json, time, hashlib, logging, uuid
import traceback
from typing import List, Dict, Any, Optional, Tuple
import httpx
import asyncio


def _rag_base_url(base_url: str | None = None) -> str:
    return (base_url or os.getenv("RAG_BASE_URL", "http://localhost:8080/v1/rag")).rstrip("/")

log = logging.getLogger("rag.store")

QDRANT_URL  = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QCOLLECTION = os.getenv("QDRANT_COLLECTION", "clike_rag")
EMB_DIM     = int(os.getenv("EMBEDDING_DIM", "1536"))
EMB_FAMILY  = os.getenv("RAG_EMBED_FAMILY", f"emb_{EMB_DIM}")
CHUNK_TOKENS   = int(os.getenv("RAG_CHUNK_TOKENS", "800"))
CHUNK_OVERLAP  = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))
TOP_K          = int(os.getenv("RAG_TOP_K", "12"))
MAX_CTX_TOKENS = int(os.getenv("RAG_MAX_CTX_TOKENS", "1800"))
MAX_EMBED_TEXT_CHARS = int(os.getenv("RAG_MAX_EMBED_TEXT_CHARS", "12000"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.30"))
TEXT_EXTS = {
    ".md",".txt",".rst",".adoc",".py",".js",".ts",".tsx",".jsx",".java",".go",".rs",
    ".cpp",".c",".h",".sql",".yml",".yaml",".json",".toml",".ini",".proto",".sh",
    ".ps1",".rb",".php",".cs",".kt"
}

def _norm_path(p: str) -> str:
    return re.sub(r"[\\]+", "/", (p or "").strip())

def _point_id(embed_family: str, path: str, sha: str, chunk_idx: int) -> str:
    raw = f"{embed_family}|{path}|{sha}|{chunk_idx}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def _split_chunks(text: str, tokens:int=CHUNK_TOKENS, overlap:int=CHUNK_OVERLAP) -> List[str]:
    if not text:
        return []
    unit = max(500, tokens * 4)
    step = max(256, overlap * 4)
    out = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + unit)
        out.append(text[i:j])
        if j == n:
            break
        i = max(i + unit - step, i + 1)
    return out


_TRANSIENT_HTTPX_ERRORS = (
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
)


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    attempts: int = 3,
    base_delay_seconds: float = 0.25,
) -> httpx.Response:
    """Run a Qdrant HTTP request with a small retry budget for transient I/O errors."""
    last_error: Optional[BaseException] = None

    for attempt in range(max(1, attempts)):
        try:
            response = await client.request(method, url, json=json_body)
            return response
        except _TRANSIENT_HTTPX_ERRORS as exc:
            last_error = exc
            if attempt >= attempts - 1:
                break

            await asyncio.sleep(base_delay_seconds * (attempt + 1))

    assert last_error is not None
    raise last_error

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

        for raw in texts:
            text = (raw or "")[:MAX_EMBED_TEXT_CHARS]
            if not text.strip():
                continue

            vec = await self._embed_one_gateway(text)
            results.append(vec)

        return results


class RagStore:
    def __init__(self, project_id: str):
        # project_id → namespace: multi-progetto nello stesso Qdrant
        self.project_id = (project_id or "default")
        self.namespace = ("proj_" + re.sub(r"[^a-zA-Z0-9_]+", "_", self.project_id)).lower()
        self.q = QDRANT_URL
        self.c = f"{QCOLLECTION}__{self.namespace}__{EMB_FAMILY}"
        self.emb = EmbeddingClient()

    

    async def ensure(self) -> None:
        # crea collection se non esiste
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await _request_with_retry(
                    client,
                    "GET",
                    f"{self.q}/collections/{self.c}",
                    attempts=2,
                )
                if r.is_success:
                    return

                body = {
                    "vectors": {"size": EMB_DIM, "distance": "Cosine"},
                    "on_disk_payload": True,
                }
                r = await _request_with_retry(
                    client,
                    "PUT",
                    f"{self.q}/collections/{self.c}",
                    json_body=body,
                    attempts=3,
                )
                r.raise_for_status()
                log.info("RAG created collection %s", self.c)
        except Exception as e:
            log.error("RAG ensure failed: %s", e)
            raise


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
                    r_del = await _request_with_retry(
                        client,
                        "POST",
                        f"{self.q}/collections/{self.c}/points/delete?wait=true",
                        json_body=delete_body,
                        attempts=3,
                    )
                    if r_del.status_code >= 400:
                        log.error("RAG delete failed status=%s body=%s", r_del.status_code, r_del.text[:500])
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

            batch_size = max(1, int(os.getenv("RAG_QDRANT_UPSERT_BATCH_SIZE", "64")))
            upserted = 0

            for start in range(0, len(points), batch_size):
                batch = points[start:start + batch_size]
                r_up = await _request_with_retry(
                    client,
                    "PUT",
                    f"{self.q}/collections/{self.c}/points?wait=true",
                    json_body={"points": batch},
                    attempts=3,
                )
                if r_up.status_code >= 400:
                    log.error(
                        "RAG upsert failed status=%s body=%s batch=%s/%s collection=%s",
                        r_up.status_code,
                        r_up.text[:500],
                        start,
                        len(points),
                        self.c,
                    )
                    r_up.raise_for_status()

                upserted += len(batch)

            log.info(
                "RAG upsert completed collection=%s points=%d paths=%d batch_size=%d",
                self.c,
                upserted,
                len(paths_to_replace),
                batch_size,
            )

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
    
    async def fetch_docs_by_prefix(
        self,
        path_prefix: str,
        *,
        max_chars_per_doc: int = 4000,
        limit_points: int = 2000,
        limit_docs: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.ensure()

        prefix = _norm_path(path_prefix)
        if not prefix:
            return []

        collected: List[Dict[str, Any]] = []
        offset = None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                while len(collected) < max(10, int(limit_points)):
                    body: Dict[str, Any] = {
                        "with_payload": True,
                        "limit": min(256, max(10, int(limit_points)) - len(collected)),
                    }
                    if offset is not None:
                        body["offset"] = offset

                    r = await client.post(
                        f"{self.q}/collections/{self.c}/points/scroll",
                        json=body,
                    )
                    r.raise_for_status()

                    data = r.json() or {}
                    result = data.get("result") or {}
                    points = result.get("points") or []
                    if not points:
                        break

                    collected.extend(points)
                    offset = result.get("next_page_offset")
                    if offset is None:
                        break

            by_path: Dict[str, List[Dict[str, Any]]] = {}
            prefix_norm = prefix.rstrip("/") + "/"

            for pt in collected:
                pl = pt.get("payload") or {}
                path = _norm_path(pl.get("path") or "")
                text = (pl.get("text") or "").strip()
                if not path or not text:
                    continue
                if not path.startswith(prefix_norm):
                    continue

                by_path.setdefault(path, []).append(
                    {
                        "chunk": int(pl.get("chunk") or 0),
                        "text": text,
                    }
                )

            out: List[Dict[str, Any]] = []
            for path in sorted(by_path.keys())[: max(1, int(limit_docs))]:
                parts = sorted(by_path.get(path) or [], key=lambda x: x["chunk"])
                if not parts:
                    continue

                acc: List[str] = []
                used = 0
                chunks = 0
                for item in parts:
                    piece = item["text"]
                    add_len = len(piece) + (1 if acc else 0)
                    if used + add_len > max_chars_per_doc:
                        remaining = max_chars_per_doc - used
                        if remaining > 0:
                            trimmed = piece[:remaining]
                            if trimmed:
                                acc.append(trimmed)
                                used += len(trimmed)
                                chunks += 1
                        break

                    acc.append(piece)
                    used += add_len
                    chunks += 1

                text = "\n".join(acc).strip()
                if text:
                    out.append({"path": path, "text": text, "chunks": chunks})

            return out
        except Exception as e:
            log.error("RAG fetch_docs_by_prefix failed: %s", e)
            return []
    
    async def fetch_docs_by_paths(
        self,
        paths: List[str],
        *,
        max_chars_per_doc: int = 4000,
        limit_points: int = 2000,
    ) -> List[Dict[str, Any]]:
        await self.ensure()

        wanted = [_norm_path(p) for p in (paths or []) if _norm_path(p)]
        if not wanted:
            return []

        filter_should = [{"key": "path", "match": {"value": p}} for p in wanted]
        collected: List[Dict[str, Any]] = []
        offset = None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                while len(collected) < max(10, int(limit_points)):
                    body: Dict[str, Any] = {
                        "filter": {"should": filter_should},
                        "with_payload": True,
                        "limit": min(256, max(10, int(limit_points)) - len(collected)),
                    }
                    if offset is not None:
                        body["offset"] = offset

                    r = await client.post(
                        f"{self.q}/collections/{self.c}/points/scroll",
                        json=body,
                    )
                    r.raise_for_status()

                    data = r.json() or {}
                    result = data.get("result") or {}
                    points = result.get("points") or []
                    if not points:
                        break

                    collected.extend(points)
                    offset = result.get("next_page_offset")
                    if offset is None:
                        break

            by_path: Dict[str, List[Dict[str, Any]]] = {p: [] for p in wanted}
            for pt in collected:
                pl = pt.get("payload") or {}
                path = _norm_path(pl.get("path") or "")
                text = (pl.get("text") or "").strip()
                if not path or not text or path not in by_path:
                    continue
                by_path[path].append(
                    {
                        "chunk": int(pl.get("chunk") or 0),
                        "text": text,
                    }
                )

            out: List[Dict[str, Any]] = []
            for p in wanted:
                parts = sorted(by_path.get(p) or [], key=lambda x: x["chunk"])
                if not parts:
                    continue

                acc: List[str] = []
                used = 0
                chunks = 0
                for item in parts:
                    piece = item["text"]
                    add_len = len(piece) + (1 if acc else 0)
                    if used + add_len > max_chars_per_doc:
                        remaining = max_chars_per_doc - used
                        if remaining > 0:
                            trimmed = piece[:remaining]
                            if trimmed:
                                acc.append(trimmed)
                                used += len(trimmed)
                                chunks += 1
                        break

                    acc.append(piece)
                    used += add_len
                    chunks += 1

                text = "\n".join(acc).strip()
                if text:
                    out.append({"path": p, "text": text, "chunks": chunks})

            return out
        except Exception as e:
            log.error("RAG fetch_docs_by_paths failed: %s", e)
            return []