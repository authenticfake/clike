from pathlib import Path
from typing import Dict, Optional

from .graph import HarperFlowGraph
from .lane_guides import generate_lane_guides
from .nodes import HarperNodeDefinition, NodeExecutionResult, NodeStatus
from .report import QuickstartReport
from .spec_plan import (
generate_plan,
generate_plan_json,
generate_spec_from_idea,
normalize_spec,
read_idea,
)

def _run_idea(node: HarperNodeDefinition, run_dir: Path) -> NodeExecutionResult:
    idea_path = Path("IDEA.md")
    artifacts = {}
    if idea_path.exists():
        artifacts["idea"] = str(idea_path)
        return NodeExecutionResult(status=NodeStatus.COMPLETED, artifacts=artifacts)
    return NodeExecutionResult(status=NodeStatus.SKIPPED, details={"reason": "IDEA.md missing"})

def _run_spec(node: HarperNodeDefinition, run_dir: Path, start_from: str) -> NodeExecutionResult:
    idea_path = Path("IDEA.md")
    spec_path = Path("docs/harper/SPEC.md")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    if start_from == "idea" or (start_from == "auto" and idea_path.exists()):
        idea_text = read_idea(idea_path) if idea_path.exists() else ""
        spec_text = generate_spec_from_idea(idea_text)
        spec_path.write_text(spec_text, encoding="utf-8")
        return NodeExecutionResult(
            status=NodeStatus.COMPLETED,
            artifacts={"spec": str(spec_path)},
            details={"source": "idea"},
        )

    if spec_path.exists():
        spec_text = normalize_spec(spec_path.read_text(encoding="utf-8"))
        spec_path.write_text(spec_text, encoding="utf-8")
        return NodeExecutionResult(
            status=NodeStatus.COMPLETED,
            artifacts={"spec": str(spec_path)},
            details={"source": "existing"},
        )

    return NodeExecutionResult(
        status=NodeStatus.FAILED,
        error="SPEC.md not found and IDEA.md missing for generation.",
    )
def _run_plan(node: HarperNodeDefinition, run_dir: Path) -> NodeExecutionResult:
    spec_path = Path("docs/harper/SPEC.md")
    plan_md_path = Path("docs/harper/PLAN.md")
    return generate_plan(spec_path, plan_md_path)

def _run_plan_json(node: HarperNodeDefinition, run_dir: Path) -> NodeExecutionResult:
    spec_path = Path("docs/harper/SPEC.md")
    plan_json_path = Path("docs/harper/plan.json")
    return generate_plan_json(spec_path, plan_json_path)

def _run_lane_guides(node: HarperNodeDefinition, run_dir: Path) -> NodeExecutionResult:
    plan_json_path = Path("docs/harper/plan.json")
    tech_constraints_path = Path("docs/harper/TECH_CONSTRAINTS.yaml")
    lane_guides_dir = Path("docs/harper/lane-guides")
    return generate_lane_guides(plan_json_path, tech_constraints_path, lane_guides_dir)

def run_quickstart(
    run_id: str,
    mode: str,
    start_from: str = "auto",
    profile: Optional[str] = None,
    run_directory: Optional[Path] = None,
) -> QuickstartReport:
    run_dir = run_directory or Path("runs") / run_id
    graph = HarperFlowGraph.create(run_id=run_id, mode=mode, start_from=start_from)
    report = QuickstartReport(run_id=run_id, start_from=start_from, mode=mode, profile=profile)

    def wrap(fn):
        return lambda node: fn(node, run_dir)

    executor: Dict[str, callable] = {
        "idea": wrap(_run_idea),
        "spec": lambda node: _run_spec(node, run_dir, start_from),
        "plan": wrap(_run_plan),
        "lane_guides": wrap(_run_lane_guides),
        "ltc_howto": lambda node: NodeExecutionResult(status=NodeStatus.SKIPPED),
        "kit": lambda node: NodeExecutionResult(status=NodeStatus.SKIPPED),
        "eval": lambda node: NodeExecutionResult(status=NodeStatus.SKIPPED),
        "gate": lambda node: NodeExecutionResult(status=NodeStatus.SKIPPED),
        "finalize": lambda node: NodeExecutionResult(status=NodeStatus.SKIPPED),
    }

    def run_plan_json_first(node: HarperNodeDefinition) -> NodeExecutionResult:
        return _run_plan_json(node, run_dir)

    executor["plan"] = wrap(_run_plan)
    executor["lane_guides"] = wrap(_run_lane_guides)

    state = graph.execute(executor=executor, run_directory=run_dir)
    graph.save(run_dir)

    for key, node_state in state.items():
        report.log_phase(
            name=key,
            status=node_state.status.value,
            artifacts=node_state.artifacts,
            error=node_state.error,
            details=node_state.details,
        )

    report.save(run_dir)
    return report
