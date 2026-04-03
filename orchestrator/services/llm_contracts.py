from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional, List

import httpx
import yaml

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

log = logging.getLogger("orchestrator.llm_contracts")


def _models_cfg_path() -> str:
    """
    Resolve the models catalog path robustly across:
    - explicit MODELS_CONFIG
    - local dev checkout
    - Docker image layout (/app)
    - workspace layout (/workspace)
    """
    env_path = os.getenv("MODELS_CONFIG")
    candidates = []

    if env_path:
        candidates.append(Path(env_path))

    here = Path(__file__).resolve()
    repo_root = here.parents[2]  # .../orchestrator/services/llm_contracts.py -> repo root
    candidates.extend(
        [
            repo_root / "configs" / "models.yaml",
            Path("/app/configs/models.yaml"),
            Path("/workspace/configs/models.yaml"),
            Path.cwd() / "configs" / "models.yaml",
        ]
    )

    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return str(p)
        except Exception:
            continue

    # Keep last-resort deterministic path for error messages
    return str(candidates[-1])


def _load_yaml_catalog() -> Dict[str, Any]:
    with open(_models_cfg_path(), "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "version": "2.3",
        "models": data.get("models") or [],
        "profiles": data.get("profiles") or {},
        "routing": data.get("routing") or {},
        "scoring": data.get("scoring") or {},
        "aliases": data.get("aliases") or {},
        "validation": data.get("validation") or {},
    }


async def _load_gateway_catalog(base_url: str) -> Optional[Dict[str, Any]]:
    """
    Accept only the new catalog shape.
    Reject legacy payloads such as {"data":[...]} so the caller can fall back cleanly.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(base_url.rstrip("/") + "/v1/models")
            r.raise_for_status()
            data = r.json()

            if isinstance(data, dict) and isinstance(data.get("models"), list):
                return {
                    "version": data.get("version") or "2.x",
                    "models": data.get("models") or [],
                    "profiles": data.get("profiles") or {},
                    "routing": data.get("routing") or {},
                    "scoring": data.get("scoring") or {},
                    "aliases": data.get("aliases") or {},
                    "validation": data.get("validation") or {},
                }

            log.warning("gateway /v1/models returned legacy or invalid shape: %s", type(data).__name__)
    except Exception as e:
        log.warning("gateway catalog unavailable: %s", e)

    return None


async def load_catalog(base_url: str) -> Dict[str, Any]:
    gw = await _load_gateway_catalog(base_url)
    if gw:
        return gw
    return _load_yaml_catalog()


def load_catalog_local() -> Dict[str, Any]:
    return _load_yaml_catalog()


def _normalize_modality(value: Optional[str]) -> str:
    v = str(value or "chat").strip().lower()
    if v in {"embed", "embedding", "embeddings"}:
        return "embeddings"
    return v


def _is_enabled(m: Dict[str, Any]) -> bool:
    return bool(m.get("enabled", True))


def _match_model(models: List[Dict[str, Any]], wanted: str) -> Optional[Dict[str, Any]]:
    w = (wanted or "").strip().lower()
    if not w:
        return None

    for m in models or []:
        vals = {
            str(m.get("id") or "").strip().lower(),
            str(m.get("name") or "").strip().lower(),
            str(m.get("remote_name") or "").strip().lower(),
        }
        vals.discard("")
        if w in vals:
            return m
    return None


def _score_by_weights(m: Dict[str, Any], weights: Dict[str, float]) -> float:
    cap = (m.get("capability") or "medium").lower()
    cap_rank = {
        "frontier": 0.0,
        "large": 0.5,
        "high": 0.75,
        "medium": 1.0,
        "small": 1.25,
        "tiny": 1.5,
        "low": 1.25,
    }.get(cap, 1.0)

    lat = (m.get("latency") or "medium").lower()
    lat_rank = {
        "ultra-low": 0.0,
        "low": 0.5,
        "medium": 1.0,
        "high": 1.5,
    }.get(lat, 1.0)

    cost = (m.get("cost") or "medium").lower()
    cost_rank = {
        "ultra-low": 0.0,
        "low": 0.5,
        "medium": 1.0,
        "high": 1.5,
    }.get(cost, 1.0)

    privacy = (m.get("privacy") or "medium").lower()
    privacy_rank = {
        "high": 0.0,
        "medium": 0.5,
        "low": 1.0,
    }.get(privacy, 0.5)

    tags = set(m.get("tags") or [])
    quality_bonus = 0.0
    if "quality" in tags or "frontier" in tags or "reasoning" in tags:
        quality_bonus -= 0.5
    if "cheap" in tags:
        quality_bonus += 0.5

    return (
        weights.get("capability", 0.45) * cap_rank
        + weights.get("latency", 0.20) * lat_rank
        + weights.get("cost", 0.20) * cost_rank
        + weights.get("privacy", 0.05) * privacy_rank
        + weights.get("quality", 0.10) * quality_bonus
    )


def _filter_candidates(
    models: List[Dict[str, Any]],
    *,
    want_modality: Optional[str],
    select: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    out = [m for m in models if _is_enabled(m)]

    if want_modality:
        wm = _normalize_modality(want_modality)
        out = [m for m in out if _normalize_modality(m.get("modality")) in {wm, "responses" if wm == "chat" else wm}]

    select = select or {}
    any_tags = set(select.get("any_tags") or [])
    avoid_tags = set(select.get("avoid_tags") or [])
    prefer_providers = set(select.get("prefer_providers") or [])

    if any_tags:
        out = [m for m in out if any(t in (m.get("tags") or []) for t in any_tags)]
    if avoid_tags:
        out = [m for m in out if not any(t in (m.get("tags") or []) for t in avoid_tags)]

    if prefer_providers:
        out.sort(key=lambda m: 0 if str(m.get("provider") or "").lower() in prefer_providers else 1)

    return out


def _select_best(catalog: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        raise RuntimeError("no candidate models available")

    weights = ((catalog.get("scoring") or {}).get("weights") or {})
    ordered = sorted(candidates, key=lambda m: _score_by_weights(m, weights))
    return ordered[0]


def _is_local_provider(provider: Optional[str]) -> bool:
    return str(provider or "").lower() in {"ollama", "vllm"}


def _apply_routing_policies(catalog: Dict[str, Any], mode: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    routing = catalog.get("routing") or {}
    out = list(candidates)

    never_send_source_to_cloud = bool(routing.get("never_send_source_to_cloud", False))
    prefer_local_for_codegen = bool(routing.get("prefer_local_for_codegen", False))
    prefer_frontier_for_reasoning = bool(routing.get("prefer_frontier_for_reasoning", False))

    if mode in {"coding", "harper"} and never_send_source_to_cloud:
        local = [m for m in out if _is_local_provider(m.get("provider"))]
        if local:
            return local

    if mode in {"coding", "harper"} and prefer_local_for_codegen:
        local = [m for m in out if _is_local_provider(m.get("provider"))]
        if local:
            out = local

    if mode == "free" and prefer_frontier_for_reasoning:
        frontier = [m for m in out if (m.get("capability") or "").lower() in {"frontier", "large", "high"}]
        if frontier:
            out = frontier

    return out


def _resolve_from_profile(
    catalog: Dict[str, Any],
    models: List[Dict[str, Any]],
    profile_name: str,
    *,
    requested_provider: Optional[str],
    mode: str,
) -> Dict[str, Any]:
    profiles = catalog.get("profiles") or {}
    p = profiles.get(profile_name) or {}
    pinned = str(p.get("model") or "").strip()

    if pinned:
        entry = _match_model(models, pinned)
        if entry and _is_enabled(entry):
            return entry

    cands = _filter_candidates(
        models,
        want_modality="chat",
        select=p.get("select") or {},
    )

    if requested_provider:
        rp = requested_provider.strip().lower()
        provider_cands = [m for m in cands if str(m.get("provider") or "").lower() == rp]
        if provider_cands:
            cands = provider_cands

    cands = _apply_routing_policies(catalog, mode, cands)
    return _select_best(catalog, cands)


def _resolve_direct_or_auto(
    catalog: Dict[str, Any],
    models: List[Dict[str, Any]],
    *,
    requested_model: str,
    requested_provider: Optional[str],
    mode: str,
) -> Optional[Dict[str, Any]]:
    req = (requested_model or "").strip()
    if req and req.lower() != "auto":
        entry = _match_model(models, req)
        if not entry:
            raise RuntimeError(f"model '{req}' not found in catalog")
        if not _is_enabled(entry):
            raise RuntimeError(f"model '{req}' is disabled")
        if requested_provider:
            rp = requested_provider.strip().lower()
            ep = str(entry.get("provider") or "").lower()
            if ep and ep != rp:
                raise RuntimeError(f"provider override '{rp}' conflicts with resolved model provider '{ep}'")
        return entry

    cands = _filter_candidates(models, want_modality="chat", select=None)

    if requested_provider:
        rp = requested_provider.strip().lower()
        provider_cands = [m for m in cands if str(m.get("provider") or "").lower() == rp]
        if provider_cands:
            cands = provider_cands

    cands = _apply_routing_policies(catalog, mode, cands)
    if not cands:
        return None
    return _select_best(catalog, cands)


def _mode_contract(mode: str, phase: Optional[str] = None) -> Dict[str, Any]:
    m = (mode or "free").strip().lower()
    phase = (phase or "").strip().lower() or None

    if m == "free":
        return {
            "mode": "free",
            "allow_file_output": False,
            "prefer_tools": False,
            "prefer_response_format": True,
            "require_phase_artifacts": False,
            "history_policy": "chat",
            "rag_policy": "allowed",
        }

    if m == "coding":
        return {
            "mode": "coding",
            "allow_file_output": True,
            "prefer_tools": True,
            "prefer_response_format": True,
            "require_phase_artifacts": False,
            "history_policy": "coding",
            "rag_policy": "allowed",
        }

    if m == "harper":
        return {
            "mode": "harper",
            "phase": phase,
            "allow_file_output": True,
            "prefer_tools": True,
            "prefer_response_format": True,
            "require_phase_artifacts": True,
            "history_policy": "harper",
            "rag_policy": "allowed",
        }

    return {
        "mode": m,
        "allow_file_output": False,
        "prefer_tools": False,
        "prefer_response_format": True,
        "require_phase_artifacts": False,
        "history_policy": "chat",
        "rag_policy": "allowed",
    }


def _default_profile_for(mode: str, phase: Optional[str], requested_model: str) -> Optional[str]:
    req = (requested_model or "").strip().lower()
    if req and req != "auto":
        return None

    m = (mode or "free").strip().lower()
    p = (phase or "").strip().lower()

    if m == "free":
        return "chat.cheap"
    if m == "coding":
        return "code.strict"
    if m == "harper":
        if p == "plan":
            return "plan.fast"
        if p in {"kit", "build"}:
            return "code.strict"
        return "chat.cheap"
    return None


def _selection_from_entry(
    entry: Dict[str, Any],
    *,
    profile: Optional[str],
    mode: str,
    phase: Optional[str],
) -> Dict[str, Any]:
    return {
        "model": entry.get("id") or entry.get("name"),
        "provider": str(entry.get("provider") or "").strip().lower() or None,
        "remote_name": entry.get("remote_name") or entry.get("name") or entry.get("id"),
        "profile": profile,
        "catalog_entry": entry,
        "mode_contract": _mode_contract(mode, phase),
    }


async def resolve_llm_selection(
    *,
    base_url: str,
    mode: str,
    phase: Optional[str],
    requested_model: str,
    requested_provider: Optional[str],
    profile_hint: Optional[str],
) -> Dict[str, Any]:
    catalog = await load_catalog(base_url)
    validation = catalog.get("validation") or {}
    if validation and not validation.get("ok", True):
        log.warning("catalog validation has errors: %s", validation.get("errors"))

    models = catalog.get("models") or []
    requested_model = (requested_model or "auto").strip()
    requested_provider = (requested_provider or "").strip().lower() or None
    profile = profile_hint or _default_profile_for(mode, phase, requested_model)

    if profile:
        try:
            entry = _resolve_from_profile(
                catalog,
                models,
                profile,
                requested_provider=requested_provider,
                mode=mode,
            )
            return _selection_from_entry(entry, profile=profile, mode=mode, phase=phase)
        except Exception as e:
            log.warning("profile-based resolution failed for profile=%s: %s", profile, e)

    entry = _resolve_direct_or_auto(
        catalog,
        models,
        requested_model=requested_model,
        requested_provider=requested_provider,
        mode=mode,
    )
    if entry:
        return _selection_from_entry(entry, profile=profile, mode=mode, phase=phase)

    return {
        "model": requested_model or "auto",
        "provider": requested_provider,
        "remote_name": None,
        "profile": profile,
        "catalog_entry": None,
        "mode_contract": _mode_contract(mode, phase),
    }