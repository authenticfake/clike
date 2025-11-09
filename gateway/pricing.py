# gateway/pricing.py
from __future__ import annotations
import os, json, yaml, logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# Chiave attesa in models.yaml:
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
        # key: model_id (es. "anthropic:claude-sonnet-4-5")
        self._table = table

    @staticmethod
    def _read_models_yaml(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def from_models_yaml(cls, path: Optional[str] = None) -> "PricingManager":
        path = path or os.getenv("HARPER_MODELS_PATH", "config/models.yaml")
        data = cls._read_models_yaml(path)
        log.info("Found %d models in %s", len(data.get("models") or []), path)
        table: Dict[str, Pricing] = {}

        for m in (data.get("models") or []):
            log.info("Found model: %s", m)
           #mid = m.get("id") or _mk_id(m.get("provider"), m.get("name"))
            mid = m.get("remote_name")
            pr = m.get("pricing") or {}
            # supporta anche alias price_* usati in alcune repo
            inp = pr.get("input_per_1k", pr.get("price_input_per_1k", 0.0)) or 0.0
            out = pr.get("output_per_1k", pr.get("price_output_per_1k", 0.0)) or 0.0
            table[str(mid)] = Pricing(float(inp), float(out))

        # fallback opzionale da env (JSON dict {model_id: {input_per_1k, output_per_1k}})
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
        # tenta model_id diretto, altrimenti provider:name
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
        p = self.for_model(model_id, provider, name)
        itok = int(usage.get("input_tokens") or 0)
        otok = int(usage.get("output_tokens") or 0)
        return p.estimate(itok, otok)

def _mk_id(provider: Optional[str], name: Optional[str]) -> str:
    return f"{provider}:{name}".lower()
