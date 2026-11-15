"""UI design systems: chosen in TECH_CONSTRAINTS, shadcn/ui by default, given to /plan and to the KIT of UI REQs."""
import json
from pathlib import Path

from services import design_systems as ds
from services.quality_context import build_quality_context


def test_the_design_system_comes_from_tech_constraints_with_aliases_and_a_default():
    assert ds.resolve("")["id"] == "shadcn-ui" and ds.resolve("")["source"] == "default"
    named = ds.resolve("tech_constraints:\n  ui:\n    design_system: Fluent 2\n")
    assert (named["id"], named["source"]) == ("fluent2", "tech_constraints") and "FluentProvider" in named["guide"]
    for alias, expected in (("shadcn/ui", "shadcn-ui"), ("IBM Carbon", "carbon"), ("material", "mui"), ("ant-design", "antd")):
        assert ds.resolve(f"tech_constraints:\n  design_system: {alias}\n")["id"] == expected, alias
    # a broken YAML still names it
    assert ds.declared("tech_constraints:\n  ui: [\n  design_system: carbon\n") == "carbon"
    assert ds.resolve("tech_constraints: {ui: {design_system: none}}") == {"id": "none", "source": "tech_constraints", "guide": ""}


def test_every_bundled_guide_has_the_same_sections():
    for design_id in ("shadcn-ui", "fluent2", "carbon", "mui", "antd"):
        guide = ds.resolve(f"tech_constraints: {{ui: {{design_system: {design_id}}}}}")["guide"]
        for section in ("## Setup", "## Theme and tokens", "## App shell", "## Components by need", "## Rules", "## Verify"):
            assert section in guide, (design_id, section)


def test_a_project_guide_overrides_or_adds_a_design_system(tmp_path: Path):
    (tmp_path / ".clike/design-systems").mkdir(parents=True)
    (tmp_path / ".clike/design-systems/acme-ds.md").write_text("# Design system: ACME\nUse <acme-button>.\n")
    (tmp_path / ".clike/design-systems/shadcn-ui.md").write_text("# Design system: shadcn/ui, ACME brand\n")
    assert "acme-button" in ds.resolve("tech_constraints: {ui: {design_system: acme-ds}}", tmp_path)["guide"]
    assert ds.resolve("", tmp_path)["guide"].startswith("# Design system: shadcn/ui, ACME brand")
    unknown = ds.resolve("tech_constraints: {ui: {design_system: polaris}}", tmp_path)
    assert unknown["id"] == "polaris" and unknown["guide"] == ""
    assert "No CLike guide for `polaris`" in "\n".join(ds.kit_lines(unknown, "REQ-001"))
    assert ds.resolve("tech_constraints: {ui: {design_system: ../../etc}}", tmp_path)["guide"] == ""


def test_a_req_has_a_ui_by_lane_or_design_profile():
    assert ds.has_ui({"lane": "typescript"})
    assert ds.has_ui({"lane": "python", "design_profiles": ["enterprise-console"]})
    assert ds.has_ui({"lane": "python", "capabilities": {"design_profiles": ["enterprise-console"]}})
    assert not ds.has_ui({"lane": "python", "design_profiles": []}) and not ds.has_ui(None)


def _workspace(tmp_path: Path, tech: str) -> Path:
    (tmp_path / "docs/harper").mkdir(parents=True)
    (tmp_path / "docs/harper/TECH_CONSTRAINTS.yaml").write_text(tech)
    (tmp_path / "docs/harper/plan.json").write_text(json.dumps({"reqs": [
        {"id": "REQ-001", "lane": "typescript", "status": "open"},
        {"id": "REQ-002", "lane": "python", "status": "open"},
    ]}))
    return tmp_path


def test_plan_gets_the_rule_and_a_ui_kit_gets_the_guide_on_every_executor(tmp_path: Path):
    root = _workspace(tmp_path, "tech_constraints:\n  ui:\n    design_system: carbon\n")
    for mode in ("cloud", "local_agent"):
        plan = build_quality_context(phase="plan", payload={}, execution_mode=mode, req_id=None, workspace_root=root)
        assert "### UI design system" in plan["text"] and "**carbon** (from TECH_CONSTRAINTS ui.design_system)" in plan["text"]
        kit = build_quality_context(phase="kit", payload={}, execution_mode=mode, req_id="REQ-001", workspace_root=root)
        assert kit["design_system"] == "carbon" and "# Design system: Carbon (IBM)" in kit["text"]
    backend = build_quality_context(phase="kit", payload={}, execution_mode="cloud", req_id="REQ-002", workspace_root=root)
    assert "design_system" not in backend and "Design system" not in backend["text"]
    evaluation = build_quality_context(phase="eval", payload={}, execution_mode="cloud", req_id="REQ-001", workspace_root=root)
    assert "Design system" not in evaluation["text"]
    # the TECH_CONSTRAINTS the extension sends wins over the file
    sent = build_quality_context(phase="kit", payload={"core_blobs": {"TECH_CONSTRAINTS.yaml": "tech_constraints: {ui: {design_system: antd}}"}},
                                 execution_mode="cloud", req_id="REQ-001", workspace_root=root)
    assert sent["design_system"] == "antd"


def test_none_turns_the_guidance_off(tmp_path: Path):
    root = _workspace(tmp_path, "tech_constraints: {ui: {design_system: none}}")
    assert "UI design system" not in build_quality_context(phase="plan", payload={}, execution_mode="cloud", req_id=None, workspace_root=root)["text"]
    kit = build_quality_context(phase="kit", payload={}, execution_mode="cloud", req_id="REQ-001", workspace_root=root)
    assert "design_system" not in kit and "Design system" not in kit["text"]
