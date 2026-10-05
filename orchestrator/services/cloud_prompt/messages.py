"""Cloud phase messages (WP8.7): the system + user messages sent to the model for a Harper phase.

Moved from gateway/routes/harper.py so that the Harper domain (phase prompts, context selection,
output checklists) lives in the orchestrator; the gateway receives ``composed_messages`` and only
adds RAG material, chat history and the provider call. Function bodies are unchanged from the
gateway (proved by the gateway golden suite, which replays orchestrator payloads); the phase system
prompts now live in orchestrator/phases/<phase>/cloud_*.md.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from services.cloud_prompt.active_output_contract import build_active_output_contract
from services.cloud_prompt.canonical_validation import validate_current_canonical_core_blobs
from services.cloud_prompt.methodology_prompt import (
    render_current_canonical_validation_for_cloud_prompt,
    render_methodology_context_for_cloud_prompt,
)

log = logging.getLogger("orchestrator.cloud_prompt")

PHASES_DIR = Path(__file__).resolve().parents[2] / "phases"
PROMPT_IDEA_SYSTEM_PATH = str(PHASES_DIR / "idea/cloud_system.md")
PROMPT_SPEC_SYSTEM_PATH = str(PHASES_DIR / "spec/cloud_system.md")
PROMPT_PLAN_SYSTEM_PATH = str(PHASES_DIR / "plan/cloud_system.md")
PROMPT_KIT_SYSTEM_PATH = str(PHASES_DIR / "kit/cloud_system.md")
PROMPT_INTEGRITY_EVAL_SYSTEM_PATH = str(PHASES_DIR / "kit/cloud_integrity_eval.md")
PROMPT_PROMOTION_HARDENER_SYSTEM_PATH = str(PHASES_DIR / "kit/cloud_promotion_hardener.md")
PROMPT_PROMOTION_EVAL_SYSTEM_PATH = str(PHASES_DIR / "kit/cloud_promotion_eval.md")
PROMPT_EVAL_SYSTEM_PATH = str(PHASES_DIR / "eval/cloud_system.md")
PROMPT_GATE_SYSTEM_PATH = str(PHASES_DIR / "gate/cloud_system.md")
PROMPT_FINALIZE_SYSTEM_PATH = str(PHASES_DIR / "finalize/cloud_system.md")
PROMPT_EXTEND_SYSTEM_PATH = str(PHASES_DIR / "extend/cloud_system.md")


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            log.info("Loading %s", path)
            return f.read()
    except Exception:
        log.error("Error reading %s", path)
        return ""


def _load_json_blob(core_blobs: dict | None, suffix: str) -> dict | None:
    if not core_blobs:
        return None

    suffix = str(suffix or "").strip().lower()
    for name, content in (core_blobs or {}).items():
        key = str(name or "").strip().lower()
        if not key.endswith(suffix):
            continue
        try:
            data = json.loads(str(content or ""))
        except Exception as exc:
            log.warning("failed to parse json blob %s from %s: %s", suffix, name, exc)
            return None
        if isinstance(data, dict):
            return data
        return None

    return None


def _load_target_contract_from_core_blobs(core_blobs: dict | None) -> dict | None:
    return _load_json_blob(core_blobs, "target_contract.json")


def _load_file_requirements_from_core_blobs(core_blobs: dict | None) -> dict | None:
    return _load_json_blob(core_blobs, "file_requirements.json")


def _compose_cloud_selected_skill_context(
    *,
    core_blobs: dict | None,
    methodology_context: dict | None,
    active_output_contract: dict | None,
) -> str:
    """
    Compose the cloud-visible selected skill context.

    Required invariant:
    - CLike selected capabilities are always injected when materialized.
    - BMAD methodology skills are injected only when methodology=bmad.
    - CLike and BMAD remain separate prompt sections.
    """
    parts: list[str] = []

    clike_context = _render_clike_selected_capability_context_for_cloud(core_blobs)
    if clike_context:
        parts.append(clike_context)

    methodology_text = render_methodology_context_for_cloud_prompt(
        methodology_context,
        active_output_contract=active_output_contract,
    )
    if str(methodology_text or "").strip():
        parts.append(str(methodology_text).strip())

    if not parts:
        return ""

    return (
        "## Cloud Selected Phase Skill Context\n\n"
        "The following context is already resolved by CLike for this exact cloud run.\n"
        "Inject only selected phase/REQ-scoped skills into the model prompt.\n"
        "Do not treat full core_blobs catalogs as selected skills.\n\n"
        + "\n\n".join(parts)
    ).strip()


def _filter_core_blobs_for_kit(
    core_blobs: dict | None,
    target_req: str | None,
) -> dict[str, str]:
    if not core_blobs:
        return {}

    target_req = str(target_req or "").strip()
    kept: dict[str, str] = {}

    always_keep_suffixes = (
        "spec.md",
        "plan.md",
        "plan.json",
        "tech_constraints.yaml",
        "target_contract.json",
        "file_requirements.json",
        "integrity_eval.json",
    )
    always_keep_prefixes = (
        "REQ_PROMOTION_MANIFEST",
        "REPO_ACCESS_MANIFEST",
        "REPO_STRUCTURE_EVIDENCE",
        "REPO_COMPOSITION_MANIFEST",
        "CLIKE_CAPABILITY_MANIFEST",
        "CLIKE_CAPABILITY_INDEX",
        "CLIKE_SELECTED_CAPABILITY_CONTEXT",
        "candidate::",
    )

    for name, content in core_blobs.items():
        key = str(name or "").strip()
        lkey = key.lower()

        if (
            lkey.startswith("companion::docs/harper/bmad/")
            or lkey.startswith("companion::docs/harper/ux/")
            or (target_req and lkey.startswith(f"companion::runs/kit/{target_req.lower()}/docs/"))
        ):
            kept[key] = str(content or "")
            continue

        if any(lkey.endswith(sfx) for sfx in always_keep_suffixes):
            kept[key] = str(content or "")
            continue

        if any(key.startswith(prefix) for prefix in always_keep_prefixes):
            kept[key] = str(content or "")
            continue

        if key.startswith("REQ_PROMOTION_MANIFEST"):
            if target_req and target_req in key:
                kept[key] = str(content or "")
            elif target_req and f"REQ Promotion Manifest — {target_req}" in str(content or ""):
                kept[key] = str(content or "")
            continue

    return kept


def _load_selected_capability_json_from_core(core_blobs: dict | None) -> dict:
    for name, content in (core_blobs or {}).items():
        if str(name or "").lower().endswith("clike_selected_capability_context.json"):
            try:
                data = json.loads(str(content or ""))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _load_selected_capability_markdown_from_core(core_blobs: dict | None) -> str:
    for name, content in (core_blobs or {}).items():
        if str(name or "").lower().endswith("clike_selected_capability_context.md"):
            return str(content or "")
    return ""


def _selected_capability_names(group: dict) -> list[str]:
    if not isinstance(group, dict):
        return []
    selected = [str(x).strip() for x in (group.get("selected") or []) if str(x or "").strip()]
    if selected:
        return selected
    resolved = group.get("resolved") if isinstance(group.get("resolved"), list) else []
    return [
        str(item.get("name")).strip()
        for item in resolved
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def _selected_capability_names_from_context(selected: dict, key: str, legacy_key: str) -> list[str]:
    names = _selected_capability_names(selected.get(key) or {})
    if names:
        return names
    return [str(x).strip() for x in (selected.get(legacy_key) or []) if str(x or "").strip()]


def _render_clike_selected_capability_context_for_cloud(core_blobs: dict | None) -> str:
    
    selected = _load_selected_capability_json_from_core(core_blobs)
    markdown = _load_selected_capability_markdown_from_core(core_blobs)
    if not selected and not markdown:
        return ""

    packs = _selected_capability_names_from_context(selected, "packs", "selected_packs")
    skills = _selected_capability_names_from_context(selected, "skills", "selected_skills")
    design_profiles = _selected_capability_names_from_context(
        selected,
        "design_profiles",
        "selected_design_profiles",
    )
    lines = [
        "### CLike Selected Capability Context",
        "- This context is generated by CLike for the current REQ.",
        "- Selected packs, skills, and design profiles are REQ-scoped implementation, test, documentation, and evidence constraints.",
        "- Capability guidance does not override SPEC, TECH_CONSTRAINTS, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, EvalRunner, Gate, or allowed write roots.",
        f"- selected CLike packs: {'; '.join(packs) if packs else 'none'}",
        f"- selected CLike skills: {'; '.join(skills) if skills else 'none'}",
        f"- selected CLike design profiles: {'; '.join(design_profiles) if design_profiles else 'none'}",
    ]
    bounded_markdown = markdown.strip()
    if bounded_markdown:
        lines.extend(
            [
                "- selected capability markdown:",
                "```markdown",
                bounded_markdown[:8000].rstrip() + ("\n...[truncated]" if len(bounded_markdown) > 8000 else ""),
                "```",
            ]
        )
    return "\n".join(lines).strip()


def _render_namespace_materialization_for_cloud(file_requirements: dict | None) -> str:
    namespace_context = (file_requirements or {}).get("namespace_materialization") or {}
    if not isinstance(namespace_context, dict) or not namespace_context.get("rules"):
        return ""
    lines = [
        "## Namespace Materialization",
        f"- ecosystem: {namespace_context.get('ecosystem') or 'unknown'}",
        f"- import_namespace: {namespace_context.get('import_namespace') or 'none'}",
        f"- package_path: {namespace_context.get('package_path') or 'none'}",
        f"- source_root: {namespace_context.get('source_root') or 'none'}",
        *[f"- {rule}" for rule in (namespace_context.get("rules") or [])],
    ]
    return "\n".join(lines).strip()


def _kit_project_context(filtered_core: dict, target_req: str) -> list[str]:
    """Project context for the KIT model: technology constraints, IDEA, SPEC and the target REQ.

    The KIT message used to carry only the contract summary and file requirements, so the model
    chose runtime and framework without seeing TECH_CONSTRAINTS or SPEC.
    """
    def blob(predicate) -> str:
        for name, content in (filtered_core or {}).items():
            base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
            if predicate(base) and str(content or "").strip():
                return str(content).strip()
        return ""

    parts: list[str] = []
    constraints = blob(lambda b: b.startswith("tech_constraints"))
    idea = blob(lambda b: b == "idea.md")
    spec = blob(lambda b: b == "spec.md")
    req_block = ""
    plan_text = blob(lambda b: b == "plan.json")
    if plan_text and target_req:
        try:
            reqs = (json.loads(plan_text) or {}).get("reqs") or []
            by_id = {str(r.get("id") or "").upper(): r for r in reqs if isinstance(r, dict)}
            target = by_id.get(target_req.upper())
            if target:
                deps = [by_id[d.upper()] for d in (target.get("dependsOn") or []) if str(d).upper() in by_id]
                req_block = json.dumps({"target": target, "dependencies": deps}, indent=2, ensure_ascii=False)
        except (ValueError, AttributeError):
            req_block = ""
    if not (constraints or idea or spec or req_block):
        return []
    parts.extend([
        "## PROJECT CONTEXT",
        "- TARGET_CONTRACT.json and FILE_REQUIREMENTS.json govern scope and emitted files.",
        "- TECHNOLOGY CONSTRAINTS are authoritative for runtime, language, framework and libraries; when absent, follow the stack stated in SPEC/IDEA.",
        "",
    ])
    if constraints:
        parts.extend(["### TECHNOLOGY CONSTRAINTS (verbatim)", "```yaml", constraints, "```", ""])
    if req_block:
        parts.extend([f"### plan.json — {target_req} and its dependencies (verbatim)", "```json", req_block, "```", ""])
    if spec:
        parts.extend(["### SPEC.md (verbatim)", spec, ""])
    if idea:
        parts.extend(["### IDEA.md (verbatim)", idea, ""])
    return parts


def _build_kit_user_message(
    phase: str,
    user: str,
    core_blobs: dict | None,
    targets: list[str] | None,
    active_contract_text: str | None = None,
) -> str:
    if (phase or "").lower() != "kit":
        return user

    target_req = str((targets or [None])[0] or "").strip()
    filtered_core = _filter_core_blobs_for_kit(core_blobs, target_req)

    target_contract = _load_target_contract_from_core_blobs(filtered_core)
    file_requirements = _load_file_requirements_from_core_blobs(filtered_core)

    refs = []
    for name, content in filtered_core.items():
        refs.append(f"- {name} ({len(str(content or ''))} chars)")

    parts = []
    if str(active_contract_text or "").strip():
        parts.extend([str(active_contract_text or "").strip(), ""])

    parts.extend([
        "## KIT EXECUTION MODE",
        f"- Current target REQ-ID: {target_req}",
        "- TARGET_CONTRACT.json is authoritative for scope, lane, paths, and acceptance.",
        "- FILE_REQUIREMENTS.json is authoritative for required emitted files and their content expectations.",
        "- REQ_PROMOTION_MANIFEST.md is authoritative for staging-vs-canonical promotion discipline.",
        "- Dependencies are read-only context only.",
        "",
    ])

    if target_contract:
        lane = str(target_contract.get("lane") or "").strip()
        title = str(target_contract.get("title") or "").strip()
        primary_outcome = str(target_contract.get("primary_outcome") or "").strip()
        acceptance = [str(x).strip() for x in (target_contract.get("acceptance") or []) if str(x).strip()]
        create_under = [str(x).strip() for x in ((target_contract.get("paths") or {}).get("create_under") or []) if str(x).strip()]
        must_reuse = [str(x).strip() for x in ((target_contract.get("paths") or {}).get("must_reuse") or []) if str(x).strip()]
        forbidden = [str(x).strip() for x in ((target_contract.get("paths") or {}).get("forbidden") or []) if str(x).strip()]

        parts.extend([
            "## TARGET CONTRACT SUMMARY",
            f"- Lane: {lane}",
            f"- Title: {title}",
            f"- Primary outcome: {primary_outcome}",
            "- Allowed createUnder roots:",
        ])
        parts.extend([f"  - {x}" for x in create_under] or ["  - none"])
        parts.append("- Must reuse:")
        parts.extend([f"  - {x}" for x in must_reuse] or ["  - none"])
        parts.append("- Forbidden roots:")
        parts.extend([f"  - {x}" for x in forbidden] or ["  - none"])
        parts.append("- Acceptance criteria:")
        parts.extend([f"  - {x}" for x in acceptance] or ["  - none"])
        parts.append("")

    selected_capability_text = _render_clike_selected_capability_context_for_cloud(filtered_core)
    if selected_capability_text:
        parts.extend([selected_capability_text, ""])

    namespace_text = _render_namespace_materialization_for_cloud(file_requirements)
    if namespace_text:
        parts.extend([namespace_text, ""])

    if file_requirements:
        parts.append("## FILE REQUIREMENTS")

        runtime_manifest_policy = file_requirements.get("runtime_manifest_policy") or {}
        if runtime_manifest_policy:
            parts.extend([
                "- Runtime eval manifest policy:",
                f"  - Required: {bool(runtime_manifest_policy.get('required', False))}",
                f"  - Scope: {runtime_manifest_policy.get('scope') or 'KIT_EVAL_ONLY'}",
                f"  - Policy: {runtime_manifest_policy.get('policy') or 'n/a'}",
            ])
            examples = [str(x).strip() for x in (runtime_manifest_policy.get("examples") or []) if str(x).strip()]
            must_not = [str(x).strip() for x in (runtime_manifest_policy.get("must_not") or []) if str(x).strip()]
            if examples:
                parts.append("  - Examples only:")
                parts.extend([f"    - {x}" for x in examples])
            if must_not:
                parts.append("  - Must not:")
                parts.extend([f"    - {x}" for x in must_not])

        launcher_policy = file_requirements.get("solution_launcher_policy") or {}
        if launcher_policy:
            parts.extend([
                "- Solution launcher/composition policy:",
                f"  - Required when executable area exists: {bool(launcher_policy.get('required_when_executable_area_exists', False))}",
                f"  - Scope: {launcher_policy.get('scope') or 'SOLUTION_COMPOSITION_ROOT'}",
                f"  - Execution areas detected: {', '.join(str(x) for x in (launcher_policy.get('execution_areas_detected') or [])) or 'not pre-detected; infer from repository evidence'}",
                f"  - Policy: {launcher_policy.get('policy') or 'n/a'}",
            ])
            must_cover = [str(x).strip() for x in (launcher_policy.get("must_cover") or []) if str(x).strip()]
            must_not = [str(x).strip() for x in (launcher_policy.get("must_not") or []) if str(x).strip()]
            if must_cover:
                parts.append("  - Must cover:")
                parts.extend([f"    - {x}" for x in must_cover])
            if must_not:
                parts.append("  - Must not:")
                parts.extend([f"    - {x}" for x in must_not])

        for item in list(file_requirements.get("required_outputs") or []):
            path_hint = str(item.get("path_hint") or "").strip()
            kind = str(item.get("kind") or "").strip()
            purpose = str(item.get("purpose") or "").strip()
            required = bool(item.get("required", False))
            must_cover = [str(x).strip() for x in (item.get("must_cover") or []) if str(x).strip()]
            must_contain = [str(x).strip() for x in (item.get("must_contain") or []) if str(x).strip()]
            must_not_contain = [str(x).strip() for x in (item.get("must_not_contain") or []) if str(x).strip()]

            parts.extend([
                f"- Output file ({kind}) [{'required' if required else 'optional'}]: {path_hint}",
                f"  - Purpose: {purpose or 'n/a'}",
            ])
            if must_cover:
                parts.append("  - Must cover:")
                parts.extend([f"    - {x}" for x in must_cover])
            if must_contain:
                parts.append("  - Must contain:")
                parts.extend([f"    - {x}" for x in must_contain])
            if must_not_contain:
                parts.append("  - Must not contain:")
                parts.extend([f"    - {x}" for x in must_not_contain])
        parts.append("")

    # project-wide documents come from the full core (the KIT filter keeps REQ-scoped material)
    parts.extend(_kit_project_context({**(core_blobs or {}), **filtered_core}, target_req))

    parts.extend([
        "## HARD RULES",
        "- Emit files only under the current target REQ staging root.",
        "- Do not emit files for adjacent REQs.",
        "- Do not invent file structure outside FILE_REQUIREMENTS.json without strong repository evidence.",
        "- If a file is marked required, emit it.",
        "- A path hint with a <placeholder> is a pattern: choose one concrete path and use that same concrete path everywhere (LTC.json commands, HOWTO.md, tests); never copy the placeholder text.",
        "- Do not create duplicate config/settings/logging/helpers if canonical equivalents already exist or are implied by repository evidence.",
        "- Prefer compact, reviewable, repo-fit files over fragmented thin files.",
        "",
        "## Included references",
    ])
    parts.extend(refs if refs else ["- none"])
    parts.extend([
        "",
        "## OUTPUT CONTRACT",
        "- Emit each output as a BEGIN_FILE / END_FILE block using workspace-relative paths.",
        "- Use exactly: BEGIN_FILE runs/kit/<REQ-ID>/... then full file content then END_FILE.",
        "- Existing fenced file:/path blocks may be parsed for compatibility, but BEGIN_FILE / END_FILE is preferred.",
        "- No prose outside file blocks.",
    ])

    return "\n".join(parts).strip()


# --- PATCH START: phase-aware output checklist ---
def _output_checklist_for_phase(phase: str) -> str:
    p = (phase or "").lower()

    if p in ("spec", "plan"):
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            "- Emit each output as a BEGIN_FILE / END_FILE block using workspace-relative paths.\n"
            "- Markdown file contents may contain fenced code blocks such as YAML; preserve those internal fences as file content.\n"
            "- Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks.\n"
            "- Do not emit prose outside BEGIN_FILE / END_FILE blocks.\n"
            f"- Top-level heading is `# {p.upper()}`.\n"
            "- All major sections use `## Section` headings (no numbered titles).\n"
            "- Required diagrams (if any) use fenced code blocks (e.g., Mermaid). No ASCII art.\n"
            "- Clean Markdown bullets (one space after `-` or `*`).\n"
        )

    if p == "finalize":
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            "- Emit each output as a BEGIN_FILE / END_FILE block using workspace-relative paths.\n"
            "- Markdown file contents may contain fenced code blocks such as YAML; preserve those internal fences as file content.\n"
            "- Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks.\n"
            "- Do not emit prose outside BEGIN_FILE / END_FILE blocks.\n"
            f"- Top-level heading is `# {p.upper()}`.\n"
            "- If additional metadata (tags/version) is included, keep it at the end in a clearly labeled section.\n"
            "- No ASCII art; diagrams (if any) use proper fenced blocks.\n"
            "- Clean Markdown bullets (one space after `-` or `*`).\n"
        )

    if p == "kit":
        return (
            "### OUTPUT CONFORMITY CHECKLIST\n"
            "- Emit each output as a BEGIN_FILE / END_FILE block using workspace-relative paths.\n"
            "- Respect the module/package and namespace structure defined in PLAN.md and plan.json during KIT.\n"
            "- Do not emit prose outside BEGIN_FILE / END_FILE blocks, except a short append-only iteration log if explicitly specified.\n"
            "- Existing fenced file:/path blocks may still be parsed for compatibility, but BEGIN_FILE / END_FILE is preferred.\n"
        )

    return (
        "### OUTPUT CONFORMITY CHECKLIST\n"
        "- Emit each output as a BEGIN_FILE / END_FILE block using workspace-relative paths.\n"
        "- Markdown file contents may contain fenced code blocks such as YAML; preserve those internal fences as file content.\n"
        "- Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks.\n"
        "- Do not emit prose outside BEGIN_FILE / END_FILE blocks.\n"
        "- Existing fenced file:/path blocks may still be parsed for compatibility, but BEGIN_FILE / END_FILE is preferred.\n"
    )


def _append_kit_target_to_user(
    user_text: str,
    targets: list[str],
    acceptance: Optional[list[str]] = None,
) -> str:
    if not targets:
        return user_text

    target_req = str(targets[0]).strip()
    acc = [str(item).strip() for item in (acceptance or []) if str(item).strip()]

    header_lines = [
        "## KIT TARGET (AUTHORITATIVE)",
        f"- Target REQ-ID: {target_req}",
        f"- Only valid staging root: runs/kit/{target_req}/",
        f"- Only valid source root: runs/kit/{target_req}/src/",
        f"- Only valid test root: runs/kit/{target_req}/test/",
        f"- Only valid docs root: runs/kit/{target_req}/docs/",
        f"- Only valid ci root: runs/kit/{target_req}/ci/",
        "- Do not emit files for any other REQ-ID.",
        "- Dependency REQs are read-only context only.",
        "- Any file path outside the target REQ staging root is invalid.",
    ]

    if acc:
        header_lines.append("- Acceptance criteria for this target:")
        header_lines.extend([f"  - {item}" for item in acc])

    authoritative_block = "\n".join(header_lines).strip()
    return f"{authoritative_block}\n\n{user_text.lstrip()}"


def _compose_system_messages(
    phase: str,
    idea_md: Optional[str],
    core_blobs: dict | None,
    profile_hint: str | None,
    model_route_label: str | None,
    run_id: str | None,
    repo_url: str | None,
    targets: Optional[list[str]],
    methodology_context: Optional[dict] = None,
) -> list[dict]:
    log.info("Compose system messages for phase %s", phase)

    system_by_phase = {
        "idea": PROMPT_IDEA_SYSTEM_PATH,
        "spec": PROMPT_SPEC_SYSTEM_PATH,
        "plan": PROMPT_PLAN_SYSTEM_PATH,
        "kit": PROMPT_KIT_SYSTEM_PATH,
        "integrity_eval": PROMPT_INTEGRITY_EVAL_SYSTEM_PATH,
        "finalize": PROMPT_FINALIZE_SYSTEM_PATH,
        "extend": PROMPT_EXTEND_SYSTEM_PATH,
        "promotion_hardener": PROMPT_PROMOTION_HARDENER_SYSTEM_PATH,
        "promotion_eval": PROMPT_PROMOTION_EVAL_SYSTEM_PATH,
        "eval": PROMPT_EVAL_SYSTEM_PATH,
        "gate": PROMPT_GATE_SYSTEM_PATH,
    }
    # WP7: unknown phases and missing prompts fail loudly (they used to fall back to the SPEC
    # prompt or to a one-line placeholder, silently producing wrong outputs).
    system_path = system_by_phase.get(phase)
    if system_path is None:
        raise HTTPException(400, f"unknown Harper phase: {phase!r}")
    system = _read_text(system_path).strip()
    if not system:
        raise HTTPException(503, f"system prompt for phase {phase!r} is not available on the gateway")


    foreground = (
        "## CLike Principles (short)\n"
        "- Harper pipeline: IDEA→SPEC→PLAN→KIT, eval-driven quality, outcome-first.\n"
        "- Keep output concise but testable; Acceptance Criteria are mandatory.\n"
        "- Maintain human-in-control tone; do not invent facts.\n"
    )

    target_req_id = str((targets or [None])[0] or "").strip() or None
    kit_file_requirements = (
        _load_file_requirements_from_core_blobs(core_blobs)
        if (phase or "").lower() == "kit"
        else None
    )
    active_output_contract = build_active_output_contract(
        phase=phase,
        runner="cloud",
        methodology_context=methodology_context,
        req_id=target_req_id,
        file_requirements=kit_file_requirements,
    )
    cloud_selected_skill_context = _compose_cloud_selected_skill_context(
        core_blobs=core_blobs,
        methodology_context=methodology_context,
        active_output_contract=active_output_contract,
    )

    if cloud_selected_skill_context:
        system = (
            system.rstrip()
            + "\n\n"
            + cloud_selected_skill_context
            + "\n"
        )

    validation_context = validate_current_canonical_core_blobs(core_blobs)
    trusted_core_blobs = validation_context.get("trusted_core_blobs") or {}
    current_invalid_canonical = validation_context.get("invalid_canonical") or []
    trusted_idea_md = idea_md
    if idea_md and (phase or "").lower() == "spec":
        idea_validation_context = validate_current_canonical_core_blobs(
            {"docs/harper/IDEA.md": idea_md}
        )
        if idea_validation_context.get("invalid_canonical"):
            current_invalid_canonical.extend(
                idea_validation_context.get("invalid_canonical") or []
            )
            trusted_idea_md = None

    constraints_chunks: list[str] = []
    other_core: dict[str, str] = {}
    if trusted_core_blobs:
        for name, content in trusted_core_blobs.items():
            lname = (name or "").lower()
            if lname.startswith("tech_constraints"):
                if isinstance(content, str) and content.strip():
                    constraints_chunks.append(content.strip())
            else:
                other_core[str(name)] = str(content or "")

    refs = ""
    if other_core:
        refs = "### Included references:\n" + "\n".join(
            f"- {k} ({len(v or '')} chars)" for k, v in other_core.items()
        )

    suffix_parts = []

    verbatim_suffixes_for_phase = {
        # /plan turns SPEC requirements into REQs: it needs IDEA and SPEC content, not just their names.
        "plan": (
            "IDEA.md",
            "SPEC.md",
        ),
        "kit": (
            "SPEC.md",
            "PLAN.md",
            "plan.json",
            "TECH_CONSTRAINTS.yaml",
            "TARGET_CONTRACT.json",
            "FILE_REQUIREMENTS.json",
        ),
        "integrity_eval": (
            "SPEC.md",
            "PLAN.md",
            "plan.json",
            "TECH_CONSTRAINTS.yaml",
            "TARGET_CONTRACT.json",
            "FILE_REQUIREMENTS.json",
        ),
        "promotion_hardener": (
            "SPEC.md",
            "PLAN.md",
            "plan.json",
            "TECH_CONSTRAINTS.yaml",
            "TARGET_CONTRACT.json",
            "FILE_REQUIREMENTS.json",
            "INTEGRITY_EVAL.json",
        ),
        "promotion_eval": (
            "SPEC.md",
            "PLAN.md",
            "plan.json",
            "TECH_CONSTRAINTS.yaml",
            "TARGET_CONTRACT.json",
            "FILE_REQUIREMENTS.json",
            "INTEGRITY_EVAL.json",
        ),
        "extend": (
            "SPEC.md",
            "PLAN.md",
            "plan.json",
            "TECH_CONSTRAINTS.yaml",
        ),
    }

    normative_prefixes = (
        "REQ_PROMOTION_MANIFEST",
        "REPO_ACCESS_MANIFEST",
        "REPO_STRUCTURE_EVIDENCE",
        "REPO_COMPOSITION_MANIFEST",
        "CLIKE_CAPABILITY_MANIFEST",
        "candidate::",
    )

    active_verbatim_suffixes = verbatim_suffixes_for_phase.get((phase or "").lower(), tuple())

    for name, content in other_core.items():
        if any((name or "").startswith(prefix) for prefix in normative_prefixes):
            suffix_parts.append(f"\n\n### {name} (verbatim)\n{content}")
            continue

        if any((name or "").endswith(sfx) for sfx in active_verbatim_suffixes):
            suffix_parts.append(f"\n\n### {name} (verbatim)\n{content}")
            continue

        suffix_parts.append(
            f"\n\n### {name} (reference only)\nIncluded as project context; do not ignore if relevant."
        )

    if constraints_chunks:
        constraints_text = "\n\n---\n\n".join(constraints_chunks)
        # B17: own paragraph, even when the previous verbatim blob has no trailing newline
        suffix_parts.append("\n\n### Technology Constraints (YAML)\n```yaml\n" + constraints_text + "\n```")

    if current_invalid_canonical:
        suffix_parts.append(
            "\n\n"
            + render_current_canonical_validation_for_cloud_prompt(
                current_invalid_canonical
            ).strip()
        )

    suffix = "".join(suffix_parts)
    idea_txt = ""
    if trusted_idea_md and phase.lower() == "spec":
        idea_txt = f"### IDEA.md (verbatim)\n{trusted_idea_md}\n\n"

    user = (
        f"{foreground}\n\n"
        f"### Route\n\n"
        f"{idea_txt}"
        f"{refs}\n\n"
        f"{_output_checklist_for_phase(phase)}"
        f"### Task\nProduce/Transform the {phase.upper()} output that strictly follows the Output contract.{suffix}"
    )

    if (phase or "").lower() == "kit":
        target_contract = _load_target_contract_from_core_blobs(core_blobs)
        acceptance = (target_contract or {}).get("acceptance") or []
        user = _build_kit_user_message(
            phase=phase,
            user=user,
            core_blobs=core_blobs,
            targets=targets,
            active_contract_text=None,
        )
        user = _append_kit_target_to_user(
            user,
            targets=targets or [],
            acceptance=acceptance,
        )

    messages_output = [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user.strip()},
    ]
    return messages_output


def _methodology_context_with_envelope_skills(
    methodology_context: dict | None,
    context_envelope: dict | None,
    *,
    methodology: str | None,
    agent: str | None,
    phase: str | None,
) -> dict | None:
    base = dict(methodology_context) if isinstance(methodology_context, dict) else {}
    envelope = context_envelope if isinstance(context_envelope, dict) else {}
    envelope_bmad = envelope.get("bmad_methodology_skills") if isinstance(envelope.get("bmad_methodology_skills"), dict) else {}

    is_bmad = (
        str(base.get("methodology") or methodology or envelope.get("methodology") or "").strip().lower()
        == "bmad"
    )
    if not is_bmad:
        return methodology_context if isinstance(methodology_context, dict) else None

    base.setdefault("methodology", "bmad")
    base.setdefault("phase", phase or envelope.get("phase"))
    base.setdefault("agent", agent or envelope.get("agent"))

    envelope_refs = envelope_bmad.get("selected_skill_references") or []
    envelope_context = envelope_bmad.get("selected_skill_context") or {}
    envelope_policy = envelope_bmad.get("skill_reference_policy") or {}

    if isinstance(envelope_refs, list) and envelope_refs and not base.get("selected_skill_references"):
        base["selected_skill_references"] = envelope_refs
    if isinstance(envelope_context, dict) and envelope_context and not base.get("selected_skill_context"):
        base["selected_skill_context"] = envelope_context
    if isinstance(envelope_policy, dict) and envelope_policy and not base.get("skill_reference_policy"):
        base["skill_reference_policy"] = envelope_policy

    return base


_REPAIR_FILE_BUDGET = 16000      # chars per candidate file shown to the model
_REPAIR_TOTAL_BUDGET = 160000    # chars for all candidate files
_REPAIR_OUTPUT_TAIL = 3000       # chars of each failed check's output


def _kit_repair_section(repair: dict, req_id: str) -> str:
    """Auto-eval repair instructions for the KIT model: failed checks, current files, rules."""
    cycle = repair.get("cycle") or 1
    max_cycles = repair.get("max_cycles") or cycle
    lines = [
        f"## AUTO-EVAL REPAIR — cycle {cycle} of {max_cycles}",
        f"The candidate KIT for {req_id} failed the canonical eval. Fix the causes of the failed checks below.",
        "",
        "Rules:",
        "- Return ONLY the files you change, each complete in a BEGIN_FILE / END_FILE block. Files you do not return stay as they are.",
        f"- Tests under runs/kit/{req_id}/test/ are locked acceptance criteria: make the code pass them; never edit, skip or weaken them.",
        f"- runs/kit/{req_id}/ci/LTC.json: you may only fix the command of a check that cannot run (wrong path, module or flag). Never remove a check or make it non-blocking.",
        f"- Vulnerable dependencies: upgrade the affected packages in runs/kit/{req_id}/ci/requirements.txt (or the ecosystem manifest) to current versions without known vulnerabilities.",
        f"- A failure caused by the environment (network, missing system tool) is not fixed by changing code: explain it in runs/kit/{req_id}/docs/KIT_{req_id}.md.",
        "- Fix the root cause in the source; do not special-case the tests.",
        "",
        "### Failed checks",
    ]
    for item in repair.get("failures") or []:
        name = str(item.get("name") or "check")
        output = str(item.get("output") or "")[-_REPAIR_OUTPUT_TAIL:]
        lines += [
            f"#### {name} (exit {item.get('code')})",
            f"command: {item.get('command') or ''}",
            "```",
            output.rstrip(),
            "```",
        ]
    hint = str(repair.get("hint") or "").strip()
    if hint:
        lines += ["", "### Developer hint", hint]
    budget = _REPAIR_TOTAL_BUDGET
    files = [f for f in (repair.get("files") or []) if isinstance(f, dict) and f.get("path")]
    if files:
        lines += ["", "### Current candidate files"]
        for f in files:
            content = str(f.get("content") or "")
            if budget <= 0:
                lines.append(f"- {f['path']} (omitted: budget exhausted)")
                continue
            shown = content[:min(_REPAIR_FILE_BUDGET, budget)]
            budget -= len(shown)
            truncated = " (truncated)" if len(shown) < len(content) else ""
            lines += [f"#### {f['path']}{truncated}", "```", shown.rstrip(), "```"]
    return "\n".join(lines)


def compose_phase_messages(payload: dict) -> list[dict]:
    """Messages for ``payload`` exactly as the gateway composed them before WP8.7
    (plus the auto-eval repair section for a KIT repair)."""
    phase = str(payload.get("phase") or payload.get("cmd") or "").strip()
    kit = payload.get("kit")
    targets = list((kit.get("targets") or []) if isinstance(kit, dict) else [])
    methodology_context = _methodology_context_with_envelope_skills(
        payload.get("methodology_context"),
        payload.get("context_envelope"),
        methodology=payload.get("methodology"),
        agent=payload.get("agent"),
        phase=phase,
    )
    messages = _compose_system_messages(
        phase,
        payload.get("idea_md") or "",
        payload.get("core_blobs") or {},
        payload.get("profileHint"),
        None,
        payload.get("runId"),
        None,
        targets,
        methodology_context,
    )
    repair = (kit or {}).get("repair") if isinstance(kit, dict) else None
    if phase.lower() == "kit" and isinstance(repair, dict) and repair and targets:
        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n\n" + _kit_repair_section(repair, str(targets[0]))}
    return messages
