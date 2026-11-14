"""Quality context (capacity profile, journey scenarios): same text for the cloud prompt and the
local agents (Claude Code, Codex), from the journey skills shipped by /init."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.context_sources import (  # noqa: E402
    append_context_sources_to_messages,
    attach_context_sources_to_local_package,
)
from services.quality_context import (  # noqa: E402
    build_quality_context,
    load_scenario_catalog,
    req_scenarios,
    resolve_capacity_profile,
)

TEMPLATE = Path(__file__).resolve().parents[2] / "extensions" / "vscode" / "templates" / "harper-init"


class CatalogTests(unittest.TestCase):
    def test_the_shipped_catalog_parses_with_unique_ids(self):
        catalog = load_scenario_catalog({}, TEMPLATE)
        names = [c["skill"] for c in catalog]
        self.assertEqual(names, sorted(names))
        for expected in ("journey-identity-access", "journey-ui-states", "journey-industrial-control", "journey-api-contract"):
            self.assertIn(expected, names)
        ids = [s["id"] for c in catalog for s in c["scenarios"]]
        self.assertEqual(len(ids), len(set(ids)))
        iam = {s["id"]: s for s in next(c for c in catalog if c["skill"] == "journey-identity-access")["scenarios"]}
        self.assertIn("reset", iam["IAM-05"]["title"].lower())
        self.assertEqual(iam["IAM-05"]["level"], "required")
        for c in catalog:  # every scenario is an EARS statement
            for s in c["scenarios"]:
                self.assertRegex(s["ears"], r"\b(shall)\b", s["id"])

    def test_core_blobs_win_over_the_workspace(self):
        blob = ("---\nname: journey-x\ndescription: d\nscenarios:\n"
                "  - XX-01 | required | One | When a, the system shall b.\n---\n")
        catalog = load_scenario_catalog({".clike/skills/journey-x/SKILL.md": blob}, TEMPLATE)
        self.assertEqual([c["skill"] for c in catalog], ["journey-x"])

    def test_req_scenarios_accepts_ids_and_objects(self):
        self.assertEqual(req_scenarios({"scenarios": ["iam-03", {"id": "UI-03"}, "IAM-03", "nonsense"]}), ["IAM-03", "UI-03"])


class ProfileTests(unittest.TestCase):
    def test_explicit_profile_or_executor_default(self):
        self.assertEqual(resolve_capacity_profile({"capacityProfile": "c3"}, "cloud"), "C3")
        self.assertEqual(resolve_capacity_profile({"flags": {"capacityProfile": "C1"}}, "local_agent"), "C1")
        self.assertEqual(resolve_capacity_profile({}, "local_agent"), "C2")
        self.assertEqual(resolve_capacity_profile({"capacityProfile": "big"}, "cloud"), "C1")


class PhaseBlockTests(unittest.TestCase):
    def test_spec_lists_every_scenario_with_its_statement(self):
        q = build_quality_context(phase="spec", payload={}, execution_mode="cloud", req_id=None, workspace_root=TEMPLATE)
        self.assertIn("## Scenarios", q["text"])
        self.assertIn("IAM-05 (required)", q["text"])
        self.assertIn("excluded — <reason>", q["text"])

    def test_plan_has_profile_seams_and_scenario_assignment(self):
        q = build_quality_context(phase="plan", payload={}, execution_mode="local_agent", req_id=None, workspace_root=TEMPLATE)
        self.assertEqual(q["profile"], "C2")
        for needle in ("REQ capacity profile: C2", "vertical slice", "Shared seams", "reqs[].scenarios"):
            self.assertIn(needle, q["text"])
        c3 = build_quality_context(phase="plan", payload={"capacityProfile": "C3"}, execution_mode="cloud", req_id=None, workspace_root=TEMPLATE)
        self.assertIn('"features"', c3["text"])

    def test_plan_without_catalog_still_gets_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = build_quality_context(phase="plan", payload={}, execution_mode="cloud", req_id=None, workspace_root=Path(tmp))
            self.assertIn("REQ capacity profile: C1", q["text"])
            self.assertNotIn("### Scenarios", q["text"])
            spec = build_quality_context(phase="spec", payload={}, execution_mode="cloud", req_id=None, workspace_root=Path(tmp))
            self.assertEqual(spec["text"], "")

    def _kit(self, req):
        plan = json.dumps({"reqs": [req]})
        blobs = {"docs/harper/plan.json": plan}
        return build_quality_context(phase="kit", payload={"core_blobs": blobs}, execution_mode="cloud",
                                     req_id=req["id"], workspace_root=TEMPLATE)

    def test_kit_gets_the_statements_of_its_scenarios(self):
        q = self._kit({"id": "REQ-002", "scenarios": ["IAM-03", "UI-03"]})
        self.assertEqual(q["scenarios"], ["IAM-03", "UI-03"])
        self.assertIn("IAM-03 Wrong credentials — If a user submits", q["text"])
        self.assertIn("docs/ACCEPTANCE.json", q["text"])
        self.assertNotIn("one feature at a time", q["text"])

    def test_kit_gets_the_test_idioms_of_its_lane_for_cloud_and_agents(self):
        # the agents read references/ natively; the cloud gets the same lane sections in the KIT block
        q = self._kit({"id": "REQ-002", "lane": "python", "scenarios": ["IAM-03", "UI-03", "DAT-04"]})
        text = q["text"]
        self.assertIn("How to prove them in this lane", text)
        self.assertIn("#### journey-identity-access\n##### Python", text)
        self.assertIn("#### journey-ui-states\n##### TypeScript / web", text)  # the UI journey in its web form
        self.assertNotIn("##### Java", text)
        self.assertNotIn("vitest + Testing Library; render the login form", text)  # web idioms only for the UI journey
        # a role lane (backend) takes the language from the REQ's own text
        q = self._kit({"id": "REQ-003", "lane": "backend", "technical_scope": "Spring Boot service, JUnit 5",
                       "scenarios": ["API-13"]})
        self.assertIn("##### Java", q["text"])
        # a REQ in a language without idioms gets the scenarios, not foreign idioms
        q = self._kit({"id": "REQ-004", "lane": "sql", "scenarios": ["DAT-02"]})
        self.assertNotIn("How to prove them in this lane", q["text"])

    def test_kit_of_an_epic_runs_feature_by_feature(self):
        q = self._kit({"id": "REQ-004", "profile": "C3", "scenarios": []})
        self.assertIn("FEATURES.json", q["text"])
        self.assertIn("PROGRESS.md", q["text"])

    def test_kit_reads_plan_json_sent_by_file_name(self):
        plan = json.dumps({"reqs": [{"id": "REQ-007", "scenarios": ["UI-03"]}]})
        with tempfile.TemporaryDirectory() as tmp:  # no plan on disk: only the core blob
            q = build_quality_context(phase="kit", payload={"core_blobs": {"plan.json": plan, **{
                f".clike/skills/{p.parent.name}/SKILL.md": p.read_text() for p in (TEMPLATE / ".clike" / "skills").glob("journey-*/SKILL.md")}}},
                execution_mode="local_agent", req_id="REQ-007", workspace_root=Path(tmp))
        self.assertEqual(q["scenarios"], ["UI-03"])
        self.assertIn("UI-03", q["text"])

    def test_kit_without_scenarios_or_epic_adds_nothing(self):
        self.assertEqual(self._kit({"id": "REQ-009"})["text"], "")

    def test_companion_only_roles_get_no_quality_block(self):
        for phase, agent in (("spec", "ux"), ("plan", "pm")):
            role = {"methodology": "bmad", "agent": agent, "artifact_policy": {"companion_only": True}}
            q = build_quality_context(phase=phase, payload={}, execution_mode="cloud", req_id=None,
                                      workspace_root=TEMPLATE, methodology_context=role)
            self.assertEqual(q["text"], "", (phase, agent))

    def test_canonical_roles_keep_the_quality_block(self):
        for role in (None, {"methodology": "bmad", "agent": "architect", "artifact_policy": {"companion_only": False}}):
            q = build_quality_context(phase="plan", payload={}, execution_mode="cloud", req_id=None,
                                      workspace_root=TEMPLATE, methodology_context=role)
            self.assertIn("capacity profile", q["text"].lower())


class ParityTests(unittest.TestCase):
    """The same quality text reaches the cloud prompt and the local agent package."""

    def _context(self):
        q = build_quality_context(phase="plan", payload={}, execution_mode="cloud", req_id=None, workspace_root=TEMPLATE)
        return {"phase": "plan", "origin": None, "items": [], "quality": q}, q["text"]

    def test_cloud_gets_it_at_the_end_of_the_user_message(self):
        context, text = self._context()
        messages = append_context_sources_to_messages(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], context)
        self.assertTrue(messages[1]["content"].endswith(text))
        self.assertEqual(messages[0]["content"], "s")

    def test_local_agent_gets_it_in_the_prompt_and_as_a_file(self):
        context, text = self._context()
        local = {"phase": "plan", "prompt_path": "runs/plan/AGENT_PROMPT.md", "prompt_content": "do the plan",
                 "package_files": [{"path": "runs/plan/AGENT_PROMPT.md", "content": "do the plan"}]}
        out = attach_context_sources_to_local_package({"local_agent": local}, context)["local_agent"]
        self.assertIn(text, out["prompt_content"])
        files = {f["path"]: f["content"] for f in out["package_files"]}
        self.assertEqual(files["runs/context/plan/CLIKE_QUALITY.md"].strip(), text)
        self.assertEqual(files["runs/plan/AGENT_PROMPT.md"], out["prompt_content"])


if __name__ == "__main__":
    unittest.main()


class RequestModelTests(unittest.TestCase):
    def test_the_capacity_profile_of_the_extension_reaches_the_orchestrator(self):
        from schemas.harper import HarperPhaseRequest

        payload = HarperPhaseRequest(cmd="plan", phase="plan", capacityProfile="C3").model_dump()
        self.assertEqual(payload["capacityProfile"], "C3")
        self.assertEqual(resolve_capacity_profile(payload, "local_agent"), "C3")
