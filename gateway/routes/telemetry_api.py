# gateway/router/telemetry_api.py
from __future__ import annotations
import logging
import json, os
from pathlib import Path
from typing import Dict, List, Optional, Iterable
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException

# opzionale se lo userai in futuro
try:
    from pricing import PricingManager  # noqa: F401
except Exception:
    PricingManager = None  # type: ignore

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])
log = logging.getLogger("gateway.telemetry")

# === Config e util ===
_TELEMETRY_DIR_ENV = os.getenv("HARPER_TELEMETRY_DIR", "/workspace/telemetry")
TELEMETRY_DIR: Path = Path(_TELEMETRY_DIR_ENV).resolve()

_EXTS = {".json", ".jsonl",".ndjson", ".log", ".txt"}

def _as_path(p) -> Path:
    return p if isinstance(p, Path) else Path(p)

def _ensure_base_dir() -> Path:
    base = _as_path(TELEMETRY_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base

def _iter_project_files() -> List[Path]:
    base = _ensure_base_dir()
    log.info("TELEMETRY_DIR [%s]: %s", type(base).__name__, base)
    files: List[Path] = []
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in _EXTS:
            files.append(p)
    files.sort()
    return files

def _safe_read_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def _load_any_json(path: Path, max_lines: Optional[int] = None) -> List[dict]:
    """
    Supporta:
     - JSON array completo
     - JSON Lines (una JSON per riga)
    max_lines: se impostato, limita le righe processate (utile per /projects)
    """
    rows: List[dict] = []
    if not path.exists():
        return rows
    text = _safe_read_text(path).strip()
    if not text:
        return rows

    if text.startswith("[") and text.endswith("]"):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                for x in arr:
                    if isinstance(x, dict):
                        rows.append(x)
            return rows
        except Exception:
            # se array fallisce, tenta come JSONL
            pass

    # JSONL
    count = 0
    for line in text.splitlines():
        if max_lines is not None and count >= max_lines:
            break
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                rows.append(obj)
                count += 1
        except Exception:
            continue
    return rows

def _load_project(project_id: str) -> List[dict]:
    # 1) file singolo <id>.(json|ndjson|log|txt) nella root
    for ext in _EXTS:
        cand = TELEMETRY_DIR / f"{project_id}{ext}"
        if cand.exists():
            return _load_any_json(cand)
    # 2) cartella telemetry/<project_id>/** con file supportati
    folder = TELEMETRY_DIR / project_id
    rows: List[dict] = []
    if folder.exists() and folder.is_dir():
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in _EXTS:
                rows.extend(_load_any_json(p))
    return rows

def _resolve_relpath(relpath: str) -> Path:
    base = _ensure_base_dir()
    # normalizza e impedisci path traversal
    p = (base / relpath).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid relpath")
    if not (p.exists() and p.is_file()):
        raise HTTPException(status_code=404, detail="File not found")
    if p.suffix.lower() not in _EXTS:
        raise HTTPException(status_code=400, detail="Unsupported extension")
    return p

def _load_file(relpath: str) -> List[dict]:
    p = _resolve_relpath(relpath)
    return _load_any_json(p)

def _num(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def _int(x, default=0) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)

def _cost_from_row(r: dict) -> float:
    """
    Normalizza il costo:
      - preferisci pricing.total_cost se presente
      - poi r['cost_usd_est']
      - fallback 0.0
    """
    pricing = r.get("pricing") or {}
    tc = pricing.get("total_cost")
    if tc is not None:
        return _num(tc, 0.0)
    return _num(r.get("cost_usd_est"), 0.0)

def _tokens_in_from_row(r: dict) -> int:
    usage = r.get("usage") or {}
    return _int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("cache_creation_input_tokens")
        or 0,
        0,
    )

def _tokens_out_from_row(r: dict) -> int:
    usage = r.get("usage") or {}
    return _int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or 0,
        0,
    )

def _project_ids_from_content(paths: Iterable[Path]) -> Dict[str, int]:
    """
    Scansiona i file e conta quante occorrenze/righe per project_id abbiamo.
    Per efficienza, per i file molto grandi legge solo le prime ~50 righe.
    """
    counts: Dict[str, int] = {}
    for p in paths:
        if not (p.is_file() and p.suffix.lower() in _EXTS):
            continue
        rows = _load_any_json(p, max_lines=50)
        for r in rows:
            pid = r.get("project_id") or r.get("project") or ""
            if not pid:
                continue
            counts[pid] = counts.get(pid, 0) + 1
    return counts

# === API: elenco file presenti (globale o filtrato per progetto) ===
@router.get("/harper/files")
def list_telemetry_files(project_id: Optional[str] = Query(None)) -> dict:
    base = _ensure_base_dir()
    items: List[dict] = []
    for p in _iter_project_files():
        if project_id:
            rows = _load_any_json(p, max_lines=50)
            # include se contiene almeno un record col project_id
            if not any((r.get("project_id") == project_id) for r in rows):
                # fallback: nome file/stem o nome cartella
                if p.stem != project_id and p.parent.name != project_id:
                    continue
        st = p.stat()
        try:
            rel = str(p.relative_to(base))
        except ValueError:
            rel = str(p)
        items.append({
            "name": p.name,
            "relpath": rel,
            "bytes": st.st_size,
            "kb": round(st.st_size / 1024, 2),
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "ext": p.suffix.lower(),
        })
    return {"dir": str(base), "files": items}

# === Elenco progetti (dedotti dal contenuto) ===
@router.get("/harper/projects")
def list_projects() -> dict:
    paths = _iter_project_files()
    counts = _project_ids_from_content(paths)

    # fallback: se vuoto, prova a dedurre da file/folder names
    if not counts:
        for p in paths:
            if p.parent == TELEMETRY_DIR and p.suffix.lower() in _EXTS:
                counts[p.stem] = counts.get(p.stem, 0) + 1
            elif p.parent.parent == TELEMETRY_DIR:
                counts[p.parent.name] = counts.get(p.parent.name, 0) + 1

    projects = [{"id": pid, "files": n} for pid, n in sorted(counts.items())]
    return {"projects": projects}

# === Helpers per aggregate/series/top/raw su una lista di righe ===
def _aggregate_rows(rows: List[dict]) -> dict:
    total_cost = 0.0
    per_phase: Dict[str, dict] = {}
    per_provider: Dict[str, dict] = {}
    per_model: Dict[str, dict] = {}
    by_day: Dict[str, dict] = {}

    for r in rows:
        phase = (r.get("phase") or "").lower()
        prov  = (r.get("provider") or "").lower()
        model = r.get("model") or ""
        tin   = _tokens_in_from_row(r)
        tout  = _tokens_out_from_row(r)
        cost  = _cost_from_row(r)
        total_cost += cost

        per = per_phase.setdefault(phase, {"runs":0,"cost_usd":0.0,"tokens_in":0,"tokens_out":0})
        per["runs"]+=1; per["cost_usd"]+=cost; per["tokens_in"]+=tin; per["tokens_out"]+=tout

        pp = per_provider.setdefault(prov, {"runs":0,"cost_usd":0.0})
        pp["runs"]+=1; pp["cost_usd"]+=cost

        pm = per_model.setdefault(model, {"runs":0,"cost_usd":0.0})
        pm["runs"]+=1; pm["cost_usd"]+=cost

        day = datetime.utcfromtimestamp(_num(r.get("timestamp"),0)).strftime("%Y-%m-%d")
        bd = by_day.setdefault(day, {"runs":0,"cost_usd":0.0,"tokens_in":0,"tokens_out":0})
        bd["runs"]+=1; bd["cost_usd"]+=cost; bd["tokens_in"]+=tin; bd["tokens_out"]+=tout

    return {
        "total_runs": len(rows),
        "total_cost_usd": round(total_cost, 6),
        "per_phase": per_phase,
        "per_provider": per_provider,
        "per_model": per_model,
        "by_day": by_day,
    }

def _series_rows(rows: List[dict], phase: Optional[str]) -> List[dict]:
    out = []
    for r in rows:
        if phase and (r.get("phase") or "").lower() != phase.lower():
            continue
        out.append({
            "t": _num(r.get("timestamp"), 0.0),
            "cost_usd": _cost_from_row(r),
            "tokens_in": _tokens_in_from_row(r),
            "tokens_out": _tokens_out_from_row(r),
            "phase": r.get("phase"),
            "model": r.get("model"),
            "provider": r.get("provider"),
            "run_id": r.get("run_id"),
        })
    out.sort(key=lambda x: x["t"])
    return out

def _raw_rows(rows: List[dict],
              phase: Optional[str], model: Optional[str], provider: Optional[str],
              q: Optional[str], sort: str, page: int, page_size: int) -> dict:
    def norm(s): return (s or "").lower()
    if phase:    rows = [r for r in rows if norm(r.get("phase"))    == norm(phase)]
    if model:    rows = [r for r in rows if norm(r.get("model"))    == norm(model)]
    if provider: rows = [r for r in rows if norm(r.get("provider")) == norm(provider)]
    if q:        rows = [r for r in rows if q.lower() in norm(r.get("run_id"))]

    for r in rows:
        r["_tokens_in"]  = _tokens_in_from_row(r)
        r["_tokens_out"] = _tokens_out_from_row(r)
        r["_cost"]       = _cost_from_row(r)
        r["_ts"]         = _num(r.get("timestamp"), 0.0)

    key, direction = sort.split(":")
    keymap = {
        "timestamp": lambda r: r["_ts"],
        "cost":      lambda r: r["_cost"],
        "tokens_in": lambda r: r["_tokens_in"],
        "tokens_out":lambda r: r["_tokens_out"],
    }
    rows.sort(key=keymap[key], reverse=(direction=="desc"))

    total = len(rows)
    start = (page-1)*page_size
    end   = start + page_size
    page_items = rows[start:end]

    for r in page_items:
        for k in ["_tokens_in","_tokens_out","_cost","_ts"]:
            r.pop(k, None)

    return {
        "page": page, "page_size": page_size, "total": total,
        "items": page_items,
    }

# === Aggregate / Series / Top per PROGETTO ===
@router.get("/harper/aggregate")
def harper_aggregate(
    project_id: str = Query(...),
    since_ts: Optional[float] = Query(None),
    until_ts: Optional[float] = Query(None),
) -> dict:
    rows = _load_project(project_id)
    if since_ts is not None:
        rows = [r for r in rows if _num(r.get("timestamp")) >= since_ts]
    if until_ts is not None:
        rows = [r for r in rows if _num(r.get("timestamp")) <= until_ts]
    agg = _aggregate_rows(rows)
    agg["project_id"] = project_id
    return agg

@router.get("/harper/series")
def harper_series(project_id: str, phase: Optional[str] = None) -> dict:
    rows = _load_project(project_id)
    return {"project_id": project_id, "phase": phase, "series": _series_rows(rows, phase)}

@router.get("/harper/top")
def harper_top(project_id: str, limit: int = Query(10, ge=1, le=100)) -> dict:
    rows = _load_project(project_id)
    ranked = sorted(rows, key=lambda r: _cost_from_row(r), reverse=True)[:limit]
    return {"project_id": project_id, "top": ranked}

@router.get("/harper/raw")
def harper_raw(
    project_id: str,
    phase: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    q: Optional[str] = Query(None, description="substring match su run_id"),
    sort: str = Query("timestamp:desc", regex=r"^(timestamp|cost|tokens_in|tokens_out):(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict:
    rows = _load_project(project_id)
    data = _raw_rows(rows, phase, model, provider, q, sort, page, page_size)
    data["project_id"] = project_id
    return data

# === Aggregate / Series / Top / Raw per FILE ===
@router.get("/harper/aggregate_file")
def harper_aggregate_file(relpath: str = Query(...)) -> dict:
    rows = _load_file(relpath)
    agg = _aggregate_rows(rows)
    agg["relpath"] = relpath
    return agg

@router.get("/harper/series_file")
def harper_series_file(relpath: str = Query(...), phase: Optional[str] = None) -> dict:
    rows = _load_file(relpath)
    return {"relpath": relpath, "phase": phase, "series": _series_rows(rows, phase)}

@router.get("/harper/top_file")
def harper_top_file(relpath: str = Query(...), limit: int = Query(10, ge=1, le=100)) -> dict:
    rows = _load_file(relpath)
    ranked = sorted(rows, key=lambda r: _cost_from_row(r), reverse=True)[:limit]
    return {"relpath": relpath, "top": ranked}

@router.get("/harper/raw_file")
def harper_raw_file(
    relpath: str = Query(...),
    phase: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    q: Optional[str] = Query(None, description="substring match su run_id"),
    sort: str = Query("timestamp:desc", regex=r"^(timestamp|cost|tokens_in|tokens_out):(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict:
    rows = _load_file(relpath)
    data = _raw_rows(rows, phase, model, provider, q, sort, page, page_size)
    data["relpath"] = relpath
    return data
