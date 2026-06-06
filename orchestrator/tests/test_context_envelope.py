import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_ROOT = REPO_ROOT / "orchestrator"
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.context_envelope import build_context_envelope
from services.methodologies.resolver import resolve_methodology_context


MANIFEST_PATH = REPO_ROOT / "orchestrator/methodologies/bmad/manifest.json"
TEMPLATE_VENDOR_ROOT = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _bmad_vendor_core_blobs():
    blobs = {
        ".clike/skills/vendor/bmad/manifest.json": (TEMPLATE_VENDOR_ROOT / "manifest.json").read_text(encoding="utf-8")
    }
    for path in sorted(TEMPLATE_VENDOR_ROOT.glob("*/SKILL.md")):
        rel = path.relative_to(REPO_ROOT / "extensions/vscode/templates/harper-init").as_posix()
        blobs[rel] = path.read_text(encoding="utf-8")
    return blobs


def _selected_capability_core_blobs():
    return {
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": "# CLike Selected Capability Context\n\n## Selected Skills\n\n### Skill: provider-realism\n",
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": json.dumps(
            {
                "schema_version": "clike.selected_capability_context.v1",
                "req_id": "REQ-001",
                "packs": {
                    "selected": ["enterprise-python"],
                    "resolved": [{"name": "enterprise-python"}],
                    "missing": [],
                },
                "skills": {
                    "selected": ["provider-realism"],
                    "resolved": [{"name": "provider-realism"}],
                    "missing": [],
                },
                "design_profiles": {
                    "selected": ["ops-console"],
                    "resolved": [{"name": "ops-console"}],
                    "missing": [],
                },
            }
        ),
    }


def _selected_ids(context):
    return [
        item["id"]
        for item in (context.get("selected_skill_references") or [])
        if isinstance(item, dict)
    ]


def _envelope_ids(envelope):
    return [
        item["id"]
        for item in (
            envelope.get("bmad_methodology_skills", {}).get("selected_skill_references") or []
        )
        if isinstance(item, dict)
    ]


def test_context_envelope_matches_manifest_driven_methodology_context_for_all_bmad_pairs():
    for key, expected in _manifest()["skill_selection"].items():
        phase, agent = key.split("/", 1)
        methodology_context = resolve_methodology_context(
            phase=phase,
            methodology="bmad",
            agent=agent,
            core_blobs=_bmad_vendor_core_blobs(),
            require_bmad_core_blobs=True,
        )

        envelope = build_context_envelope(
            phase=phase,
            req_id="REQ-001" if phase in {"kit", "eval"} else None,
            execution_mode="cloud",
            core_blobs=_bmad_vendor_core_blobs(),
            methodology_context=methodology_context,
            active_output_contract={},
            namespace_materialization={},
        )

        assert _selected_ids(methodology_context) == expected
        assert _envelope_ids(envelope) == expected
        assert envelope["bmad_methodology_skills"]["selected_skill_context"]["snippets"]
        assert (
            envelope["bmad_methodology_skills"]["selected_skill_context"]
            == methodology_context["selected_skill_context"]
        )


def test_context_envelope_rehydrates_stale_empty_bmad_skill_context():
    stale_context = {
        "methodology": "bmad",
        "phase": "kit",
        "agent": "developer",
        "selected_skill_references": [],
        "selected_skill_context": {},
    }

    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="local_agent",
            core_blobs=_bmad_vendor_core_blobs(),
        methodology_context=stale_context,
        active_output_contract={},
        namespace_materialization={},
    )

    assert _envelope_ids(envelope) == _manifest()["skill_selection"]["kit/developer"]
    assert envelope["bmad_methodology_skills"]["selected_skill_context"]["snippets"]


def test_context_envelope_rehydrates_compact_client_bmad_context_with_phase_hint():
    compact_context = {
        "methodology": "bmad",
        "agent": "developer",
        "selected_skill_references": [],
        "selected_skill_context": {},
    }

    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="local_agent",
            core_blobs=_bmad_vendor_core_blobs(),
        methodology_context=compact_context,
        active_output_contract={},
        namespace_materialization={},
    )

    assert _envelope_ids(envelope) == _manifest()["skill_selection"]["kit/developer"]
    assert envelope["bmad_methodology_skills"]["selected_skill_context"]["snippets"]


def test_context_envelope_keeps_native_runs_clean():
    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="cloud",
        core_blobs={},
        methodology_context=None,
        active_output_contract={},
        namespace_materialization={},
    )

    assert envelope["methodology"] is None
    assert envelope["bmad_methodology_skills"]["selected_skill_references"] == []
    assert envelope["bmad_methodology_skills"]["selected_skill_context"] == {}


def test_context_envelope_preserves_native_clike_capabilities_without_bmad_skills():
    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="cloud",
        core_blobs=_selected_capability_core_blobs(),
        methodology_context=None,
        active_output_contract={},
        namespace_materialization={},
    )

    assert envelope["clike_capabilities"]["selected_packs"] == ["enterprise-python"]
    assert envelope["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert envelope["clike_capabilities"]["selected_design_profiles"] == ["ops-console"]
    assert envelope["bmad_methodology_skills"]["selected_skill_references"] == []


def test_context_envelope_preserves_clike_capabilities_and_bmad_skills_together():
    methodology_context = resolve_methodology_context(
        phase="kit",
        methodology="bmad",
        agent="developer",
        core_blobs=_bmad_vendor_core_blobs(),
        require_bmad_core_blobs=True,
    )
    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="local_agent",
        core_blobs={**_selected_capability_core_blobs(), **_bmad_vendor_core_blobs()},
        methodology_context=methodology_context,
        active_output_contract={},
        namespace_materialization={},
        require_bmad_core_blobs=True,
    )

    assert envelope["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert _envelope_ids(envelope) == _manifest()["skill_selection"]["kit/developer"]


def test_context_envelope_tolerates_legacy_flat_selected_capability_context():
    envelope = build_context_envelope(
        phase="kit",
        req_id="REQ-001",
        execution_mode="cloud",
        core_blobs={
            "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": json.dumps(
                {
                    "schema_version": "legacy",
                    "selected_packs": ["enterprise-python"],
                    "selected_skills": ["provider-realism"],
                    "selected_design_profiles": ["ops-console"],
                }
            )
        },
        methodology_context=None,
        active_output_contract={},
        namespace_materialization={},
    )

    assert envelope["clike_capabilities"]["selected_packs"] == ["enterprise-python"]
    assert envelope["clike_capabilities"]["selected_skills"] == ["provider-realism"]
    assert envelope["clike_capabilities"]["selected_design_profiles"] == ["ops-console"]
