from __future__ import annotations

from typing import Any, Dict, List, Set


_ALLOWED_PROVIDERS = {
    "openai",
    "anthropic",
    "ollama",
    "vllm",
    "deepseek",
    "azure_openai",
}

_ALLOWED_MODALITIES = {
    "chat",
    "responses",
    "completion",
    "embeddings",
}

_ALLOWED_COSTS = {"ultra-low", "low", "medium", "high"}
_ALLOWED_LATENCIES = {"ultra-low", "low", "medium", "high"}
_ALLOWED_PRIVACY = {"low", "medium", "high"}
_ALLOWED_CAPABILITY = {"tiny", "small", "medium", "high", "large", "frontier"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _collect_index(models: List[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for m in models or []:
        v = _norm(m.get(key))
        if not v:
            continue
        out.setdefault(v, []).append(m)
    return out


def validate_catalog(data: Dict[str, Any], models: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    models = models or []
    profiles = (data or {}).get("profiles") or {}
    routing = (data or {}).get("routing") or {}

    ids_idx = _collect_index(models, "id")
    names_idx = _collect_index(models, "name")
    remotes_idx = _collect_index(models, "remote_name")

    for label, idx in (("id", ids_idx), ("name", names_idx), ("remote_name", remotes_idx)):
        for key, items in idx.items():
            if len(items) > 1:
                errors.append(f"duplicate {label}: '{key}'")

    all_keys: Set[str] = set()
    for m in models:
        for k in ("id", "name", "remote_name"):
            v = _norm(m.get(k))
            if v:
                all_keys.add(v)

    for i, m in enumerate(models):
        mid = str(m.get("id") or "").strip()
        name = str(m.get("name") or "").strip()
        provider = _norm(m.get("provider"))
        modality = _norm(m.get("modality"))
        capability = _norm(m.get("capability"))
        latency = _norm(m.get("latency"))
        cost = _norm(m.get("cost"))
        privacy = _norm(m.get("privacy"))

        if not mid:
            errors.append(f"models[{i}] missing id")
        if not name:
            errors.append(f"models[{i}] missing name")
        if provider not in _ALLOWED_PROVIDERS:
            errors.append(f"model '{mid or name}' invalid provider '{provider}'")
        if modality not in _ALLOWED_MODALITIES:
            errors.append(f"model '{mid or name}' invalid modality '{modality}'")

        if capability and capability not in _ALLOWED_CAPABILITY:
            warnings.append(f"model '{mid or name}' unusual capability '{capability}'")
        if latency and latency not in _ALLOWED_LATENCIES:
            warnings.append(f"model '{mid or name}' unusual latency '{latency}'")
        if cost and cost not in _ALLOWED_COSTS:
            warnings.append(f"model '{mid or name}' unusual cost '{cost}'")
        if privacy and privacy not in _ALLOWED_PRIVACY:
            warnings.append(f"model '{mid or name}' unusual privacy '{privacy}'")

        remote_name = str(m.get("remote_name") or "").strip()
        if provider == "openai" and not remote_name:
            errors.append(f"openai model '{mid or name}' missing remote_name")

        if provider == "anthropic" and modality == "embeddings":
            errors.append(f"anthropic model '{mid or name}' cannot be embeddings")

    for pname, pdef in profiles.items():
        if not isinstance(pdef, dict):
            errors.append(f"profile '{pname}' must be an object")
            continue

        pinned = _norm(pdef.get("model"))
        if pinned and pinned not in all_keys:
            errors.append(f"profile '{pname}' points to unknown model '{pinned}'")

        fallback = pdef.get("fallback") or []
        if isinstance(fallback, list):
            for f in fallback:
                ff = _norm(f)
                if ff and ff not in all_keys:
                    warnings.append(f"profile '{pname}' fallback unknown '{ff}'")

        select = pdef.get("select")
        if select is not None and not isinstance(select, dict):
            errors.append(f"profile '{pname}'.select must be an object")

    for task, profile_name in routing.items():
        pn = _norm(profile_name)
        if pn and profile_name not in profiles:
            errors.append(f"routing '{task}' points to unknown profile '{profile_name}'")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "models": len(models),
            "profiles": len(profiles),
            "routing_rules": len(routing),
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }