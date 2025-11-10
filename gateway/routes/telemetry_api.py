# gateway/router/telemetry_api.py
from __future__ import annotations
import logging
import json, os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Query

from pricing import PricingManager

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])
log = logging.getLogger("gateway.telemetry")

# ✅ Prende da env ma converte SUBITO in Path
_TELEMETRY_DIR_ENV = os.getenv("HARPER_TELEMETRY_DIR", "/workspace/telemetry")
TELEMETRY_DIR: Path = Path(_TELEMETRY_DIR_ENV).resolve()

def _as_path(p) -> Path:
    return p if isinstance(p, Path) else Path(p)


# ---------------- IO helpers ----------------
_EXTS = {".json", ".ndjson", ".log", ".txt"}

def _iter_project_files() -> List[Path]:
    base = _as_path(TELEMETRY_DIR)
    base.mkdir(parents=True, exist_ok=True)
    log.info("TELEMETRY_DIR [%s]: %s", type(base).__name__, base)

    files: List[Path] = []
    # usa rglob in sicurezza
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in _EXTS:
            files.append(p)

    files.sort()
    return files


def _load_any_json(path: Path) -> List[dict]:
    """Supporta:
       - JSON Lines (una JSON per riga)
       - Array JSON unico: [ {...}, {...} ]
    """
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        text = f.read().strip()
        if not text:
            return rows
        # array JSON completo
        if text.startswith("[") and text.endswith("]"):
            try:
                arr = json.loads(text)
                if isinstance(arr, list):
                    rows.extend([x for x in arr if isinstance(x, dict)])
                return rows
            except Exception:
                pass
        # altrimenti JSONL
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                # ignora righe corrotte
                continue
    return rows

def _load_project(project_id: str) -> List[dict]:
    # 1) file singolo <id>.json / .jsonl / .ndjson nella root
    for ext in _EXTS:
        cand = TELEMETRY_DIR / f"{project_id}{ext}"
        if cand.exists():
            return _load_any_json(cand)
    # 2) cartella telemetry/<project_id>/**.json*
    folder = TELEMETRY_DIR / project_id
    rows: List[dict] = []
    if folder.exists() and folder.is_dir():
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in _EXTS:
                rows.extend(_load_any_json(p))
    return rows

def _num(x, default=0.0):
    try: return float(x)
    except Exception: return float(default)

def _int(x, default=0):
    try: return int(x)
    except Exception: return int(default)

# ---------------- API: files listing ----------------
@router.get("/harper/files")
def list_telemetry_files() -> dict:
    base = _as_path(TELEMETRY_DIR)
    items: List[dict] = []

    for p in _iter_project_files():
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
        })

    return {"dir": str(base), "files": items}



# ---------------- API: aggregate/series/top ----------------
@router.get("/harper/aggregate")
def harper_aggregate(
    project_id: str = Query(...),
    since_ts: Optional[float] = Query(None),
    until_ts: Optional[float] = Query(None),
) -> dict:
    rows = _load_project(project_id)
    if since_ts is not None: rows = [r for r in rows if _num(r.get("timestamp")) >= since_ts]
    if until_ts is not None: rows = [r for r in rows if _num(r.get("timestamp")) <= until_ts]

    total_cost = 0.0
    per_phase: Dict[str, dict] = {}
    per_provider: Dict[str, dict] = {}
    per_model: Dict[str, dict] = {}
    by_day: Dict[str, dict] = {}

    for r in rows:
        phase = (r.get("phase") or "").lower()
        prov  = (r.get("provider") or "").lower()
        model = r.get("model") or ""
        usage = r.get("usage") or {}
        cost  = _num(r.get("cost_usd_est"))
        tin   = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
        tout  = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
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
        "project_id": project_id,
        "total_runs": len(rows),
        "total_cost_usd": round(total_cost, 6),
        "per_phase": per_phase,
        "per_provider": per_provider,
        "per_model": per_model,
        "by_day": by_day,
    }

@router.get("/harper/series")
def harper_series(project_id: str, phase: Optional[str] = None) -> dict:
    rows = _load_project(project_id)
    out = []
    for r in rows:
        if phase and (r.get("phase") or "").lower() != phase.lower(): 
            continue
        usage = r.get("usage") or {}
        out.append({
            "t": _num(r.get("timestamp"), 0.0),
            "cost_usd": _num(r.get("cost_usd_est"), 0.0),
            "tokens_in": _int(usage.get("prompt_tokens") or usage.get("input_tokens"), 0),
            "tokens_out": _int(usage.get("completion_tokens") or usage.get("output_tokens"), 0),
            "phase": r.get("phase"), "model": r.get("model"),
            "provider": r.get("provider"), "run_id": r.get("run_id"),
        })
    out.sort(key=lambda x: x["t"])
    return {"project_id": project_id, "phase": phase, "series": out}

@router.get("/harper/top")
def harper_top(project_id: str, limit: int = Query(10, ge=1, le=100)) -> dict:
    rows = _load_project(project_id)
    ranked = sorted(rows, key=lambda r: _num(r.get("cost_usd_est")), reverse=True)[:limit]
    return {"project_id": project_id, "top": ranked}

# ---------------- API: RAW tabellare ----------------
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

    def norm(s): return (s or "").lower()
    if phase:    rows = [r for r in rows if norm(r.get("phase"))    == norm(phase)]
    if model:    rows = [r for r in rows if norm(r.get("model"))    == norm(model)]
    if provider: rows = [r for r in rows if norm(r.get("provider")) == norm(provider)]
    if q:        rows = [r for r in rows if q.lower() in norm(r.get("run_id"))]

    for r in rows:
        usage = r.get("usage") or {}
        r["_tokens_in"]  = _int(usage.get("prompt_tokens") or usage.get("input_tokens"), 0)
        r["_tokens_out"] = _int(usage.get("completion_tokens") or usage.get("output_tokens"), 0)
        r["_cost"]       = _num(r.get("cost_usd_est"), 0.0)
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
        "project_id": project_id,
        "page": page, "page_size": page_size, "total": total,
        "items": page_items,
    }
