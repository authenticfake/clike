from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


MAX_DOC_CHARS = 18_000
MAX_ITEM_PREVIEW_CHARS = 1_200


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
            "- PLAN may still emit candidate skill names when grounded in SPEC, TECH_CONSTRAINTS, or explicit user intent.",
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
            "- PLAN may still emit candidate pack names when grounded in SPEC, TECH_CONSTRAINTS, or explicit user intent.",
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
            "- PLAN should assign design profiles only for UI/UX requirements when grounded by available project context or explicit user intent.",
            "",
        ])

    lines.extend([
        "## Capability Selection Rules",
        "- PLAN may select skills, packs, and design profiles as candidate hints per REQ.",
        "- KIT must treat selected capabilities as constraints only when they are available, grounded, and relevant.",
        "- EVAL/GATE may later verify skill_adherence, pack_adherence, design_adherence, runtime_profile_adherence, and domain_safety.",
        "- Do not invent unavailable tools or claim unavailable integrations.",
        "- Do not clone protected brands or imply affiliation with external design systems.",
        "- Use design profiles as inspiration/constraints, not as brand replication.",
    ])

    manifest = "\n".join(lines).strip() + "\n"
    if len(manifest) <= MAX_DOC_CHARS:
        return manifest

    return manifest[:MAX_DOC_CHARS].rstrip() + "\n\n...[capability manifest truncated]\n"


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