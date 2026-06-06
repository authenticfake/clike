import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.methodologies.errors import (
    MethodologyPhaseAgentError,
    MissingMethodologyError,
    UnsupportedMethodologyAgentError,
    UnsupportedMethodologyError,
)
from services.methodologies.resolver import resolve_methodology_context


BMAD_MANIFEST_PATH = REPO_ROOT / "orchestrator" / "methodologies" / "bmad" / "manifest.json"
BMAD_PROFILE_ROOT = REPO_ROOT / "orchestrator" / "methodologies" / "bmad"


def _bmad_manifest():
    return json.loads(BMAD_MANIFEST_PATH.read_text(encoding="utf-8"))


def _profile_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class MethodologyResolverTests(unittest.TestCase):
    def test_bmad_manifest_provenance_is_machine_readable(self):
        manifest = _bmad_manifest()
        provenance = manifest["provenance"]
        review_policy = manifest["reference_review_policy"]

        self.assertEqual(provenance["profile_owner"], "CLike")
        self.assertEqual(provenance["profile_type"], "clike-owned-bmad-aware-methodology-profile")
        self.assertEqual(provenance["reference_name"], "BMAD Method")
        self.assertIsInstance(provenance["reference_repository"], str)
        self.assertIsInstance(provenance["reference_docs"], str)
        self.assertEqual(provenance["review_policy"], "manual-review-only")
        self.assertIs(provenance["auto_track_latest_at_runtime"], False)
        self.assertEqual(
            provenance["mapping_report_path"],
            "docs/integrations/bmad/PROFILE_SYNC_REPORT.md",
        )
        self.assertTrue((REPO_ROOT / provenance["mapping_report_path"]).exists())
        self.assertEqual(provenance["fixture_workspace_strategy"], "optional-manual-comparison-only")

        self.assertIs(review_policy["clike_does_not_auto_track_bmad_latest_at_runtime"], True)
        self.assertIn("manual review", review_policy["review_flow"])
        self.assertIn("agent responsibilities", review_policy["adopted_concepts"])
        self.assertIn("runtime dependency", review_policy["excluded_concepts"])

    def test_bmad_manifest_runtime_dependency_flags_are_false(self):
        manifest = _bmad_manifest()
        provenance = manifest["provenance"]
        governance = manifest["governance"]

        for key in [
            "runtime_dependency_enabled",
            "external_bmad_cli_enabled",
            "official_bmad_runtime_content_vendored",
        ]:
            with self.subTest(key=key):
                self.assertIs(provenance[key], False)
                self.assertIs(governance[key], False)

    def test_bmad_manifest_artifact_policy_baseline_exists(self):
        manifest = _bmad_manifest()
        policy = manifest["artifact_policy"]

        for key in [
            "idea/analyst",
            "spec/pm",
            "spec/ux",
            "plan/architect",
            "plan/pm",
            "kit/developer",
            "eval/qa",
            "finalize/tech-writer",
        ]:
            with self.subTest(key=key):
                entry = policy[key]
                self.assertIn("canonical_outputs", entry)
                self.assertIn("mandatory_companion_outputs", entry)
                self.assertIn("allowed_companion_root_globs", entry)
                self.assertIn("forbidden_outputs", entry)
                self.assertEqual(entry["conflict_resolution"], "canonical-wins")
                self.assertIs(entry["open_ended_generation_allowed"], True)

    def test_bmad_agent_and_workflow_files_exist(self):
        manifest = _bmad_manifest()

        for agent in manifest["supported_agents"]:
            with self.subTest(agent=agent):
                profile_path = BMAD_PROFILE_ROOT / manifest["agents"][agent]["profile_path"]
                self.assertTrue(profile_path.exists(), f"Missing BMAD agent profile: {profile_path}")

        for phase, workflow in manifest["workflows"].items():
            with self.subTest(phase=phase):
                workflow_path = BMAD_PROFILE_ROOT / workflow["workflow_path"]
                self.assertTrue(workflow_path.exists(), f"Missing BMAD workflow profile: {workflow_path}")

    def test_bmad_profiles_have_reference_mapping_sections(self):
        manifest = _bmad_manifest()
        profile_paths = [
            BMAD_PROFILE_ROOT / manifest["agents"][agent]["profile_path"]
            for agent in manifest["supported_agents"]
        ]
        profile_paths.extend(
            BMAD_PROFILE_ROOT / workflow["workflow_path"]
            for workflow in manifest["workflows"].values()
        )

        required_markers = [
            "## Reference mapping",
            "BMAD concept adopted",
            "CLike adaptation",
            "Artifact outputs",
            "Handoff consumers",
            "Governance constraints",
        ]
        required_agent_markers = [
            "## Role intent",
            "## Required inputs",
            "## Canonical outputs",
            "## Companion outputs",
            "## Quality bar",
            "## Downstream handoff",
            "## Forbidden behavior",
        ]
        required_workflow_markers = [
            "## Phase goal",
            "## Step-by-step artifact workflow",
            "## Mandatory companion outputs",
            "## Optional open-ended companion outputs under allowed roots",
            "## Handoff rules",
            "## Readiness checklist",
            "## Governance constraints",
        ]

        for path in profile_paths:
            text = _profile_text(path)
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                for marker in required_markers:
                    self.assertIn(marker, text)
                if "/agents/" in path.as_posix():
                    for marker in required_agent_markers:
                        self.assertIn(marker, text)
                if "/workflows/" in path.as_posix():
                    for marker in required_workflow_markers:
                        self.assertIn(marker, text)

    def test_bmad_workflows_reference_mandatory_companion_outputs(self):
        manifest = _bmad_manifest()
        phase_to_policy_keys = {
            "idea": ["idea/analyst"],
            "spec": ["spec/pm", "spec/ux"],
            "plan": ["plan/architect", "plan/pm"],
            "kit": ["kit/developer"],
            "eval": ["eval/qa"],
            "finalize": ["finalize/tech-writer"],
        }

        for phase, policy_keys in phase_to_policy_keys.items():
            workflow_path = BMAD_PROFILE_ROOT / manifest["workflows"][phase]["workflow_path"]
            workflow_text = _profile_text(workflow_path)
            with self.subTest(phase=phase):
                for policy_key in policy_keys:
                    for output in manifest["artifact_policy"][policy_key]["mandatory_companion_outputs"]:
                        self.assertIn(output, workflow_text)

    def test_bmad_profiles_state_core_governance_constraints(self):
        manifest = _bmad_manifest()
        profile_paths = [
            BMAD_PROFILE_ROOT / manifest["agents"][agent]["profile_path"]
            for agent in manifest["supported_agents"]
        ]
        profile_paths.extend(
            BMAD_PROFILE_ROOT / workflow["workflow_path"]
            for workflow in manifest["workflows"].values()
        )

        for path in profile_paths:
            text = _profile_text(path).lower()
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                self.assertIn("canonical artifacts", text)
                self.assertIn("eval/gate", text)
                self.assertIn("write boundaries", text)
                self.assertIn("no bmad runtime", text)

    def test_bmad_default_agent_resolution_per_phase(self):
        cases = [
            ("idea", "analyst"),
            ("spec", "pm"),
            ("plan", "architect"),
            ("kit", "developer"),
            ("eval", "qa"),
            ("finalize", "tech-writer"),
        ]

        for phase, expected_agent in cases:
            with self.subTest(phase=phase):
                context = resolve_methodology_context(phase=phase, methodology="bmad")

                self.assertEqual(context["methodology"], "bmad")
                self.assertEqual(context["phase"], phase)
                self.assertEqual(context["agent"], expected_agent)
                self.assertEqual(context["default_agent"], expected_agent)
                self.assertIn("workflow_summary", context)
                self.assertIn("artifact_policy", context)
                self.assertIsInstance(context["workflow_focus"], list)
                self.assertIsInstance(context["required_context"], list)
                self.assertIsInstance(context["companion_artifacts"], list)
                self.assertIsInstance(context["governance_boundaries"], list)

    def test_bmad_explicit_agent_resolution(self):
        context = resolve_methodology_context(
            phase="plan",
            methodology="bmad",
            agent="pm",
        )

        self.assertEqual(context["agent"], "pm")
        self.assertEqual(context["requested_agent"], "pm")
        self.assertEqual(context["allowed_agents"], ["architect", "pm"])

    def test_allowed_explicit_roles_per_phase(self):
        cases = [
            ("idea", "analyst"),
            ("spec", "pm"),
            ("spec", "ux"),
            ("plan", "architect"),
            ("plan", "pm"),
            ("kit", "developer"),
            ("eval", "qa"),
            ("eval", "developer"),
            ("finalize", "tech-writer"),
        ]

        for phase, agent in cases:
            with self.subTest(phase=phase, agent=agent):
                context = resolve_methodology_context(
                    phase=phase,
                    methodology="bmad",
                    agent=agent,
                )

                self.assertEqual(context["agent"], agent)
                self.assertIn(agent, context["allowed_agents"])

    def test_phase_agent_allowances_match_bmad_profile(self):
        self.assertEqual(
            resolve_methodology_context(phase="idea", methodology="bmad")["agent"],
            "analyst",
        )
        self.assertEqual(
            resolve_methodology_context(phase="spec", methodology="bmad", agent="ux")["agent"],
            "ux",
        )
        self.assertEqual(
            resolve_methodology_context(phase="plan", methodology="bmad", agent="pm")["agent"],
            "pm",
        )
        self.assertEqual(
            resolve_methodology_context(phase="kit", methodology="bmad")["agent"],
            "developer",
        )
        self.assertEqual(
            resolve_methodology_context(phase="finalize", methodology="bmad")["agent"],
            "tech-writer",
        )

    def test_plan_workflow_metadata_is_implementation_legible(self):
        context = resolve_methodology_context(phase="plan", methodology="bmad")
        focus_text = " ".join(context["workflow_focus"]).lower()

        self.assertIn("functional", focus_text)
        self.assertIn("security", focus_text)
        self.assertIn("integration", focus_text)
        self.assertIn("data contracts", focus_text)
        self.assertIn("what later reqs may assume", focus_text)
        self.assertIn("TECH_CONSTRAINTS.yaml", context["required_context"])

    def test_workflow_metadata_and_governance_boundaries_exist(self):
        context = resolve_methodology_context(phase="kit", methodology="bmad")

        self.assertIn("workflow_summary", context)
        self.assertTrue(context["workflow_summary"])
        self.assertGreaterEqual(len(context["workflow_focus"]), 1)
        self.assertGreaterEqual(len(context["required_context"]), 1)
        self.assertGreaterEqual(len(context["companion_artifacts"]), 1)
        self.assertGreaterEqual(len(context["governance_boundaries"]), 1)
        boundaries = " ".join(context["governance_boundaries"]).lower()
        self.assertIn("allowed_write_roots", boundaries)
        self.assertIn("forbidden_paths", boundaries)
        self.assertIn("eval/gate", boundaries)

    def test_kit_developer_selects_bmad_skill_context(self):
        explicit = resolve_methodology_context(
            phase="kit",
            methodology="bmad",
            agent="developer",
        )
        defaulted = resolve_methodology_context(phase="kit", methodology="bmad")

        for context in [explicit, defaulted]:
            self.assertEqual(context["agent"], "developer")
            self.assertEqual(
                [item["id"] for item in context["selected_skill_references"]],
                ["dev-story-execution", "story-readiness"],
            )
            self.assertIn("selected_skill_context", context)
            self.assertIn("skill_reference_policy", context)

        self.assertIsNone(resolve_methodology_context(phase="kit"))

    def test_spec_ux_artifact_policy_is_companion_only_and_forbids_spec(self):
        context = resolve_methodology_context(phase="spec", methodology="bmad", agent="ux")
        policy = context["artifact_policy"]

        self.assertEqual(policy["canonical_outputs"], [])
        self.assertIs(policy["companion_only"], True)
        self.assertIn("docs/harper/SPEC.md", policy["forbidden_outputs"])
        self.assertIn("docs/harper/ux/DESIGN.md", policy["mandatory_companion_outputs"])
        self.assertIn("docs/harper/ux/SPEC_UX_APPENDIX.md", policy["mandatory_companion_outputs"])
        self.assertIn("docs/harper/ux/**", policy["allowed_companion_root_globs"])
        self.assertEqual(policy["allowed_companion_root_globs"], ["docs/harper/ux/**"])
        self.assertEqual(policy["conflict_resolution"], "canonical-wins")
        self.assertIs(policy["open_ended_generation_allowed"], True)

    def test_spec_pm_artifact_policy_owns_canonical_spec(self):
        context = resolve_methodology_context(phase="spec", methodology="bmad", agent="pm")
        policy = context["artifact_policy"]

        self.assertIn("docs/harper/SPEC.md", policy["canonical_outputs"])
        self.assertIs(policy["companion_only"], False)
        self.assertNotIn("docs/harper/SPEC.md", policy["forbidden_outputs"])
        self.assertIn("docs/harper/bmad/spec/PRD.md", policy["mandatory_companion_outputs"])
        self.assertIn("docs/harper/bmad/spec/EPICS.md", policy["mandatory_companion_outputs"])
        self.assertTrue(
            all(
                item.startswith("docs/harper/bmad/spec/")
                for item in policy["mandatory_companion_outputs"]
            )
        )
        self.assertIn("docs/harper/bmad/spec/**", policy["allowed_companion_root_globs"])

    def test_eval_qa_artifact_policy_is_advisory_only(self):
        context = resolve_methodology_context(phase="eval", methodology="bmad", agent="qa")
        policy = context["artifact_policy"]

        self.assertIs(context["advisory_only"], True)
        self.assertEqual(context["authority"], "advisory")
        self.assertEqual(policy["canonical_outputs"], [])
        self.assertEqual(policy["authority"], "advisory-companion-context-only")
        self.assertIn("runs/kit/<REQ-ID>/docs/BMAD_QA_ADVISORY.md", policy["mandatory_companion_outputs"])
        self.assertIn("runs/kit/<REQ-ID>/docs/**", policy["allowed_companion_root_globs"])

    def test_agent_without_methodology_is_rejected(self):
        with self.assertRaisesRegex(MissingMethodologyError, "--agent requires --methodology"):
            resolve_methodology_context(phase="kit", agent="developer")

    def test_invalid_methodology_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedMethodologyError, "Unsupported methodology: scrum"):
            resolve_methodology_context(phase="spec", methodology="scrum")

    def test_invalid_bmad_agent_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedMethodologyAgentError, "Unsupported BMAD agent: coach"):
            resolve_methodology_context(phase="spec", methodology="bmad", agent="coach")

    def test_invalid_phase_agent_mapping_is_rejected(self):
        with self.assertRaisesRegex(MethodologyPhaseAgentError, "not allowed for phase 'kit'"):
            resolve_methodology_context(phase="kit", methodology="bmad", agent="architect")

    def test_eval_is_advisory_only(self):
        context = resolve_methodology_context(phase="eval", methodology="bmad")

        self.assertEqual(context["agent"], "qa")
        self.assertIs(context["advisory_only"], True)
        self.assertEqual(context["authority"], "advisory")

    def test_gate_has_no_bmad_authority_context(self):
        context = resolve_methodology_context(phase="gate", methodology="bmad")

        self.assertIsNone(context["agent"])
        self.assertEqual(context["allowed_agents"], [])
        self.assertIsNone(context["default_agent"])
        self.assertIs(context["advisory_only"], False)
        self.assertEqual(context["authority"], "clike_only")
        self.assertNotIn("artifact_policy", context)

    def test_gate_rejects_explicit_bmad_agent(self):
        with self.assertRaisesRegex(MethodologyPhaseAgentError, "Gate remains CLike-only"):
            resolve_methodology_context(phase="gate", methodology="bmad", agent="qa")


if __name__ == "__main__":
    unittest.main()
