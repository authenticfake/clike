import json
from pathlib import Path

from services.local_agent_package import (
    build_eval_local_agent_package,
    build_finalize_local_agent_package,
    build_kit_local_agent_package,
)
from services.methodologies.errors import ClikeSelectedCapabilitiesMissingError
from services.methodologies.resolver import resolve_methodology_context
from utils.namespace_paths import python_module_boundary_to_package_path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "orchestrator/methodologies/bmad/manifest.json"
TEMPLATE_VENDOR_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _execution_policy():
    return {
        "requested": "prefer_local_agent",
        "selected": "local_agent",
        "reason": "test",
        "phase_supported": True,
    }


def _selected_capability_blobs(req_id: str = "REQ-001"):
    index = {
        "schema_version": "clike.capability_index.v1",
        "repo_root": "/workspace/project",
        "skills": [
            {
                "kind": "skill",
                "name": "provider-realism",
                "description": "Use real provider SDK seams where the REQ names a provider.",
                "path": ".clike/skills/provider-realism/SKILL.md",
                "metadata": {"phases": ["kit", "eval"], "gate_required": "true"},
                "preview": "# Provider Realism\n\n## Required behavior\nUse SDK-backed adapter seams.\n",
            }
        ],
        "packs": [
            {
                "kind": "pack",
                "name": "enterprise-python",
                "description": "Enterprise Python runtime constraints.",
                "path": ".clike/packs/enterprise-python/PACK.md",
                "metadata": {"default_runtime_profiles": ["python"]},
                "preview": "# Enterprise Python\n\n## Eval expectations\nRun deterministic tests.\n",
            }
        ],
        "design_profiles": [
            {
                "kind": "design_profile",
                "name": "ops-console",
                "description": "Operational console interaction profile.",
                "path": ".clike/design-profiles/ops-console/DESIGN.md",
                "metadata": {"strictness": "advisory"},
                "preview": "# Ops Console\n\n## UX principles\nDense, scannable operational UI.\n",
            }
        ],
    }
    selected = {
        "schema_version": "clike.selected_capability_context.v1",
        "req_id": req_id,
        "packs": {
            "selected": ["enterprise-python"],
            "resolved": [index["packs"][0]],
            "missing": [],
        },
        "skills": {
            "selected": ["provider-realism"],
            "resolved": [index["skills"][0]],
            "missing": [],
        },
        "design_profiles": {
            "selected": ["ops-console"],
            "resolved": [index["design_profiles"][0]],
            "missing": [],
        },
        "selection_policy": {
            "source": "plan.json/TARGET_CONTRACT.json",
            "binding_for_kit": True,
            "missing_selected_capability_is_blocking_gap": True,
        },
    }
    return {
        "CLIKE_CAPABILITY_MANIFEST.md": "# CLike Capability Manifest\n\n## Skills\n- provider-realism\n",
        "CLIKE_CAPABILITY_INDEX.json": json.dumps(index, ensure_ascii=False, indent=2),
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": (
            "# CLike Selected Capability Context\n\n"
            f"Target REQ: `{req_id}`\n\n"
            "## Selected Skills\n\n"
            "### Skill: provider-realism\n"
        ),
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": json.dumps(selected, ensure_ascii=False, indent=2),
    }


def _bmad_vendor_core_blobs():
    blobs = {
        ".clike/skills/vendor/bmad/manifest.json": (TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")
    }
    for path in sorted(TEMPLATE_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _payload(methodology_context=None):
    req = {
        "id": "REQ-001",
        "title": "Build provider boundary",
        "status": "open",
        "acceptance": ["Provider boundary is testable"],
        "dependsOn": [],
        "lane": "python",
        "domain": "runtime",
        "runtime_profile": "python",
        "packs": ["enterprise-python"],
        "skills": ["provider-realism"],
        "design_profiles": ["ops-console"],
        "gate_expectations": ["provider realism evidence"],
        "main_module_boundary": "coffeebuddy.runtime",
    }
    payload = {
        "runId": "local-agent-test",
        "project_id": "project",
        "project_name": "Project",
        "localAgentExecutor": "gpt_codex",
        "localAgentCapabilities": {},
        "core_blobs": {
            "IDEA.md": "# IDEA - Project\n",
            "SPEC.md": "# SPEC\n",
            "PLAN.md": "# PLAN\n",
            "TECH_CONSTRAINTS.yaml": "tech_constraints:\n  runtime: python\n",
            "plan.json": json.dumps({"reqs": [req]}),
            **_selected_capability_blobs(),
            **_bmad_vendor_core_blobs(),
        },
    }
    if methodology_context:
        payload["methodology_context"] = methodology_context
    return payload


def _package_context(package):
    for item in _package_files(package):
        if item["path"].endswith("AGENT_EXECUTION_CONTEXT.json"):
            return json.loads(item["content"])
    raise AssertionError("missing AGENT_EXECUTION_CONTEXT.json")


def _package_json(package, suffix):
    for item in _package_files(package):
        if item["path"].endswith(suffix):
            return json.loads(item["content"])
    raise AssertionError(f"missing package context: {suffix}")


def _package_files(package):
    for item in package["local_agent"]["package_files"]:
        if isinstance(item, list):
            yield from item
        else:
            yield item


def _package_file_content(package, suffix):
    for item in _package_files(package):
        if item["path"].endswith(suffix):
            return item["content"]
    raise AssertionError(f"missing package file: {suffix}")


def test_bmad_kit_local_agent_contains_bmad_skills_and_selected_clike_capabilities():
    methodology_context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
    )
    package = build_kit_local_agent_package(
        payload=_payload(methodology_context),
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)

    assert [item["id"] for item in context["selected_skill_references"]] == [
        "dev-story-execution",
        "story-readiness",
    ]
    assert context["selected_skill_context"]["required_outputs"]
    assert context["skill_reference_policy"]["local_agent_context_enabled"] is True
    assert context["capability_context"]["skills"] == ["provider-realism"]
    assert context["capability_context"]["packs"] == ["enterprise-python"]
    assert context["capability_context"]["design_profiles"] == ["ops-console"]
    assert context["capability_context"]["manifest"]["selected_context_available"] is True
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert context["selected_clike_packs"] == ["enterprise-python"]
    assert context["selected_clike_design_profiles"] == ["ops-console"]
    assert context["context_envelope"]["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]
    assert context["namespace_materialization"]["package_path"] == "coffeebuddy/runtime"

    selected_json = json.loads(_package_file_content(package, "CLIKE_SELECTED_CAPABILITY_CONTEXT.json"))
    assert selected_json["skills"]["resolved"][0]["name"] == "provider-realism"
    assert "### CLike Selected Capability Context" in package["local_agent"]["prompt_content"]
    assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]
    assert "dev-story-execution" in package["local_agent"]["prompt_content"]
    assert "story-readiness" in package["local_agent"]["prompt_content"]
    assert "CLIKE_SELECTED_CAPABILITY_CONTEXT.md" in package["local_agent"]["prompt_content"]
    assert "Do not create `src/coffeebuddy.runtime`" in package["local_agent"]["prompt_content"]


def test_bmad_kit_local_agent_generates_selected_capability_context_when_missing_or_empty():
    methodology_context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
    )
    payload = _payload(methodology_context)
    payload["core_blobs"]["CLIKE_SELECTED_CAPABILITY_CONTEXT.md"] = ""
    payload["core_blobs"]["CLIKE_SELECTED_CAPABILITY_CONTEXT.json"] = "{}"

    package = build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)

    assert context["context_envelope"]["clike_capabilities"]["selected_packs"] == ["enterprise-python"]
    assert context["context_envelope"]["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert context["context_envelope"]["clike_capabilities"]["selected_design_profiles"] == ["ops-console"]
    selected_json = json.loads(_package_file_content(package, "CLIKE_SELECTED_CAPABILITY_CONTEXT.json"))
    assert selected_json["skills"]["selected"] == ["provider-realism"]


def test_kit_local_agent_generates_selected_capability_context_from_raw_clike_core_blobs():
    payload = _payload()
    for key in [
        "CLIKE_CAPABILITY_MANIFEST.md",
        "CLIKE_CAPABILITY_INDEX.json",
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md",
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.json",
    ]:
        payload["core_blobs"].pop(key, None)
    payload["core_blobs"].update(
        {
            ".clike/skills/provider-realism/SKILL.md": (
                "---\n"
                "name: provider-realism\n"
                "description: Provider adapters must stay realistic.\n"
                "---\n"
                "# Provider Realism\n\n"
                "## Required behavior\nUse real SDK seams.\n"
            ),
            ".clike/packs/enterprise-python/PACK.md": (
                "---\n"
                "name: enterprise-python\n"
                "description: Enterprise Python runtime policy.\n"
                "---\n"
                "# Enterprise Python\n"
            ),
            ".clike/design-profiles/ops-console/DESIGN.md": (
                "---\n"
                "name: ops-console\n"
                "description: Operational UI profile.\n"
                "---\n"
                "# Ops Console\n"
            ),
        }
    )

    package = build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)

    assert context["context_envelope"]["clike_capabilities"]["selected_packs"] == ["enterprise-python"]
    assert context["context_envelope"]["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert context["context_envelope"]["clike_capabilities"]["selected_design_profiles"] == ["ops-console"]
    selected_json = json.loads(_package_file_content(package, "CLIKE_SELECTED_CAPABILITY_CONTEXT.json"))
    assert selected_json["packs"]["resolved"][0]["path"] == ".clike/packs/enterprise-python/PACK.md"
    assert selected_json["skills"]["resolved"][0]["path"] == ".clike/skills/provider-realism/SKILL.md"
    capability_index = json.loads(_package_file_content(package, "CLIKE_CAPABILITY_INDEX.json"))
    assert "dev-story-execution" not in [item["name"] for item in capability_index["skills"]]


def test_bmad_kit_local_agent_preserves_nested_req_capabilities():
    methodology_context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
    )
    payload = _payload(methodology_context)
    plan = json.loads(payload["core_blobs"]["plan.json"])
    req = plan["reqs"][0]
    req.pop("packs")
    req.pop("skills")
    req.pop("design_profiles")
    req["capabilities"] = {
        "packs": ["enterprise-python"],
        "skills": ["provider-realism"],
        "design_profiles": ["ops-console"],
    }
    payload["core_blobs"]["plan.json"] = json.dumps(plan)
    payload["core_blobs"].pop("CLIKE_SELECTED_CAPABILITY_CONTEXT.md")
    payload["core_blobs"].pop("CLIKE_SELECTED_CAPABILITY_CONTEXT.json")

    package = build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)

    assert context["selected_clike_packs"] == ["enterprise-python"]
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert context["selected_clike_design_profiles"] == ["ops-console"]
    assert context["context_envelope"]["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert [item["id"] for item in context["selected_skill_references"]] == [
        "dev-story-execution",
        "story-readiness",
    ]


def test_kit_local_agent_fails_when_declared_clike_capabilities_cannot_be_resolved():
    payload = _payload()
    payload["core_blobs"].pop("CLIKE_CAPABILITY_INDEX.json")
    payload["core_blobs"].pop("CLIKE_SELECTED_CAPABILITY_CONTEXT.md")
    payload["core_blobs"].pop("CLIKE_SELECTED_CAPABILITY_CONTEXT.json")

    try:
        build_kit_local_agent_package(
            payload=payload,
            req_id="REQ-001",
            execution_policy=_execution_policy(),
        )
    except ClikeSelectedCapabilitiesMissingError as exc:
        assert "CLIKE_SELECTED_CAPABILITIES_MISSING" in str(exc)
        assert "provider-realism" in str(exc)
    else:
        raise AssertionError("expected CLIKE_SELECTED_CAPABILITIES_MISSING")


def test_bmad_kit_local_agent_rehydrates_stale_empty_skill_context_from_manifest():
    stale_context = {
        "methodology": "bmad",
        "phase": "kit",
        "agent": "developer",
        "selected_skill_references": [],
        "selected_skill_context": {},
        "skill_reference_policy": {},
    }

    package = build_kit_local_agent_package(
        payload=_payload(stale_context),
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)
    expected = _manifest()["skill_selection"]["kit/developer"]

    assert [item["id"] for item in context["methodology_context"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["selected_skill_references"]] == expected
    assert context["selected_skill_context"]["snippets"]
    assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]
    for skill_id in expected:
        assert skill_id in package["local_agent"]["prompt_content"]


def test_bmad_kit_local_agent_rehydrates_compact_client_methodology_context_from_manifest():
    payload = _payload(
        {
            "methodology": "bmad",
            "agent": "developer",
            "selected_skill_references": [],
            "selected_skill_context": {},
        }
    )

    package = build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)
    expected = _manifest()["skill_selection"]["kit/developer"]

    assert [item["id"] for item in context["methodology_context"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["selected_skill_references"]] == expected
    assert context["selected_skill_context"]["snippets"]
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]
    for skill_id in expected:
        assert skill_id in package["local_agent"]["prompt_content"]


def test_bmad_kit_local_agent_resolves_skills_from_top_level_methodology_and_agent():
    payload = _payload()
    payload["phase"] = "kit"
    payload["methodology"] = "bmad"
    payload["agent"] = "developer"

    package = build_kit_local_agent_package(
        payload=payload,
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)
    expected = _manifest()["skill_selection"]["kit/developer"]

    assert [item["id"] for item in context["methodology_context"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]] == expected
    assert [item["id"] for item in context["selected_skill_references"]] == expected
    assert context["selected_skill_context"]["snippets"]
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]
    for skill_id in expected:
        assert skill_id in package["local_agent"]["prompt_content"]


def test_native_kit_local_agent_contains_selected_clike_capabilities_without_bmad_skills():
    package = build_kit_local_agent_package(
        payload=_payload(),
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_context(package)

    assert "methodology_context" not in context
    assert "selected_skill_references" not in context
    assert "skill_reference_policy" not in context
    assert context["capability_context"]["skills"] == ["provider-realism"]
    assert context["capability_context"]["manifest"]["selected_context_available"] is True
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert context["namespace_materialization"]["package_path"] == "coffeebuddy/runtime"
    assert "### CLike Selected Capability Context" in package["local_agent"]["prompt_content"]
    assert "BMAD Skill Reference Context" not in package["local_agent"]["prompt_content"]
    assert "CLIKE_SELECTED_CAPABILITY_CONTEXT.md" in package["local_agent"]["prompt_content"]


def test_python_dotted_module_boundary_materializes_as_package_path():
    assert python_module_boundary_to_package_path("coffeebuddy.runtime") == "coffeebuddy/runtime"


def test_bmad_eval_local_agent_contains_qa_skill_and_selected_clike_capabilities():
    methodology_context = resolve_methodology_context(
        phase="eval",
        methodology="bmad",
        agent="qa",
    )
    package = build_eval_local_agent_package(
        payload=_payload(methodology_context),
        req_id="REQ-001",
        execution_policy=_execution_policy(),
    )
    context = _package_json(package, "AGENT_EVAL_CONTEXT.json")

    assert [item["id"] for item in context["selected_skill_references"]] == ["qa-risk-review"]
    assert context["selected_clike_skills"] == ["provider-realism"]
    assert context["context_envelope"]["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert context["namespace_materialization"]["package_path"] == "coffeebuddy/runtime"
    prompt = package["local_agent"]["prompt_content"]
    assert "### BMAD Skill Reference Context" in prompt
    assert "qa-risk-review" in prompt
    assert "### CLike Selected Capability Context" in prompt
    assert "Do not create `src/coffeebuddy.runtime`" in prompt


def test_bmad_finalize_local_agent_context_contains_release_narrative_skill():
    methodology_context = resolve_methodology_context(
        phase="finalize",
        methodology="bmad",
        agent="tech-writer",
    )
    package = build_finalize_local_agent_package(
        payload=_payload(methodology_context),
        execution_policy=_execution_policy(),
    )
    context = _package_json(package, "AGENT_FINALIZE_CONTEXT.json")

    assert [item["id"] for item in context["selected_skill_references"]] == ["release-narrative"]
    assert context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]
    assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]


def test_manifest_declared_local_agent_pairs_are_propagated_to_contexts_and_prompts():
    cases = {
        "kit/developer": (
            build_kit_local_agent_package,
            "AGENT_EXECUTION_CONTEXT.json",
            {"req_id": "REQ-001", "execution_policy": _execution_policy()},
        ),
        "eval/qa": (
            build_eval_local_agent_package,
            "AGENT_EVAL_CONTEXT.json",
            {"req_id": "REQ-001", "execution_policy": _execution_policy()},
        ),
        "finalize/tech-writer": (
            build_finalize_local_agent_package,
            "AGENT_FINALIZE_CONTEXT.json",
            {"execution_policy": _execution_policy()},
        ),
    }

    for key, (builder, context_suffix, kwargs) in cases.items():
        phase, agent = key.split("/", 1)
        expected = _manifest()["skill_selection"][key]
        methodology_context = resolve_methodology_context(
            phase=phase,
            methodology="bmad",
            agent=agent,
        )
        package = builder(payload=_payload(methodology_context), **kwargs)
        context = _package_json(package, context_suffix)

        assert [item["id"] for item in context["selected_skill_references"]] == expected
        assert [
            item["id"]
            for item in context["context_envelope"]["bmad_methodology_skills"]["selected_skill_references"]
        ] == expected
        assert context["selected_skill_context"]["snippets"]
        assert "### BMAD Skill Reference Context" in package["local_agent"]["prompt_content"]
        for skill_id in expected:
            assert skill_id in package["local_agent"]["prompt_content"]
    assert "release-narrative" in package["local_agent"]["prompt_content"]


def test_kit_local_agent_verifies_in_the_eval_sandbox_before_finishing():
    # cdl-pipeline REQ-001: the agent's own sandbox had no database, browser or registry, so 5
    # criteria stayed partial and the first eval started a repair; asked, the KIT runs its checks
    # in the eval sandbox before it finishes.
    methodology_context = resolve_methodology_context(phase="kit", methodology="bmad", agent="developer")
    payload = _payload(methodology_context)
    payload["kit"] = {"targets": ["REQ-001"], "eval_check": True, "eval_check_max_runs": 3}
    package = build_kit_local_agent_package(payload=payload, req_id="REQ-001", execution_policy=_execution_policy())
    local = package["local_agent"]
    assert {k: v for k, v in local["eval_check"].items() if k != "regression"} == {
        "command": "node .clike/bin/eval-check.mjs", "max_runs": 3, "targets": [], "stage": "kit",
        "profile": "runs/kit/REQ-001/ci/LTC.json",
    }
    assert local["kit_stage"] == "kit" and local["repair"] is False
    prompt = local["prompt_content"]
    assert "VERIFY IN THE EVAL SANDBOX:" in prompt
    assert "`node .clike/bin/eval-check.mjs` (no arguments) runs every check" in prompt
    assert "(at most 3 runs)" in prompt
    assert "A check your own sandbox could not run is not a reason for partial" in prompt

    # not asked (setting 0, cloud, older extension): the KIT is as before
    payload["kit"] = {"targets": ["REQ-001"]}
    package = build_kit_local_agent_package(payload=payload, req_id="REQ-001", execution_policy=_execution_policy())
    assert "eval_check" not in package["local_agent"]
    assert "eval-check.mjs" not in package["local_agent"]["prompt_content"]


def test_kit_eval_check_is_not_offered_to_the_acceptance_stage_nor_doubled_in_a_repair():
    from services.local_agent.common import _kit_repair_context
    from services.local_agent.kit import _kit_eval_check, _kit_stage

    tests_only = {"kit": {"phases": ["acceptance"], "eval_check": True}}
    assert _kit_eval_check(tests_only["kit"], {}) is None
    assert "eval-check" not in "\n".join(_kit_stage("REQ-001", tests_only, {})[2])

    locked = {"kit": {"acceptance_first": True, "eval_check": True, "eval_check_max_runs": 2}}
    stage, _title, rules = _kit_stage("REQ-001", locked, {})
    assert stage == "code_after_locked_acceptance"
    assert any("(at most 2 runs)" in rule for rule in rules)

    repair = {"kit": {"eval_check": True, "repair": {"cycle": 1, "max_cycles": 2, "eval_check": True,
                                                      "failures": [{"name": "unit", "code": 1}]}}}
    context = _kit_repair_context("REQ-001", repair)
    assert _kit_eval_check(repair["kit"], context) is None
    stage, _title, rules = _kit_stage("REQ-001", repair, context)
    assert stage == "repair"
    assert sum("eval-check.mjs" in rule for rule in rules) == 1


def test_kit_options_schema_keeps_the_eval_check_request():
    from schemas.harper import HarperKitOptions

    kit = HarperKitOptions(targets=["REQ-002"], eval_check=True, eval_check_max_runs=4).model_dump(exclude_none=True)
    assert (kit["eval_check"], kit["eval_check_max_runs"]) == (True, 4)



def test_the_kit_last_run_adds_the_regression_of_the_promoted_reqs():
    # cdl-pipeline REQ-006: a shared file broke REQ-002 and only the eval found it (one repair)
    from services.local_agent.kit import _kit_eval_check, kit_eval_check_rules, _kit_stage

    plan = {"reqs": [
        {"id": "REQ-001", "status": "done"}, {"id": "REQ-002", "status": "done"},
        {"id": "REQ-003", "status": "in_progress"}, {"id": "REQ-004", "status": "open"},
    ]}
    payload = {"kit": {"eval_check": True}, "core_blobs": {"plan.json": json.dumps(plan)}}
    _stage, _title, rules = _kit_stage("REQ-003", payload, {})
    text = "\n".join(rules)
    assert "`node .clike/bin/eval-check.mjs regression::REQ-001 regression::REQ-002`" in text
    assert "never weaken their tests" in text
    # the first REQ has no regression: no such rule
    first = {"kit": {"eval_check": True}, "core_blobs": {"plan.json": json.dumps({"reqs": [{"id": "REQ-001", "status": "in_progress"}]})}}
    assert "regression::" not in "\n".join(_kit_stage("REQ-001", first, {})[2])
    assert _kit_eval_check({"eval_check": True}, {}, ["REQ-001"])["regression"] == ["REQ-001"]
    assert all("regression::" not in r for r in kit_eval_check_rules(_kit_eval_check({"eval_check": True}, {}, [])))



def test_an_acceptance_first_kit_tells_the_bridge_its_tests_are_locked():
    # the bridge then warns when a passing run relies on changes to locked tests (restored afterwards)
    from services.local_agent.kit import _kit_eval_check

    assert _kit_eval_check({"eval_check": True}, {}, [], locked=True)["locked"] is True
    assert "locked" not in _kit_eval_check({"eval_check": True}, {}, [])
    methodology_context = resolve_methodology_context(phase="kit", methodology="bmad", agent="developer")
    payload = _payload(methodology_context)
    payload["kit"] = {"targets": ["REQ-001"], "eval_check": True, "acceptance_first": True}
    local = build_kit_local_agent_package(payload=payload, req_id="REQ-001", execution_policy=_execution_policy())["local_agent"]
    assert local["kit_stage"] == "code_after_locked_acceptance" and local["eval_check"]["locked"] is True
