# orchestrator/services/model_router.py
from __future__ import annotations
import os, yaml, asyncio
from typing import Dict, Any, List, Optional

try:
    # single source of truth for core config
    from orchestrator.config import settings  # type: ignore
except Exception:  # very early boot / tests
    settings = None  # fallback later

# --- Legacy scoring & policy (kept for backward compatibility) ---
SCORE_MAP = {
    "capability": {"high": 0, "medium": 1, "low": 2},
    "latency":    {"low": 0,  "medium": 1, "high": 2},
    "cost":       {"low": 0,  "medium": 1, "high": 2},
    "privacy":    {"high": 0, "medium": 1, "low": 2},
}
LOCAL_PROVIDERS = {"ollama", "vllm"}

# =============== Loaders ===============

def _models_config_path() -> str:
    """
    Retro-compat: path del vecchio YAML dei modelli.
    Prefer settings.MODELS_CONFIG_PATH se presente; altrimenti ENV; poi default.
    """
    if settings and getattr(settings, "MODELS_CONFIG_PATH", None):
        return settings.MODELS_CONFIG_PATH  # type: ignore[attr-defined]
    return settings.MODELS_CONFIG_PATH


def _load_from_yaml() -> Dict[str, Any]:
    path = _models_config_path()
    if not os.path.exists(path):
        return {"models": [], "routing": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Normalize
    data.setdefault("models", [])
    data.setdefault("routing", {})
    for m in data["models"]:
        m.setdefault("enabled", True)
        m.setdefault("modality", "chat")
        m.setdefault("capability", "medium")
        m.setdefault("latency", "medium")
        m.setdefault("cost", "medium")
        m.setdefault("privacy", "medium")
    return data

def _normalize_gateway_models(gw_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Map the Gateway /v1/models shape to the legacy model dict used here.
    Gateway model example:
      { id, provider, profile, capabilities[], context_window, default }
    Legacy fields we keep:
      name, provider, modality, enabled, capability, latency, cost, privacy
    """
    out: List[Dict[str, Any]] = []
    for m in gw_models:
        out.append({
            "name": m.get("id"),
            "provider": str(m.get("provider", "unknown")).lower(),
            "modality": "chat",
            "enabled": True,
            # Heuristics/defaults to preserve sorting behaviour
            "capability": "high" if "code" in (m.get("capabilities") or []) else "medium",
            "latency": "medium",
            "cost": "medium",
            "privacy": "medium",
            # Optional passthroughs for advanced routers
            "context_window": m.get("context_window"),
            "profile": m.get("profile"),
            "default": m.get("default", False),
        })
    return out

def _load_from_gateway_blocking() -> Optional[Dict[str, Any]]:
    """
    Prefer the Gateway as source of truth. This is a *blocking* sync fetch intended
    for legacy sync callers. If we're already inside an event loop, we *do not* call
    the async client (to avoid RuntimeError) and return None so the caller can fall back.
    """
    # If we're already in an event loop, skip (FastAPI handlers are async).
    try:
        asyncio.get_running_loop()
        return None  # let caller fall back to YAML for backward compatibility
    except RuntimeError:
        pass  # no running loop: safe to do a blocking HTTP call

    # Use a small local httpx client to avoid coupling to async client here.
    try:
        import httpx
        base = str(settings.GATEWAY_URL).rstrip("/")

        with httpx.Client(timeout=float(getattr(settings, "REQUEST_TIMEOUT_S", 10))) as client:
            r = client.get(base + "/v1/models")
            r.raise_for_status()
            payload = r.json() or {}
            models = payload.get("models", [])
            routing = {}  # routing lives in YAML; keep empty here
            return {"models": _normalize_gateway_models(models), "routing": routing}
    except Exception:
        return None  # gracefully fall back

# =============== Helpers (unchanged behaviour) ===============

def _score(p: Dict[str, Any]) -> int:
    s = 0
    for dim, m in SCORE_MAP.items():
        val = str(p.get(dim, "medium")).lower()
        s += m.get(val, 1)
    return s

def _is_local(p: Dict[str, Any]) -> bool:
    return str(p.get("provider", "")).lower() in LOCAL_PROVIDERS

def _enabled(p: Dict[str, Any]) -> bool:
    return bool(p.get("enabled", False))

# =============== Public API (retro-compatible) ===============

def choose_model(task: str = "codegen",
                 modality: Optional[str] = "chat",
                 name_or_auto: str = "auto") -> Dict[str, Any]:
    """
    Backward-compatible model selection.
    Prefers Gateway (/v1/models) as the source of truth; falls back to legacy YAML.
    Returns the full legacy model dict (name, provider, modality, ...).
    """
    # 1) Try Gateway (blocking) unless we're already in an async loop
    cfg: Optional[Dict[str, Any]] = _load_from_gateway_blocking()

    # 2) Fallback to YAML (retro-compat)
    if cfg is None:
        cfg = _load_from_yaml()

    routing = cfg.get("routing", {}) or {}
    models: List[Dict[str, Any]] = cfg.get("models", []) or []

    # Filters
    candidates = [m for m in models if _enabled(m)]
    if modality:
        candidates = [m for m in candidates if str(m.get("modality", "chat")).lower() == modality]
    if not candidates:
        raise RuntimeError(f"no enabled models matching filters (modality={modality})")

    # Explicit name wins
    if name_or_auto != "auto":
        for m in candidates:
            if str(m.get("name")) == name_or_auto:
                return m
        raise RuntimeError(f"model '{name_or_auto}' not found or disabled for modality={modality}")

    # Routing policies (kept as in legacy behaviour)
    if routing.get("never_send_source_to_cloud", False):
        local_only = [m for m in candidates if _is_local(m)]
        if local_only:
            candidates = local_only

    if task == "codegen" and routing.get("prefer_local_for_codegen", False):
        local_only = [m for m in candidates if _is_local(m)]
        if local_only:
            candidates = local_only

    prefer_frontier = (task == "reasoning" and routing.get("prefer_frontier_for_reasoning", False))

    def sort_key(m: Dict[str, Any]):
        cap_rank = SCORE_MAP["capability"].get(str(m.get("capability", "medium")).lower(), 1)
        total = _score(m)
        # prefer frontier == prioritize capability
        return (cap_rank if prefer_frontier else 0, total)

    candidates.sort(key=sort_key)
    return candidates[0]
