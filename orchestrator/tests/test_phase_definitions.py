"""Phase definitions (WP8.3): orchestrator/phases/*.yaml are the single source.

The extension keeps a pre-filter copy of the document-phase write tables
(extensions/vscode/local-agent-write-policy.js); this test keeps it in step.
"""

import json
import re
import sys
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services import local_agent_package as lap  # noqa: E402
from services.phase_definitions import phase_definition, shared_definitions  # noqa: E402

JS_POLICY = ORCHESTRATOR_ROOT.parent / "extensions/vscode/local-agent-write-policy.js"


def _js_table(name: str):
    src = JS_POLICY.read_text(encoding="utf-8")
    body = re.search(rf"const {name} = (\{{.*?\}}|\[.*?\]);", src, re.S).group(1)
    body = re.sub(r"(\w+):", r'"\1":', body).replace("'", '"')
    body = re.sub(r",\s*([}\]])", r"\1", body)
    return json.loads(body)


def test_every_definition_loads_with_the_expected_sections():
    for phase in ("idea", "spec", "plan"):
        d = phase_definition(phase)
        assert d["phase"] == phase
        assert {"schema_version", "allowed_write_roots", "output_contract", "hard_rules", "prompt_lines"} <= set(d["local_agent"])
        assert d["canonical_expectations"] and d["accepted_result_paths"]
    ext = phase_definition("extend")
    assert ext["local_agent"]["schema_version"] == "clike.agent.extend_context.v1"
    assert shared_definitions()["document_phase_forbidden_paths"]


def test_definitions_are_returned_as_copies():
    d = phase_definition("idea")
    d["local_agent"]["hard_rules"].append("mutated")
    assert "mutated" not in phase_definition("idea")["local_agent"]["hard_rules"]


def test_required_outputs_are_accepted_and_match_the_extension():
    js_required = _js_table("DOCUMENT_PHASE_REQUIRED_OUTPUTS")
    js_prefixes = _js_table("DOCUMENT_PHASE_ALLOWED_PREFIXES")
    for phase in ("idea", "spec", "plan"):
        d = phase_definition(phase)
        required = d["local_agent"]["output_contract"]["always"]
        assert required == js_required[phase]
        assert all(lap._path_accepted(phase, p) for p in required)
        # every wildcard pattern corresponds to an extension prefix
        wild = [p.split("*")[0] for p in d["accepted_result_paths"] if "*" in p]
        assert wild == js_prefixes[phase]


def test_extend_accepts_the_extension_exact_paths():
    exact = _js_table("EXTEND_ALLOWED_EXACT")
    assert all(lap._path_accepted("extend", p) for p in exact)
    assert lap._path_accepted("extend", "docs/harper/EXTEND_2026-10-04_REQ-3_REQ-3.md")
    assert not lap._path_accepted("extend", "docs/harper/AGENT_EXTEND_CONTEXT.json")
    assert not lap._path_accepted("extend", "src/app.py")
