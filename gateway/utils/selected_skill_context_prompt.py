from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _render_bullets(items: list[Any], *, empty: str = "- none", limit: int = 12) -> list[str]:
    values = [str(item).strip() for item in items[:limit] if str(item or "").strip()]
    return [f"- {item}" for item in values] if values else [empty]


def load_text_blob(core_blobs: dict | None, suffix: str) -> str:
    if not isinstance(core_blobs, dict):
        return ""

    normalized_suffix = str(suffix or "").strip().lower()
    if not normalized_suffix:
        return ""

    for name, content in core_blobs.items():
        key = str(name or "").strip().lower()
        if key.endswith(normalized_suffix):
            return str(content or "").strip()

    return ""


def render_clike_selected_capability_context(core_blobs: dict | None) -> str:
    selected_context = load_text_blob(core_blobs, "CLIKE_SELECTED_CAPABILITY_CONTEXT.md")
    if not selected_context:
        return ""

    normalized = selected_context.strip()
    if normalized.startswith("# CLike Selected Capability Context"):
        normalized = normalized.replace("# CLike Selected Capability Context", "", 1).strip()

    return (
        "### CLike Selected Capability Context\n"
        "- source: CLIKE_SELECTED_CAPABILITY_CONTEXT.md\n"
        "- source_transport: core_blobs\n"
        "- scope: selected CLike packs, skills, and design profiles for the current target REQ/phase only\n"
        "- rule: apply these selected CLike capabilities to source, tests, docs, LTC, HOWTO, and gate evidence when relevant\n"
        "- rule: do not scan all `.clike` skills opportunistically; use only this selected context\n\n"
        f"{normalized}"
    ).strip()


def _snippet_text(item: dict) -> str:
    return str(item.get("snippet") or item.get("text") or "").strip()


def render_bmad_selected_skill_context(
    methodology_context: dict | None,
    active_output_contract: dict | None = None,
) -> str:
    _ = active_output_contract

    if not isinstance(methodology_context, dict):
        return ""
    if methodology_context.get("methodology") != "bmad":
        return ""

    references = [
        item
        for item in _as_list(methodology_context.get("selected_skill_references"))
        if isinstance(item, dict)
    ]
    selected_context = methodology_context.get("selected_skill_context") or {}
    if not isinstance(selected_context, dict):
        selected_context = {}
    snippets = [
        item
        for item in _as_list(selected_context.get("snippets"))
        if isinstance(item, dict)
    ]

    if not references and not snippets:
        return ""

    policy = methodology_context.get("skill_reference_policy") or {}
    if not isinstance(policy, dict):
        policy = {}

    source_root = (
        selected_context.get("source_root")
        or policy.get("workspace_vendor_reference_root")
        or ".clike/skills/vendor/bmad"
    )
    source_transport = selected_context.get("source_transport") or "core_blobs"

    lines = [
        "### BMAD Skill Reference Context",
        "- These are CLike-owned BMAD skill mappings already selected by methodology, phase, and agent.",
        f"- source_root: {source_root}",
        f"- source_transport: {source_transport}",
        "- Vendor BMAD skill files are reference material only.",
        "- BMAD runtime is not executed.",
        "- Canonical CLike artifacts remain authoritative.",
        "- Do not scan all `.clike` skills opportunistically; use only the selected references and snippets below.",
        "- selected_skill_ids:",
        *_render_bullets([item.get("id") for item in references], limit=12),
        "- normalized_mapping_paths:",
        *_render_bullets([item.get("path") for item in references], limit=12),
    ]

    if snippets:
        lines.append("- bounded_snippets:")
        for item in snippets[:8]:
            snippet = _snippet_text(item)
            lines.append(f"  - id: {item.get('id')}")
            path = item.get("path")
            if path:
                lines.append(f"    path: {path}")
            if snippet:
                lines.append("    snippet: |")
                lines.extend([f"      {line}" for line in snippet.splitlines()[:40]])
            if item.get("truncated"):
                lines.append("    truncated: true")

    return "\n".join(lines).strip()


def compose_cloud_selected_phase_skill_context(
    core_blobs: dict | None,
    methodology_context: dict | None,
    active_output_contract: dict | None = None,
) -> str:
    parts: list[str] = []

    clike_context = render_clike_selected_capability_context(core_blobs)
    if clike_context:
        parts.append(clike_context)

    bmad_context = render_bmad_selected_skill_context(
        methodology_context,
        active_output_contract=active_output_contract,
    )
    if bmad_context:
        parts.append(bmad_context)

    if not parts:
        return ""

    return (
        "## Cloud Selected Phase Skill Context\n\n"
        "The following context is already resolved by CLike for this exact cloud run.\n"
        "Inject only selected phase/REQ-scoped skills into the model prompt.\n"
        "Do not treat full core_blobs catalogs as selected skills.\n\n"
        + "\n\n".join(parts)
    ).strip()
