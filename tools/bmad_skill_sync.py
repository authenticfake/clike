#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


ALLOWED_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}
REQUIRED_SKILL_SECTIONS = [
    "## Intent",
    "## Required outputs",
    "## Companion outputs",
    "## Quality checks",
    "## Forbidden behavior",
    "## Governance boundaries",
]
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "cache",
    "build",
    "dist",
    "out",
    "output",
    "outputs",
    "coverage",
    ".venv",
    "venv",
}
MAX_FILE_BYTES = 512 * 1024


def _is_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@")


def _iter_candidate_files(source: Path) -> Iterable[Path]:
    for path in sorted(source.rglob("*")):
        relative_parts = path.relative_to(source).parts
        if any(part.startswith(".") for part in relative_parts[:-1]):
            continue
        if any(part in SKIP_DIRS for part in relative_parts):
            continue
        if path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        yield path


def _read_text_file(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES or b"\x00" in data:
        return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return data


def _build_manifest(source: Path, imported: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "vendor": "bmad",
        "purpose": "reference-only skill material seeded by the CLike VS Code extension",
        "source_path": str(source),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "imported_by_tool": "tools/bmad_skill_sync.py",
        "runtime_execution_enabled": False,
        "external_bmad_cli_enabled": False,
        "network_fetch_enabled": False,
        "activated_by": "methodology=bmad",
        "native_harper_active": False,
        "reviewed_status": "pending_manual_review",
        "imported_files": imported,
        "notes": [
            "This directory is seeded into new workspaces by the VS Code extension.",
            "Files in this directory are reference material only.",
            "CLike uses normalized BMAD skill mappings from the Orchestrator methodology profile.",
        ],
    }


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected object JSON: {path}")
    return data


def _all_manifest_skill_ids(manifest: Dict[str, Any]) -> List[str]:
    seen: List[str] = []
    selection = manifest.get("skill_selection") or {}
    if not isinstance(selection, dict):
        return seen
    for values in selection.values():
        if not isinstance(values, list):
            continue
        for item in values:
            skill_id = str(item or "").strip()
            if skill_id and skill_id not in seen:
                seen.append(skill_id)
    return seen


def _runtime_vendor_manifest(*, profile_manifest: Dict[str, Any], imported: List[Dict[str, Any]]) -> Dict[str, Any]:
    skill_ids = _all_manifest_skill_ids(profile_manifest)
    skill_map = {
        skill_id: {
            "path": f".clike/skills/vendor/bmad/{skill_id}/SKILL.md",
            "runtime_execution_enabled": False,
        }
        for skill_id in skill_ids
    }
    return {
        "vendor": "bmad",
        "methodology": "bmad",
        "name": profile_manifest.get("name", "BMAD"),
        "version": profile_manifest.get("version", "clike-vendor-skills"),
        "purpose": "reference-only CLike-owned BMAD methodology skill material seeded by the CLike VS Code extension",
        "workspace_vendor_reference_root": ".clike/skills/vendor/bmad",
        "runtime_execution_enabled": False,
        "external_bmad_cli_enabled": False,
        "network_fetch_enabled": False,
        "activated_by": "methodology=bmad",
        "native_harper_active": False,
        "reviewed_status": "clike_owned_normalized_mapping",
        "skill_reference_policy": {
            "enabled": True,
            "workspace_vendor_reference_root": ".clike/skills/vendor/bmad",
            "template_vendor_reference_root": "extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad",
            "activation": "methodology=bmad",
            "runtime_import_enabled": False,
            "external_skill_execution_enabled": False,
            "external_bmad_cli_enabled": False,
            "network_fetch_enabled": False,
            "official_bmad_runtime_content_vendored": False,
            "sync_mode": "manual_or_container_controlled",
            "review_required_before_activation": True,
            "cloud_context_enabled": True,
            "local_agent_context_enabled": True,
        },
        "supported_agents": list(profile_manifest.get("supported_agents") or []),
        "phase_mapping": profile_manifest.get("phase_mapping") or {},
        "skill_selection": profile_manifest.get("skill_selection") or {},
        "skills": skill_map,
        "governance_boundaries": [
            "CLike remains the governance runtime and source of truth.",
            "BMAD skills are methodology guidance only.",
            "BMAD runtime is not executed.",
            "External BMAD CLI calls are disabled.",
            "Network fetch is disabled.",
            "CLike contracts, EvalRunner, Gate, write roots, and active output contracts remain authoritative.",
        ],
        "imported_files": imported,
        "notes": [
            "This directory is seeded into new workspaces by the VS Code extension.",
            "Files in this directory are reference material only.",
            "Cloud transport uses request core_blobs.",
            "CLike selected capabilities and BMAD methodology skills are separate and composable.",
        ],
    }


def _validate_skill_text(path: Path, text: str) -> List[str]:
    missing = [section for section in REQUIRED_SKILL_SECTIONS if section not in text]
    return [f"{path}: missing {section}" for section in missing]


def sync_normalized_bmad_skills(
    *,
    normalized_source: Path,
    profile_manifest_path: Path,
    dest: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if not normalized_source.exists() or not normalized_source.is_dir():
        raise ValueError(f"invalid normalized skill source: {normalized_source}")
    profile_manifest = _load_json(profile_manifest_path)
    skill_ids = _all_manifest_skill_ids(profile_manifest)
    if not skill_ids:
        raise ValueError("profile manifest does not declare skill_selection")

    imported: List[Dict[str, Any]] = []
    errors: List[str] = []
    for skill_id in skill_ids:
        src = normalized_source / f"{skill_id}.md"
        if not src.exists() or not src.is_file():
            errors.append(f"missing normalized skill file: {src}")
            continue
        data = _read_text_file(src)
        if data is None:
            errors.append(f"invalid normalized skill file: {src}")
            continue
        text = data.decode("utf-8")
        errors.extend(_validate_skill_text(src, text))
        rel = f"{skill_id}/SKILL.md"
        imported.append(
            {
                "relative_path": rel,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if not dry_run:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")

    if errors:
        raise ValueError("; ".join(errors))

    manifest = _runtime_vendor_manifest(profile_manifest=profile_manifest, imported=imported)
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        readme = dest / "README.md"
        if not readme.exists():
            readme.write_text(
                "# BMAD Vendor Skill Seed\n\n"
                "This directory contains CLike-owned BMAD methodology skill guidance seeded into workspaces by the VS Code extension.\n"
                "It is reference material only. CLike does not execute BMAD runtime or call the BMAD CLI during Harper phases.\n",
                encoding="utf-8",
            )

    return {
        "source": normalized_source.as_posix(),
        "dest": dest.as_posix(),
        "dry_run": dry_run,
        "imported_count": len(imported),
        "skipped_count": 0,
        "manifest": manifest,
    }


def validate_vendor_tree(dest: Path) -> Dict[str, Any]:
    manifest_path = dest / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"missing vendor manifest: {manifest_path}")
    manifest = _load_json(manifest_path)
    errors: List[str] = []
    for key in ["runtime_execution_enabled", "external_bmad_cli_enabled", "network_fetch_enabled"]:
        if bool(manifest.get(key)):
            errors.append(f"{key} must be false")
    policy = manifest.get("skill_reference_policy") or {}
    if not isinstance(policy, dict):
        errors.append("skill_reference_policy must be an object")
        policy = {}
    for key in ["runtime_import_enabled", "external_skill_execution_enabled", "external_bmad_cli_enabled", "network_fetch_enabled"]:
        if bool(policy.get(key)):
            errors.append(f"skill_reference_policy.{key} must be false")
    skill_ids = _all_manifest_skill_ids(manifest)
    skills = manifest.get("skills") or {}
    if not isinstance(skills, dict):
        errors.append("skills must be an object")
        skills = {}
    for skill_id in skill_ids:
        item = skills.get(skill_id) if isinstance(skills.get(skill_id), dict) else {}
        rel = str(item.get("path") or f".clike/skills/vendor/bmad/{skill_id}/SKILL.md").strip()
        expected_suffix = f"{skill_id}/SKILL.md"
        skill_path = dest / expected_suffix
        if not rel.endswith(expected_suffix):
            errors.append(f"{skill_id}: manifest path must end with {expected_suffix}")
        if not skill_path.exists():
            errors.append(f"{skill_id}: missing {skill_path}")
            continue
        text = skill_path.read_text(encoding="utf-8")
        errors.extend(_validate_skill_text(skill_path, text))
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "dest": dest.as_posix(),
        "skill_count": len(skill_ids),
        "ok": True,
    }


def sync_bmad_skills(*, source: Path, dest: Path, dry_run: bool = False) -> Dict[str, Any]:
    if _is_url(str(source)):
        raise ValueError("source must be a local path, not a URL")
    if not source.exists() or not source.is_dir():
        raise ValueError(f"invalid source directory: {source}")

    imported: List[Dict[str, Any]] = []
    skipped = 0
    for src in _iter_candidate_files(source):
        data = _read_text_file(src)
        if data is None:
            skipped += 1
            continue
        rel = src.relative_to(source).as_posix()
        imported.append(
            {
                "relative_path": rel,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if not dry_run:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    manifest = _build_manifest(source, imported)
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        readme = dest / "README.md"
        if not readme.exists():
            readme.write_text(
                "# BMAD Skill Reference Seed\n\n"
                "This directory contains reference-only BMAD skill material imported by controlled CLike tooling.\n"
                "It is seeded into new workspaces by the VS Code extension and is not executable authority.\n"
                "CLike uses normalized Orchestrator BMAD mappings when methodology=bmad is selected.\n",
                encoding="utf-8",
            )

    return {
        "source": source.as_posix(),
        "dest": dest.as_posix(),
        "dry_run": dry_run,
        "imported_count": len(imported),
        "skipped_count": skipped,
        "manifest": manifest,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync local BMAD reference skill material into a CLike vendor seed directory.")
    parser.add_argument("--source", required=True, help="Local BMAD reference workspace or extracted skill directory.")
    parser.add_argument("--dest", required=True, help="Destination vendor directory, for example extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and summarize without writing destination files.")
    parser.add_argument("--normalized", action="store_true", help="Treat --source as CLike normalized BMAD skill mapping root and generate vendor SKILL.md layout.")
    parser.add_argument("--manifest", default="orchestrator/methodologies/bmad/manifest.json", help="BMAD profile manifest used with --normalized.")
    parser.add_argument("--check-only", action="store_true", help="Validate the destination vendor tree without writing files.")
    args = parser.parse_args(argv)

    try:
        dest = Path(args.dest).expanduser().resolve()
        if args.check_only:
            summary = validate_vendor_tree(dest)
        elif args.normalized:
            summary = sync_normalized_bmad_skills(
                normalized_source=Path(args.source).expanduser().resolve(),
                profile_manifest_path=Path(args.manifest).expanduser().resolve(),
                dest=dest,
                dry_run=bool(args.dry_run),
            )
        else:
            summary = sync_bmad_skills(
                source=Path(args.source).expanduser().resolve(),
                dest=dest,
                dry_run=bool(args.dry_run),
            )
    except Exception as exc:
        print(f"bmad_skill_sync: error: {exc}", file=sys.stderr)
        return 2

    if args.check_only:
        print(
            "bmad_skill_sync: "
            f"dest={summary['dest']} skill_count={summary['skill_count']} check_only=true"
        )
    else:
        print(
            "bmad_skill_sync: "
            f"source={summary['source']} dest={summary['dest']} "
            f"imported={summary['imported_count']} skipped={summary['skipped_count']} "
            f"dry_run={summary['dry_run']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
