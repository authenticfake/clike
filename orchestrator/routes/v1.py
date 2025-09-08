# routes/v1.py
import os, json, uuid, time, logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
import httpx

from config import settings
from services import utils as su
from services import llm_client
from services import model_router

router = APIRouter(prefix="/v1")
log = logging.getLogger("orchestrator.v1")

def _runs_root() -> str:
    return getattr(settings, "RUNS_DIR", os.path.join(os.getcwd(), "runs"))

def _new_run_dir(prefix: str = "run") -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    aid = uuid.uuid4().hex[:8]
    root = _runs_root()
    os.makedirs(root, exist_ok=True)
    d = os.path.join(root, f"{ts}_{prefix}_{aid}")
    os.makedirs(d, exist_ok=True)
    log.info("Create run dir: %s", d)
    return d
from typing import Any, Dict, List, Optional

def _mode_from_name(mid: str) -> str:
    """Heuristic: classify model id/name as 'embed' or 'chat'."""
    if not mid:
        return "chat"
    low = mid.lower()
    if "embed" in low or "embedding" in low or "nomic-embed" in low:
        return "embed"
    return "chat"

def _normalize_models(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize gateway responses into:
    [{"name": str, "modality": "chat"|"embed", "enabled": bool, ...}]
    Supports:
      - CLike-style: {"models":[{...}]}
      - OpenAI-style: {"data":[{"id": "..."}]}
    """
    # Case 1: CLike-style
    if isinstance(payload.get("models"), list):
        out = []
        for m in payload["models"]:
            name = m.get("name") or m.get("id") or m.get("model")
            if not name:
                continue
            mm = dict(m)  # copy
            mm.setdefault("name", name)
            mm.setdefault("modality", _mode_from_name(name))
            mm.setdefault("enabled", True)
            out.append(mm)
        return out

    # Case 2: OpenAI-style
    data = payload.get("data")
    if isinstance(data, list):
        out = []
        for m in data:
            mid = m.get("id")
            if not mid:
                continue
            out.append({
                "name": mid,
                "provider": "unknown",
                "modality": _mode_from_name(mid),
                "enabled": True,
                "capability": "medium",
                "latency": "medium",
                "cost": "medium",
                "privacy": "medium",
            })
        return out

    return []

def _filter_by_modality(models: List[Dict[str, Any]], modality: Optional[str]) -> List[Dict[str, Any]]:
    """
    If modality is 'chat' or 'embed', filter accordingly.
    If None, return as-is.
    """
    if modality in ("chat", "embed"):
        return [m for m in models if (m.get("modality") or "chat") == modality]
    return models

def _first_by_modality(models: List[Dict[str, Any]], modality: str) -> Optional[str]:
    for m in models:
        if (m.get("modality") or "chat") == modality:
            return m.get("name")
    return None

async def _load_models_or_fallback() -> List[Dict[str, Any]]:
    # try gateway
    try:
        payload = await _gateway_get("/v1/models")
        models = _normalize_models(payload)
        if models:
            return models
    except Exception:
        pass
    # fallback YAML
    try:
        cfg = model_router._load_cfg()
        raw = cfg.get("models", [])
        out = []
        for m in raw:
            name = m.get("name") or m.get("id") or m.get("model")
            if not name:
                continue
            mm = dict(m)
            mm.setdefault("name", name)
            mm.setdefault("modality", _mode_from_name(name))
            mm.setdefault("enabled", True)
            out.append(mm)
        return out
    except Exception:
        return []

async def _gateway_get(path: str) -> Dict[str, Any]:
    base = str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/")
    url = f"{base}{path}"
    timeout = float(getattr(settings, "REQUEST_TIMEOUT_S", 60))
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

from fastapi import Query

@router.get("/models")
async def list_models(
    modality: Optional[str] = Query(default="chat", regex="^(chat|embed|all)$")
):
    """
    Returns {"version":"1.0","models":[...]}
    Default modality='chat' (so UI won't show embedding-only models).
    Use modality=embed to list embed models, or modality=all to return all.
    """
    try:
        models = await _load_models_or_fallback()
        if modality != "all":
            models = _filter_by_modality(models, modality)
        return {"version": "1.0", "models": models}
    except Exception as ex:
        raise HTTPException(502, f"cannot load models: {type(ex).__name__}: {ex}")

@router.post("/chat")
async def chat(req: Request):
    body = await req.json()
    mode = (body.get("mode") or "free").lower()
    if mode not in ("free",):
        raise HTTPException(400, "mode must be 'free' for /v1/chat")
    model = body.get("model") or "auto"
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")

    run_dir = _new_run_dir("chat")
    with open(os.path.join(run_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    # validate model modality
    all_models = await _load_models_or_fallback()
    requested = model
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==requested)), None)

    # A) STRICT: errore se l’utente seleziona un embed
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{requested}' is an embedding model and cannot be used for chat. Pick a chat model.")

    # B) (OPZIONALE) AUTO-CORRECT:
    # if requested_modality == "embed":
    #     fallback = _first_by_modality(all_models, "chat")
    #     if not fallback:
    #         raise HTTPException(400, "no chat-capable models available")
    #     model = fallback

    try:
        text = await llm_client.call_gateway_chat(
            model, messages,
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.2),
            max_tokens=body.get("max_tokens", 512),
        )       
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    with open(os.path.join(run_dir, "response.json"), "w", encoding="utf-8") as f:
        json.dump({"text": text}, f, ensure_ascii=False, indent=2)

    return {
        "version": "1.0",
        "text": text,
        "usage": {},
        "sources": [],
        "audit_id": os.path.basename(run_dir),
        "run_dir": run_dir
    }

def _extract_json(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        pass
    import re
    m = re.search(r"```json\\s*(\\{[\\s\\S]*?\\})\\s*```", s, re.M)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    i = s.find("{"); j = s.rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(s[i:j+1])
    raise ValueError("no valid JSON found")

def _system_for_generate(mode: str) -> str:
    base = "You are CLike, an super expert software and product-engineering copilot. Output strictly JSON, no prose."
    if mode == "harper":
        return base + ' Return: {"files":[{"path":"...","content":"..."}], "notes":[]}'
    return base + ' Return: {"files":[{"path":"...","content":"..."}]}'

@router.post("/generate")
async def generate(req: Request):
    body = await req.json()
    mode = (body.get("mode") or "coding").lower()
    if mode not in ("harper", "coding"):
        raise HTTPException(400, "mode must be 'harper' or 'coding'")
    model = body.get("model") or "auto"
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(422, "messages (list) is required")

    sysmsg = {"role": "system", "content": _system_for_generate(mode)}
    msgs = [sysmsg] + messages

    run_dir = _new_run_dir("gen")
    with open(os.path.join(run_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    # validate model modality for generation
    all_models = await _load_models_or_fallback()
    requested = model
    requested_modality = next((m.get("modality") for m in all_models if (m.get("name")==requested)), None)

    # A) STRICT:
    if requested_modality == "embed":
        raise HTTPException(400, f"model '{requested}' is an embedding model and cannot be used for code generation. Pick a chat model.")

    # B) AUTO-CORRECT (opzionale, come sopra)
    # if requested_modality == "embed":
    #     fallback = _first_by_modality(all_models, "chat")
    #     if not fallback:
    #         raise HTTPException(400, "no chat-capable models available")
    #     model = fallback

    try:
        raw = await llm_client.call_gateway_chat(
            model, msgs,
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")),
            timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 60)),
            temperature=body.get("temperature", 0.1),
            max_tokens=body.get("max_tokens", 1024),
        )
    except Exception as e:
        raise HTTPException(502, f"gateway chat failed: {type(e).__name__}: {e}")

    with open(os.path.join(run_dir, "raw_model.txt"), "w", encoding="utf-8") as f:
        f.write(raw)

    try:
        pj = _extract_json(raw)
    except Exception as e:
        raise HTTPException(502, f"model did not return JSON: {type(e).__name__}: {e}")

    files = pj.get("files") or []
    if not isinstance(files, list) or not files:
        raise HTTPException(422, "no files produced by model")

    diffs: List[Dict[str, Any]] = []
    for fobj in files:
        path = fobj.get("path"); content = fobj.get("content", "")
        if not path:
            raise HTTPException(422, "every file must have 'path'")
        prev = su.read_file(path) or ""
        patch = su.to_diff(prev, content, path)
        diffs.append({"path": path, "diff": patch})

    with open(os.path.join(run_dir, "files.json"), "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=2)
    with open(os.path.join(run_dir, "diffs.json"), "w", encoding="utf-8") as f:
        json.dump(diffs, f, ensure_ascii=False, indent=2)

    resp = {
        "version": "1.0",
        "files": files,
        "diffs": diffs,
        "eval_report": {"status": "skipped"},
        "audit_id": os.path.basename(run_dir),
        "run_dir": run_dir
    }
    with open(os.path.join(run_dir, "response.json"), "w", encoding="utf-8") as f:
        json.dump(resp, f, ensure_ascii=False, indent=2)
    return resp

@router.post("/apply")
async def apply(req: Request):
    body = await req.json()
    run_dir = body.get("run_dir")
    audit_id = body.get("audit_id")
    selection = body.get("selection") or {"apply_all": True}

    if not run_dir and audit_id:
        root = _runs_root()
        cands = [d for d in os.listdir(root) if audit_id in d]
        if not cands:
            raise HTTPException(404, "audit_id not found")
        run_dir = os.path.join(root, cands[0])

    if not run_dir:
        raise HTTPException(422, "run_dir or audit_id required")

    files_path = os.path.join(run_dir, "files.json")
    if not os.path.exists(files_path):
        raise HTTPException(404, "files.json not found for this run")

    with open(files_path, "r", encoding="utf-8") as f:
        files = json.load(f)

    applied = []
    if selection.get("apply_all", False):
        targets = [f["path"] for f in files]
    else:
        targets = [p for p in selection.get("paths", [])]

    for fobj in files:
        if fobj["path"] in targets:
            su.write_file(fobj["path"], fobj.get("content", ""))
            applied.append(fobj["path"])

    return {"version": "1.0", "applied": applied, "next": {"harper_state": None, "approval": None}}
