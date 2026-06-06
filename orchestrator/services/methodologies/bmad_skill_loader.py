from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import BmadSelectedSkillsMissingError


MAX_SNIPPET_CHARS_PER_SKILL = 1400
MAX_TOTAL_SNIPPET_CHARS = 5000
BMAD_VENDOR_ROOT = ".clike/skills/vendor/bmad"
BMAD_VENDOR_MANIFEST_PATH = f"{BMAD_VENDOR_ROOT}/manifest.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _orchestrator_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_manifest() -> Dict[str, Any]:
    path = _orchestrator_root() / "methodologies" / "bmad" / "manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_template_vendor_manifest() -> Dict[str, Any]:
    path = _repo_root() / "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad/manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _selected_skill_ids_from_manifest(
    selection: Dict[str, Any],
    *,
    phase_name: str,
    agent_name: str,
) -> List[str]:
    flat = selection.get(f"{phase_name}/{agent_name}")
    nested = selection.get(phase_name)
    if flat is None and isinstance(nested, dict):
        flat = nested.get(agent_name)
    if flat is None:
        return []
    return [
        str(item).strip()
        for item in (flat if isinstance(flat, list) else [])
        if str(item or "").strip()
    ]


def _normalize_blob_path(path: str) -> str:
    return str(path or "").strip().replace("\\", "/").lstrip("/")


def _core_blob_lookup(core_blobs: Optional[Dict[str, Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for key, value in (core_blobs or {}).items():
        normalized = _normalize_blob_path(str(key or ""))
        if normalized:
            lookup[normalized] = str(value or "")
    return lookup


def load_bmad_vendor_manifest_from_core_blobs(core_blobs: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    lookup = _core_blob_lookup(core_blobs)
    raw = lookup.get(BMAD_VENDOR_MANIFEST_PATH)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise BmadSelectedSkillsMissingError(
            "BMAD_SELECTED_SKILLS_MISSING: invalid vendor manifest in core_blobs"
        ) from exc
    return parsed if isinstance(parsed, dict) else None


def _skill_path_for_id(manifest: Dict[str, Any], skill_id: str) -> str:
    skills = manifest.get("skills")
    if isinstance(skills, dict):
        item = skills.get(skill_id)
        if isinstance(item, str) and item.strip():
            return _normalize_blob_path(item)
        if isinstance(item, dict):
            path = item.get("path") or item.get("source_path") or item.get("mapping_path")
            if path:
                return _normalize_blob_path(str(path))
    return f"{BMAD_VENDOR_ROOT}/{skill_id}/SKILL.md"


def _selected_skill_texts_from_core_blobs(
    *,
    manifest: Dict[str, Any],
    core_blobs: Optional[Dict[str, Any]],
    selected_ids: List[str],
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    lookup = _core_blob_lookup(core_blobs)
    available_skill_ids: List[str] = []
    selected_files: List[Dict[str, Any]] = []
    missing: List[str] = []

    for key in sorted(lookup):
        if not key.startswith(f"{BMAD_VENDOR_ROOT}/") or not key.endswith("/SKILL.md"):
            continue
        parts = key.split("/")
        if len(parts) >= 6:
            skill_id = parts[-2]
            if skill_id not in available_skill_ids:
                available_skill_ids.append(skill_id)

    for skill_id in selected_ids:
        path = _skill_path_for_id(manifest, skill_id)
        text = lookup.get(path)
        if text is None:
            missing.append(skill_id)
            continue
        selected_files.append({"id": skill_id, "path": path, "text": text})

    return selected_files, missing, available_skill_ids


def _selected_skill_texts_from_template(
    *,
    manifest: Dict[str, Any],
    selected_ids: List[str],
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    root = _repo_root() / "extensions/vscode/templates/harper-init"
    selected_files: List[Dict[str, Any]] = []
    missing: List[str] = []
    available: List[str] = []
    vendor_root = root / BMAD_VENDOR_ROOT
    if vendor_root.exists():
        for path in sorted(vendor_root.glob("*/SKILL.md")):
            available.append(path.parent.name)
    for skill_id in selected_ids:
        rel = _skill_path_for_id(manifest, skill_id)
        path = root / rel
        if not path.exists():
            missing.append(skill_id)
            continue
        selected_files.append({"id": skill_id, "path": rel, "text": path.read_text(encoding="utf-8")})
    return selected_files, missing, available


def _raise_missing_selected_skills(
    *,
    methodology: Optional[str],
    phase_name: str,
    agent_name: str,
    selected_ids: List[str],
    missing_skill_ids: List[str],
    available_skill_ids: List[str],
) -> None:
    raise BmadSelectedSkillsMissingError(
        "BMAD_SELECTED_SKILLS_MISSING: "
        f"methodology={_normalize(methodology)} phase={phase_name} agent={agent_name} "
        f"manifest_has_selection={bool(selected_ids)} vendor_root={BMAD_VENDOR_ROOT} "
        f"missing_skill_ids={missing_skill_ids} available_skill_ids={available_skill_ids} "
        "source_transport=core_blobs"
    )


def _empty_selection(policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "selected_skill_ids": [],
        "selected_skill_references": [],
        "selected_skill_context": {
            "snippets": [],
            "required_outputs": [],
            "companion_outputs": [],
            "quality_checks": [],
            "forbidden_behavior": [],
            "governance_boundaries": [],
            "source_transport": None,
            "source_root": None,
        },
        "skill_reference_policy": policy or {},
    }


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"(?ims)^##\s+{re.escape(heading)}\s*$")
    match = pattern.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"(?m)^##\s+", rest)
    return (rest[: next_heading.start()] if next_heading else rest).strip()


def _section_lines(text: str, heading: str, *, limit: int = 8) -> List[str]:
    section = _extract_section(text, heading)
    values: List[str] = []
    for line in section.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        if cleaned and cleaned not in values:
            values.append(cleaned)
        if len(values) >= limit:
            break
    return values


def _bounded_snippet(text: str, max_chars: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n\n...[truncated]"


def _load_vendor_inventory(workspace_root: Optional[str | Path], policy: Dict[str, Any]) -> Dict[str, Any]:
    if not workspace_root:
        return {}
    root = Path(workspace_root).expanduser().resolve()
    vendor_root = root / str(policy.get("workspace_vendor_reference_root") or ".clike/skills/vendor/bmad")
    manifest_path = vendor_root / "manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return {
            "present": False,
            "workspace_vendor_reference_root": str(policy.get("workspace_vendor_reference_root") or ".clike/skills/vendor/bmad"),
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "present": True,
            "workspace_vendor_reference_root": str(policy.get("workspace_vendor_reference_root") or ".clike/skills/vendor/bmad"),
            "manifest_valid": False,
        }
    imported = manifest.get("imported_files") if isinstance(manifest.get("imported_files"), list) else []
    return {
        "present": True,
        "manifest_valid": True,
        "workspace_vendor_reference_root": str(policy.get("workspace_vendor_reference_root") or ".clike/skills/vendor/bmad"),
        "vendor": manifest.get("vendor"),
        "reviewed_status": manifest.get("reviewed_status"),
        "runtime_execution_enabled": bool(manifest.get("runtime_execution_enabled", False)),
        "external_bmad_cli_enabled": bool(manifest.get("external_bmad_cli_enabled", False)),
        "network_fetch_enabled": bool(manifest.get("network_fetch_enabled", False)),
        "imported_file_count": len(imported),
        "imported_files_sample": [
            {
                "relative_path": item.get("relative_path"),
                "bytes": item.get("bytes"),
                "sha256": str(item.get("sha256") or "")[:16],
            }
            for item in imported[:12]
            if isinstance(item, dict)
        ],
    }


def select_bmad_skill_context(
    *,
    methodology: Optional[str],
    phase: Optional[str],
    agent: Optional[str],
    req_id: Optional[str] = None,
    workspace_root: Optional[str | Path] = None,
    core_blobs: Optional[Dict[str, Any]] = None,
    require_core_blobs: bool = False,
    max_snippet_chars_per_skill: int = MAX_SNIPPET_CHARS_PER_SKILL,
    max_total_snippet_chars: int = MAX_TOTAL_SNIPPET_CHARS,
) -> Dict[str, Any]:
    if _normalize(methodology) != "bmad":
        return _empty_selection()

    manifest = load_bmad_vendor_manifest_from_core_blobs(core_blobs)
    source_transport = "core_blobs" if manifest is not None else "template"
    if manifest is None:
        if require_core_blobs:
            fallback_manifest = _load_manifest()
            phase_name = _normalize(phase)
            agent_name = _normalize(agent)
            selected_ids = _selected_skill_ids_from_manifest(
                fallback_manifest.get("skill_selection") if isinstance(fallback_manifest.get("skill_selection"), dict) else {},
                phase_name=phase_name,
                agent_name=agent_name,
            )
            if selected_ids:
                _raise_missing_selected_skills(
                    methodology=methodology,
                    phase_name=phase_name,
                    agent_name=agent_name,
                    selected_ids=selected_ids,
                    missing_skill_ids=selected_ids,
                    available_skill_ids=[],
                )
        manifest = _load_template_vendor_manifest()
    policy = dict(manifest.get("skill_reference_policy") or {})
    if not policy.get("enabled"):
        return _empty_selection(policy)

    phase_name = _normalize(phase)
    agent_name = _normalize(agent)
    selection = manifest.get("skill_selection") or {}
    selected_ids = _selected_skill_ids_from_manifest(
        selection if isinstance(selection, dict) else {},
        phase_name=phase_name,
        agent_name=agent_name,
    )
    if not selected_ids:
        return _empty_selection(policy)

    if source_transport == "core_blobs":
        selected_files, missing_skill_ids, available_skill_ids = _selected_skill_texts_from_core_blobs(
            manifest=manifest,
            core_blobs=core_blobs,
            selected_ids=selected_ids,
        )
    else:
        selected_files, missing_skill_ids, available_skill_ids = _selected_skill_texts_from_template(
            manifest=manifest,
            selected_ids=selected_ids,
        )
        if require_core_blobs:
            missing_skill_ids = selected_ids

    if missing_skill_ids or len(selected_files) != len(selected_ids):
        _raise_missing_selected_skills(
            methodology=methodology,
            phase_name=phase_name,
            agent_name=agent_name,
            selected_ids=selected_ids,
            missing_skill_ids=missing_skill_ids or [
                skill_id for skill_id in selected_ids if skill_id not in {item["id"] for item in selected_files}
            ],
            available_skill_ids=available_skill_ids,
        )

    references: List[Dict[str, Any]] = []
    snippets: List[Dict[str, Any]] = []
    required_outputs: List[str] = []
    companion_outputs: List[str] = []
    quality_checks: List[str] = []
    forbidden_behavior: List[str] = []
    governance_boundaries: List[str] = []
    total_chars = 0

    def add_unique(target: List[str], values: List[str]) -> None:
        for value in values:
            rendered = value.replace("<REQ-ID>", str(req_id or "<REQ-ID>"))
            if rendered not in target:
                target.append(rendered)

    for item in selected_files:
        skill_id = str(item["id"])
        relative_path = _normalize_blob_path(str(item["path"]))
        text = str(item["text"] or "")
        remaining = max(0, max_total_snippet_chars - total_chars)
        snippet = _bounded_snippet(text, min(max_snippet_chars_per_skill, remaining))
        total_chars += len(snippet)
        references.append(
            {
                "id": skill_id,
                "path": relative_path,
                "bytes": len(text.encode("utf-8")),
                "source_transport": source_transport,
                "source_root": BMAD_VENDOR_ROOT,
            }
        )
        snippets.append(
            {
                "id": skill_id,
                "path": relative_path,
                "snippet": snippet,
                "truncated": len(snippet) < len(text.strip()),
            }
        )
        add_unique(required_outputs, _section_lines(text, "Required outputs"))
        add_unique(companion_outputs, _section_lines(text, "Companion outputs", limit=16))
        add_unique(quality_checks, _section_lines(text, "Quality checks"))
        add_unique(forbidden_behavior, _section_lines(text, "Forbidden behavior"))
        add_unique(governance_boundaries, _section_lines(text, "Governance boundaries"))

    context = {
        "snippets": snippets,
        "required_outputs": required_outputs[:24],
        "companion_outputs": companion_outputs[:24],
        "quality_checks": quality_checks[:24],
        "forbidden_behavior": forbidden_behavior[:24],
        "governance_boundaries": governance_boundaries[:12],
        "source_transport": source_transport,
        "source_root": BMAD_VENDOR_ROOT,
        "mapping_paths": [item["path"] for item in references],
    }
    vendor_inventory = _load_vendor_inventory(workspace_root, policy)
    if vendor_inventory:
        context["vendor_inventory_summary"] = vendor_inventory

    return {
        "selected_skill_ids": [item["id"] for item in references],
        "selected_skill_references": references,
        "selected_skill_context": context,
        "skill_reference_policy": policy,
    }
