from typing import List, Dict, Optional, Any


def _score_by_weights(m: Dict[str, Any], weights: Dict[str, float]) -> float:
    cap = (m.get("capability") or "medium").lower()
    cap_rank = {
        "frontier": 0.0,
        "large": 0.5,
        "high": 0.75,
        "medium": 1.0,
        "small": 1.25,
        "tiny": 1.5,
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

    tags = set(m.get("tags") or [])
    q = 0.0
    if "quality" in tags or "frontier" in tags:
        q -= 0.5
    if "cheap" in tags:
        q += 0.5

    return (
        weights.get("capability", 0.5) * cap_rank
        + weights.get("latency", 0.2) * lat_rank
        + weights.get("cost", 0.2) * cost_rank
        + weights.get("quality", 0.1) * q
    )


def _is_enabled(m: Dict[str, Any]) -> bool:
    return bool(m.get("enabled", True))


def _normalize_modality(m: Dict[str, Any]) -> str:
    mod = str(m.get("modality") or "chat").strip().lower()
    if mod in {"embedding", "embeddings", "embed"}:
        return "embeddings"
    return mod


def _matches_model(m: Dict[str, Any], wanted: str) -> bool:
    w = (wanted or "").strip().lower()
    if not w:
        return False

    vals = {
        str(m.get("id") or "").strip().lower(),
        str(m.get("name") or "").strip().lower(),
        str(m.get("remote_name") or "").strip().lower(),
    }
    vals.discard("")
    return w in vals


def _filter_candidates(
    models: List[Dict[str, Any]],
    *,
    want_modality: Optional[str],
    select: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    out = [m for m in models if _is_enabled(m)]

    if want_modality:
        wm = want_modality.strip().lower()
        out = [m for m in out if _normalize_modality(m) == wm]

    select = select or {}
    any_tags = set(select.get("any_tags") or [])
    avoid_tags = set(select.get("avoid_tags") or [])
    prefer_providers = set(select.get("prefer_providers") or [])

    if any_tags:
        out = [m for m in out if any(t in (m.get("tags") or []) for t in any_tags)]
    if avoid_tags:
        out = [m for m in out if not any(t in (m.get("tags") or []) for t in avoid_tags)]

    if prefer_providers:
        out.sort(key=lambda m: 0 if (m.get("provider") in prefer_providers) else 1)

    return out


def _resolve_explicit_model(
    models: List[Dict[str, Any]],
    wanted: str,
    *,
    want_modality: Optional[str],
) -> Dict[str, Any]:
    cands = [m for m in models if _is_enabled(m)]
    if want_modality:
        cands = [m for m in cands if _normalize_modality(m) == want_modality.lower()]

    for m in cands:
        if _matches_model(m, wanted):
            return m

    raise RuntimeError(f"model '{wanted}' not found or disabled")


def _select_best(
    cfg: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not candidates:
        raise RuntimeError("no candidate models available")

    weights = ((cfg.get("scoring") or {}).get("weights") or {})
    ordered = sorted(candidates, key=lambda m: _score_by_weights(m, weights))
    return ordered[0]


def resolve_model(
    cfg: Dict[str, Any],
    models: List[Dict[str, Any]],
    name_or_auto: str,
    *,
    profile: Optional[str] = None,
    want_modality: Optional[str] = None,
) -> Dict[str, Any]:
    requested = (name_or_auto or "auto").strip()

    # 1) Explicit profile
    profiles = (cfg or {}).get("profiles") or {}
    profile_key = (profile or "").strip() or (
        requested if requested and requested in profiles else None
    )

    if profile_key and profile_key in profiles:
        p = profiles[profile_key] or {}
        pinned = str(p.get("model") or "").strip()
        if pinned:
            return _resolve_explicit_model(
                models,
                pinned,
                want_modality=want_modality,
            )

        cands = _filter_candidates(
            models,
            want_modality=want_modality,
            select=p.get("select") or {},
        )
        return _select_best(cfg, cands)

    # 2) Explicit model
    if requested and requested.lower() != "auto":
        return _resolve_explicit_model(
            models,
            requested,
            want_modality=want_modality,
        )

    # 3) AUTO
    cands = _filter_candidates(
        models,
        want_modality=want_modality,
        select=None,
    )

    routing = (cfg or {}).get("routing") or {}
    prefer_local_for_codegen = bool(routing.get("prefer_local_for_codegen", False))
    never_send_source_to_cloud = bool(routing.get("never_send_source_to_cloud", False))

    def _is_local(m: Dict[str, Any]) -> bool:
        return str(m.get("provider") or "").lower() in {"ollama", "vllm"}

    if never_send_source_to_cloud:
        local = [m for m in cands if _is_local(m)]
        if local:
            cands = local
    elif prefer_local_for_codegen:
        local = [m for m in cands if _is_local(m)]
        if local:
            cands = local

    return _select_best(cfg, cands)