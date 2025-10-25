from __future__ import annotations
import os,  logging
import httpx

log = logging.getLogger("gateway.utils")

# ===== RAG hooks (best-effort; non bloccanti) =====
def _rag_project_id(body: dict) -> str:
    pid = (body or {}).get("project_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return "default"

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
def _rag_base_url() -> str:
    # es.: "http://localhost:8080/v1/rag"
    base = _get_cfg("RAG_BASE_URL", "http://localhost:8080/v1/rag")
    return base.rstrip("/")

def _get_cfg(name: str, default: str) -> str:
    """Legge prima da os.environ, poi da settings, altrimenti default."""
    v = os.getenv(name)
    if v is not None and str(v).strip():
        return str(v).strip()
    try:
        vv = getattr(settings, name, None)
        if vv is not None and str(vv).strip():
            return str(vv).strip()
    except Exception:
        pass
    return default

async def rag_index_items(project_id: str, items: list[dict]):
    # Optional server-side index; we prefer client-side, but keep for completeness.
    if not items:
        return
    payload = {"project_id": project_id, "items": []}
    for it in (items or []):
        p = (it.get("path") or "").strip()
        t = (it.get("text") or "").strip()
        if p and t:
            payload["items"].append({"path": p, "text": t})
    if not payload["items"]:
        return
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(f"{_rag_base_url()}/index", json=payload)
    except Exception as e:
        log.warning("rag_index_items failed: %s", e)
        raise e

async def rag_query(project_id: str, query: str, top_k: int = None):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_rag_base_url()}/search",
                                  json={"project_id": project_id,
                                        "query": query or "",
                                        "top_k": int(top_k or RAG_TOP_K)})
            r.raise_for_status()
            data = r.json() or {}
            return data.get("hits") or []
    except Exception as e:
        log.warning("rag_query failed: %s", e)
        return []

# --- RAG (http-based) collector ------------------------------------------------
async def collect_rag_materials_http(
    project_id: str ,
    queries: list[str] | None,
    core_blobs: dict | None,
    top_k: int | None = None,
) -> list[dict]:
    """
    Interroga il servizio RAG via utils.rag_query() per ogni query.
    Ritorna: [{title, text, source}] senza duplicati, cap ~12 estratti.
    """
    pid = (project_id or "default").strip()
    qlist: list[str] = []

    # 1) Se non arrivano query, creale in base a path noti e heading dei core_blobs
    if not queries:
        # path-based (gli stessi che l'estensione indicizza)
        # qlist.extend([
        #     "path:docs/harper/README.md",
        #     "path:docs/harper/SPEC.md",
        #     "path:docs/harper/PLAN.md",
        #     "path:docs/harper/plan.json",
        #     "path:docs/harper/KIT.md",
        #     "path:docs/harper/",
        #     "path:src/",
        # ])
        qlist.extend([
            "path:src/",
        ])
        # heading-based (prima linea # ... di SPEC/PLAN se presenti nei core_blobs)
        # for key in ("SPEC.md", "PLAN.md"):
        #     txt = (core_blobs or {}).get(key, "") or ""
        #     for ln in txt.splitlines():
        #         if ln.strip().startswith("#"):
        #             qlist.append(ln.strip("# ").strip())
        #             break
    else:
        qlist = list(queries)

    # 2) esegui le query
    materials: list[dict] = []
    seen = set()
    cap = min(int(top_k or RAG_TOP_K), 120)
    for q in qlist[:8]:               # massimo 8 query
        hits = await rag_query(pid, q, top_k=cap)
        for h in (hits or []):
            path = (h.get("path") or "").strip()
            text = (h.get("text") or "").strip()
            if not text:
                continue
            key = (path, h.get("chunk"))
            if key in seen:
                continue
            seen.add(key)
            title = f"{path or 'doc'}#{h.get('chunk',0)}"
            if "score" in h:
                try:
                    title += f" (score={float(h['score']):.3f})"
                except Exception:
                    pass
            item = {"title": title, "text": text, "source": "rag"}
            log.info("RAG item: %s", item)
            materials.append(item)
            if len(materials) >= cap:
                break
        if len(materials) >= cap:
            break
    return materials

