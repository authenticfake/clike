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

    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")

        if not key:
            continue

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
        "- Do not scan `.clike` randomly. Use this selected context, TARGET_CONTRACT.json, FILE_REQUIREMENTS.json, PLAN.md, and plan.json as primary guidance.",
        "- If a selected capability is missing, report a blocking capability-context gap instead of silently relaxing the obligation.",
        "- Capability guidance never overrides SPEC, TECH_CONSTRAINTS, repository evidence, or explicit user instructions.",
        "",
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
            "- Apply selected capabilities only where they affect the current REQ implementation, tests, docs, LTC, HOWTO, or gate evidence.",
            "- Do not add decorative architecture to make a capability appear used.",
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

def build_capability_context(repository_context: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Build capability core blobs for Harper phases.

    The result is intentionally plain dict[str, str] so it can be injected into
    existing core_blobs without changing request schemas.
    """
    repo_root = _repo_root_from_context(repository_context)
    if not repo_root:
        return {}

    index = {
        "schema_version": "clike.capability_index.v1",
        "repo_root": str(repo_root),
        "skills": _discover_skill_dirs(repo_root),
        "packs": _discover_pack_dirs(repo_root),
        "design_profiles": _discover_design_profiles(repo_root),
    }

    manifest = _build_manifest(index)

    return {
        "CLIKE_CAPABILITY_MANIFEST.md": manifest,
        "CLIKE_CAPABILITY_INDEX.json": json.dumps(index, ensure_ascii=False, indent=2),
    }