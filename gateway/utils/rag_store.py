"""Gateway client of the orchestrator RAG API (WP9.3).

The orchestrator owns retrieval-augmented generation (indexing, embeddings, Qdrant, /v1/rag);
the gateway only fetches already indexed documents to add them to a Harper run. The previous
gateway-side Qdrant store and embedder were unused and have been removed.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import httpx

from utils.service_auth import internal_auth_headers

log = logging.getLogger("rag.store")


def _rag_base_url(base_url: str | None = None) -> str:
    return (base_url or os.getenv("RAG_BASE_URL", "http://localhost:8080/v1/rag")).rstrip("/")


class RagStore:
    """Documents of one project, fetched from the orchestrator RAG API."""

    def __init__(self, project_id: str):
        self.project_id = project_id or "default"

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
            async with httpx.AsyncClient(timeout=timeout_sec, headers=internal_auth_headers()) as client:
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
            async with httpx.AsyncClient(timeout=timeout_sec, headers=internal_auth_headers()) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                return data.get("docs") or []
        except Exception as e:
            log.warning("fetch_docs failed: %s", e)
            return []
