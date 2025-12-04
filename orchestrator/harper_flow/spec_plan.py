import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

REQ_PATTERN = re.compile(r"REQ-[A-Z0-9\-]+")


@dataclass
class SpecPlanArtifacts:
    spec_path: Path
    plan_path: Path
    plan_json_path: Path
    req_ids: List[str] = field(default_factory=list)


class SpecPlanGenerator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.docs_dir = project_root / "docs" / "harper"
        self.spec_path = self.docs_dir / "SPEC.md"
        self.plan_path = self.docs_dir / "PLAN.md"
        self.plan_json_path = self.docs_dir / "plan.json"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def generate_spec(self, start_from: str, run_id: str, idea_override: Optional[Path] = None) -> Dict:
        start_from = (start_from or "auto").lower()
        idea_path_candidates = [
            idea_override,
            self.project_root / "IDEA.md",
            self.docs_dir / "IDEA.md",
        ]
        idea_path = next((p for p in idea_path_candidates if p and p.exists()), None)

        spec_exists = self.spec_path.exists()
        if start_from == "spec" and spec_exists:
            content = self.spec_path.read_text(encoding="utf-8")
            normalized = self._normalize_spec(content)
            self.spec_path.write_text(normalized, encoding="utf-8")
            return {"path": str(self.spec_path), "source": "existing", "normalized": True}

        if not idea_path:
            raise FileNotFoundError("IDEA.md not found for SPEC generation")

        idea_text = idea_path.read_text(encoding="utf-8")
        spec_text = self._render_spec_from_idea(idea_text, run_id)
        if spec_exists:
            existing = self.spec_path.read_text(encoding="utf-8")
            spec_text = self._merge_existing_spec(existing, spec_text)
        self.spec_path.write_text(spec_text, encoding="utf-8")
        return {"path": str(self.spec_path), "source": str(idea_path), "normalized": False}

    def generate_plan(self) -> SpecPlanArtifacts:
        if not self.spec_path.exists():
            raise FileNotFoundError("SPEC.md is required to generate PLAN")

        spec_text = self.spec_path.read_text(encoding="utf-8")
        req_ids = self._extract_req_ids(spec_text)
        existing_plan_json = self._load_plan_json()
        merged_plan_json = self._merge_plan_json(existing_plan_json, req_ids)

        self.plan_json_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_json_path.write_text(json.dumps(merged_plan_json, indent=2), encoding="utf-8")

        plan_md = self._render_plan_md(merged_plan_json)
        self.plan_path.write_text(plan_md, encoding="utf-8")

        return SpecPlanArtifacts(
            spec_path=self.spec_path,
            plan_path=self.plan_path,
            plan_json_path=self.plan_json_path,
            req_ids=req_ids,
        )

    def _extract_req_ids(self, spec_text: str) -> List[str]:
        unique: Set[str] = set(REQ_PATTERN.findall(spec_text))
        return sorted(unique)

    def _load_plan_json(self) -> List[Dict]:
        if not self.plan_json_path.exists():
            return []
        try:
            return json.loads(self.plan_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _merge_plan_json(self, existing: List[Dict], req_ids: List[str]) -> List[Dict]:
        indexed_existing = {item.get("id"): item for item in existing if item.get("id")}
        merged: List[Dict] = []

        for req in req_ids:
            current = indexed_existing.get(req, {})
            merged.append(
                {
                    "id": req,
                    "status": current.get("status", "pending"),
                    "lane": current.get("lane", "core"),
                    "dependsOn": current.get("dependsOn", []),
                    "test_profile": current.get("test_profile", "default"),
                    "gate_policy_ref": current.get("gate_policy_ref", "default"),
                }
            )

        for req_id, item in indexed_existing.items():
            if req_id not in req_ids:
                merged.append(item)

        merged.sort(key=lambda x: x.get("id", ""))
        return merged

    def _render_plan_md(self, plan_json: List[Dict]) -> str:
        lines = ["# PLAN", "", "## Work Breakdown", ""]
        for entry in plan_json:
            req = entry.get("id")
            status = entry.get("status", "pending")
            lane = entry.get("lane", "core")
            deps = entry.get("dependsOn", [])
            dep_text = f" (depends on: {', '.join(deps)})" if deps else ""
            lines.append(f"- {req} — lane: {lane}; status: {status}{dep_text}")
        lines.extend(
            [
                "",
                "## Traceability",
                "Coverage: 100% of SPEC requirements mapped to PLAN entries.",
                "",
                "## Test Strategy",
                "Unit Tests\nFunctional Tests\nIntegration Tests\nSecurity Tests\nUAT Tests",
                "",
                "## Milestones",
                "- M1: SPEC ready\n- M2: PLAN agreed\n- M3: KIT/EVAL/GATE slice complete",
                "",
                "## Risks & Mitigations",
                "- TBD",
                "",
                "## Non-Functionals",
                "Performance targets documented; security controls aligned with constraints.",
                "",
                "## Environment Profiles",
                "Reflect tech_constraints profiles (e.g., onprem/cloud)",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _render_spec_from_idea(self, idea_text: str, run_id: str) -> str:
        return (
            "# SPEC\n\n"
            "## Problem\n"
            f"{idea_text.strip()}\n\n"
            "## Objectives\n"
            "- Define objectives derived from IDEA.\n\n"
            "## Scope\n"
            "- In scope items tied to IDEA outcomes.\n\n"
            "## Non-Goals\n"
            "- Out of scope items.\n\n"
            "## Constraints\n"
            "- Technology constraints captured as YAML below.\n\n"
            "```yaml\ntech_constraints:\n  profiles: [default]\n  notes: Generated in quickstart run {run_id}\n```\n\n"
            "## KPIs\n"
            "- KPI placeholder with measurement method.\n\n"
            "## Assumptions\n"
            "- Assumptions captured here.\n\n"
            "## Risks\n"
            "- Risk placeholders.\n\n"
            "## Acceptance Criteria\n"
            "- REQ-EXAMPLE-001: Placeholder acceptance criteria mapped to tests.\n\n"
            "## Sources & Evidence\n"
            "- IDEA.md\n\n"
            "## Technology Constraints\n"
            "- Mirror of constraints YAML above.\n"
        )

    def _merge_existing_spec(self, existing: str, generated: str) -> str:
        required_sections = [
            "Problem",
            "Objectives",
            "Scope",
            "Non-Goals",
            "Constraints",
            "KPIs",
            "Assumptions",
            "Risks",
            "Acceptance Criteria",
            "Sources & Evidence",
            "Technology Constraints",
        ]
        merged = existing
        for section in required_sections:
            header = f"## {section}"
            if header not in merged and header in generated:
                merged = merged.rstrip() + "\n\n" + self._extract_section(generated, header)
        return merged

    def _extract_section(self, text: str, header: str) -> str:
        lines = text.splitlines()
        capture = False
        buffer: List[str] = []
        for line in lines:
            if line.startswith("## "):
                capture = line == header
            if capture:
                buffer.append(line)
        return "\n".join(buffer)

    def _normalize_spec(self, spec_text: str) -> str:
        required = [
            "## Problem",
            "## Objectives",
            "## Scope",
            "## Non-Goals",
            "## Constraints",
            "## KPIs",
            "## Assumptions",
            "## Risks",
            "## Acceptance Criteria",
            "## Sources & Evidence",
            "## Technology Constraints",
        ]
        normalized = spec_text.rstrip()
        for header in required:
            if header not in normalized:
                normalized += f"\n\n{header}\n- TBD"
        return normalized + "\n"
