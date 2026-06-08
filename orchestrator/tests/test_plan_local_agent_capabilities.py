import json

from services.local_agent_package import (
    build_document_phase_local_agent_package,
    normalize_local_agent_result,
)


def _execution_policy():
    return {
        "requested": "prefer_local_agent",
        "selected": "local_agent",
        "reason": "test",
        "phase_supported": True,
    }


CAPABILITY_INDEX = json.dumps(
    {
        "packs": [{"name": "enterprise-api"}, {"name": "observability"}],
        "skills": [{"name": "fastapi-service"}],
        "design_profiles": [{"name": "rest-clean-arch"}],
    }
)


def _plan_payload(with_capabilities=True, selected=None):
    payload = {"runId": "plan-run"}
    if with_capabilities:
        payload["core_blobs"] = {
            "CLIKE_CAPABILITY_INDEX.json": CAPABILITY_INDEX,
            "CLIKE_CAPABILITY_MANIFEST.md": "# Capabilities\n- enterprise-api\n",
        }
        payload["context_envelope"] = {
            "clike_capabilities": {
                "selected_packs": (selected or {}).get("packs", []),
                "selected_skills": (selected or {}).get("skills", []),
                "selected_design_profiles": (selected or {}).get("design_profiles", []),
            }
        }
    return payload


def _package(payload):
    return build_document_phase_local_agent_package(
        phase="plan", payload=payload, execution_policy=_execution_policy()
    )


def _context(package):
    agent = package["local_agent"]
    for entry in agent["package_files"]:
        if entry["path"] == agent["context_path"]:
            return json.loads(entry["content"])
    raise AssertionError("context missing")


# --- Capability context exposure ---

def test_plan_context_embeds_available_capabilities():
    package = _package(_plan_payload())
    caps = _context(package)["capabilities"]
    assert caps["has_capabilities"] is True
    assert caps["available"]["packs"] == ["enterprise-api", "observability"]
    assert caps["available"]["skills"] == ["fastapi-service"]
    assert caps["available"]["design_profiles"] == ["rest-clean-arch"]


def test_plan_prompt_lists_capabilities_and_forbids_default_not_applicable():
    prompt = _package(_plan_payload())["local_agent"]["prompt_content"]
    assert "CLike capability context (BINDING planning constraints" in prompt
    assert "enterprise-api" in prompt
    assert "fastapi-service" in prompt
    assert "rest-clean-arch" in prompt
    assert 'Do NOT default packs/skills/design_profiles to "not_applicable"' in prompt
    # Capability source files are added to the required reads.
    assert ".clike/capabilities.yaml" in prompt
    assert ".clike/packs/**" in prompt


def test_plan_package_surfaces_available_capabilities_for_completion():
    agent = _package(_plan_payload())["local_agent"]
    assert agent["available_capabilities"]["packs"] == ["enterprise-api", "observability"]


def test_plan_selected_capabilities_take_precedence_in_prompt():
    payload = _plan_payload(selected={"packs": ["observability"]})
    prompt = _package(payload)["local_agent"]["prompt_content"]
    # Selected packs are surfaced as the chosen set for the agent.
    assert "available/selected packs: observability" in prompt


def test_plan_without_capabilities_has_no_capability_block_or_reads():
    package = _package(_plan_payload(with_capabilities=False))
    context = _context(package)
    caps = context["capabilities"]
    assert caps["has_capabilities"] is False
    prompt = package["local_agent"]["prompt_content"]
    assert "CLike capability context (BINDING" not in prompt
    assert ".clike/capabilities.yaml" not in prompt
    # No available_capabilities surfaced when none exist.
    assert "available_capabilities" not in package["local_agent"]


def test_idea_and_spec_unchanged_no_capability_block():
    for phase in ("idea", "spec"):
        payload = {"runId": f"{phase}-run", "core_blobs": {"CLIKE_CAPABILITY_INDEX.json": CAPABILITY_INDEX}}
        if phase == "idea":
            payload["attachments"] = [{"name": "IDEA.md", "path": ".clike/uploads/IDEA.md", "content": "x\n"}]
        package = build_document_phase_local_agent_package(
            phase=phase, payload=payload, execution_policy=_execution_policy()
        )
        agent = package["local_agent"]
        context = next(
            json.loads(e["content"]) for e in agent["package_files"] if e["path"] == agent["context_path"]
        )
        assert "capabilities" not in context
        assert "available_capabilities" not in agent
        assert "CLike capability context (BINDING" not in agent["prompt_content"]


# --- Normalization: capability degradation warning ---

VALID_PLAN_MD = (
    "# PLAN — Demo\n\n## REQ-1 — A\nVerification checkpoints: tests.\n"
)


def _plan_json(packs, skills, design):
    return json.dumps(
        {
            "snapshot": {"total": 1},
            "reqs": [
                {
                    "id": "REQ-1",
                    "title": "A",
                    "status": "open",
                    "acceptance": ["a1"],
                    "dependsOn": [],
                    "packs": packs,
                    "skills": skills,
                    "design_profiles": design,
                }
            ],
        }
    )


def _normalize_plan(plan_json_text, available_capabilities):
    return normalize_local_agent_result(
        {
            "phase": "plan",
            "req_id": "SOLUTION",
            "runId": "plan-run",
            "exit_code": 0,
            "available_capabilities": available_capabilities,
            "files": [
                {"path": "docs/harper/PLAN.md", "content": VALID_PLAN_MD},
                {"path": "docs/harper/plan.json", "content": plan_json_text},
            ],
        }
    )


def test_normalize_warns_on_blanket_not_applicable_with_available_packs():
    result = _normalize_plan(
        _plan_json("not_applicable", "not_applicable", "not_applicable"),
        {"packs": ["enterprise-api"], "skills": [], "design_profiles": []},
    )
    # Warning-level, non-blocking: ok stays True (no listed cap may apply).
    assert result["ok"] is True
    assert any(
        w == "plan:all_reqs_packs_not_applicable_despite_available_capabilities"
        for w in result["warnings"]
    )


def test_normalize_no_capability_warning_when_populated():
    result = _normalize_plan(
        _plan_json(["enterprise-api"], ["fastapi-service"], ["rest-clean-arch"]),
        {"packs": ["enterprise-api"], "skills": ["fastapi-service"], "design_profiles": ["rest-clean-arch"]},
    )
    assert result["ok"] is True
    assert not any("not_applicable_despite_available" in w for w in result["warnings"])


def test_normalize_no_capability_warning_when_none_available():
    result = _normalize_plan(
        _plan_json("not_applicable", "not_applicable", "not_applicable"),
        {"packs": [], "skills": [], "design_profiles": []},
    )
    assert result["ok"] is True
    assert not any("not_applicable_despite_available" in w for w in result["warnings"])
