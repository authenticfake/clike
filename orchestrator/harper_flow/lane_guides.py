import json
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from .nodes import NodeExecutionResult, NodeStatus

GENERATED_START = "<!-- CLike Generated Start -->"
GENERATED_END = "<!-- CLike Generated End -->"

LANE_GUIDE_TEMPLATE = """# Lane Guide — {lane}

    {generated_start}

    Overview
    Scope: {scope}

    Constraints: {constraints}

    Tooling
    Tests: {tests}

    Lint: {lint}

    Type checks: {types}

    Security: {security}

    Build: {build}

    Commands & Reports
    Example test command: {test_cmd}

    Example lint command: {lint_cmd}

    Example type-check command: {type_cmd}

    Example security command: {security_cmd}

    Example build command: {build_cmd}

    Expected reports:

    Tests: {test_report}

    Lint: {lint_report}

    Type: {type_report}

    Security: {security_report}

    Build: {build_report}

    Gate Policy Hint
    Default gate policy reference: {gate_policy}

    Required reports for gate: {gate_reports}

    Runner / CI Notes
    Recommended runner: {runner}

    Notes: {runner_notes}
    {generated_end}

    TODO (manual)
    Refine tooling specifics for this lane.

    Confirm report paths and retention.

    Add any lane-specific caveats or escalation paths.
    """

def _load_plan_lanes(plan_json_path: Path) -> Set[str]:
    if not plan_json_path.exists():
        return set()
    data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    lanes = {item.get("lane", "core") for item in data.get("requirements", [])}
    return {lane for lane in lanes if lane}

def _load_tech_constraints(tech_constraints_path: Path) -> Dict:
    if not tech_constraints_path.exists():
        return {}
    try:
        return yaml.safe_load(tech_constraints_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _render_lane_guide(lane: str, tech_constraints: Dict) -> str:
    lane_info = tech_constraints.get("lanes", {}).get(lane, {})
    scope = lane_info.get("scope", f"Work assigned to lane {lane}")
    constraints = lane_info.get("constraints", "Follow TECH_CONSTRAINTS and repo policies.")
    tooling = lane_info.get("tooling", {})
    reports = lane_info.get("reports", {})
    runner = lane_info.get("runner", "default runner")
    runner_notes = lane_info.get("notes", "Add CI runner notes or infra expectations.")
    gate_policy = lane_info.get("gate_policy_ref", "default")
    values = {
        "lane": lane,
        "scope": scope,
        "constraints": constraints,
        "tests": tooling.get("tests", "TODO: test tool"),
        "lint": tooling.get("lint", "TODO: lint tool"),
        "types": tooling.get("types", "TODO: type checker"),
        "security": tooling.get("security", "TODO: security scanner"),
        "build": tooling.get("build", "TODO: build tool"),
        "test_cmd": tooling.get("test_cmd", "npm test"),
        "lint_cmd": tooling.get("lint_cmd", "npm run lint"),
        "type_cmd": tooling.get("type_cmd", "npm run typecheck"),
        "security_cmd": tooling.get("security_cmd", "npm run security"),
        "build_cmd": tooling.get("build_cmd", "npm run build"),
        "test_report": reports.get("tests", "reports/tests.xml"),
        "lint_report": reports.get("lint", "reports/lint.txt"),
        "type_report": reports.get("types", "reports/types.txt"),
        "security_report": reports.get("security", "reports/security.json"),
        "build_report": reports.get("build", "reports/build.txt"),
        "gate_policy": gate_policy,
        "gate_reports": ", ".join(
            reports.get("required_for_gate", ["tests", "lint", "types", "security", "build"])
        ),
        "runner": runner,
        "runner_notes": runner_notes,
        "generated_start": GENERATED_START,
        "generated_end": GENERATED_END,
    }
    return LANE_GUIDE_TEMPLATE.format(**values)

def _merge_existing(existing: str, generated: str) -> str:
    if GENERATED_START in existing and GENERATED_END in existing:
        before, rest = existing.split(GENERATED_START, 1)
        _, after = rest.split(GENERATED_END, 1)
        return f"{before}{generated}{after}"
    return existing.rstrip() + "\n\n" + generated

def generate_lane_guides(
    plan_json_path: Path,
    tech_constraints_path: Path,
    lane_guides_dir: Path,
    ) -> NodeExecutionResult:
    lanes = _load_plan_lanes(plan_json_path)
    tech_constraints = _load_tech_constraints(tech_constraints_path)
    created: List[str] = []
    updated: List[str] = []

    lane_guides_dir.mkdir(parents=True, exist_ok=True)

    for lane in sorted(lanes):
        target = lane_guides_dir / f"{lane}.md"
        generated = _render_lane_guide(lane, tech_constraints)

        if target.exists():
            existing = target.read_text(encoding="utf-8")
            merged = _merge_existing(existing, generated)
            if merged != existing:
                target.write_text(merged, encoding="utf-8")
                updated.append(str(target))
        else:
            target.write_text(generated, encoding="utf-8")
            created.append(str(target))

    status = NodeStatus.COMPLETED
    artifacts = {"lane_guides_created": created, "lane_guides_updated": updated}
    return NodeExecutionResult(status=status, artifacts=artifacts, details={"lanes": list(lanes)})
