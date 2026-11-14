"""Eval and gate runs reach the telemetry portal: their time and outcome, no model."""

import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import eval_telemetry  # noqa: E402
from tests.test_eval_regression import _RegressionProject  # noqa: E402


class EvalTelemetryRecordTests(unittest.TestCase):
    def test_the_row_carries_time_scope_and_outcome_without_a_model(self):
        payload = {"req_id": "REQ-009", "status": "PASS_WITH_WARNINGS", "passed_count": 98, "failed": 0,
                   "blocked_count": 0, "warning_count": 1, "regression": True,
                   "timings": {"total_s": 156.8, "checks_s": 43.9, "regression_s": 111.4, "regression_workers": 3}}
        row = eval_telemetry.build_record(Path("/w/CDL Pipeline"), None, "eval", payload, time.monotonic() - 2, "full")
        self.assertEqual((row["project_id"], row["phase"], row["req_id"]), ("cdl-pipeline", "eval", "REQ-009"))
        self.assertEqual((row["execution"], row["model"], row["usage"], row["pricing"]), ("eval_sandbox", None, {}, {}))
        self.assertGreaterEqual(row["duration_ms"], 2000)
        self.assertEqual(row["outcome"], {"scope": "full", "status": "PASS_WITH_WARNINGS", "passed": 98, "failed": 0,
                                          "blocked": 0, "warnings": 1, "regression": True, "checks_s": 43.9,
                                          "regression_s": 111.4, "regression_workers": 3, "reused": False})
        gate = eval_telemetry.build_record(Path("/w/x"), "cdl-pipeline", "gate",
                                           {"gate": "PASS", "status": "PASS", "reused_eval_at": "t"}, time.monotonic(), "gate")
        self.assertEqual((gate["project_id"], gate["outcome"]["status"], gate["outcome"]["reused"]), ("cdl-pipeline", "PASS", True))

    def test_sent_in_the_background_and_a_gateway_failure_never_fails_the_eval(self):
        for post in (AsyncMock(return_value={"ok": True}), AsyncMock(side_effect=RuntimeError("down"))):
            async def run():
                eval_telemetry.record(Path("/w/p"), None, "eval", {"req_id": "REQ-001"}, time.monotonic(), "full")
                await asyncio.gather(*list(eval_telemetry._pending))
            with patch("services.harper._post_json", post):
                asyncio.run(run())
            path, row = post.await_args.args
            self.assertEqual((path, row["phase"], row["req_id"]), ("/v1/harper/telemetry", "eval", "REQ-001"))
        eval_telemetry.record(Path("/w/p"), None, "eval", {}, time.monotonic(), "full")  # no loop: skipped quietly


class EvalRouteTelemetryTests(_RegressionProject):
    def test_every_eval_and_gate_is_recorded_but_an_agents_own_runs(self):
        with patch.object(eval_telemetry, "record") as rec:
            self._post("/v1/eval/run", "REQ-002", regression=True)
            self._post("/v1/eval/run", "REQ-002", regression=True, regression_reqs=["REQ-001"])
            self._post("/v1/eval/run", "REQ-002", checks=["unit"])
            self._post("/v1/eval/run", "REQ-002", agent_check=True)
            self._post("/v1/gate/check", "REQ-002", regression=True)
        calls = [(c.args[2], c.args[5], c.args[3]["req_id"]) for c in rec.call_args_list]
        self.assertEqual(calls, [("eval", "full", "REQ-002"), ("eval", "targeted", "REQ-002"),
                                 ("eval", "checks", "REQ-002"), ("gate", "gate", "REQ-002")])
        self.assertEqual(rec.call_args_list[0].args[0], self.proj)


if __name__ == "__main__":
    unittest.main()
