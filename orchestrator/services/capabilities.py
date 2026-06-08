from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


MAX_DOC_CHARS = 60_000
MAX_ITEM_PREVIEW_CHARS = 8_000


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _repo_root_from_context(repository_context: Optional[Dict[str, Any]]) -> Optional[Path]:
    repo_ctx = dict(repository_context or {})
    raw = (
        _safe_str(repo_ctx.get("repo_root"))
        or _safe_str(repo_ctx.get("workspace_folder"))
        or _safe_str(repo_ctx.get("root"))
    )
    if not raw:
        return None

    root = Path(raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return None

    return root


def _read_text(path: Path, max_chars: int = MAX_ITEM_PREVIEW_CHARS) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars].rstrip() + "\n...[truncated]"


def _extract_frontmatter(text: str) -> Dict[str, Any]:
    """
    Minimal YAML-frontmatter reader.

    This intentionally supports only simple key/value and inline list forms.
    It avoids introducing a new dependency and keeps capability discovery safe.
    """
    raw = str(text or "")
    if not raw.startswith("---"):
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---\s*", raw, flags=re.DOTALL)
    if not match:
        return {}

    frontmatter = match.group(1)
    out: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()

        # Block (multi-line) YAML list item, e.g. under `recommended_skills:`.
        # Items may contain commas; do not split them.
        if current_list_key and line.startswith("- "):
            item = line[2:].strip().strip("'\"")
            if item and isinstance(out.get(current_list_key), list):
                out[current_list_key].append(item)
            continue

        if not line or line.startswith("#") or ":" not in line:
            current_list_key = None
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")

        if not key:
            current_list_key = None
            continue

        if value == "":
            # Possibly a block list header; collect following `- item` lines.
            out[key] = []
            current_list_key = key
            continue

        current_list_key = None
        if value.startswith("[") and value.endswith("]"):
            items = [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
            out[key] = items
        else:
            out[key] = value

    return out


def _discover_skill_dirs(repo_root: Path) -> List[Dict[str, Any]]:
    base = repo_root / ".clike" / "skills"
    if not base.exists() or not base.is_dir():
        return []

    items: List[Dict[str, Any]] = []

    for skill_md in sorted(base.glob("*/SKILL.md")):
        rel = skill_md.relative_to(repo_root).as_posix()
        text = _read_text(skill_md)
        meta = _extract_frontmatter(text)

        name = _safe_str(meta.get("name")) or skill_md.parent.name
        description = _safe_str(meta.get("description"))

        items.append(
            {
                "kind": "skill",
                "name": name,
                "description": description,
                "path": rel,
                "metadata": meta,
                "preview": text,
            }
        )

    return items


def _discover_pack_dirs(repo_root: Path) -> List[Dict[str, Any]]:
    base = repo_root / ".clike" / "packs"
    if not base.exists() or not base.is_dir():
        return []

    items: List[Dict[str, Any]] = []

    for pack_dir in sorted([p for p in base.iterdir() if p.is_dir()]):
        pack_file = pack_dir / "PACK.md"
        if not pack_file.exists():
            pack_file = pack_dir / "README.md"

        text = _read_text(pack_file) if pack_file.exists() else ""
        meta = _extract_frontmatter(text)

        docs = []
        for doc in sorted(pack_dir.glob("*.md")):
            rel = doc.relative_to(repo_root).as_posix()
            docs.append(rel)

        name = _safe_str(meta.get("name")) or pack_dir.name
        description = _safe_str(meta.get("description"))

        items.append(
            {
                "kind": "pack",
                "name": name,
                "description": description,
                "path": pack_file.relative_to(repo_root).as_posix() if pack_file.exists() else pack_dir.relative_to(repo_root).as_posix(),
                "docs": docs,
                "metadata": meta,
                "preview": text,
            }
        )

    return items


def _discover_design_profiles(repo_root: Path) -> List[Dict[str, Any]]:
    roots = [
        repo_root / ".clike" / "design-profiles",
        repo_root / "docs" / "harper" / "design-profiles",
        repo_root / "docs" / "harper" / "design",
    ]

    items: List[Dict[str, Any]] = []

    for base in roots:
        if not base.exists() or not base.is_dir():
            continue

        candidates = list(base.glob("*/DESIGN.md"))
        if (base / "DESIGN.md").exists():
            candidates.append(base / "DESIGN.md")

        for design_md in sorted(set(candidates)):
            rel = design_md.relative_to(repo_root).as_posix()
            text = _read_text(design_md)
            meta = _extract_frontmatter(text)

            name = _safe_str(meta.get("name")) or design_md.parent.name
            if design_md.parent == base:
                name = _safe_str(meta.get("name")) or "default-design"

            description = _safe_str(meta.get("description"))

            items.append(
                {
                    "kind": "design_profile",
                    "name": name,
                    "description": description,
                    "path": rel,
                    "metadata": meta,
                    "preview": text,
                }
            )

    return items


def _path_parent_name(rel_path: str, marker: str, default: str = "") -> str:
    parts = [part for part in str(rel_path or "").replace("\\", "/").split("/") if part]
    try:
        idx = parts.index(marker)
    except ValueError:
        return default
    if idx + 1 < len(parts):
        return parts[idx + 1]
    return default


def _capability_blob_items(core_blobs: Optional[Dict[str, Any]], *, kind: str) -> List[Dict[str, Any]]:
    blobs = dict(core_blobs or {})
    items: List[Dict[str, Any]] = []

    for raw_path, raw_content in sorted(blobs.items(), key=lambda item: str(item[0])):
        rel = str(raw_path or "").replace("\\", "/").lstrip("/")
        lower = rel.lower()
        text = str(raw_content or "")
        if not text.strip():
            continue

        if kind == "skill":
            if not lower.startswith(".clike/skills/") or not lower.endswith("/skill.md"):
                continue
            if lower.startswith(".clike/skills/vendor/bmad/"):
                continue
            fallback = _path_parent_name(rel, "skills")
            meta = _extract_frontmatter(text)
            items.append(
                {
                    "kind": "skill",
                    "name": _safe_str(meta.get("name")) or fallback,
                    "description": _safe_str(meta.get("description")),
                    "path": rel,
                    "metadata": meta,
                    "preview": text[:MAX_ITEM_PREVIEW_CHARS],
                }
            )

        elif kind == "pack":
            if not lower.startswith(".clike/packs/") or not (
                lower.endswith("/pack.md") or lower.endswith("/readme.md")
            ):
                continue
            fallback = _path_parent_name(rel, "packs")
            meta = _extract_frontmatter(text)
            items.append(
                {
                    "kind": "pack",
                    "name": _safe_str(meta.get("name")) or fallback,
                    "description": _safe_str(meta.get("description")),
                    "path": rel,
                    "docs": [rel],
                    "metadata": meta,
                    "preview": text[:MAX_ITEM_PREVIEW_CHARS],
                }
            )

        elif kind == "design_profile":
            if not lower.startswith(".clike/design-profiles/") or not lower.endswith("/design.md"):
                continue
            fallback = _path_parent_name(rel, "design-profiles")
            meta = _extract_frontmatter(text)
            items.append(
                {
                    "kind": "design_profile",
                    "name": _safe_str(meta.get("name")) or fallback,
                    "description": _safe_str(meta.get("description")),
                    "path": rel,
                    "metadata": meta,
                    "preview": text[:MAX_ITEM_PREVIEW_CHARS],
                }
            )

    return items


def build_capability_context_from_core_blobs(core_blobs: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Build capability manifest/index from project-visible `.clike` core blobs."""
    index = {
        "schema_version": "clike.capability_index.v1",
        "repo_root": "core_blobs",
        "source_transport": "core_blobs",
        "skills": _capability_blob_items(core_blobs, kind="skill"),
        "packs": _capability_blob_items(core_blobs, kind="pack"),
        "design_profiles": _capability_blob_items(core_blobs, kind="design_profile"),
    }
    if not (index["skills"] or index["packs"] or index["design_profiles"]):
        return {}

    return {
        "CLIKE_CAPABILITY_MANIFEST.md": _build_manifest(index),
        "CLIKE_CAPABILITY_INDEX.json": json.dumps(index, ensure_ascii=False, indent=2),
    }


def _build_manifest(index: Dict[str, Any]) -> str:
    skills = list(index.get("skills") or [])
    packs = list(index.get("packs") or [])
    design_profiles = list(index.get("design_profiles") or [])

    lines: List[str] = [
        "# CLike Capability Manifest",
        "",
        "This manifest is generated by the CLike orchestrator from local project capability files.",
        "",
        "## Purpose",
        "- Capabilities are planning and generation constraints.",
        "- Capabilities are not model-provider-specific.",
        "- Capabilities are not agent-specific.",
        "- Capabilities must not override SPEC, TECH_CONSTRAINTS, repository evidence, or explicit user instructions.",
        "- Capabilities are hints for PLAN/KIT/EVAL/GATE and must remain verifiable.",
        "",
        "## Capability Contract",
        "- Skills must be atomic operational capabilities.",
        "- Packs must be scenario bundles that select constraints and recommended capabilities.",
        "- Design profiles must apply only to UI/UX requirements and must not clone external brands.",
        "- Every capability must define when it applies, when it does not apply, required behavior, forbidden behavior, evidence, repair guidance, and gate implications when relevant.",
        "- A capability is valid only if PLAN can select it, KIT can act on it, EVAL can check evidence, and GATE can enforce the result.",
        "",
        "## Required Skill Sections",
        "- Intent",
        "- Use when",
        "- Do not use when",
        "- Signals",
        "- Required behavior",
        "- Forbidden behavior",
        "- Evidence required",
        "- Repair guidance",
        "- Gate implications",
        "- Examples",
        "- Non-examples",
        "",
        "## Required Pack Sections",
        "- Intent",
        "- Scenario signals",
        "- Use when",
        "- Do not use when",
        "- Required capabilities",
        "- Runtime assumptions",
        "- Security/compliance assumptions",
        "- Architecture constraints",
        "- Eval expectations",
        "- Gate implications",
        "",
        "## Required Design Profile Sections",
        "- Intent",
        "- Use when",
        "- Do not use when",
        "- Visual principles",
        "- UX principles",
        "- Components/patterns",
        "- Accessibility expectations",
        "- Evidence required",
        "- Gate implications",
        "",
        "## Discovery Summary",
    ]
    if skills:
        lines.extend(["## Skills", ""])
        for item in skills:
            lines.append(f"### Skill: {item.get('name')}")
            lines.append(f"- Path: `{item.get('path')}`")
            if item.get("description"):
                lines.append(f"- Description: {item.get('description')}")
            meta = item.get("metadata") or {}
            for key in ("phases", "lanes", "domains", "runtime_profiles", "gate_required"):
                if key in meta:
                    lines.append(f"- {key}: `{meta.get(key)}`")
            lines.append("")
    else:
        lines.extend([
            "## Skills",
            "",
            "- No local `.clike/skills/*/SKILL.md` files discovered.",
            "- If PLAN selects a skill, the selected skill should exist in the local capability index or be explicitly marked as unavailable. KIT must not silently relax missing selected skill obligations.",
            "",
        ])

    if packs:
        lines.extend(["## Packs", ""])
        for item in packs:
            lines.append(f"### Pack: {item.get('name')}")
            lines.append(f"- Path: `{item.get('path')}`")
            if item.get("description"):
                lines.append(f"- Description: {item.get('description')}")
            docs = list(item.get("docs") or [])
            if docs:
                lines.append("- Docs:")
                lines.extend([f"  - `{doc}`" for doc in docs])
            meta = item.get("metadata") or {}
            for key in ("domains", "default_runtime_profiles", "recommended_skills", "gate_required"):
                if key in meta:
                    lines.append(f"- {key}: `{meta.get(key)}`")
            lines.append("")
    else:
        lines.extend([
            "## Packs",
            "",
            "- No local `.clike/packs/*` files discovered.",
            "- If PLAN selects a pack, the selected pack should exist in the local capability index or be explicitly marked as unavailable. KIT must not silently relax missing selected pack obligations.",
            "",
        ])

    if design_profiles:
        lines.extend(["## Design Profiles", ""])
        for item in design_profiles:
            lines.append(f"### Design Profile: {item.get('name')}")
            lines.append(f"- Path: `{item.get('path')}`")
            if item.get("description"):
                lines.append(f"- Description: {item.get('description')}")
            meta = item.get("metadata") or {}
            for key in ("domains", "lanes", "inspired_by", "strictness"):
                if key in meta:
                    lines.append(f"- {key}: `{meta.get(key)}`")
            lines.append("")
    else:
        lines.extend([
            "## Design Profiles",
            "",
            "- No local `.clike/design-profiles/*/DESIGN.md` files discovered.",
            "- No local `docs/harper/design*/DESIGN.md` files discovered.",
            "- If PLAN selects a design profile, the selected design profile should exist in the local capability index or be explicitly marked as unavailable. KIT must not silently relax missing selected design obligations.",
            "",
        ])

    lines.extend([
        "## Capability Selection Rules",
        "- PLAN may select skills, packs, and design profiles per REQ, but selected capabilities become binding constraints for KIT/EVAL/GATE.",
        "- KIT must treat selected capabilities as mandatory REQ constraints when they are selected by PLAN. If a selected capability is missing from the manifest/index, KIT must report a blocking capability-context gap instead of relaxing the obligation.",
        "- EVAL/GATE may later verify skill_adherence, pack_adherence, design_adherence, runtime_profile_adherence, and domain_safety.",
        "- Do not invent unavailable tools or claim unavailable integrations.",
        "- Do not clone protected brands or imply affiliation with external design systems.",
        "- Use design profiles as inspiration/constraints, not as brand replication.",
    ])

    manifest = "\n".join(lines).strip() + "\n"
    if len(manifest) <= MAX_DOC_CHARS:
        return manifest

    return manifest[:MAX_DOC_CHARS].rstrip() + "\n\n...[capability manifest truncated]\n"



def _as_list(value: Any) -> List[str]:
    """Return a normalized list of non-empty strings without changing names."""
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]

    out: List[str] = []
    for item in raw_items:
        text = _safe_str(item)
        if text and text not in out:
            out.append(text)
    return out


def _lookup_selected_items(index: Dict[str, Any], kind: str, selected_names: List[str]) -> Dict[str, Any]:
    """Resolve selected capability names against the generated capability index."""
    items = index.get(kind) or []
    if not isinstance(items, list):
        items = []

    by_name = {
        _safe_str(item.get("name")).lower(): item
        for item in items
        if isinstance(item, dict) and _safe_str(item.get("name"))
    }

    resolved: List[Dict[str, Any]] = []
    missing: List[str] = []

    for name in selected_names:
        item = by_name.get(name.lower())
        if item is None:
            missing.append(name)
        else:
            resolved.append(item)

    return {
        "selected": selected_names,
        "resolved": resolved,
        "missing": missing,
    }


def _render_selected_capability_context(*, req_id: str, selected: Dict[str, Any]) -> str:
    """Render selected capability guidance for KIT/cloud and local agents."""
    lines: List[str] = [
        "# CLike Selected Capability Context",
        "",
        f"Target REQ: `{req_id}`",
        "",
        "## Contract",
        "- This file is generated by the CLike orchestrator for the current REQ only.",
        "- Selected skills, packs, and design profiles are binding KIT constraints when present.",
        "- Treat selected capability guidance as operational implementation, test, LTC, HOWTO, and gate-evidence requirements for this REQ.",
        "- Do not scan `.clike` randomly. Use this selected context, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, PLAN.md, and plan.json as primary guidance.",
        "- If a selected capability is missing, report a blocking capability-context gap instead of silently relaxing the obligation.",
        "- Capability guidance never overrides SPEC, TECH_CONSTRAINTS, repository evidence, or explicit user instructions.",
        "- Prefer official or widely adopted SDKs inside adapter/infrastructure boundaries when a selected capability or REQ scope names concrete providers.",
        "- Do not reimplement provider protocols, auth/signing, wire formats, or client behavior when mature SDKs exist unless SPEC explicitly requires it.",        "",
    ]

    for key, title in (
        ("packs", "Pack"),
        ("skills", "Skill"),
        ("design_profiles", "Design Profile"),
    ):
        group = selected.get(key) or {}
        resolved = group.get("resolved") or []
        missing = group.get("missing") or []

        lines.extend([f"## Selected {title}s", ""])

        if missing:
            lines.append("### Missing selected capabilities")
            for name in missing:
                lines.append(f"- `{name}`")
            lines.append("")

        if not resolved:
            lines.append("- None selected or none resolved.")
            lines.append("")
            continue

        for item in resolved:
            if not isinstance(item, dict):
                continue

            name = _safe_str(item.get("name"))
            path = _safe_str(item.get("path"))
            description = _safe_str(item.get("description"))
            preview = _safe_str(item.get("preview"))
            metadata = item.get("metadata") or {}

            lines.append(f"### {title}: {name}")
            if path:
                lines.append(f"- Path: `{path}`")
            if description:
                lines.append(f"- Description: {description}")
            if isinstance(metadata, dict) and metadata:
                lines.append(f"- Metadata: `{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}`")
            if preview:
                lines.extend(["", "```markdown", preview, "```"])
            lines.append("")

    lines.extend(
        [
            "## KIT Usage Rules",
            "- Apply selected capabilities where they affect the current REQ implementation, tests, docs, LTC, HOWTO, or gate evidence.",
            "- Selected capabilities are not decorative: each applicable selected skill/pack must either be implemented, tested, or explicitly marked not applicable with a short reason.",
            "- Do not add decorative architecture to make a capability appear used.",
            "- Use official or widely adopted SDKs inside adapter/infrastructure boundaries when the selected capability or REQ scope names concrete providers.",
            "- Keep business-facing contracts provider-independent unless SPEC explicitly requires provider-specific contracts.",
            "- Document capability evidence in `runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md`.",
            "- Encode capability checks or evidence paths in `runs/kit/<REQ-ID>/ci/LTC.json` where practical.",
            "- Mark external/infrastructure checks as environment-blocked/non-blocking only when the LTC explains the missing prerequisite and provides a deterministic local smoke fallback.",        
        ]
    )

    return "\n".join(lines).strip() + "\n"


def build_selected_capability_context(
    *,
    core_blobs: Dict[str, Any],
    target_req_id: str,
    target_contract: Dict[str, Any],
) -> Dict[str, str]:
    """
    Build REQ-scoped selected capability blobs for cloud KIT and local agents.

    The full manifest/index tells PLAN what exists. The selected context tells KIT
    what is binding for the current REQ without forcing the model or agent to scan
    every `.clike` file opportunistically.
    """
    raw_index = _safe_str(core_blobs.get("CLIKE_CAPABILITY_INDEX.json"))
    if not raw_index:
        return {}

    try:
        index = json.loads(raw_index)
    except Exception:
        return {
            "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": (
                "# CLike Selected Capability Context\n\n"
                f"Target REQ: `{target_req_id}`\n\n"
                "Capability index is unavailable or invalid. KIT must report this as a capability-context gap when selected capabilities exist.\n"
            )
        }

    selected = {
        "schema_version": "clike.selected_capability_context.v1",
        "req_id": target_req_id,
        "packs": _lookup_selected_items(index, "packs", _as_list(target_contract.get("packs"))),
        "skills": _lookup_selected_items(index, "skills", _as_list(target_contract.get("skills"))),
        "design_profiles": _lookup_selected_items(index, "design_profiles", _as_list(target_contract.get("design_profiles"))),
        "selection_policy": {
            "source": "plan.json/TARGET_CONTRACT.json",
            "binding_for_kit": True,
            "missing_selected_capability_is_blocking_gap": True,
            "do_not_randomly_scan_dot_clike": True,
        },
    }

    return {
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.md": _render_selected_capability_context(
            req_id=target_req_id,
            selected=selected,
        ),
        "CLIKE_SELECTED_CAPABILITY_CONTEXT.json": json.dumps(selected, ensure_ascii=False, indent=2),
    }

def build_capability_context(
    repository_context: Optional[Dict[str, Any]],
    core_blobs: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Build capability core blobs for Harper phases.

    The result is intentionally plain dict[str, str] so it can be injected into
    existing core_blobs without changing request schemas.
    """
    repo_root = _repo_root_from_context(repository_context)
    if not repo_root:
        return build_capability_context_from_core_blobs(core_blobs)

    index = {
        "schema_version": "clike.capability_index.v1",
        "repo_root": str(repo_root),
        "skills": _discover_skill_dirs(repo_root),
        "packs": _discover_pack_dirs(repo_root),
        "design_profiles": _discover_design_profiles(repo_root),
    }

    manifest = _build_manifest(index)

    discovered = {
        "CLIKE_CAPABILITY_MANIFEST.md": manifest,
        "CLIKE_CAPABILITY_INDEX.json": json.dumps(index, ensure_ascii=False, indent=2),
    }
    if index["skills"] or index["packs"] or index["design_profiles"]:
        return discovered
    return build_capability_context_from_core_blobs(core_blobs) or discovered


# ---------------------------------------------------------------------------
# Deterministic plan.json capability enrichment
#
# PLAN selects WHICH capabilities apply per REQ (the legacy `packs`/`skills`/
# `design_profiles` name lists). This enrichment expands those names into a
# structured, machine-readable `capabilities` block using the operational
# frontmatter (obligations / eval_checks / gate_implications / evidence) carried
# by each capability file in the capability index. It is conservative and
# idempotent, preserves legacy fields, and is shared by the cloud and
# local-agent /plan completion paths so both produce the same shape.
# ---------------------------------------------------------------------------

PLAN_CAPABILITY_SCHEMA_VERSION = "1.1.0"

# Per-kind frontmatter fields that become structured obligations in plan.json.
_CAPABILITY_METADATA_FIELDS = {
    "skills": ("obligations", "eval_checks", "gate_implications", "evidence_required"),
    "packs": (
        "obligations",
        "implementation_directives",
        "eval_checks",
        "gate_implications",
        "evidence_required",
    ),
    "design_profiles": (
        "ui_obligations",
        "accessibility_expectations",
        "eval_checks",
        "gate_implications",
        "evidence_required",
    ),
}


def build_capability_metadata_map(capability_index: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """name(lower) -> operational metadata, per kind, from the capability index."""
    index = capability_index if isinstance(capability_index, dict) else {}
    result: Dict[str, Any] = {"skills": {}, "packs": {}, "design_profiles": {}}
    for kind in result:
        for item in index.get(kind) or []:
            if not isinstance(item, dict):
                continue
            name = _safe_str(item.get("name"))
            if not name:
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            entry: Dict[str, Any] = {"id": name, "kind": kind[:-1] if kind.endswith("s") else kind}
            for field in _CAPABILITY_METADATA_FIELDS[kind]:
                values = _as_list(meta.get(field))
                if values:
                    entry[field] = values
            result[kind][name.lower()] = entry
    return result


def _capability_names_from_req_field(value: Any) -> List[str]:
    """Normalize a legacy plan.json capability field to a list of real names."""
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "not_applicable":
            return []
        return [text]
    return _as_list(value)


def _req_field_is_not_applicable(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() == "not_applicable"


def enrich_plan_capabilities(
    plan_obj: Dict[str, Any], capability_metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add a structured per-REQ `capabilities` block derived from the REQ's selected
    capability names + capability metadata. Preserves legacy fields, sets
    schema_version, is idempotent, and never invents capabilities absent from the
    metadata map (unknown names are still recorded so context is not dropped).
    """
    if not isinstance(plan_obj, dict):
        return plan_obj
    reqs = plan_obj.get("reqs") or plan_obj.get("requirements") or plan_obj.get("items")
    if not isinstance(reqs, list):
        return plan_obj

    metadata = capability_metadata if isinstance(capability_metadata, dict) else {}
    plan_obj.setdefault("schema_version", PLAN_CAPABILITY_SCHEMA_VERSION)

    for req in reqs:
        if not isinstance(req, dict):
            continue
        # Idempotent: do not overwrite a structured block already present.
        existing = req.get("capabilities")
        if isinstance(existing, dict) and any(existing.get(k) for k in ("packs", "skills", "design_profiles")):
            continue

        block: Dict[str, List[Dict[str, Any]]] = {"packs": [], "skills": [], "design_profiles": []}
        exclusions: List[Dict[str, Any]] = list(req.get("capability_exclusions") or [])

        for kind in ("packs", "skills", "design_profiles"):
            names = _capability_names_from_req_field(req.get(kind))
            kind_meta = metadata.get(kind) or {}
            for name in names:
                entry: Dict[str, Any] = {
                    "id": name,
                    "source": "plan",
                    "reason": f"selected in plan.json {kind} for this REQ",
                }
                known = kind_meta.get(name.lower())
                if isinstance(known, dict):
                    for field, value in known.items():
                        if field in ("id", "kind"):
                            continue
                        entry[field] = value
                else:
                    entry["unresolved"] = True
                block[kind].append(entry)

            if not names and _req_field_is_not_applicable(req.get(kind)):
                exclusions.append(
                    {"kind": kind, "reason": "marked not_applicable in plan.json for this REQ"}
                )

        req["capabilities"] = block
        if exclusions:
            req["capability_exclusions"] = exclusions

    return plan_obj


def build_capability_coverage(
    plan_obj: Dict[str, Any], capability_metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Read-only diagnostic: which capabilities cover which REQs, the expected
    eval_checks/gate_implications they imply, REQs with no capability coverage,
    and capability ids selected but missing from the index. Consumable by the
    existing eval/gate reporting; does not block or mutate anything.
    """
    result = {
        "selected": {"packs": [], "skills": [], "design_profiles": []},
        "expected_eval_checks": [],
        "expected_gate_implications": [],
        "reqs_without_capabilities": [],
        "unresolved_capability_ids": [],
        "per_req": [],
    }
    if not isinstance(plan_obj, dict):
        return result
    reqs = plan_obj.get("reqs") or plan_obj.get("requirements") or plan_obj.get("items")
    if not isinstance(reqs, list):
        return result
    metadata = capability_metadata if isinstance(capability_metadata, dict) else {}

    sel = {k: set() for k in ("packs", "skills", "design_profiles")}
    eval_checks: List[str] = []
    gate_impls: List[str] = []
    unresolved: List[str] = []

    def _add_unique(dst: List[str], values: Any) -> None:
        for v in _as_list(values):
            if v not in dst:
                dst.append(v)

    for req in reqs:
        if not isinstance(req, dict):
            continue
        rid = _safe_str(req.get("id"))
        caps = req.get("capabilities") if isinstance(req.get("capabilities"), dict) else {}
        covered = False
        req_view = {"id": rid, "packs": [], "skills": [], "design_profiles": []}
        for kind in ("packs", "skills", "design_profiles"):
            for entry in caps.get(kind) or []:
                if not isinstance(entry, dict):
                    continue
                cid = _safe_str(entry.get("id"))
                if not cid:
                    continue
                covered = True
                sel[kind].add(cid)
                req_view[kind].append(cid)
                if entry.get("unresolved") or not (metadata.get(kind) or {}).get(cid.lower()):
                    if cid not in unresolved:
                        unresolved.append(cid)
                _add_unique(eval_checks, entry.get("eval_checks"))
                _add_unique(gate_impls, entry.get("gate_implications"))
        if not covered and not req.get("capability_exclusions"):
            result["reqs_without_capabilities"].append(rid)
        result["per_req"].append(req_view)

    for kind in sel:
        result["selected"][kind] = sorted(sel[kind])
    result["expected_eval_checks"] = eval_checks
    result["expected_gate_implications"] = gate_impls
    result["unresolved_capability_ids"] = unresolved
    return result


def enrich_plan_json_text(
    plan_json_text: str, capability_metadata: Optional[Dict[str, Any]]
) -> str:
    """Defensive text wrapper: enrich plan.json content, return original on error."""
    try:
        plan_obj = json.loads(plan_json_text)
    except Exception:
        return plan_json_text
    if not isinstance(plan_obj, dict):
        return plan_json_text
    enriched = enrich_plan_capabilities(plan_obj, capability_metadata)
    try:
        return json.dumps(enriched, ensure_ascii=False, indent=2)
    except Exception:
        return plan_json_text


# ---------------------------------------------------------------------------
# Capability-file structure validation (used by tests + coverage diagnostics)
# ---------------------------------------------------------------------------

# Applicability sections every capability must declare in prose. Behavioral and
# gate obligations are enforced via the operational frontmatter below (the
# machine-readable contract) so files can express domain behavior under their own
# headings without being forced into generic, duplicated boilerplate sections.
_REQUIRED_SECTIONS = {
    "skill": ["## Intent", "## Use when", "## Do not use when"],
    "pack": ["## Intent", "## Use when", "## Do not use when"],
    "design_profile": ["## Intent", "## Use when", "## Do not use when", "## Accessibility"],
}

# Machine-readable operational contract required per kind (drives plan.json
# enrichment + eval/gate consumption). This is the real "behavior/gate" contract.
_OPERATIONAL_FRONTMATTER = {
    "skill": ["obligations", "eval_checks", "gate_implications"],
    "pack": ["obligations", "eval_checks", "gate_implications"],
    "design_profile": [
        "ui_obligations",
        "accessibility_expectations",
        "eval_checks",
        "gate_implications",
    ],
}

# Generic filler that must NOT appear in a capability file: a demanding reviewer
# expects domain-specific operational content, not boilerplate pointing back at
# the frontmatter. Presence of any of these marks the file as low-quality.
_GENERIC_BOILERPLATE_MARKERS = [
    "Apply this capability's obligations (see frontmatter",
    "Do not claim this capability is satisfied without the evidence listed in",
    "Gate must block promotion when the conditions in this capability's",
    "Meet the accessibility expectations declared in frontmatter",
    "See this capability's obligations and gate implications above.",
]


def validate_capability_markdown(text: str, kind: str) -> Dict[str, Any]:
    """
    Strict structural validation for a capability file. Returns
    {ok, has_frontmatter, missing_sections, missing_operational_frontmatter,
     generic_boilerplate}. Deterministic; no LLM.

    A file is `ok` only when it declares the applicability sections, carries the
    full operational frontmatter for its kind, and contains no generic boilerplate.
    """
    raw = str(text or "")
    lower = raw.lower()
    meta = _extract_frontmatter(raw)

    required = _REQUIRED_SECTIONS.get(kind, [])
    missing_sections = [s for s in required if s.lower() not in lower]

    operational = _OPERATIONAL_FRONTMATTER.get(kind, [])
    missing_operational = [f for f in operational if not _as_list(meta.get(f))]

    generic_boilerplate = [m for m in _GENERIC_BOILERPLATE_MARKERS if m in raw]

    return {
        "kind": kind,
        "has_frontmatter": bool(meta),
        "missing_sections": missing_sections,
        "missing_operational_frontmatter": missing_operational,
        "generic_boilerplate": generic_boilerplate,
        "ok": not missing_sections and not missing_operational and not generic_boilerplate,
    }
