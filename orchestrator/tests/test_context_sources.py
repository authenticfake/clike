"""Project context sources (.clike/context.yaml): resolution, conversion, cloud and local delivery. No LLM."""
import asyncio
import io
import os
from pathlib import Path

import docx
import openpyxl
from pptx import Presentation

from services import harper
from services.context_sources import (
    append_context_sources_to_messages,
    attach_context_sources_to_local_package,
    PREVIOUS_RELEASE_ROLE,
    load_context_manifest,
    render_context_sources_for_cloud,
    resolve_context_sources,
)
from services.local_agent_package import build_document_phase_local_agent_package

MANIFEST = """\
version: 1
sources:
  - path: docs/inputs/**
    role: requirements
    phases: [idea, spec, plan]
  - path: docs/harper/ux/**
    role: ui_reference
    phases: [spec, plan, kit]
  - path: docs/reference/*.html
    role: ui_reference
    phases: [spec, plan, kit]
"""


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _workspace(tmp_path: Path, manifest: str | None = MANIFEST) -> Path:
    ws = tmp_path / "project"
    (ws / "docs/inputs").mkdir(parents=True)
    (ws / "docs/harper/ux/assets").mkdir(parents=True)
    (ws / "docs/reference").mkdir(parents=True)
    (ws / ".clike").mkdir()
    if manifest is not None:
        (ws / ".clike/context.yaml").write_text(manifest, encoding="utf-8")

    d = docx.Document()
    d.add_paragraph("Leads are stored in PostgreSQL 16, schema leads.")
    d.save(ws / "docs/inputs/Specifiche.docx")
    wb = openpyxl.Workbook()
    wb.active.append(["company", "country"])
    wb.active.append(["ACME", "IT"])
    wb.save(ws / "docs/inputs/sample.xlsx")
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Lead scoring pitch"
    deck.save(ws / "docs/inputs/pitch.pptx")
    (ws / "docs/inputs/brief.pdf").write_bytes(_minimal_pdf("Budget cap per research run"))

    (ws / "docs/harper/ux/UI_DEMO.html").write_text("<html><nav>Overview</nav><button>New research</button></html>")
    (ws / "docs/harper/ux/assets/console.css").write_text(":root{--accent:#0b5}")
    (ws / "docs/harper/ux/assets/logo.svg").write_text("<svg><title>logo</title></svg>")
    (ws / "docs/harper/ux/assets/mock.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    (ws / "docs/harper/ux/.DS_Store").write_bytes(b"x")
    (ws / "docs/reference/UI_REFERENCE.html").write_text("<main>Run monitor</main>")
    (ws / "docs/reference/CLIKE_REVIEW.md").write_text("review of the tool, not product input")
    (ws / "docs/harper/IDEA.md").write_text("# IDEA")
    return ws


def _paths(ctx):
    return {item["path"]: item for item in ctx["items"]}


def test_manifest_sources_are_resolved_per_phase_and_converted(tmp_path):
    ws = _workspace(tmp_path)
    spec = _paths(resolve_context_sources(ws, "spec"))
    assert spec["docs/inputs/Specifiche.docx"]["kind"] == "converted"
    assert "PostgreSQL 16" in spec["docs/inputs/Specifiche.docx"]["text"]
    assert "ACME\tIT" in spec["docs/inputs/sample.xlsx"]["text"]
    assert "Lead scoring pitch" in spec["docs/inputs/pitch.pptx"]["text"]
    assert "Budget cap per research run" in spec["docs/inputs/brief.pdf"]["text"]
    assert spec["docs/harper/ux/UI_DEMO.html"]["kind"] == "text"
    assert spec["docs/harper/ux/UI_DEMO.html"]["role"] == "ui_reference"
    assert spec["docs/harper/ux/assets/console.css"]["kind"] == "text"
    assert spec["docs/harper/ux/assets/logo.svg"]["kind"] == "text"
    assert spec["docs/harper/ux/assets/mock.png"]["kind"] == "image"
    assert "docs/reference/UI_REFERENCE.html" in spec
    # not declared, hidden, or canonical
    assert "docs/reference/CLIKE_REVIEW.md" not in spec
    assert "docs/harper/ux/.DS_Store" not in spec
    assert "docs/harper/IDEA.md" not in spec

    kit = _paths(resolve_context_sources(ws, "kit"))
    assert "docs/harper/ux/UI_DEMO.html" in kit and "docs/inputs/Specifiche.docx" not in kit
    idea = _paths(resolve_context_sources(ws, "idea"))
    assert "docs/inputs/Specifiche.docx" in idea and "docs/harper/ux/UI_DEMO.html" not in idea
    assert resolve_context_sources(ws, "eval")["items"] == []


def test_default_convention_without_manifest(tmp_path):
    ws = _workspace(tmp_path, manifest=None)
    manifest = load_context_manifest(ws)
    assert manifest["origin"] == "default_convention"
    spec = _paths(resolve_context_sources(ws, "spec"))
    assert "docs/inputs/Specifiche.docx" in spec and "docs/harper/ux/UI_DEMO.html" in spec
    # docs/reference is part of the convention: background material (as-is docs of a brownfield project)
    assert spec["docs/reference/UI_REFERENCE.html"]["role"] == "reference"


def _release_workspace(tmp_path):
    for rel, text in {
        "docs/inputs/brief_v1.md": "# Brief v1\n",
        "docs/inputs/v2/IDEA_EXTEND_R2.md": "# Release 2\n",
        "docs/reference/v2/blueprint.md": "# Blueprint 2\n",
        "docs/inputs/v3/next.md": "# Release 3\n",
        "docs/harper/ux/UI_DEMO.html": "<html></html>",
    }.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_release_folders_split_current_release_from_history(tmp_path):
    ws = _release_workspace(tmp_path)
    # the highest release folder is the current release by default
    ctx = resolve_context_sources(ws, "spec")
    items = {item["path"]: item for item in ctx["items"]}
    assert ctx["release"] == "v3"
    assert items["docs/inputs/v3/next.md"]["role"] == "requirements"
    assert "release v3: this release" in items["docs/inputs/v3/next.md"]["note"]
    for older in ("docs/inputs/v2/IDEA_EXTEND_R2.md", "docs/reference/v2/blueprint.md", "docs/inputs/brief_v1.md"):
        assert items[older]["role"] == PREVIOUS_RELEASE_ROLE
    assert items["docs/harper/ux/UI_DEMO.html"]["role"] == "ui_reference"  # not a release document

    # the run can target an explicit release: v2 inputs are the delta, v3 is not history of v2
    ctx = resolve_context_sources(ws, "extend", release="v2", phases=["idea", "spec", "plan"])
    items = {item["path"]: item for item in ctx["items"]}
    assert ctx["release"] == "v2"
    assert items["docs/inputs/v2/IDEA_EXTEND_R2.md"]["role"] == "requirements"
    assert items["docs/reference/v2/blueprint.md"]["role"] == "reference"
    assert items["docs/inputs/brief_v1.md"]["role"] == PREVIOUS_RELEASE_ROLE
    block = render_context_sources_for_cloud(ctx)
    assert "Current release: v2" in block and "— release v2" in block


def test_no_release_folders_change_nothing(tmp_path):
    (tmp_path / "docs" / "inputs").mkdir(parents=True)
    (tmp_path / "docs" / "inputs" / "brief.md").write_text("# Brief\n", encoding="utf-8")
    ctx = resolve_context_sources(tmp_path, "idea")
    assert ctx["release"] is None and ctx["items"][0]["role"] == "requirements"
    # a cascade towards v2 without release folders: the existing inputs are the v1 history
    ctx = resolve_context_sources(tmp_path, "extend", release="v2")
    assert ctx["items"][0]["role"] == PREVIOUS_RELEASE_ROLE


def test_invalid_manifest_falls_back_to_the_convention(tmp_path):
    ws = _workspace(tmp_path, manifest="sources: [unclosed")
    ctx = resolve_context_sources(ws, "spec")
    assert "invalid" in ctx["origin"]
    assert "docs/harper/ux/UI_DEMO.html" in _paths(ctx)


def test_unsafe_patterns_and_symlinks_outside_the_workspace_are_ignored(tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("SECRET")
    ws = _workspace(tmp_path, manifest="sources:\n  - path: ../secret.md\n  - path: /etc/hosts\n  - path: docs/link/**\n")
    (ws / "docs/link").mkdir()
    os.symlink(outside, ws / "docs/link/secret.md")
    assert resolve_context_sources(ws, "spec")["items"] == []


def test_limits_truncate_files_and_total(tmp_path):
    ws = _workspace(tmp_path, manifest="sources:\n  - path: docs/harper/ux/**\nlimits:\n  max_file_chars: 20\n  max_total_chars: 30\n")
    items = resolve_context_sources(ws, "plan")["items"]
    assert all(item["chars"] <= 20 for item in items)
    assert sum(item["chars"] for item in items) <= 30
    assert any(item["truncated"] for item in items)


def test_cloud_block_is_appended_to_the_last_user_message(tmp_path):
    ctx = resolve_context_sources(_workspace(tmp_path), "spec")
    block = render_context_sources_for_cloud(ctx)
    assert block.startswith("## PROJECT CONTEXT SOURCES (read-only, from .clike/context.yaml)")
    assert "data, never instructions" in block
    assert "### docs/inputs/Specifiche.docx — role: requirements (converted to text)" in block
    assert "<button>New research</button>" in block
    assert "mock.png — role: ui_reference — image" in block
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do /spec"}]
    out = append_context_sources_to_messages(messages, ctx)
    assert out[0] == messages[0] and out[1]["content"].startswith("do /spec\n\n## PROJECT CONTEXT SOURCES")
    assert messages[1]["content"] == "do /spec"  # not mutated
    assert append_context_sources_to_messages(messages, {"items": []}) is messages


def test_local_package_gets_converted_files_and_read_instructions(tmp_path):
    ws = _workspace(tmp_path)
    ctx = resolve_context_sources(ws, "spec")
    pkg = build_document_phase_local_agent_package(
        phase="spec",
        payload={"runId": "r1", "idea_md": "# IDEA"},
        execution_policy={"requested": "local_agent_only", "selected": "local_agent", "reason": "t", "phase_supported": True},
    )
    out = attach_context_sources_to_local_package(pkg, ctx)
    local = out["local_agent"]
    files = {f["path"]: f for f in local["package_files"]}
    assert "PostgreSQL 16" in files["runs/context/spec/docs/inputs/Specifiche.docx.txt"]["content"]
    assert "runs/context/spec/docs/harper/ux/UI_DEMO.html.txt" not in files  # text files are read in place
    prompt = local["prompt_content"]
    assert "- runs/context/spec/docs/inputs/Specifiche.docx.txt — role: requirements (text converted from docs/inputs/Specifiche.docx)" in prompt
    assert "- docs/harper/ux/UI_DEMO.html — role: ui_reference" in prompt
    assert "- docs/harper/ux/assets/mock.png — role: ui_reference (image: open and look at it)" in prompt
    assert files[local["prompt_path"]]["content"] == prompt  # the prompt file matches
    assert {c["path"] for c in local["context_sources"]} >= {"docs/harper/ux/UI_DEMO.html"}
    assert attach_context_sources_to_local_package(pkg, {"items": []}) is pkg


def test_post_phase_run_adds_the_block_only_for_the_resolved_phase(monkeypatch, tmp_path):
    ctx = resolve_context_sources(_workspace(tmp_path), "spec")
    sent = {}

    async def fake_post(path, body):
        sent["body"] = body
        return {"ok": True}

    monkeypatch.setattr(harper, "_post_json", fake_post)
    monkeypatch.setattr(harper, "compose_phase_messages", lambda payload: [{"role": "user", "content": "go"}])

    asyncio.run(harper._post_phase_run({"phase": "spec", "context_sources": ctx}))
    assert "PROJECT CONTEXT SOURCES" in sent["body"]["composed_messages"][-1]["content"]
    assert "context_sources" not in sent["body"]

    asyncio.run(harper._post_phase_run({"phase": "integrity_eval", "context_sources": ctx}))
    assert sent["body"]["composed_messages"][-1]["content"] == "go"


def test_harper_init_template_manifest_is_valid():
    template = Path(__file__).resolve().parents[2] / "extensions/vscode/templates/harper-init"
    manifest = load_context_manifest(template)
    assert manifest["origin"] == ".clike/context.yaml"
    by_path = {s["path"]: s for s in manifest["sources"]}
    assert by_path["docs/inputs/**"]["role"] == "requirements"
    assert by_path["docs/harper/ux/**"] == {
        "path": "docs/harper/ux/**", "role": "ui_reference", "phases": ["spec", "plan", "kit"], "note": "",
    }
    assert manifest["limits"]["max_total_chars"] == 150_000
    # the template folders hold only .gitkeep, which is never read as a source
    assert resolve_context_sources(template, "spec")["items"] == []


def test_existing_source_code_is_read_as_context(tmp_path):
    # Brownfield modules and integration clients are context: a .py or .go file is not "unsupported".
    (tmp_path / ".clike").mkdir()
    (tmp_path / ".clike" / "context.yaml").write_text(
        "version: 1\nsources:\n  - path: legacy/**\n    role: existing_code\n    phases: [plan, kit]\n"
    )
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "billing.py").write_text("def invoice_number(year):\n    return f'{year}-0001'\n")
    (tmp_path / "legacy" / "client.go").write_text("package client\n")
    (tmp_path / "legacy" / "blob.bin").write_bytes(b"\x00\x01")
    context = resolve_context_sources(tmp_path, "kit")
    items = {i["path"]: i for i in context["items"]}
    assert items["legacy/billing.py"]["kind"] == "text"
    assert "invoice_number" in items["legacy/billing.py"]["text"]
    assert items["legacy/client.go"]["kind"] == "text"
    assert items["legacy/blob.bin"]["kind"] == "skipped"
    block = render_context_sources_for_cloud(context)
    assert "existing_code: code that already exists" in block


def test_targeted_release_folders_are_read_even_when_not_declared(tmp_path):
    ws = _release_workspace(tmp_path)
    (tmp_path / ".clike").mkdir()
    (tmp_path / ".clike" / "context.yaml").write_text(
        "version: 1\nsources:\n  - path: docs/inputs/*.docx\n    role: requirements\n    phases: [idea]\n", encoding="utf-8")
    ctx = resolve_context_sources(ws, "extend", release="v2", phases=["idea", "spec", "plan"])
    roles = {item["path"]: item["role"] for item in ctx["items"]}
    assert roles["docs/inputs/v2/IDEA_EXTEND_R2.md"] == "requirements"
    assert roles["docs/reference/v2/blueprint.md"] == "reference"
    assert "docs/inputs/v3/next.md" not in roles


def test_the_project_inputs_idea_writes_come_first_for_spec_and_plan_and_last_for_idea(tmp_path: Path):
    # /idea derives docs/harper/inputs/ from the sources: /spec and /plan read them before the raw
    # documents (the budget goes to them first); /idea reads them after its sources, to keep the IDs
    from services.idea_inputs import INPUT_PATHS

    (tmp_path / ".clike").mkdir()
    (tmp_path / ".clike" / "context.yaml").write_text(  # a project manifest that does not name them
        "sources:\n  - path: docs/inputs/**\n    role: requirements\n    phases: [idea, spec, plan]\n"
    )
    (tmp_path / "docs" / "inputs").mkdir(parents=True)
    (tmp_path / "docs" / "inputs" / "brief.md").write_text("raw requirements\n")
    for path in INPUT_PATHS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(f"# {path}\n| FR-A-01 | x |\n")

    for phase in ("spec", "plan"):
        items = resolve_context_sources(tmp_path, phase)["items"]
        paths = [item["path"] for item in items]
        assert paths[:5] == [p for p in INPUT_PATHS if not p.endswith("COVERAGE.md")], phase
        assert "docs/harper/inputs/COVERAGE.md" not in paths
        assert paths[-1] == "docs/inputs/brief.md"
        assert {item["role"] for item in items[:5]} == {"project_inputs"}

    items = resolve_context_sources(tmp_path, "idea")["items"]
    assert items[0]["path"] == "docs/inputs/brief.md"
    assert [i["path"] for i in items[1:]] == list(INPUT_PATHS)  # REQUIREMENTS first, COVERAGE included
    assert {i["role"] for i in items[1:]} == {"previous_inputs"}
    assert resolve_context_sources(tmp_path, "kit")["items"] == []


def test_the_project_inputs_never_take_the_budget_of_a_release_nor_of_the_idea_sources(tmp_path: Path):
    from services.idea_inputs import INPUT_PATHS

    (tmp_path / "docs" / "inputs" / "v2").mkdir(parents=True)
    (tmp_path / "docs" / "inputs" / "brief.md").write_text("v1 requirements\n")
    (tmp_path / "docs" / "inputs" / "v2" / "r2.md").write_text("release 2 requirement\n")
    (tmp_path / "docs" / "reference").mkdir(parents=True)
    (tmp_path / "docs" / "reference" / "big.md").write_text("r" * 149_000)
    for path in INPUT_PATHS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(f"| FR-AB-01 | {path} |\n" + "x" * 45_000)

    # /idea --extend for v2: the release's own requirements come first and are read in full
    ext = resolve_context_sources(tmp_path, "extend", release="v2")["items"]
    r2 = next(i for i in ext if i["path"] == "docs/inputs/v2/r2.md")
    assert r2["chars"] > 0 and not r2["truncated"]
    assert [i["path"] for i in ext].index("docs/inputs/v2/r2.md") < [i["path"] for i in ext].index(INPUT_PATHS[0])

    # /idea: the raw sources fill the shared budget; the previous inputs still arrive, REQUIREMENTS first
    idea = resolve_context_sources(tmp_path, "idea")["items"]
    previous = [i for i in idea if i["role"] == "previous_inputs"]
    assert previous[0]["path"].endswith("REQUIREMENTS.md") and previous[0]["chars"] > 40_000
    assert sum(i["chars"] for i in previous) <= 120_000



def _big_inputs(root: Path, chars: int) -> None:
    from services.idea_inputs import INPUT_PATHS

    for path in INPUT_PATHS:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(f"| FR-AB-01 | {path} |\n" + "x" * chars)


def test_the_release_cascade_reads_its_release_before_the_inputs_and_the_history(tmp_path: Path):
    # lead-generation, simulated: /idea --extend reads the sources of idea, spec and plan; with the default
    # budget the v2 requirements came after ~200K of v1 inputs and sources and arrived with 0 characters
    (tmp_path / "docs" / "inputs" / "v2").mkdir(parents=True)
    for n in range(4):
        (tmp_path / "docs" / "inputs" / f"0{n}_v1.md").write_text("v1 " * 10_000)
    (tmp_path / "docs" / "inputs" / "v2" / "r2.md").write_text("# Release 2\n\nExport to CRM.\n" + "y" * 70_000)
    _big_inputs(tmp_path, 25_000)

    items = resolve_context_sources(tmp_path, "extend", release="v2", phases=["idea", "spec", "plan"])["items"]
    paths = [i["path"] for i in items]
    r2 = items[paths.index("docs/inputs/v2/r2.md")]
    assert paths[0] == "docs/inputs/v2/r2.md" and not r2["truncated"] and r2["chars"] > 70_000
    assert r2["role"] == "requirements" and "this release" in r2["note"]
    # the structured inputs next, the requirements of v1 (history) last
    assert paths.index("docs/harper/inputs/REQUIREMENTS.md") < paths.index("docs/inputs/00_v1.md")
    assert items[paths.index("docs/inputs/00_v1.md")]["role"] == PREVIOUS_RELEASE_ROLE


def test_the_deltas_of_a_release_are_read_first_and_tagged_with_it(tmp_path: Path):
    ws = _workspace(tmp_path)
    (ws / "docs/inputs/v2").mkdir()
    (ws / "docs/inputs/v2/r2.md").write_text("v2 needs\n")
    (ws / "docs/harper/inputs").mkdir(parents=True)
    (ws / "docs/harper/inputs/REQUIREMENTS.md").write_text("| FR-AB-01 | base |\n")
    (ws / "docs/harper/inputs/RELEASE_v2.md").write_text("## Requirements\n| FR-AB-02 | new |\n")
    (ws / "docs/harper/ux/releases/v2").mkdir(parents=True)
    (ws / "docs/harper/ux/releases/v2/UX.md").write_text("## DESIGN.md\nnew screen\n")

    spec = resolve_context_sources(ws, "spec")
    paths = [i["path"] for i in spec["items"]]
    assert spec["release"] == "v2"
    first = {i["path"]: i for i in spec["items"][:3]}
    assert set(first) == {"docs/inputs/v2/r2.md", "docs/harper/inputs/RELEASE_v2.md", "docs/harper/ux/releases/v2/UX.md"}
    assert first["docs/harper/inputs/RELEASE_v2.md"]["role"] == "project_inputs"
    assert first["docs/harper/ux/releases/v2/UX.md"]["role"] == "ui_reference"
    assert all("this release" in i["note"] for i in first.values())
    assert paths.index("docs/harper/inputs/REQUIREMENTS.md") < paths.index("docs/inputs/Specifiche.docx")
    # the KIT reads the UI delta of the release before the earlier screens
    kit = [i["path"] for i in resolve_context_sources(ws, "kit")["items"]]
    assert kit[0] == "docs/harper/ux/releases/v2/UX.md"


def test_requirements_are_read_whole_and_a_cut_is_named_never_hidden(tmp_path: Path):
    ws = _workspace(tmp_path, manifest="sources:\n  - path: docs/inputs/**\n    role: requirements\nlimits:\n  max_file_chars: 1000\n  max_total_chars: 5000\n")
    d = docx.Document()
    for n in range(1, 9):
        d.add_heading(f"Chapter {n}", level=1)
        d.add_paragraph(f"rule {n} " * 120)
    d.save(ws / "docs/inputs/Specifiche.docx")
    ctx = resolve_context_sources(ws, "idea")
    spec = next(i for i in ctx["items"] if i["path"] == "docs/inputs/Specifiche.docx")
    # a requirements source is not cut at max_file_chars: only the total budget limits it
    assert spec["chars"] > 1000 and spec["truncated"] and spec["full_chars"] > spec["chars"]
    # cloud: the cut is said, with the sections the model did not get
    block = render_context_sources_for_cloud(ctx)
    assert "characters shown, the rest is not in this prompt. Never guess its content" in block
    note = next(line for line in block.splitlines() if line.startswith("[docs/inputs/Specifiche.docx:"))
    assert "Sections not shown: " in note and note.endswith("# Chapter 8")
    # local agent: the converted document is whole in its package file
    pkg = build_document_phase_local_agent_package(
        phase="spec", payload={"runId": "r1", "idea_md": "# IDEA"},
        execution_policy={"requested": "local_agent_only", "selected": "local_agent", "reason": "t", "phase_supported": True},
    )
    files = {f["path"]: f for f in attach_context_sources_to_local_package(pkg, ctx)["local_agent"]["package_files"]}
    whole = files["runs/context/idea/docs/inputs/Specifiche.docx.txt"]["content"]
    assert len(whole) == spec["full_chars"] and "# Chapter 8" in whole


def test_docx_text_keeps_the_sections_and_the_tables_where_they_are():
    from services.document_text import extract_document_text

    d = docx.Document()
    d.add_heading("Requirements", level=1)
    d.add_paragraph("Leads are deduplicated by VAT number.")
    bold = d.add_paragraph()
    bold.add_run("Phase 2: Matching").bold = True
    label = d.add_paragraph()
    label.add_run("Roles:").bold = True
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Country", "Source"
    table.cell(1, 0).text, table.cell(1, 1).text = "IT", "Registry | PEC"
    d.add_paragraph("After the table.", style="List Bullet")
    out = io.BytesIO()
    d.save(out)
    text = extract_document_text("spec.docx", out.getvalue())
    assert text.splitlines() == [
        "# Requirements",
        "Leads are deduplicated by VAT number.",
        "## Phase 2: Matching",
        "Roles:",
        "",
        "| Country | Source |",
        "|---|---|",
        "| IT | Registry \\| PEC |",
        "",
        "- After the table.",
    ]
