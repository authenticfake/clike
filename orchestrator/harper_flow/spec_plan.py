import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .nodes import NodeExecutionResult, NodeStatus

SPEC_TEMPLATE = """# SPEC

Context
{context}

Problem Statement
{problem}

Target Users
{users}

Values & Outcomes
{values}

Requirements
{requirements}

Out of Scope
{out_of_scope}
"""

PLAN_TEMPLATE_HEADER = """# PLAN

Summary
Derived from SPEC requirements.

Keep this synchronized with docs/harper/plan.json.
"""

PLAN_ENTRY_TEMPLATE = """### {req_id}

Acceptance: {acceptance}

Lane: {lane}

Depends on: {depends_on}
"""

def read_idea(idea_path: Path) -> str:
    return idea_path.read_text(encoding="utf-8").strip()

def generate_spec_from_idea(idea_text: str) -> str:
    context = "Context derived from IDEA.md"
    problem = "Problem statement derived from IDEA.md"
    users = "Primary users and stakeholders"
    values = "Desired outcomes and values"
    requirements = "- REQ-001: Fill detailed requirement here"
    out_of_scope = "- Non-goals and exclusions"
    return SPEC_TEMPLATE.format(
    context=context,
    problem=problem,
    users=users,
    values=values,
    requirements=requirements,
    out_of_scope=out_of_scope,
)

def normalize_spec(spec_text: str) -> str:
    if not spec_text.lstrip().startswith("# SPEC"):
        return "# SPEC\n\n" + spec_text
    return spec_text

def extract_requirements(spec_text: str) -> List[Tuple[str, str]]:
    reqs: List[Tuple[str, str]] = []
    for line in spec_text.splitlines():
        line = line.strip()
        if line.startswith("- REQ-"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                reqs.append((parts[0].strip("- ").strip(), parts[1].strip()))
    return reqs

def load_spec_requirements(spec_path: Path) -> List[Tuple[str, str]]:
    if not spec_path.exists():
        return []
    return extract_requirements(spec_path.read_text(encoding="utf-8"))

def build_plan_entries(requirements: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for req_id, desc in requirements:
        entries.append(
        {
        "id": req_id,
        "status": "pending",
        "lane": "core",
        "dependsOn": [],
        "description": desc,
        "test_profile": "default",
        "gate_policy_ref": "default",
        }
    )
    return entries

def generate_plan_md(entries: List[Dict[str, str]]) -> str:
    parts = [PLAN_TEMPLATE_HEADER]
    for entry in entries:
        parts.append(
        PLAN_ENTRY_TEMPLATE.format(
            req_id=entry["id"],
            acceptance=entry.get("description", "TBD"),
            lane=entry.get("lane", "core"),
            depends_on=", ".join(entry.get("dependsOn", [])) or "none",
            )
        )
    return "\n".join(parts).strip() + "\n"

def merge_plan_json(existing: Dict[str, Dict], new_entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: Dict[str, Dict] = {item["id"]: item for item in new_entries}
    for item in existing.get("requirements", []):
        merged[item["id"]] = {**item, **merged.get(item["id"], item)}
    return list(merged.values())

def generate_plan(spec_path: Path, plan_md_path: Path) -> NodeExecutionResult:
    requirements = load_spec_requirements(spec_path)
    entries = build_plan_entries(requirements)
    plan_md = generate_plan_md(entries)
    plan_md_path.parent.mkdir(parents=True, exist_ok=True)
    plan_md_path.write_text(plan_md, encoding="utf-8")
    return NodeExecutionResult(
        status=NodeStatus.COMPLETED,
        artifacts={"plan_md": str(plan_md_path)},
        details={"requirements": [e["id"] for e in entries]},
    )

def generate_plan_json(spec_path: Path, plan_json_path: Path) -> NodeExecutionResult:
    requirements = load_spec_requirements(spec_path)
    new_entries = build_plan_entries(requirements)
    existing: Dict[str, Dict] = {}
    if plan_json_path.exists():
        try:
            existing = json.loads(plan_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        merged_entries = merge_plan_json(existing, new_entries)
        payload = {"requirements": merged_entries}
        plan_json_path.parent.mkdir(parents=True, exist_ok=True)
        plan_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return NodeExecutionResult(
            status=NodeStatus.COMPLETED,
            artifacts={"plan_json": str(plan_json_path)},
            details={"requirements": [e["id"] for e in merged_entries]},
        )