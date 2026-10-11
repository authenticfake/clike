"""API-equivalent cost of local-agent telemetry rows without a reported cost. No LLM."""
from pricing import Pricing, PricingManager
from routes import telemetry_api


def _manager():
    return PricingManager({
        "openai:gpt-6.1-sol": Pricing(0.002, 0.01, 0.0001),
        "anthropic:claude-opus-5-5": Pricing(0.005, 0.025),
    })


def test_codex_input_includes_cached_tokens():
    est = _manager().estimate_agent_run(
        "openai:gpt-6.1-sol",
        {"input_tokens": 1_000_000, "cache_read_input_tokens": 900_000, "output_tokens": 10_000},
        input_includes_cached=True,
    )
    # 100k fresh * 2$/M + 900k cached * 0.10$/M + 10k out * 10$/M
    assert est["total_cost"] == round(0.2 + 0.09 + 0.1, 6)
    assert est["unit"] == "usd_api_equivalent" and est["estimated"] is True


def test_unpriced_model_is_not_estimated():
    assert _manager().estimate_agent_run("openai:gpt6-1-sol", {"input_tokens": 5}, input_includes_cached=True) is None


def test_rows_get_the_estimate_and_reported_costs_are_kept(monkeypatch):
    monkeypatch.setattr(telemetry_api, "_PRICING_MANAGER", _manager())
    rows = [
        {"execution": "local_agent", "executor": "gpt_codex", "model": "gpt-6.1-sol",
         "usage": {"input_tokens": 1000, "output_tokens": 1000}, "pricing": {}},
        {"execution": "local_agent", "executor": "claude_code", "model": "claude-opus-5-5",
         "usage": {"input_tokens": 1000}, "pricing": {"total_cost": 1.5}},
        {"execution": "local_agent", "executor": "gpt_codex", "model": "gpt-unknown", "usage": {}, "pricing": {}},
        {"provider": "openai", "model": "gpt-6.1-sol", "pricing": {}},
    ]
    out = telemetry_api._with_estimated_cost(rows)
    assert telemetry_api._cost_from_row(out[0]) == round(0.002 + 0.01, 6)
    assert telemetry_api._cost_from_row(out[1]) == 1.5
    assert out[2]["pricing"] == {} and out[3]["pricing"] == {}
