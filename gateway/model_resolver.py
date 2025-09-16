# gateway/model_resolver.py
from typing import List, Dict, Optional, Tuple

def _score_by_weights(m: Dict, weights: Dict[str, float]) -> float:
    # capacità: frontier>large>medium>small>tiny → punteggio minore = migliore
    cap = (m.get("capability") or "medium").lower()
    cap_rank = {"frontier": 0, "large": 0.5, "high": 0.75, "medium": 1.0, "small": 1.25, "tiny": 1.5}.get(cap, 1.0)

    # latency: ultra-low>low>medium>high
    lat = (m.get("latency") or "medium").lower()
    lat_rank = {"ultra-low": 0, "low": 0.5, "medium": 1.0, "high": 1.5}.get(lat, 1.0)

    # cost: ultra-low>low>medium>high
    cost = (m.get("cost") or "medium").lower()
    cost_rank = {"ultra-low": 0, "low": 0.5, "medium": 1.0, "high": 1.5}.get(cost, 1.0)

    # quality tag
    tags = set(m.get("tags") or [])
    q = 0.0
    if "quality" in tags or "frontier" in tags: q -= 0.5
    if "cheap" in tags: q += 0.5

    return (
        weights.get("capability", 0.5) * cap_rank
        + weights.get("latency", 0.2) * lat_rank
        + weights.get("cost", 0.2) * cost_rank
        + weights.get("quality", 0.1) * q
    )

def _filter_candidates(models: List[Dict], *, want_modality: Optional[str], select: Dict) -> List[Dict]:
    out = [m for m in models if m.get("enabled", True)]
    if want_modality:
        out = [m for m in out if (m.get("modality") == want_modality)]
    any_tags = set((select or {}).get("any_tags") or [])
    avoid_tags = set((select or {}).get("avoid_tags") or [])
    prefer_providers = set((select or {}).get("prefer_providers") or [])
    if any_tags:
        out = [m for m in out if any(t in (m.get("tags") or []) for t in any_tags)]
    if avoid_tags:
        out = [m for m in out if not any(t in (m.get("tags") or []) for t in avoid_tags)]
    if prefer_providers:
        # sposta in testa i provider preferiti
        out.sort(key=lambda m: 0 if (m.get("provider") in prefer_providers) else 1)
    return out

def _resolve_by_name(models: List[Dict], name: str, *, want_modality: Optional[str]) -> Dict:
    cands = [m for m in models if m.get("enabled", True)]
    if want_modality:
        cands = [m for m in cands if (m.get("modality") == want_modality)]
    for m in cands:
        if m.get("name") == name or m.get("id") == name:
            return m
    raise RuntimeError(f"model '{name}' not found or disabled")

def resolve_model(
    cfg: Dict,
    models: List[Dict],
    name_or_auto: str,
    *,
    profile: Optional[str] = None,
    want_modality: Optional[str] = None
) -> Dict:
    """
    - Se name_or_auto è un nome modello → prende quello (compat attuale).
    - Se profile è valorizzato o name_or_auto coincide con un profilo → usa 'profiles' di cfg.
    - Altrimenti 'auto' con preferenza locale e tie-break tramite 'scoring' di cfg.
    """
    name_or_auto = (name_or_auto or "auto").strip()

    # 1) name puntato esplicito → compat
    if name_or_auto != "auto" and ":" not in name_or_auto and (profile is None):
        try:
            return _resolve_by_name(models, name_or_auto, want_modality=want_modality)
        except RuntimeError:
            pass  # prosegui (potrebbe essere un profilo con lo stesso nome umano)

    # 2) profilo (esplicito o dedotto dal name_or_auto)
    prof_key = profile or (name_or_auto if "." in name_or_auto else None)
    profiles = (cfg or {}).get("profiles") or {}
    if prof_key and prof_key in profiles:
        p = profiles[prof_key] or {}
        # se c’è un pin 'model', risolviamo quello direttamente
        pinned = (p.get("model") or "").strip()
        if pinned:
            return _resolve_by_name(models, pinned, want_modality=want_modality)
        # altrimenti selettore + scoring
        select = p.get("select") or {}
        cands = _filter_candidates(models, want_modality=want_modality, select=select)
        if not cands:
            raise RuntimeError(f"profile '{prof_key}': no candidates after filters")
        weights = ((cfg.get("scoring") or {}).get("weights") or {})
        cands.sort(key=lambda m: _score_by_weights(m, weights))
        return cands[0]

    # 3) AUTO: prefer locali (ollama/vllm), poi scoring
    def is_local(m): return (m.get("provider") or "").lower() in {"ollama", "vllm"}
    cands = [m for m in models if m.get("enabled", True)]
    if want_modality:
        cands = [m for m in cands if (m.get("modality") == want_modality)]
    if not cands:
        raise RuntimeError("no enabled models matching filters")
    locals_first = [m for m in cands if is_local(m)] or cands
    weights = ((cfg.get("scoring") or {}).get("weights") or {})
    locals_first.sort(key=lambda m: _score_by_weights(m, weights))
    return locals_first[0]
