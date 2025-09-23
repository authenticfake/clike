# Model routing logic for schemaVersion:2.1 as per your models.yaml.
# Priority: pinned profile -> fallback list -> selector criteria -> global default
# Robust to:
#  - model/fallback nested under 'select' (we normalize)
#  - 'embedding' vs 'embeddings' modality
#  - odd providers (e.g., 'provider: llama3'): normalize by base_url/name
#  - missing fallback IDs: ignored and reported in warnings
# Global policy overrides (soft): NEVER_SEND_SOURCE_TO_CLOUD / prefer_local_for_codegen / prefer_frontier_for_reasoning
from __future__ import annotations
from typing import Dict, Any, List, Optional, Literal, Tuple
import yaml
import os
import logging

from config import settings

Task = Literal["spec","plan","kit","build","chat"]

_CAP_ORD = {"tiny":0,"small":1,"medium":2,"large":3,"frontier":4}
_LAT_ORD = {"ultra-low":3,"low":2,"medium":1,"high":0}
_COST_ORD = {"ultra-low":3,"low":2,"medium":1,"high":0}

log = logging.getLogger("router")

def _as_bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")

def resolve_explain(task: str, hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Wrapper di resolve(...) che restituisce una vista 'spiegabile':
    - chosen: modello scelto (id, provider, base_url, remote_name, tags)
    - profile: profilo usato (da routing[...] o hint)
    - policy: flag/ambienti (optimize_for, redaction, prefer_local, etc.)
    - candidates: ids (best-effort) considerati
    - warnings: eventuali warning
    """
    chosen, warnings = resolve(task=task, hint=hint)  # usa la funzione esistente
    # best-effort: estrai alcune info standard dal chosen
    info = {
        "task": task,
        "hint": hint,
        "chosen": {
            "id": chosen.get("id"),
            "name": chosen.get("name"),
            "provider": chosen.get("provider"),
            "base_url": chosen.get("base_url"),
            "remote_name": chosen.get("remote_name") or chosen.get("model") or chosen.get("name"),
            "tags": chosen.get("tags", []),
            "profile": chosen.get("profile"),  # se la resolve la mette, altrimenti None
        },
        "profile": chosen.get("profile"),
        "policy": {
            # questi campi sono opzionali: se li gestite già in Settings/config, popolateli lì
            "redact_source": chosen.get("redact_source"),
            "optimize_for": chosen.get("optimize_for"),
            "privacy": chosen.get("privacy"),
        },
        # candidate ids best-effort (se la vostra resolve le estrae, altrimenti vuoto)
        "candidates": chosen.get("_candidates", []),
        "warnings": warnings or [],
    }
    # log strutturato per telemetria
    try:
        log.info("router.decision %s", info)
    except Exception:
        pass
    return info

def _resolve_models_path() -> str:
    """
    Decide il path effettivo di configs/models.yaml:

    Priorità:
    1) MODELS_PATH (ENV diretta) se assoluta/esistente
    2) settings.MODELS_CONFIG_PATH (dal tuo config.py) — accetta anche relativo (normalizzato su WORKSPACE_ROOT)
    3) fallback: <WORKSPACE_ROOT>/configs/models.yaml
    4) fallback: /workspace/configs/models.yaml
    """
    candidates = []

    # 1) ENV esplicita (comoda in docker-compose)
    envp = os.getenv("MODELS_PATH")
    if envp:
        p = envp if os.path.isabs(envp) else os.path.abspath(os.path.join(settings.WORKSPACE_ROOT, envp))
        candidates.append(p)

    # 2) Valore dal tuo Settings (MODELS_CONFIG_PATH già calcolato)
    if getattr(settings, "MODELS_CONFIG_PATH", None):
        p = settings.MODELS_CONFIG_PATH
        log.info("settings.MODELS_CONFIG_PATH: %s", p)

        p = p if os.path.isabs(p) else os.path.abspath(os.path.join(settings.WORKSPACE_ROOT, p))
        log.info("yo be candidate: %s", p)

        candidates.append(p)

    # 3) Fallback ragionevoli
    candidates.append(os.path.join(settings.WORKSPACE_ROOT, "configs", "models.yaml"))
    candidates.append("/workspace/configs/models.yaml")

    log.info("models.yaml candidates: %s", candidates)

    for p in candidates:
        if p and os.path.isfile(p):
            return p

    raise FileNotFoundError(
        "models.yaml not found. Checked: " + ", ".join(candidates) +
        ". Set CL_MODELS_PATH=/app/configs/models.yaml (and mount configs/)."
    )


def _load_cfg() -> dict:
    #p = _resolve_models_path()
    p = os.getenv("MODELS_CONFIG_", "/workspace/configs/models.yaml")

    with open(p, "r", encoding="utf-8") as f:
          data = yaml.safe_load(f) or {}
    #logging.getLogger("router").info("Loaded models.yaml: %s", data)
    return data


def _apply_policy(task: str, chosen: dict, m_all: dict) -> dict:
    """
    Applica toggles/policy ai modelli (es. preferenze frontier/local, privacy).
    'chosen' è il modello già selezionato per profilo; puoi sovrascriverlo se necessario.
    """
    # Leggi i flag dal tuo Settings (UPPERCASE)
    prefer_frontier = _as_bool(getattr(settings, "PREFER_FRONTIER_FOR_REASONING", "false"))
    prefer_local    = _as_bool(getattr(settings, "PREFER_LOCAL_FOR_CODEGEN", "false"))
    never_cloud     = _as_bool(getattr(settings, "NEVER_SEND_SOURCE_TO_CLOUD", "false"))

    # Esempi di policy (NON cambiano la tua logica se non l'avevi):
    if prefer_frontier and task in {"spec", "plan", "chat"}:
        # puoi qui sostituire 'chosen' con un frontier se disponibile in m_all
        pass

    if prefer_local and task in {"kit", "build"}:
        # puoi preferire un modello con tag [local] se presente
        pass

    if never_cloud:
        # assicurati che 'chosen' non sia cloud; in caso seleziona fallback 'local'
        pass

    return chosen

def select_model_for_phase(task: str,
                           profile_hint: Optional[str],
                           model_override: Optional[str]) -> Tuple[str, str]:
    """
    Ritorna (model_id, profile_used).
    - se model_override è impostato e != 'auto' → ('quello', 'manual')
    - altrimenti, risolve tramite il tuo 'resolve(task, hint=...)' che legge da models.yaml
    """
    # 1) Modello fissato dall'utente
    if model_override and str(model_override).lower() != "auto":
        return model_override, "manual"

    # 2) Profilo/hint → usa la tua 'resolve'
    chosen, _warn = resolve(task=task, hint=profile_hint)   # <-- usa la tua funzione esistente
    return chosen.get("id"), (chosen.get("profile") or "default")


def _norm_provider(m: Dict[str,Any]) -> str:
    p = (m.get("provider") or "").lower()
    base = (m.get("base_url") or "").lower()
    if p in {"ollama","openai","anthropic","vllm","azure","google","deepseek"}:
        return p
    if "ollama" in base:
        return "ollama"
    if "openai" in base:
        return "openai"
    if "anthropic" in base:
        return "anthropic"
    if "vllm" in base:
        return "vllm"
    return p or "vllm"

def _norm_modality(m: Dict[str,Any]) -> str:
    md = (m.get("modality") or "").lower()
    return "embedding" if md in {"embedding","embeddings"} else (md or "chat")

def _model_id(m: Dict[str, Any]) -> str:
    if m.get("id"):
        return m["id"]
    return f"{_norm_provider(m)}:{m.get('name','unknown')}"

def _quality_signal(tags: List[str]) -> int:
    t = set(tags or [])
    score = 1 if ({"quality","frontier"} & t) else 0
    if "cheap" in t:
        score -= 1
    return score

def _score(m: Dict[str, Any], w: Dict[str, float]) -> float:
    cap = _CAP_ORD.get(m.get("capability","small"), 1)
    lat = _LAT_ORD.get(m.get("latency","medium"), 1)
    cost = _COST_ORD.get(m.get("cost","medium"), 1)
    qual = _quality_signal(m.get("tags", []))
    return (cap*w.get("capability",0.5) + lat*w.get("latency",0.2)
            + cost*w.get("cost",0.2) + qual*w.get("quality",0.1))

def _index_models(models: List[Dict[str,Any]]) -> Dict[str, Dict[str,Any]]:
    idx = {}
    for m in models:
        mm = dict(m)
        mm["provider"] = _norm_provider(mm)
        mm["modality"] = _norm_modality(mm)
        if not mm.get("enabled", True):
            continue
        idx[_model_id(mm)] = mm
    return idx

def _filter_by_selector(models: List[Dict[str,Any]], select: Dict[str,Any]) -> List[Dict[str,Any]]:
    if not select:
        return [m for m in models if m.get("enabled", True)]
    any_tags = set(select.get("any_tags") or [])
    avoid_tags = set(select.get("avoid_tags") or [])
    prefer_providers = set(select.get("prefer_providers") or [])
    out = []
    for m in models:
        if not m.get("enabled", True): 
            continue
        mtags = set(m.get("tags", []))
        if any_tags and not (any_tags & mtags):
            continue
        if avoid_tags & mtags:
            continue
        # prefer_providers is a soft preference handled later if needed
        out.append(m)
    return out

def _apply_policy(task: Task, model: Dict[str,Any], candidates: List[Dict[str,Any]]) -> Dict[str,Any]:
    # Prefer frontier for reasoning tasks
    if settings.PREFER_FRONTIER_FOR_REASONING and task in {"spec","plan","chat"}:
        frontier = [m for m in candidates if "frontier" in (m.get("tags") or [])]
        if frontier and _model_id(model) not in {_model_id(x) for x in frontier}:
            # choose highest capability among frontier
            model = max(frontier, key=lambda m: _CAP_ORD.get(m.get("capability","small"),1))
    # Prefer local for codegen tasks
    if settings.PREFER_LOCAL_FOR_CODEGEN and task in {"kit","build"}:
        local = [m for m in candidates if (m.get("provider") in {"ollama","vllm"} or "local" in (m.get("tags") or []))]
        if local and _model_id(model) not in {_model_id(x) for x in local}:
            model = max(local, key=lambda m: _CAP_ORD.get(m.get("capability","small"),1))
    return model

def _normalize_profile(profile: Dict[str,Any]) -> Dict[str,Any]:
    # Lift `model`/`fallback` out of select if nested
    p = dict(profile or {})
    sel = dict(p.get("select") or {})
    if "model" in sel and "model" not in p:
        p["model"] = sel.pop("model")
    if "fallback" in sel and "fallback" not in p:
        p["fallback"] = sel.pop("fallback")
    p["select"] = sel
    return p

def resolve(task: Task, hint: Optional[str] = None) -> Tuple[Dict[str,Any], List[str]]:
    cfg = _load_cfg()
    logging.info(f"Resolving task={task} with hint={hint}")
    models = cfg.get("models") or []
    profiles = cfg.get("profiles") or {}
    routing = cfg.get("routing") or {}
    weights = (cfg.get("scoring") or {}).get("weights", {})
    defaults = cfg.get("defaults") or {}

    
    log.info(f"Resolving profiles={profiles} ")
    log.info(f"Resolving routing={routing} with weights={weights}")
    m_index = _index_models(models)
    m_all = list(m_index.values())

    warnings: List[str] = []

    # Determine profile name and normalize its shape
    profile_name = hint if (hint and hint in profiles) else routing.get(task)
    profile_raw = profiles.get(profile_name, {}) if profile_name else {}
    profile = _normalize_profile(profile_raw)

    chosen: Dict[str,Any] = {}

    # 1) Pinned model
    pinned = profile.get("model")
    pinned_list = pinned if isinstance(pinned, list) else [pinned] if pinned else []
    for mid in pinned_list:
        if mid in m_index:
            chosen = m_index[mid]
            break
        else:
            warnings.append(f"pinned model '{mid}' not found")

    # 2) Fallback list
    if not chosen:
        for mid in (profile.get("fallback") or []):
            if mid in m_index:
                chosen = m_index[mid]; break
            else:
                warnings.append(f"fallback model '{mid}' not found")

    # 3) Selector criteria
    if not chosen:
        cands = _filter_by_selector(m_all, profile.get("select") or {})
        if cands:
            chosen = max(cands, key=lambda m: _score(m, weights))

    # 4) Global default
    if not chosen and m_all:
        chosen = m_all[0]
        warnings.append("no match: using first enabled model as default")

    # 5) Policy overrides (soft)
    chosen = _apply_policy(task, chosen, m_all)
    chosen["profile"] = profile_name  # es. "plan.fast" / "code.strict" / ...
    # policy semplice: se il modello è cloud (privacy low) attiva redaction
    if chosen.get("privacy") == "low":
        chosen["redact_source"] = True

    # 6) Redaction/flags
    is_cloud = chosen.get("provider") in {"openai","anthropic","azure","google","deepseek"}
    payload = {
        "id": _model_id(chosen),
        "name": chosen.get("name"),
        "provider": chosen.get("provider"),
        "base_url": chosen.get("base_url"),
        "model": chosen.get("remote_name") or chosen.get("name"),
        "temperature": chosen.get("temperature", 0.2),
        "tags": chosen.get("tags", []),
        "modality": chosen.get("modality", "chat"),
        "redact_source": bool(settings.NEVER_SEND_SOURCE_TO_CLOUD and is_cloud),
        "optimize_for": settings.OPTIMIZE_FOR,
        "profile": profile_name or "default",
        "defaults": defaults,
    }
    logging.info(f"Resolving payload={payload}")
    return payload, warnings

# Back-compat helper used by services
def select_profile(task: Task, hint: Optional[str] = None) -> Dict[str, Any]:
    chosen, _ = resolve(task, hint)
    return chosen