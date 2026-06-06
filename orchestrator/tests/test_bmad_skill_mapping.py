import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.local_agent_package import build_eval_local_agent_package, build_kit_local_agent_package
from services.methodologies.bmad_skill_loader import select_bmad_skill_context
from services.methodologies.resolver import ensure_bmad_skill_context, resolve_methodology_context


MANIFEST_PATH = REPO_ROOT / "orchestrator/methodologies/bmad/manifest.json"
SKILL_ROOT = REPO_ROOT / "orchestrator" / "methodologies" / "bmad" / "skills"
TEMPLATE_VENDOR_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad"
REQUIRED_SKILLS = {
    "prd-shaping",
    "epic-framing",
    "acceptance-modeling",
    "ux-flow-modeling",
    "architecture-readiness",
    "story-readiness",
    "dev-story-execution",
    "qa-risk-review",
    "release-narrative",
}
REQUIRED_SECTIONS = [
    "## Intent",
    "## BMAD source/reference concept",
    "## CLike adaptation",
    "## Applies when",
    "## Required inputs",
    "## Required outputs",
    "## Companion outputs",
    "## Downstream consumers",
    "## Quality checks",
    "## Eval/Gate evidence expectations",
    "## Forbidden behavior",
    "## Runtime dependency status",
    "## Cloud usage notes",
    "## Local-agent usage notes",
    "## Governance boundaries",
]


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _vendor_manifest():
    return json.loads((TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _bmad_vendor_core_blobs():
    blobs = {
        ".clike/skills/vendor/bmad/manifest.json": (TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")
    }
    for path in sorted(TEMPLATE_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _load_gateway_prompt_module():
    path = REPO_ROOT / "gateway/utils/methodology_prompt.py"
    spec = importlib.util.spec_from_file_location("gateway_methodology_prompt_for_bmad_skills", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_sync_tool():
    path = REPO_ROOT / "tools/bmad_skill_sync.py"
    spec = importlib.util.spec_from_file_location("bmad_skill_sync_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_payload(methodology_context=None):
    payload = {
        "runId": "skill-test",
        "project_id": "project",
        "project_name": "Project",
        "localAgentExecutor": "gpt_codex",
        "localAgentCapabilities": {},
        "core_blobs": {
            "IDEA.md": "# IDEA - Project\n",
            "SPEC.md": "# SPEC\n",
            "PLAN.md": "# PLAN\nREQ-001\nDependencies\nKIT Readiness\n",
            "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: node\n",
            "plan.json": json.dumps(
                {
                    "reqs": [
                        {
                            "id": "REQ-001",
                            "title": "Build slice",
                            "status": "open",
                            "acceptance": ["Works"],
                            "dependsOn": [],
                            "lane": "app",
                        }
                    ]
                }
            ),
            **_bmad_vendor_core_blobs(),
        },
    }
    if methodology_context:
        payload["methodology_context"] = methodology_context
    return payload


def _package_context(package, suffix):
    for item in package["local_agent"]["package_files"]:
        if item["path"].endswith(suffix):
            return json.loads(item["content"])
    raise AssertionError(f"missing package context: {suffix}")


def _execution_policy():
    return {
        "requested": "prefer_local_agent",
        "selected": "local_agent",
        "reason": "test",
        "phase_supported": True,
    }


class BmadSkillMappingTests(unittest.TestCase):
    def test_manifest_skill_reference_policy_exists_and_disables_runtime(self):
        policy = _manifest()["skill_reference_policy"]

        self.assertIs(policy["enabled"], True)
        self.assertEqual(policy["workspace_vendor_reference_root"], ".clike/skills/vendor/bmad")
        self.assertEqual(
            policy["template_vendor_reference_root"],
            "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad",
        )
        self.assertEqual(policy["vendor_skill_root"], ".clike/skills/vendor/bmad")
        self.assertEqual(policy["activation"], "methodology=bmad")
        for key in [
            "runtime_import_enabled",
            "external_skill_execution_enabled",
            "external_bmad_cli_enabled",
            "network_fetch_enabled",
            "official_bmad_runtime_content_vendored",
        ]:
            self.assertIs(policy[key], False)
        self.assertIs(policy["cloud_context_enabled"], True)
        self.assertIs(policy["local_agent_context_enabled"], True)

    def test_template_vendor_reference_seed_exists(self):
        manifest = json.loads((TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertTrue((TEMPLATE_VENDOR_ROOT / "README.md").exists())
        self.assertEqual(manifest["vendor"], "bmad")
        self.assertIn("BMAD methodology skill material", manifest["purpose"])
        self.assertIs(manifest["runtime_execution_enabled"], False)
        self.assertIs(manifest["external_bmad_cli_enabled"], False)
        self.assertIs(manifest["network_fetch_enabled"], False)
        self.assertEqual(manifest["activated_by"], "methodology=bmad")
        self.assertIs(manifest["native_harper_active"], False)
        self.assertEqual(manifest["reviewed_status"], "clike_owned_normalized_mapping")
        self.assertEqual(manifest["skill_selection"], _manifest()["skill_selection"])
        self.assertIn(
            "Cloud transport uses request core_blobs.",
            manifest["notes"],
        )

    def test_template_vendor_skills_exist_for_every_manifest_selection(self):
        manifest = _vendor_manifest()
        for skill_id in REQUIRED_SKILLS:
            with self.subTest(skill_id=skill_id):
                path = TEMPLATE_VENDOR_ROOT / skill_id / "SKILL.md"
                self.assertTrue(path.exists(), f"missing vendor skill: {path}")
                self.assertEqual(
                    manifest["skills"][skill_id]["path"],
                    f".clike/skills/vendor/bmad/{skill_id}/SKILL.md",
                )
                text = path.read_text(encoding="utf-8")
                for section in [
                    "## Intent",
                    "## Required outputs",
                    "## Companion outputs",
                    "## Quality checks",
                    "## Forbidden behavior",
                    "## Governance boundaries",
                ]:
                    self.assertIn(section, text)

    def test_normalized_skill_files_exist_and_have_required_sections(self):
        for skill_id in REQUIRED_SKILLS:
            path = SKILL_ROOT / f"{skill_id}.md"
            with self.subTest(skill_id=skill_id):
                self.assertTrue(path.exists(), f"missing skill mapping: {path}")
                text = path.read_text(encoding="utf-8")
                for section in REQUIRED_SECTIONS:
                    self.assertIn(section, text)

    def test_resolver_selects_expected_skills(self):
        cases = {
            ("idea", "analyst"): ["prd-shaping"],
            ("spec", "pm"): ["prd-shaping", "epic-framing", "acceptance-modeling"],
            ("spec", "ux"): ["ux-flow-modeling"],
            ("plan", "architect"): ["architecture-readiness", "story-readiness"],
            ("plan", "pm"): ["epic-framing", "story-readiness"],
            ("kit", "developer"): ["dev-story-execution", "story-readiness"],
            ("eval", "qa"): ["qa-risk-review"],
            ("finalize", "tech-writer"): ["release-narrative"],
        }

        for (phase, agent), expected in cases.items():
            with self.subTest(phase=phase, agent=agent):
                context = resolve_methodology_context(
                    phase=phase,
                    methodology="bmad",
                    agent=agent,
                    core_blobs=_bmad_vendor_core_blobs(),
                    require_bmad_core_blobs=True,
                )
                self.assertEqual(
                    [item["id"] for item in context["selected_skill_references"]],
                    expected,
                )
                self.assertEqual(context["skill_reference_policy"]["activation"], "methodology=bmad")

    def test_resolver_selection_is_manifest_driven_for_every_declared_pair(self):
        manifest = _manifest()
        for key, expected in manifest["skill_selection"].items():
            phase, agent = key.split("/", 1)
            with self.subTest(phase=phase, agent=agent):
                context = resolve_methodology_context(
                    phase=phase,
                    methodology="bmad",
                    agent=agent,
                    core_blobs=_bmad_vendor_core_blobs(),
                    require_bmad_core_blobs=True,
                )
                selected = [item["id"] for item in context["selected_skill_references"]]

                self.assertEqual(selected, expected)
                self.assertTrue(context["selected_skill_context"]["snippets"])
                self.assertTrue(context["selected_skill_context"]["quality_checks"])
                for skill_id in expected:
                    self.assertTrue((TEMPLATE_VENDOR_ROOT / skill_id / "SKILL.md").exists())
                self.assertLessEqual(
                    sum(
                        len(item["snippet"])
                        for item in context["selected_skill_context"]["snippets"]
                    ),
                    5000 + len("\n\n...[truncated]") * len(expected),
                )

    def test_manifest_enrichment_repairs_empty_bmad_skill_fields(self):
        stale_context = {
            "methodology": "bmad",
            "phase": "kit",
            "agent": "developer",
            "selected_skill_references": [],
            "selected_skill_context": {},
        }

        enriched = ensure_bmad_skill_context(
            stale_context,
            core_blobs=_bmad_vendor_core_blobs(),
            require_bmad_core_blobs=True,
        )

        self.assertEqual(
            [item["id"] for item in enriched["selected_skill_references"]],
            _manifest()["skill_selection"]["kit/developer"],
        )
        self.assertTrue(enriched["selected_skill_context"]["snippets"])
        self.assertTrue(enriched["skill_reference_policy"]["enabled"])

    def test_native_harper_does_not_select_bmad_skills(self):
        self.assertIsNone(resolve_methodology_context(phase="spec"))
        selection = select_bmad_skill_context(methodology=None, phase="spec", agent="pm")

        self.assertEqual(selection["selected_skill_ids"], [])
        self.assertEqual(selection["selected_skill_references"], [])

    def test_selected_snippets_are_bounded_and_include_contract_summaries(self):
        selection = select_bmad_skill_context(
            methodology="bmad",
            phase="spec",
            agent="pm",
            core_blobs=_bmad_vendor_core_blobs(),
            require_core_blobs=True,
            max_total_snippet_chars=1800,
        )
        snippets = selection["selected_skill_context"]["snippets"]

        self.assertEqual(selection["selected_skill_ids"], ["prd-shaping", "epic-framing", "acceptance-modeling"])
        self.assertTrue(snippets)
        self.assertLessEqual(sum(len(item["snippet"]) for item in snippets), 1800 + len("\n\n...[truncated]") * len(snippets))
        self.assertTrue(selection["selected_skill_context"]["required_outputs"])
        self.assertTrue(selection["selected_skill_context"]["quality_checks"])
        self.assertTrue(selection["selected_skill_context"]["forbidden_behavior"])

    def test_cloud_prompt_includes_skill_context_for_bmad_and_excludes_native(self):
        module = _load_gateway_prompt_module()
        bmad_context = resolve_methodology_context(
            phase="spec",
            methodology="bmad",
            agent="pm",
            core_blobs=_bmad_vendor_core_blobs(),
            require_bmad_core_blobs=True,
        )

        rendered = module.render_methodology_context_for_cloud_prompt(bmad_context)
        native = module.render_methodology_context_for_cloud_prompt(None)

        self.assertIn("### BMAD Skill Reference Context", rendered)
        self.assertIn("prd-shaping", rendered)
        self.assertIn("epic-framing", rendered)
        self.assertIn("acceptance-modeling", rendered)
        self.assertIn("BMAD runtime is not executed", rendered)
        self.assertNotIn("BMAD Skill Reference Context", native)

    def test_local_agent_context_includes_skill_references_for_bmad_kit_and_eval(self):
        kit_context = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
            core_blobs=_bmad_vendor_core_blobs(),
            require_bmad_core_blobs=True,
        )
        kit_package = build_kit_local_agent_package(
            payload=_base_payload(kit_context),
            req_id="REQ-001",
            execution_policy=_execution_policy(),
        )
        kit_json = _package_context(kit_package, "AGENT_EXECUTION_CONTEXT.json")

        eval_context = resolve_methodology_context(
            phase="eval",
            methodology="bmad",
            agent="qa",
            core_blobs=_bmad_vendor_core_blobs(),
            require_bmad_core_blobs=True,
        )
        eval_package = build_eval_local_agent_package(
            payload=_base_payload(eval_context),
            req_id="REQ-001",
            execution_policy=_execution_policy(),
        )
        eval_json = _package_context(eval_package, "AGENT_EVAL_CONTEXT.json")

        self.assertEqual(
            [item["id"] for item in kit_json["selected_skill_references"]],
            ["dev-story-execution", "story-readiness"],
        )
        self.assertEqual(
            [item["id"] for item in eval_json["selected_skill_references"]],
            ["qa-risk-review"],
        )
        self.assertIn("BMAD skill context", kit_package["local_agent"]["prompt_content"])
        self.assertIn("never execute BMAD runtime", kit_package["local_agent"]["prompt_content"])
        self.assertIn("BMAD skill context", eval_package["local_agent"]["prompt_content"])
        self.assertIn("canonical EvalRunner remains authoritative", eval_package["local_agent"]["prompt_content"])

    def test_local_agent_context_excludes_skill_references_for_native(self):
        package = build_kit_local_agent_package(
            payload=_base_payload(),
            req_id="REQ-001",
            execution_policy=_execution_policy(),
        )
        context = _package_context(package, "AGENT_EXECUTION_CONTEXT.json")

        self.assertNotIn("selected_skill_references", context)
        self.assertNotIn("skill_reference_policy", context)
        self.assertNotIn("BMAD skill context", package["local_agent"]["prompt_content"])

    def test_sync_tool_dry_run_does_not_write_files(self):
        tool = _load_sync_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            dest = root / "dest"
            source.mkdir()
            (source / "guide.md").write_text("# Guide\n", encoding="utf-8")

            summary = tool.sync_bmad_skills(source=source, dest=dest, dry_run=True)

            self.assertEqual(summary["imported_count"], 1)
            self.assertFalse(dest.exists())

    def test_sync_tool_imports_allowed_text_and_skips_hidden_and_binary(self):
        tool = _load_sync_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            dest = root / "dest"
            (source / ".hidden").mkdir(parents=True)
            (source / "node_modules/pkg").mkdir(parents=True)
            (source / "docs").mkdir(parents=True)
            (source / "docs/skill.md").write_text("# Skill\n", encoding="utf-8")
            (source / "docs/data.json").write_text('{"ok": true}\n', encoding="utf-8")
            (source / ".hidden/secret.md").write_text("# Hidden\n", encoding="utf-8")
            (source / "node_modules/pkg/readme.md").write_text("# Vendor\n", encoding="utf-8")
            (source / "docs/binary.md").write_bytes(b"\x00\x01binary")

            summary = tool.sync_bmad_skills(source=source, dest=dest, dry_run=False)
            manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
            imported_paths = [item["relative_path"] for item in manifest["imported_files"]]

            self.assertEqual(summary["imported_count"], 2)
            self.assertIn("docs/skill.md", imported_paths)
            self.assertIn("docs/data.json", imported_paths)
            self.assertNotIn(".hidden/secret.md", imported_paths)
            self.assertNotIn("node_modules/pkg/readme.md", imported_paths)
            self.assertNotIn("docs/binary.md", imported_paths)
            for item in manifest["imported_files"]:
                self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
            self.assertIs(manifest["runtime_execution_enabled"], False)
            self.assertIs(manifest["external_bmad_cli_enabled"], False)
            self.assertIs(manifest["network_fetch_enabled"], False)
            self.assertEqual(manifest["activated_by"], "methodology=bmad")
            self.assertIs(manifest["native_harper_active"], False)

    def test_sync_tool_check_only_validates_template_vendor_tree(self):
        tool = _load_sync_tool()
        summary = tool.validate_vendor_tree(TEMPLATE_VENDOR_ROOT)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["skill_count"], len(REQUIRED_SKILLS))

    def test_sync_tool_check_only_fails_missing_vendor_skill(self):
        tool = _load_sync_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vendor"
            root.mkdir()
            manifest = _vendor_manifest()
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                tool.validate_vendor_tree(root)

            self.assertIn("missing", str(raised.exception))

    def test_bmad_selection_from_core_blobs_fails_when_vendor_skill_missing(self):
        blobs = _bmad_vendor_core_blobs()
        blobs.pop(".clike/skills/vendor/bmad/dev-story-execution/SKILL.md")

        with self.assertRaises(Exception) as raised:
            select_bmad_skill_context(
                methodology="bmad",
                phase="kit",
                agent="developer",
                core_blobs=blobs,
                require_core_blobs=True,
            )

        self.assertIn("BMAD_SELECTED_SKILLS_MISSING", str(raised.exception))
        self.assertIn("dev-story-execution", str(raised.exception))

    def test_sync_tool_rejects_invalid_source_and_has_no_network_or_bmad_cli_execution(self):
        tool = _load_sync_tool()
        source_text = (REPO_ROOT / "tools/bmad_skill_sync.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                tool.sync_bmad_skills(source=Path(tmp) / "missing", dest=Path(tmp) / "dest")

        self.assertNotIn("subprocess", source_text)
        self.assertNotIn("requests", source_text)
        self.assertNotIn("urllib", source_text)
        self.assertNotIn("httpx", source_text)
        self.assertNotIn("npx bmad-method", source_text)


if __name__ == "__main__":
    unittest.main()
