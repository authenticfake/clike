# gateway/pricing.py
from __future__ import annotations
import os, json, yaml, logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Expected key in models.yaml:
# models:
#   - id: openai:gpt-5
#     provider: openai
#     name: gpt-5
#     pricing:
#       input_per_1k: 0.005
#       output_per_1k: 0.015
log = logging.getLogger(__name__)
@dataclass(frozen=True)
class Pricing:
    input_per_1k: float = 0.0
    output_per_1k: float = 0.0
    # price of cache-read input tokens; None = not listed (charged as normal input)
    cached_input_per_1k: Optional[float] = None
    # Anthropic prompt-cache writes (5-minute and 1-hour TTL); None = charged as normal input
    cache_write_per_1k: Optional[float] = None
    cache_write_1h_per_1k: Optional[float] = None

    def estimate_usage(self, usage: Dict[str, Any], *, cached_in_input: bool) -> Dict[str, Any]:
        """Cost of a provider usage block, prompt cache included.

        OpenAI-style usage counts cache reads inside input_tokens (input_tokens_details /
        prompt_tokens_details.cached_tokens); Anthropic-style usage reports cache reads
        (cache_read_input_tokens) and writes (cache_creation_input_tokens, split by TTL in
        cache_creation) apart from input_tokens."""
        u = usage or {}
        details = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
        inp = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
        cached = int(u.get("cache_read_input_tokens") or (details.get("cached_tokens") if isinstance(details, dict) else 0) or 0)
        creation = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
        write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
        write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
        if not (write_1h or write_5m):
            write_5m = int(u.get("cache_creation_input_tokens") or 0)
        out = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
        fresh = max(inp - cached, 0) if cached_in_input else inp
        rate = lambda v, default: default if v is None else v  # noqa: E731
        cached_cost = cached / 1000.0 * rate(self.cached_input_per_1k, self.input_per_1k)
        write_rate = rate(self.cache_write_per_1k, self.input_per_1k)
        write_cost = write_5m / 1000.0 * write_rate + write_1h / 1000.0 * rate(self.cache_write_1h_per_1k, write_rate)
        input_cost = fresh / 1000.0 * self.input_per_1k + cached_cost + write_cost
        output_cost = out / 1000.0 * self.output_per_1k
        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
            "cached_tokens": cached,
            "cache_write_tokens": write_5m + write_1h,
            "cached_cost": round(cached_cost, 6),
            "cache_write_cost": round(write_cost, 6),
        }

    def estimate(self, input_tokens: int = 0, output_tokens: int = 0) -> Dict[str, float]:
        ic = (input_tokens / 1000.0) * self.input_per_1k
        oc = (output_tokens / 1000.0) * self.output_per_1k
        return {
            "input_cost": round(ic, 6),
            "output_cost": round(oc, 6),
            "total_cost": round(ic + oc, 6),
        }

class PricingManager:
    def __init__(self, table: Dict[str, Pricing]):
        # key: model_id (e.g. "anthropic:claude-sonnet-4-5")
        self._table = table

    @staticmethod
    def _read_models_yaml(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def from_models_yaml(cls, path: Optional[str] = None) -> "PricingManager":
        log.info("Loading models from %s", path)

        path = path or os.getenv("MODELS_CONFIG", "../config/models.yaml")
        data = cls._read_models_yaml(path)
        log.info("Found %d models in %s", len(data.get("models") or []), path)
        table: Dict[str, Pricing] = {}

        for m in (data.get("models") or []):
            mid = m.get("id") or _mk_id(m.get("provider"), m.get("name"))
            #mid = m.get("remote_name")
            pr = m.get("pricing") or {}
            # also supports price_* aliases used in some repos
            inp = pr.get("input_per_1k", pr.get("price_input_per_1k", 0.0)) or 0.0
            out = pr.get("output_per_1k", pr.get("price_output_per_1k", 0.0)) or 0.0
            opt = lambda key: None if pr.get(key) is None else float(pr[key])  # noqa: E731
            table[str(mid)] = Pricing(
                float(inp), float(out), opt("cached_input_per_1k"), opt("cache_write_per_1k"), opt("cache_write_1h_per_1k"),
            )

        # optional fallback from env (JSON dict {model_id: {input_per_1k, output_per_1k}})
        extra = os.getenv("HARPER_PRICING_JSON")
        if extra:
            try:
                blob = json.loads(extra)
                for mid, pr in (blob or {}).items():
                    table[str(mid)] = Pricing(
                        float(pr.get("input_per_1k", 0.0)),
                        float(pr.get("output_per_1k", 0.0)),
                    )
            except Exception:
                pass

        return cls(table)

    def for_model(self, model_id: Optional[str], provider: Optional[str], name: Optional[str]) -> Pricing:
        # try model_id directly, otherwise provider:name
        keys = []
        if model_id:
            keys.append(model_id)
        if provider and name:
            keys.append(_mk_id(provider, name))
        for k in keys:
            if k in self._table:
                return self._table[k]
        # default: zero cost
        return Pricing()

    def estimate_cost(
        self,
        model_id: Optional[str],
        provider: Optional[str],
        name: Optional[str],
        usage: Dict[str, Any],
    ) -> Dict[str, float]:
        log.info("Pricing estimate_cost for model %s", model_id)

        p = self.for_model(model_id, provider, name)
        family = str(provider or (model_id or "").split(":", 1)[0]).lower()
        return p.estimate_usage(usage or {}, cached_in_input=family != "anthropic")

    def has_price(self, model_id: str) -> bool:
        p = self._table.get(model_id)
        return bool(p and (p.input_per_1k or p.output_per_1k))

    def estimate_agent_run(self, model_id: str, usage: Dict[str, Any], *, input_includes_cached: bool) -> Optional[Dict[str, Any]]:
        """API-equivalent cost of a local-agent run (the subscription is not billed per token).

        Codex (OpenAI usage) counts cache reads inside input_tokens; Claude Code (Anthropic usage)
        reports them apart, with cache writes in cache_creation_input_tokens. None if unpriced."""
        if not self.has_price(model_id):
            return None
        est = self._table[model_id].estimate_usage(usage or {}, cached_in_input=input_includes_cached)
        return {**est, "unit": "usd_api_equivalent", "estimated": True, "price_source": model_id}


def _mk_id(provider: Optional[str], name: Optional[str]) -> str:
    return f"{provider}:{name}".lower()
