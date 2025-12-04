from pathlib import Path
from typing import Dict, Optional

from .graph import HarperFlowGraph
from .nodes import NodeExecutionResult, NodeStatus
from .report import QuickstartReport
from .spec_plan import SpecPlanGenerator


class HarperQuickstartRunner:
    """
    Lightweight runner that wires SPEC generation/normalization and PLAN generation
    into the Harper flow graph. Remaining nodes are currently no-ops so callers can
    layer additional executors later.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.generator = SpecPlanGenerator(project_root)

    def run(self, run_id: str, start_from: str = "auto", mode: str = "plan-only", idea_override: Optional[Path] = None):
        run_directory = self.project_root / "runs" / run_id
        graph = HarperFlowGraph.create(run_id=run_id, mode=mode, start_from=start_from)
        report = QuickstartReport(run_id=run_id, run_directory=run_directory)
        report.set_inputs({"startFrom": start_from, "mode": mode})

        executor = self._build_executor(report, start_from, idea_override)
        graph.save(run_directory)
        graph.execute(executor=executor, run_directory=run_directory)
        return graph, report

    def _build_executor(self, report: QuickstartReport, start_from: str, idea_override: Optional[Path]):
        def spec_executor(_node):
            try:
                details = self.generator.generate_spec(start_from=start_from, run_id=report.run_id, idea_override=idea_override)
                report.log_phase("spec", "completed", details)
                return NodeExecutionResult(status=NodeStatus.COMPLETED, artifacts=details)
            except Exception as exc:  # pragma: no cover
                report.log_phase("spec", "failed", {"error": str(exc)})
                return NodeExecutionResult(status=NodeStatus.FAILED, error=str(exc))

        def plan_executor(_node):
            try:
                artifacts = self.generator.generate_plan()
                detail_dict = {
                    "spec": str(artifacts.spec_path),
                    "plan": str(artifacts.plan_path),
                    "plan_json": str(artifacts.plan_json_path),
                    "req_ids": artifacts.req_ids,
                }
                report.log_phase("plan", "completed", detail_dict)
                return NodeExecutionResult(status=NodeStatus.COMPLETED, artifacts=detail_dict)
            except Exception as exc:  # pragma: no cover
                report.log_phase("plan", "failed", {"error": str(exc)})
                return NodeExecutionResult(status=NodeStatus.FAILED, error=str(exc))

        def noop_executor(phase: str):
            def _inner(_node):
                report.log_phase(phase, "skipped", {})
                return NodeExecutionResult(status=NodeStatus.SKIPPED)

            return _inner

        return {
            "idea": noop_executor("idea"),
            "spec": spec_executor,
            "plan": plan_executor,
            "lane_guides": noop_executor("lane_guides"),
            "ltc_howto": noop_executor("ltc_howto"),
            "kit": noop_executor("kit"),
            "eval": noop_executor("eval"),
            "gate": noop_executor("gate"),
            "finalize": noop_executor("finalize"),
        }
