"""Single source of truth for which model providers are usable right now.

The gateway is the only process that holds the cloud API keys in its
environment, so it owns the decision of whether a provider can be reached:

- cloud providers (openai/anthropic/deepseek) are available when their API key
  env var is set to a non-empty value;
- local providers (ollama/vllm) are available when their base URL answers.

Orchestrator and the VS Code extension consume this via GET /v1/providers and
the annotated GET /v1/models, so the "cloud yes/no" decision is computed in
exactly one place.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Dict, Tuple

import httpx

log = logging.getLogger("gateway.providers")

# provider -> env var holding its API key
_CLOUD_KEY_ENV: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# provider -> (base-url env var, default base url)
_LOCAL_BASE_ENV: Dict[str, Tuple[str, str]] = {
    "ollama": ("OLLAMA_BASE_URL", "http://ollama:11434"),
    "vllm": ("VLLM_BASE_URL", "http://vllm:8000/v1"),
}

_CACHE: Dict[str, object] = {"ts": 0.0, "data": None}
_TTL_SECONDS = 30.0
_REACH_TIMEOUT = 1.5


def _key_present(env_name: str) -> bool:
    # Q4: only "absent" or "present but zero-length" counts as missing.
    value = os.getenv(env_name)
    return bool(value and value.strip())


async def _reachable(client: httpx.AsyncClient, base: str) -> bool:
    if not base:
        return False
    try:
        r = await client.get(base.rstrip("/"))
        # Any answer (even 404) proves the local runtime is up; only connection
        # failures or 5xx mean "not reachable".
        return r.status_code < 500
    except httpx.HTTPError:
        return False


async def provider_availability(*, use_cache: bool = True) -> Dict[str, object]:
    now = time.time()
    cached = _CACHE.get("data")
    if use_cache and isinstance(cached, dict) and (now - float(_CACHE["ts"]) < _TTL_SECONDS):
        return cached

    providers: Dict[str, bool] = {}
    reasons: Dict[str, str] = {}

    for prov, env_name in _CLOUD_KEY_ENV.items():
        ok = _key_present(env_name)
        providers[prov] = ok
        if not ok:
            reasons[prov] = f"missing {env_name}"

    async with httpx.AsyncClient(timeout=_REACH_TIMEOUT) as client:
        for prov, (env_name, default) in _LOCAL_BASE_ENV.items():
            base = os.getenv(env_name, default)
            ok = await _reachable(client, base)
            providers[prov] = ok
            if not ok:
                reasons[prov] = f"{prov} not reachable at {base}"

    any_cloud = any(providers.get(p) for p in _CLOUD_KEY_ENV)
    any_local = any(providers.get(p) for p in _LOCAL_BASE_ENV)

    data: Dict[str, object] = {
        "providers": providers,
        "reasons": reasons,
        "any_cloud": any_cloud,
        "any_local": any_local,
        "any": any_cloud or any_local,
    }
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data


def cloud_key_env(provider: str) -> str | None:
    return _CLOUD_KEY_ENV.get((provider or "").strip().lower())


def model_availability(provider: str, availability: Dict[str, object]) -> Tuple[bool, str]:
    """Resolve availability for one model's provider against a computed snapshot.

    Unknown providers are treated as available so the catalog never hides models
    the gateway does not explicitly understand how to gate.
    """
    prov = (provider or "").strip().lower()
    providers = availability.get("providers") or {}
    reasons = availability.get("reasons") or {}
    if prov in providers:
        ok = bool(providers[prov])
        return ok, ("" if ok else str(reasons.get(prov, "provider unavailable")))
    return True, ""
