import json
from pathlib import Path

from services.local_agent_package import build_document_phase_local_agent_package


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init"
TEMPLATE_VENDOR_ROOT = TEMPLATE_ROOT / ".clike/skills/vendor/bmad"


def _bmad_vendor_core_blobs():
    blobs = {
        ".clike/skills/vendor/bmad/manifest.json": (
            TEMPLATE_VENDOR_ROOT / "manifest.json"
        ).read_text(encoding="utf-8")
    }
    for path in sorted(TEMPLATE_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(TEMPLATE_ROOT).as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _execution_policy():
    return {
        "requested": "prefer_local_agent",
        "selected": "local_agent",
        "reason": "test",
        "phase_supported": True,
    }


def _default_payload(phase):
    payload = {"runId": "doc-run"}
    # /idea requires at least one current-run attachment (with inline content so
    # the orchestrator can materialize it into a workspace-local package file).
    if phase == "idea":
        payload["attachments"] = [
            {
                "name": "IDEA.md",
                "path": ".clike/uploads/IDEA.md",
                "mime": "text/markdown",
                "content": "# Source IDEA\n\nProduct concept, users, and goals.\n",
            }
        ]
    return payload


def _materialized_package_files(package):
    agent = package["local_agent"]
    context_path = agent["context_path"]
    prompt_path = agent["prompt_path"]
    return [
        f
        for f in agent["package_files"]
        if f["path"] not in {context_path, prompt_path}
    ]


def _package(phase, payload=None):
    return build_document_phase_local_agent_package(
        phase=phase,
        payload=payload if payload is not None else _default_payload(phase),
        execution_policy=_execution_policy(),
    )


def _context_file(package):
    context_path = package["local_agent"]["context_path"]
    for entry in package["local_agent"]["package_files"]:
        if entry["path"] == context_path:
            return json.loads(entry["content"])
    raise AssertionError("context file missing from package")


def test_idea_package_shape_and_outputs():
    package = _package("idea")
    agent = package["local_agent"]

    assert package["phase"] == "idea"
    assert agent["action"] == "local_agent_required"
    assert agent["phase"] == "idea"
    assert agent["req_id"] == "SOLUTION"
    assert agent["package_id"].endswith(":SOLUTION:idea")
    assert agent["allowed_write_roots"] == ["docs/harper/IDEA.md"]
    assert agent["expected_outputs"]["always"] == ["docs/harper/IDEA.md"]
    assert agent["context_path"] == "runs/idea/docs/AGENT_IDEA_CONTEXT.json"
    assert agent["prompt_path"] == "runs/idea/docs/AGENT_IDEA_PROMPT.md"
    assert agent["prompt_content"]
    # Envelope must ship the context + prompt package files, plus any
    # materialized current-run attachments under runs/idea/attachments/.
    paths = {f["path"] for f in agent["package_files"]}
    assert {agent["context_path"], agent["prompt_path"]}.issubset(paths)
    extra = paths - {agent["context_path"], agent["prompt_path"]}
    assert all(p.startswith("runs/idea/attachments/") for p in extra)


def test_spec_package_outputs_and_active_contract():
    package = _package("spec")
    agent = package["local_agent"]

    assert agent["allowed_write_roots"] == ["docs/harper/SPEC.md"]
    assert agent["expected_outputs"]["always"] == ["docs/harper/SPEC.md"]
    contract = agent["active_output_contract"]
    assert contract["methodology"] == "native_clike"
    assert contract["required_outputs"] == ["docs/harper/SPEC.md"]
    assert "# SPEC — <Project Name>" in agent["prompt_content"]
    assert "SPEC_END" in agent["prompt_content"]


def test_plan_package_outputs_include_plan_json_and_lane_guides():
    package = _package("plan")
    agent = package["local_agent"]

    assert "docs/harper/PLAN.md" in agent["allowed_write_roots"]
    assert "docs/harper/plan.json" in agent["allowed_write_roots"]
    assert "docs/harper/lane-guides" in agent["allowed_write_roots"]
    assert agent["expected_outputs"]["always"] == [
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
    ]
    contract = agent["active_output_contract"]
    assert "docs/harper/PLAN.md" in contract["required_outputs"]
    assert "docs/harper/plan.json" in contract["required_outputs"]
    assert "docs/harper/lane-guides/**" in contract["required_outputs"]


def test_document_phases_block_unrelated_docs_harper_writes():
    # Allowed write roots are narrow: only the exact phase-owned outputs.
    for phase, allowed in (
        ("idea", {"docs/harper/IDEA.md"}),
        ("spec", {"docs/harper/SPEC.md"}),
    ):
        agent = _package(phase)["local_agent"]
        assert set(agent["allowed_write_roots"]) == allowed
        # Source/test/git roots remain forbidden.
        for forbidden in ("src", "test", "tests", ".git", "runs/kit"):
            assert forbidden in agent["forbidden_paths"]


def test_document_phase_carries_methodology_context_when_enabled():
    payload = {
        "runId": "doc-run",
        "methodology": "bmad",
        "core_blobs": _bmad_vendor_core_blobs(),
        "attachments": [{"name": "IDEA.md", "path": ".clike/uploads/IDEA.md"}],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    context = _context_file(package)
    assert context["methodology_context"]["methodology"] == "bmad"
    assert "Methodology profile:" in package["local_agent"]["prompt_content"]


def test_native_document_package_omits_methodology_context():
    package = _package("plan")
    context = _context_file(package)
    assert "methodology_context" not in context
    assert context["active_output_contract"]["methodology"] == "native_clike"


def test_document_package_files_live_under_run_scoped_paths():
    # Package internals live under runs/<phase>/ (docs/ for AGENT_* files,
    # attachments/ for materialized attachments) — never under docs/harper/.
    for phase in ("idea", "spec", "plan"):
        run_prefix = f"runs/{phase}/"
        docs_prefix = f"runs/{phase}/docs/"
        agent = _package(phase)["local_agent"]
        package_paths = {f["path"] for f in agent["package_files"]}
        assert package_paths, f"{phase} package has no files"
        for path in package_paths:
            assert path.startswith(run_prefix), f"{phase}: {path} not under {run_prefix}"
            # No AGENT_* package internals leak into canonical docs/harper.
            assert not path.startswith("docs/harper/")
        assert agent["context_path"].startswith(docs_prefix)
        assert agent["prompt_path"].startswith(docs_prefix)


def test_attachment_manifest_lists_multiple_attachments():
    payload = {
        "runId": "doc-run",
        "attachments": [
            {
                "name": "IDEA.md",
                "path": "/Users/x/external/CoffeeBuddy/IDEA.md",
                "mime": "text/markdown",
                "size": 120,
                "content": "# External IDEA\n",
            },
            {"name": "notes.txt", "mime": "text/plain", "content": "extra notes\n"},
        ],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    context = _context_file(package)
    manifest = context["attachments"]
    assert manifest["present"] is True
    assert manifest["count"] == 2

    first = manifest["items"][0]
    assert first["mime"] == "text/markdown"
    assert first["size"] == 120
    # Original external path is metadata only; the agent reads the workspace copy.
    assert first["original_path"] == "/Users/x/external/CoffeeBuddy/IDEA.md"
    assert first["workspace_path"] == "runs/idea/attachments/IDEA.md"
    assert first["materialized"] is True
    assert manifest["items"][1]["workspace_path"] == "runs/idea/attachments/notes.txt"

    prompt = package["local_agent"]["prompt_content"]
    assert "runs/idea/attachments/IDEA.md" in prompt
    assert "runs/idea/attachments/notes.txt" in prompt
    assert "Read every workspace_path" in prompt
    assert "Do NOT read original_path" in prompt
    assert "ONLY source of truth for /idea" in prompt


def test_attachment_manifest_empty_when_no_attachments():
    # /spec does not require attachments, so it exercises the empty-manifest path.
    context = _context_file(_package("spec"))
    manifest = context["attachments"]
    assert manifest == {"present": False, "count": 0, "items": []}


# --- Attachment materialization into workspace-local package files ---

def test_external_attachment_is_materialized_into_workspace_package_file():
    payload = {
        "runId": "doc-run",
        "attachments": [
            {
                "name": "IDEA.md",
                # External absolute path outside the agent's cwd (the reported bug).
                "path": "/Users/a.franco/dev/authenticfake/clike/clike_mvp/CoffeeBuddy/IDEA.md",
                "mime": "text/markdown",
                "content": "# CoffeeBuddy\n\nThe source idea.\n",
            }
        ],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    materialized = _materialized_package_files(package)
    assert len(materialized) == 1
    entry = materialized[0]
    assert entry["path"] == "runs/idea/attachments/IDEA.md"
    assert entry["content"] == "# CoffeeBuddy\n\nThe source idea.\n"
    # The external path is never used as a read target.
    item = _context_file(package)["attachments"]["items"][0]
    assert item["original_path"].startswith("/Users/")
    assert item["workspace_path"] == "runs/idea/attachments/IDEA.md"


def test_multiple_attachments_are_materialized_with_collision_safe_names():
    payload = {
        "runId": "doc-run",
        "attachments": [
            {"name": "IDEA.md", "path": "/a/IDEA.md", "content": "one\n"},
            {"name": "IDEA.md", "path": "/b/IDEA.md", "content": "two\n"},
        ],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    paths = [f["path"] for f in _materialized_package_files(package)]
    assert paths == ["runs/idea/attachments/IDEA.md", "runs/idea/attachments/IDEA_1.md"]
    contents = {f["path"]: f["content"] for f in _materialized_package_files(package)}
    assert contents["runs/idea/attachments/IDEA.md"] == "one\n"
    assert contents["runs/idea/attachments/IDEA_1.md"] == "two\n"


def test_binary_attachment_is_materialized_as_base64_package_file():
    payload = {
        "runId": "doc-run",
        "attachments": [
            {"name": "diagram.png", "path": "/x/diagram.png", "bytes_b64": "AAEC", "mime": "image/png"}
        ],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    entry = _materialized_package_files(package)[0]
    assert entry["path"] == "runs/idea/attachments/diagram.png"
    assert entry["content_base64"] == "AAEC"
    assert entry["encoding"] == "base64"


def test_attachment_without_content_is_not_materialized_but_listed():
    payload = {
        "runId": "doc-run",
        "attachments": [
            {"name": "IDEA.md", "path": ".clike/uploads/IDEA.md"},  # no inline content
        ],
    }
    package = build_document_phase_local_agent_package(
        phase="idea",
        payload=payload,
        execution_policy=_execution_policy(),
    )
    # Still counts as a present attachment (so /idea is not blocked) but no
    # workspace package file is emitted because there is no content to copy.
    assert _materialized_package_files(package) == []
    item = _context_file(package)["attachments"]["items"][0]
    assert item["materialized"] is False
    assert "workspace_path" not in item


# --- /idea attachment-only source-of-truth rules ---

def test_idea_without_attachments_raises():
    import pytest

    with pytest.raises(ValueError) as exc:
        build_document_phase_local_agent_package(
            phase="idea",
            payload={"runId": "doc-run"},
            execution_policy=_execution_policy(),
        )
    assert "without at least one attached source file" in str(exc.value)


def test_idea_prompt_forbids_stale_and_idea_variants():
    prompt = _package("idea")["local_agent"]["prompt_content"]
    assert "ONLY source of truth for /idea" in prompt
    assert "ORI.IDEA.md" in prompt
    assert "IDEA* variant" in prompt
    assert "overwrite target only" in prompt
    # Hard rules carry the same source-of-truth constraints.
    context = _context_file(_package("idea"))
    hard_rules = " ".join(context["hard_rules"])
    assert "current-run attachments" in hard_rules
    assert "overwrite target" in hard_rules


def test_spec_prompt_allows_idea_and_variants_as_context():
    context = _context_file(_package("spec"))
    reads = " ".join(context["required_reads"])
    assert "docs/harper/IDEA.md" in reads
    assert "IDEA* prefix variants" in reads


def test_plan_prompt_allows_spec_and_variants_as_context():
    context = _context_file(_package("plan"))
    reads = " ".join(context["required_reads"])
    assert "docs/harper/SPEC.md" in reads
    assert "SPEC* prefix variants" in reads


# --- Regenerative source discipline: same-phase outputs are overwrite targets only ---

def test_spec_prompt_uses_idea_and_forbids_existing_spec_as_source():
    package = _package("spec")
    prompt = package["local_agent"]["prompt_content"]
    # IDEA is the source.
    assert "docs/harper/IDEA.md" in prompt
    # SPEC.md is overwrite-target-only and must not be read as input.
    assert "docs/harper/SPEC.md is an overwrite target only" in prompt
    assert "Do NOT read docs/harper/SPEC.md or any SPEC* variant as input" in prompt


def test_spec_required_reads_exclude_spec_outputs():
    context = _context_file(_package("spec"))
    for entry in context["required_reads"]:
        assert "SPEC.md" not in entry, f"SPEC output leaked into required_reads: {entry!r}"
        assert "SPEC*" not in entry
    # Hard rules carry the same constraint.
    hard_rules = " ".join(context["hard_rules"])
    assert "Existing SPEC files are stale outputs" in hard_rules
    assert "overwrite target only" in hard_rules


def test_plan_prompt_uses_spec_and_forbids_existing_plan_as_source():
    package = _package("plan")
    prompt = package["local_agent"]["prompt_content"]
    # SPEC is the source.
    assert "docs/harper/SPEC.md" in prompt
    # PLAN outputs are overwrite-targets-only and must not be read as input.
    assert "PLAN.md, plan.json, and lane-guides are overwrite targets only" in prompt
    assert (
        "Do NOT read docs/harper/PLAN.md, docs/harper/plan.json, docs/harper/lane-guides/**, or any PLAN*/plan* variant as input"
        in prompt
    )


def test_plan_required_reads_exclude_plan_outputs():
    context = _context_file(_package("plan"))
    for entry in context["required_reads"]:
        assert "PLAN.md" not in entry, f"PLAN output leaked into required_reads: {entry!r}"
        assert "plan.json" not in entry
        assert "lane-guides" not in entry
        assert "PLAN*" not in entry
    # Hard rules forbid reconciling with stale plan outputs (no positive
    # reconcile/preserve directive remains; only an explicit prohibition).
    hard_rules = " ".join(context["hard_rules"])
    assert "Existing plan files are stale outputs" in hard_rules
    assert "never reconcile with the old plan output" in hard_rules
    assert "preserve done items" not in hard_rules


def test_document_phase_write_policy_unchanged():
    # Regression: write roots remain narrow and phase-owned only.
    assert _package("spec")["local_agent"]["allowed_write_roots"] == ["docs/harper/SPEC.md"]
    assert _package("plan")["local_agent"]["allowed_write_roots"] == [
        "docs/harper/PLAN.md",
        "docs/harper/plan.json",
        "docs/harper/lane-guides",
    ]


# --- Cloud-parity: local-agent /plan prompt carries the full cloud schema ---

def test_plan_prompt_embeds_plan_json_field_schema():
    prompt = _package("plan")["local_agent"]["prompt_content"]
    # plan.json must instruct the rich per-REQ field schema, not just "valid JSON".
    for field in (
        "functional_scope",
        "technical_scope",
        "non_functional_requirements",
        "security_requirements",
        "integration_contracts",
        "data_contracts",
        "test_strategy",
        "gate_policy_ref",
        "main_module_boundary",
    ):
        assert field in prompt, f"plan.json field {field!r} missing from prompt"
    assert "snapshot.total == len(reqs)" in prompt
    assert "acceptance (>=5 non-empty bullets)" in prompt


def test_plan_prompt_embeds_plan_md_section_structure():
    prompt = _package("plan")["local_agent"]["prompt_content"]
    for section in (
        "## Plan Snapshot",
        "## REQ-IDs Table",
        "### Functional Scope — <REQ-ID>",
        "### Acceptance — <REQ-ID>",
        "## Dependency Graph",
        "## KIT Readiness",
        "PLAN_END",
    ):
        assert section in prompt, f"PLAN.md section {section!r} missing from prompt"


def test_plan_prompt_embeds_lane_guide_structure_and_rule():
    prompt = _package("plan")["local_agent"]["prompt_content"]
    assert "## Lane Guide — <lane>" in prompt
    assert "### Purpose and Scope" in prompt
    assert "### Eval/Gate Expectations" in prompt
    # Lane-guide emission rule mirrors cloud: one per detected lane, else rationale.
    assert "for every detected lane" in prompt
    assert "If no lanes are detected, state the rationale under PLAN.md → Notes" in prompt


def test_plan_prompt_treats_skills_capabilities_as_binding():
    prompt = _package("plan")["local_agent"]["prompt_content"]
    assert "BINDING planning constraints" in prompt
    assert "design_profiles" in prompt


# --- Cloud-parity: gateway canonical expectations embedded in prompts ---

GATEWAY_PROMPTS = {
    "idea": REPO_ROOT / "gateway/prompts/harper/idea_system.md",
    "spec": REPO_ROOT / "gateway/prompts/harper/spec_system.md",
    "plan": REPO_ROOT / "gateway/prompts/harper/plan_system.md",
}


def _canonical_expectations(phase):
    from services.local_agent_package import _DOCUMENT_PHASE_CANONICAL_EXPECTATIONS

    return _DOCUMENT_PHASE_CANONICAL_EXPECTATIONS[phase]


def test_canonical_expectations_are_present_in_local_agent_prompts():
    for phase in ("idea", "spec", "plan"):
        prompt = _package(phase)["local_agent"]["prompt_content"]
        assert "cloud parity" in prompt.lower()
        for expectation in _canonical_expectations(phase):
            assert expectation in prompt, f"{phase}: missing expectation {expectation!r}"


def test_canonical_expectations_are_derived_from_gateway_prompts():
    # Cross-check: every embedded expectation still exists verbatim in the
    # canonical gateway phase prompt, so the local-agent path stays derived from
    # (not divergent with) the cloud prompt.
    for phase, prompt_path in GATEWAY_PROMPTS.items():
        gateway_text = prompt_path.read_text(encoding="utf-8")
        for expectation in _canonical_expectations(phase):
            assert expectation in gateway_text, (
                f"{phase}: expectation {expectation!r} not found in {prompt_path.name}"
            )
