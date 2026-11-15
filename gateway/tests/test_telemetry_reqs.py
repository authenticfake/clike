"""Telemetry portal: requirements ranking, phase drill-down, KPIs and estimate."""

import sys
from pathlib import Path

GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from routes import telemetry_api, telemetry_ui  # noqa: E402


def _row(phase, req, ts, ms, cost=0.0, status=None, execution="local_agent", tokens=0, cached=0):
    row = {"phase": phase, "req_id": req, "timestamp": ts, "duration_ms": ms, "execution": execution,
           "pricing": {"total_cost": cost}, "usage": {"input_tokens": tokens, "cache_read_input_tokens": cached}}
    if status:
        row["outcome"] = {"status": status}
    return row


ROWS = [
    _row("plan", "PLAN", 50, 10_000, cost=1.0),
    # REQ-001: one KIT, eval passes first time, gate passes
    _row("kit", "REQ-001", 100, 60_000, cost=2.0, tokens=1000, cached=900),
    _row("eval", "REQ-001", 200, 30_000, status="PASS", execution="eval_sandbox"),
    _row("gate", "REQ-001", 210, 1_000, status="PASS", execution="eval_sandbox"),
    # REQ-002: KIT, failing eval, repair, passing eval, gate with warnings
    _row("kit", "REQ-002", 300, 120_000, cost=4.0, tokens=2000, cached=1000),
    _row("eval", "REQ-002", 400, 40_000, status="FAIL", execution="eval_sandbox"),
    _row("kit", "REQ-002", 500, 60_000, cost=3.0, tokens=1000, cached=500),
    _row("eval", "REQ-002", 600, 40_000, status="PASS_WITH_WARNINGS", execution="eval_sandbox"),
    _row("gate", "REQ-002", 610, 1_000, status="PASS_WITH_WARNINGS", execution="eval_sandbox"),
]


def test_requirements_are_ranked_with_their_attempts_outcomes_and_time():
    data = telemetry_api._req_analytics(ROWS)
    by = {r["req_id"]: r for r in data["reqs"]}
    assert [r["req_id"] for r in data["reqs"]][:2] == ["REQ-002", "REQ-001"]  # by cost
    two = by["REQ-002"]
    assert (two["cost_usd"], two["kit_runs"], two["repairs"], two["eval_runs"], two["eval_failed"]) == (7.0, 2, 1, 2, 1)
    assert (two["eval_first"], two["eval_last"], two["gate"]) == ("FAIL", "PASS_WITH_WARNINGS", "PASS_WITH_WARNINGS")
    assert (two["agent_ms"], two["sandbox_ms"]) == (180_000, 81_000)
    assert two["span_s"] == 610 - (300 - 120)  # from the start of the first run to the end of the last
    assert set(two["per_phase"]) == {"kit", "eval", "gate"} and two["per_phase"]["kit"]["runs"] == 2


def test_a_phase_drills_down_to_its_requirements():
    kit = telemetry_api._req_analytics(ROWS)["phase_reqs"]["kit"]
    assert [(x["req_id"], x["runs"], x["cost_usd"]) for x in kit] == [("REQ-002", 2, 7.0), ("REQ-001", 1, 2.0)]


def test_kpis_and_the_estimate_come_from_the_measured_requirements_only():
    data = telemetry_api._req_analytics(ROWS, estimate_reqs=10)
    k = data["kpis"]
    assert k["reqs"] == 2
    assert k["repairs_per_req"] == 0.5
    assert k["eval_first_pass_rate"] == 0.5 and k["gate_pass_rate"] == 1.0
    assert k["cache_hit_rate"] == 2400 / 4000
    assert k["other_phases"]["cost_usd"] == 1.0 and k["other_phases"]["runs"] == 1  # the plan run, apart
    e = data["estimate"]
    assert e["reqs"] == 10 and e["basis_reqs"] == 2
    assert e["cost_usd"]["median"] <= e["cost_usd"]["p90"]
    assert telemetry_api._req_analytics([], estimate_reqs=3)["estimate"] is None


def test_the_portal_has_the_requirements_and_kpi_views():
    html = telemetry_ui._HTML
    for marker in ('data-tab="reqs"', 'data-tab="kpis"', 'id="phaseDrill"', "/v1/metrics/harper/reqs", "estimate_reqs"):
        assert marker in html
