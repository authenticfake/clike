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


def test_cloud_openai_cached_input_is_charged_at_the_cached_price():
    pm = PricingManager({"openai:gpt-5": Pricing(0.00125, 0.01, 0.000125)})
    est = pm.estimate_cost("openai:gpt-5", "openai", "gpt-5", {
        "input_tokens": 100_000, "input_tokens_details": {"cached_tokens": 90_000}, "output_tokens": 1_000,
    })
    assert est["total_cost"] == round(10_000 / 1000 * 0.00125 + 90_000 / 1000 * 0.000125 + 0.01, 6)
    assert est["cached_tokens"] == 90_000


def test_cloud_anthropic_cache_reads_and_writes_are_charged():
    pm = PricingManager({"anthropic:claude-opus-5-5": Pricing(0.004, 0.02, 0.0002, 0.005, 0.008)})
    usage = {
        "input_tokens": 1_000, "cache_read_input_tokens": 100_000, "cache_creation_input_tokens": 12_000,
        "cache_creation": {"ephemeral_5m_input_tokens": 10_000, "ephemeral_1h_input_tokens": 2_000}, "output_tokens": 2_000,
    }
    est = pm.estimate_cost("anthropic:claude-opus-5-5", "anthropic", "claude-opus-5-5", usage)
    assert est["cache_write_cost"] == round(10 * 0.005 + 2 * 0.008, 6)
    assert est["total_cost"] == round(0.004 + 100 * 0.0002 + 10 * 0.005 + 2 * 0.008 + 2 * 0.02, 6)


def test_portal_recomputes_old_cloud_rows_with_cache_tokens(monkeypatch):
    monkeypatch.setattr(telemetry_api, "_PRICING_MANAGER", PricingManager({"openai:gpt-5": Pricing(0.00125, 0.01, 0.000125)}))
    old = {"provider": "openai", "model": "gpt-5", "pricing": {"total_cost": 0.135},
           "usage": {"input_tokens": 100_000, "input_tokens_details": {"cached_tokens": 90_000}, "output_tokens": 1_000}}
    plain = {"provider": "openai", "model": "gpt-5", "pricing": {"total_cost": 0.5}, "usage": {"input_tokens": 10, "output_tokens": 1}}
    rows = telemetry_api._with_estimated_cost([old, plain])
    assert rows[0]["pricing"]["cache_recomputed"] is True and rows[0]["pricing"]["total_cost"] < 0.135
    assert rows[1]["pricing"] == {"total_cost": 0.5}
    agg = telemetry_api._aggregate_rows(rows)
    assert agg["total_tokens_cached"] == 90_000
