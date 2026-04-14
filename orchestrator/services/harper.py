# Phase services (SPEC/PLAN/KIT) orchestrating prompts, evals and runs.
# Iterations: each call may update documents and re-run gates.
# Branching (future): for KIT change-requests, create feature branches per request.
# Phase services (SPEC/PLAN/KIT/BUILD) orchestrating routing and gateway calls.
from __future__ import annotations

from typing import Dict, Any, Optional, List
import json
import os
import logging
import time
import re
from datetime import datetime
from pathlib import Path

import httpx

from config import settings
from services.utils import GATEWAY_URL
from services.llm_contracts import resolve_llm_selection
from services.repository_manifest import (
    build_req_promotion_manifest,
    build_repo_access_manifest,
    build_repo_structure_evidence,
    build_repo_composition_manifest,
)
log = logging.getLogger("service.router")

_KIT_PHASE_SEQUENCE: List[str] = [
    "kit",
    "integrity_eval",
    "promotion_hardener",
    "promotion_eval",
]


async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base_url = str(GATEWAY_URL or "").rstrip("/")
    rel_path = "/" + str(path or "").lstrip("/")
    url = f"{base_url}{rel_path}"

    start_time = time.time()

    log.info(
        "POST %s phase=%s core=%d atts=%d",
        url,
        payload.get("phase"),
        len(payload.get("core") or []),
        len(payload.get("attachments") or []),
    )
    TIMEOUT = float(os.environ.get("TIMEOUT", 980.0))
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=payload)
        elapsed_time = time.time() - start_time
        log.info("POST phase=%s elapsed=%.3fs", payload.get("phase"), elapsed_time)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_text = ""
            try:
                body_text = r.text
            except Exception:
                body_text = "<unavailable>"

            log.error(
                "Gateway error status=%s url=%s body=%s",
                r.status_code,
                url,
                body_text[:2000],
            )

            detail = body_text[:2000] if body_text else str(exc)
            raise RuntimeError(f"Gateway upstream error {r.status_code}: {detail}") from None

        return r.json()  
async def _normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    # --- Normalizzazione messages ---
    raw_msgs = msg.get("messages") or []
    norm_msgs = []
    for m in raw_msgs:
        if m is None:
            continue
        # Supporta: Pydantic model, oggetto con .dict(), o già dict
        if hasattr(m, "model_dump"):
            d = m.model_dump()
        elif hasattr(m, "dict"):
            d = m.dict()
        elif isinstance(m, dict):
            d = m
        else:
            # ignora elementi non conformi
            continue

        role = d.get("role")
        content = d.get("content")
        if isinstance(role, str) and isinstance(content, str):
            norm_msgs.append({"role": role, "content": content})

    if norm_msgs:
        msg["messages"] = norm_msgs
    else:
        # se vuoto rimuovi per lasciare al gateway la composizione di default
        msg.pop("messages", None)
    return dict(msg)


def _normalize_requested_kit_phases(kit_options: Dict[str, Any]) -> List[str]:
    raw = list((kit_options or {}).get("phases") or [])
    if not raw:
        return ["kit"]

    normalized: List[str] = []
    seen = set()

    for item in raw:
        phase_name = str(item or "").strip().lower()
        if not phase_name:
            continue
        if phase_name not in _KIT_PHASE_SEQUENCE:
            raise ValueError(
                f"Unsupported /kit phase '{phase_name}'. Allowed: {', '.join(_KIT_PHASE_SEQUENCE)}"
            )
        if phase_name not in seen:
            normalized.append(phase_name)
            seen.add(phase_name)

    if not normalized:
        return ["kit"]

    # Always execute in canonical order, regardless of input order.
    ordered = [p for p in _KIT_PHASE_SEQUENCE if p in seen]
    return ordered or ["kit"]


def _load_existing_req_candidate_artifacts(req_id: str) -> List[Dict[str, Any]]:
    existing = _collect_existing_req_candidate_files(req_id)
    artifacts: List[Dict[str, Any]] = []

    for path in sorted(existing.keys()):
        artifacts.append(
            {
                "path": path,
                "content": existing[path],
                "encoding": "utf-8",
            }
        )

    return artifacts

def _collect_existing_req_candidate_files(req_id: str) -> Dict[str, str]:
    runs_dir = os.getenv("RUNS_DIR", "/runs")
    runs: Path = Path(runs_dir).resolve()
    base = runs / "kit" / req_id
    log.info("collecting files from %s,  exists=%s, is_dir=%s", base, base.exists(), base.is_dir())
    if not base.exists() or not base.is_dir():
        return {}
    
    out: Dict[str, str] = {}
    for sub in ("src", "test", "docs", "ci"):
        root = base / sub
        if not root.exists() or not root.is_dir():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.as_posix()
            try:
                out[rel] = path.read_text(encoding="utf-8")
            except Exception:
                # Skip unreadable files; normalization should remain best-effort on text artifacts.
                continue

    return out

def _detect_req_path_mismatch(
    req_id: str,
    files: List[Dict[str, Any]],
) -> List[str]:
    expected_prefix = f"runs/kit/{req_id}/"
    blockers: List[str] = []

    for item in files or []:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if not path.startswith(expected_prefix):
            blockers.append(
                f"REQ {req_id} received out-of-target file path: {path}"
            )

    return blockers

def _collect_candidate_file_artifacts_from_output(out: Dict[str, Any], req_id: str) -> List[Dict[str, Any]]:
    files = out.get("files") or []
    target_prefix = f"runs/kit/{req_id}/"
    collected: List[Dict[str, Any]] = []

    for item in files:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if not path.startswith(target_prefix):
            continue
        collected.append(dict(item))

    return collected

def _filter_req_stage_files(files: List[Dict[str, Any]], req_id: str) -> List[Dict[str, Any]]:
    target_prefix = f"runs/kit/{req_id}/"
    out: List[Dict[str, Any]] = []

    for item in files or []:
        path = str(item.get("path") or "").strip()
        if not path.startswith(target_prefix):
            continue
        out.append(dict(item))

    return out


def _load_plan_json_from_core_blobs(core_blobs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not core_blobs:
        return None

    for name, content in core_blobs.items():
        key = str(name or "").strip().lower()
        if not key.endswith("plan.json"):
            continue
        try:
            data = json.loads(str(content or ""))
        except Exception as exc:
            log.warning("failed to parse plan.json from core_blobs[%s]: %s", name, exc)
            return None
        if isinstance(data, dict):
            return data
        return None

    return None

def _slugify_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "req_slice"


def _infer_contract_paths(contract_like: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort path inference when plan.json does not provide explicit structured paths.

    Priority:
    1. explicit plan paths
    2. create_under / must_reuse
    3. architecture-aware fallback for known families
    4. otherwise let the model decide later
    """
    paths = dict(contract_like.get("paths") or {})
    canonical_family = str(paths.get("canonical_module_family") or "").strip()
    expected_source_roots = list(paths.get("expected_source_roots") or [])
    expected_test_roots = list(paths.get("expected_test_roots") or [])
    create_under = list(paths.get("create_under") or [])
    must_reuse = list(paths.get("must_reuse") or [])

    title = str(contract_like.get("title") or "").strip()
    primary_outcome = str(contract_like.get("primary_outcome") or "").strip()
    lane = str(contract_like.get("lane") or "").strip().lower()
    track = str(contract_like.get("track") or "").strip().lower()
    acceptance_blob = " ".join(str(x) for x in (contract_like.get("acceptance") or []))
    blob = f"{title} {primary_outcome} {acceptance_blob}".lower()

    # 1) Explicit path hints from create_under / must_reuse
    if not canonical_family:
        for candidate in create_under + must_reuse:
            c = str(candidate or "").strip()
            if c.startswith("src/"):
                canonical_family = c
                break

    if not expected_source_roots:
        expected_source_roots = [str(x).strip() for x in create_under if str(x).strip().startswith("src/")]

    if not expected_test_roots:
        expected_test_roots = [str(x).strip() for x in create_under if str(x).strip().startswith(("test/", "tests/"))]

    # 2) Architecture-aware fallback only when the plan strongly implies the family.
    if not canonical_family:
        if any(k in blob for k in ["adapter", "profile", "provider", "parity", "runtime mode", "runtime profile"]):
            canonical_family = "src/shared/adapters"
        elif lane == "sql" or any(k in blob for k in ["schema", "migration", "backbone", "lifecycle", "postgres", "table"]):
            canonical_family = "src/data/schema"
        elif lane == "node" or track == "frontend":
            canonical_family = f"src/frontend/features/{_slugify_text(title)}"

    if not expected_source_roots and canonical_family:
        if canonical_family == "src/shared/adapters":
            expected_source_roots = ["src/shared/adapters"]
        elif canonical_family == "src/data/schema":
            expected_source_roots = ["src/data/schema", "src/data/migrations"]
        else:
            expected_source_roots = [canonical_family]

    if not expected_test_roots and canonical_family:
        if canonical_family == "src/shared/adapters":
            expected_test_roots = ["test/shared/adapters"]
        elif canonical_family == "src/data/schema":
            expected_test_roots = ["test/data/schema"]
        elif canonical_family.startswith("src/frontend/"):
            expected_test_roots = ["test/frontend"]
        elif canonical_family.startswith("src/"):
            expected_test_roots = ["test/" + canonical_family[len("src/"):].strip("/")]

    return {
        "create_under": create_under,
        "must_reuse": must_reuse,
        "forbidden": list(paths.get("forbidden") or []),
        "canonical_module_family": canonical_family,
        "expected_source_roots": expected_source_roots,
        "expected_test_roots": expected_test_roots,
        "new_modules_allowed": bool(paths.get("new_modules_allowed") or paths.get("newModulesAllowed") or False),
    }

def _extract_target_contract(
    core_blobs: Dict[str, Any],
    req_id: str,
) -> Optional[Dict[str, Any]]:
    plan_data = _load_plan_json_from_core_blobs(core_blobs)
    if not plan_data:
        return None

    reqs = plan_data.get("reqs") or []
    target = None
    for item in reqs:
        if str(item.get("id") or "").strip() == req_id:
            target = item
            break

    if not target:
        return None

    raw_paths = dict(target.get("paths") or {})
    mandatory_tests = dict(target.get("mandatoryTests") or {})
    kit_minimum = dict(target.get("kitMinimumDeliverable") or {})

    contract = {
        "version": "1.0.0",
        "req_id": req_id,
        "title": str(target.get("title") or "").strip(),
        "lane": str(target.get("lane") or "").strip(),
        "track": str(target.get("track") or "").strip(),
        "primary_outcome": str(target.get("primaryOutcome") or "").strip(),
        "acceptance": list(target.get("acceptance") or []),
        "in_scope": list(target.get("inScope") or []),
        "out_of_scope": list(target.get("outOfScope") or []),
        "depends_on": list(target.get("dependsOn") or []),
        "dependency_type": list(target.get("dependencyType") or []),
        "paths": {
            "create_under": list(raw_paths.get("createUnder") or raw_paths.get("create_under") or []),
            "must_reuse": list(raw_paths.get("mustReuse") or raw_paths.get("must_reuse") or []),
            "forbidden": list(raw_paths.get("forbidden") or []),
            "canonical_module_family": str(raw_paths.get("canonicalModuleFamily") or raw_paths.get("canonical_module_family") or "").strip(),
            "expected_source_roots": list(raw_paths.get("expectedSourceRoots") or raw_paths.get("expected_source_roots") or []),
            "expected_test_roots": list(raw_paths.get("expectedTestRoots") or raw_paths.get("expected_test_roots") or []),
            "new_modules_allowed": bool(raw_paths.get("newModulesAllowed", raw_paths.get("new_modules_allowed", False))),
        },
        "mandatory_tests": {
            "unit": list(mandatory_tests.get("unit") or []),
            "integration": list(mandatory_tests.get("integration") or []),
            "e2e": list(mandatory_tests.get("e2e") or []),
        },
        "gate_policy_ref": str(target.get("gate_policy_ref") or "").strip(),
        "test_profile": str(target.get("test_profile") or "").strip(),
        "kit_minimum_deliverable": {
            "source_files_min": int(kit_minimum.get("sourceFilesMin") or 0),
            "integration_tests_min": int(kit_minimum.get("integrationTestsMin") or 0),
            "api_docs_required": bool(kit_minimum.get("apiDocsRequired", False)),
        },
        "auth_rules": list(target.get("authRules") or []),
        "audit_requirements": list(target.get("auditRequirements") or []),
        "downstream_guarantees": list(target.get("downstreamGuarantees") or []),
        "state_transitions": list(target.get("stateTransitions") or []),
        "data_contracts": list(target.get("dataContracts") or []),
        "api_contracts": list(target.get("apiContracts") or []),
        "event_contracts": list(target.get("eventContracts") or []),
    }
    contract["paths"] = _infer_contract_paths(contract)
    return contract


def _load_lane_guide_policy(contract: Dict[str, Any], core_blobs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort loader for dynamic lane-guide policy generated at /plan time.

    The lane guide is a policy enhancer, not the primary contract.
    It should enrich architecture, quality, testing posture, and anti-pattern rules.
    """
    lane = str(contract.get("lane") or "").strip().lower()
    track = str(contract.get("track") or "").strip().lower()
    canonical_family = str((contract.get("paths") or {}).get("canonical_module_family") or "").strip().lower()

    candidates: List[tuple[int, str, str]] = []

    for name, content in (core_blobs or {}).items():
        key = str(name or "").strip()
        lkey = key.lower()
        if "lane" not in lkey or "guide" not in lkey:
            continue

        score = 0
        if lane and lane in lkey:
            score += 5
        if track and track in lkey:
            score += 3
        if canonical_family and canonical_family.split("/")[-1] in lkey:
            score += 2
        if "plan" in lkey:
            score += 1

        candidates.append((score, key, str(content or "")))

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_name = candidates[0][1] if candidates else None
    best_content = candidates[0][2] if candidates else ""

    policy: Dict[str, Any] = {
        "source": best_name,
        "raw_text": best_content or "",
        "artifact_roles_expected": [],
        "artifact_roles_forbidden": [],
        "test_posture": [],
        "quality_posture": [],
        "anti_patterns": [],
        "composition_rules": [],
    }

    text = str(best_content or "")
    if not text.strip():
        return policy

    lowered = text.lower()

    def _contains_any(*phrases: str) -> bool:
        return any(p.lower() in lowered for p in phrases)

    # anti-patterns
    if _contains_any("no standalone app", "no per-req app", "no per req app", "do not create app bootstrap"):
        policy["anti_patterns"].append("per_req_app_bootstrap")
    if _contains_any("no duplicate settings", "avoid duplicate settings", "do not create settings wrappers"):
        policy["anti_patterns"].append("duplicate_settings_wrapper")
    if _contains_any("no duplicate logging", "avoid logging wrappers", "do not wrap logging"):
        policy["anti_patterns"].append("duplicate_logging_wrapper")
    if _contains_any("thin source", "no thin source"):
        policy["anti_patterns"].append("thin_source")

    # composition rules
    if _contains_any("shared/common", "shared common", "cross-slice reuse", "shared module"):
        policy["composition_rules"].append("respect_shared_common_rules")
    if _contains_any("composition root", "reuse existing composition", "do not create parallel module family"):
        policy["composition_rules"].append("respect_composition_root")

    # expected artifact roles
    if _contains_any("dto", "typed boundary", "boundary contract", "request/response contract"):
        policy["artifact_roles_expected"].append("boundary_contract")
    if _contains_any("route", "handler", "api surface", "rest api", "endpoint binding"):
        policy["artifact_roles_expected"].append("entry_binding")
    if _contains_any("workflow", "notification", "event", "consumer", "idempotency"):
        policy["artifact_roles_expected"].append("workflow_component")
    if _contains_any("provider adapter", "runtime adapter", "profile parity", "deployment parity", "adapter contract"):
        policy["artifact_roles_expected"].append("adapter_contract")

    # testing posture
    if _contains_any("integration test", "integration smoke", "ephemeral postgres", "real seam"):
        policy["test_posture"].append("integration_expected")
    if _contains_any("negative path", "rejection path", "guardrail", "invalid transition"):
        policy["test_posture"].append("negative_paths_expected")
    if _contains_any("easy local execution", "developer runnable", "copy-paste commands"):
        policy["test_posture"].append("local_execution_expected")

    # quality posture
    if _contains_any("architecture", "composition", "ownership", "namespace", "repo-aware"):
        policy["quality_posture"].append("architecture_explicit")
    if _contains_any("promotion", "promotable", "pull request", "production-ready"):
        policy["quality_posture"].append("promotion_oriented")

    return policy


def _resolve_requirement_family(contract: Dict[str, Any], lane_policy: Dict[str, Any]) -> str:
    """
    Resolve the REQ architectural family.

    This is intentionally architecture-driven, not language-driven.
    Lane remains only a fallback signal.
    """
    paths = dict(contract.get("paths") or {})
    canonical_family = str(paths.get("canonical_module_family") or "").strip().lower()
    source_roots = [str(x).strip().lower() for x in (paths.get("expected_source_roots") or [])]
    acceptance_blob = " ".join(str(x).lower() for x in (contract.get("acceptance") or []))
    api_contracts = list(contract.get("api_contracts") or [])
    event_contracts = list(contract.get("event_contracts") or [])
    track = str(contract.get("track") or "").strip().lower()
    lane = str(contract.get("lane") or "").strip().lower()

    if canonical_family.startswith("src/data/") or any(r.startswith("src/data/") for r in source_roots):
        return "schema_backbone"

    if canonical_family.startswith("src/frontend/") or any(r.startswith("src/frontend/") for r in source_roots):
        return "ui_feature"

    if canonical_family.startswith("src/infra/") or any(r.startswith("src/infra/") for r in source_roots):
        return "runtime_profile_slice"

    if event_contracts or "workflow_component" in (lane_policy.get("artifact_roles_expected") or []):
        if any(k in acceptance_blob for k in ["task", "workflow", "notification", "event", "queue", "consumer"]):
            return "workflow_slice"

    if api_contracts:
        return "application_slice"

    if any(k in acceptance_blob for k in ["adapter", "provider", "profile", "parity", "observability", "secret"]):
        return "runtime_profile_slice"

    if track == "data":
        return "schema_backbone"
    if track == "infra":
        return "runtime_profile_slice"
    if lane == "js-ts":
        return "ui_feature"
    if lane == "sql":
        return "schema_backbone"

    return "application_slice"


def _derive_artifact_roles(
    contract: Dict[str, Any],
    family: str,
    lane_policy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    acceptance = list(contract.get("acceptance") or [])
    mandatory_tests = dict(contract.get("mandatory_tests") or {})
    api_docs_required = bool(dict(contract.get("kit_minimum_deliverable") or {}).get("api_docs_required", False))
    expected_roles = set(lane_policy.get("artifact_roles_expected") or [])
    test_posture = set(lane_policy.get("test_posture") or [])
    anti_patterns = set(lane_policy.get("anti_patterns") or [])

    roles: List[Dict[str, Any]] = []

    if family == "schema_backbone":
        roles.extend([
            {
                "role": "primary_contract_or_schema",
                "required": True,
                "purpose": "Define canonical schema contracts, lifecycle states, and invariants.",
                "must_cover": acceptance,
                "must_contain": [
                    "explicit lifecycle states or schema contracts",
                    "invariants or transition guards",
                ],
                "must_not_contain": [
                    "http handlers",
                    "standalone app bootstrap",
                ],
            },
            {
                "role": "mapping_or_models",
                "required": True,
                "purpose": "Define metadata or ORM mapping for canonical entities.",
                "must_cover": acceptance,
                "must_contain": [
                    "entity mapping or metadata definitions",
                    "keys and constraints",
                ],
                "must_not_contain": [
                    "api route logic",
                ],
            },
            {
                "role": "migration",
                "required": True,
                "purpose": "Define schema migration for the REQ scope.",
                "must_cover": acceptance,
                "must_contain": [
                    "object creation",
                    "constraints",
                    "indexes where required",
                ],
                "must_not_contain": [
                    "runtime service code",
                ],
            },
        ])

    elif family in {"application_slice", "workflow_slice"}:
        roles.extend([
            {
                "role": "primary_implementation",
                "required": True,
                "purpose": "Implement the REQ business or orchestration slice inside the canonical family.",
                "must_cover": acceptance,
                "must_contain": [
                    "real implementation logic",
                    "explicit ownership boundary",
                    "repo-fit composition",
                ],
                "must_not_contain": sorted(set([
                    "toy_only_architecture",
                    *anti_patterns,
                ])),
            },
            {
                "role": "boundary_contract",
                "required": ("boundary_contract" in expected_roles or bool(contract.get("api_contracts") or [])),
                "purpose": "Define boundary contracts, DTOs, or typed request/response models when the REQ crosses boundaries.",
                "must_cover": acceptance,
                "must_contain": [
                    "typed contracts when needed",
                ],
                "must_not_contain": [
                    "placeholder contract files without usage",
                ],
            },
            {
                "role": "entry_binding",
                "required": api_docs_required or ("entry_binding" in expected_roles),
                "purpose": "Expose handler, route, or binding only if the REQ defines an application-facing seam.",
                "must_cover": acceptance,
                "must_contain": [
                    "binding or handler wiring when required",
                ],
                "must_not_contain": [
                    "per_req_app_bootstrap",
                ],
            },
        ])

        if family == "workflow_slice" or ("workflow_component" in expected_roles):
            roles.append({
                "role": "workflow_component",
                "required": True,
                "purpose": "Implement consumer, notifier, task transition, or idempotent workflow component when required.",
                "must_cover": acceptance,
                "must_contain": [
                    "workflow or event behavior when required",
                ],
                "must_not_contain": [
                    "stateless placeholder component",
                ],
            })

    elif family == "ui_feature":
        roles.extend([
            {
                "role": "primary_ui_feature",
                "required": True,
                "purpose": "Implement the primary UI feature slice in the canonical frontend family.",
                "must_cover": acceptance,
                "must_contain": [
                    "feature logic",
                    "repo-fit component or state wiring",
                ],
                "must_not_contain": [
                    "backend service code",
                    "parallel routing tree",
                ],
            },
        ])

    elif family == "runtime_profile_slice":
        roles.extend([
            {
                "role": "adapter_contract",
                "required": True,
                "purpose": "Define runtime/profile adapter contracts and validation rules.",
                "must_cover": acceptance,
                "must_contain": [
                    "adapter or profile contract",
                    "parity or validation rules",
                ],
                "must_not_contain": [
                    "business-logic forks by provider",
                ],
            },
        ])

    else:
        roles.extend([
            {
                "role": "primary_implementation",
                "required": True,
                "purpose": "Implement the REQ slice with real substance.",
                "must_cover": acceptance,
                "must_contain": [
                    "real implementation substance",
                ],
                "must_not_contain": [
                    "adjacent REQ scope",
                ],
            },
        ])

    # test roles
    roles.append({
        "role": "acceptance_tests",
        "required": True,
        "purpose": "Validate the emitted REQ slice behavior.",
        "must_cover": list(mandatory_tests.get("unit") or []) + list(mandatory_tests.get("integration") or []),
        "must_contain": [
            "real assertions",
            "negative path coverage when relevant" if "negative_paths_expected" in test_posture else "behavior assertions",
        ],
        "must_not_contain": [
            "empty tests",
            "assertion-light tests",
        ],
    })

    if "integration_expected" in test_posture:
        roles.append({
            "role": "integration_smoke",
            "required": True,
            "purpose": "Validate integration through a realistic seam.",
            "must_cover": list(mandatory_tests.get("integration") or []),
            "must_contain": [
                "integration smoke or realistic seam assertions",
            ],
            "must_not_contain": [
                "fake integration tags without meaningful assertions",
            ],
        })

    # always-on operational artifacts
    roles.extend([
        {
            "role": "operational_readme",
            "required": True,
            "purpose": "Explain what was emitted, prerequisites, commands, and assumptions.",
            "must_cover": [
                "what was emitted",
                "prerequisites",
                "how to run tests",
                "assumptions and gaps",
            ],
            "must_contain": [
                "scope",
                "emitted files summary",
                "commands",
                "assumptions",
            ],
            "must_not_contain": [
                "claims unsupported by emitted files",
            ],
        },
        {
            "role": "kit_notes",
            "required": True,
            "purpose": "Explain the REQ slice shape and bounded gaps truthfully.",
            "must_cover": [
                "target req summary",
                "repo-fit notes",
                "promotion-oriented notes",
            ],
            "must_contain": [
                "implementation rationale",
                "architectural notes",
            ],
            "must_not_contain": [
                "fictional architecture",
            ],
        },
        {
            "role": "execution_contract",
            "required": True,
            "purpose": "Define executable checks and commands for this REQ candidate.",
            "must_cover": [
                "real commands",
                "real reports or expected outputs",
            ],
            "must_contain": [
                "lane",
                "commands",
                "reports",
                "gate_policy",
            ],
            "must_not_contain": [
                "generic commands unrelated to emitted files",
            ],
        },
        {
            "role": "execution_howto",
            "required": True,
            "purpose": "Provide copy-paste operational steps for local execution.",
            "must_cover": [
                "prerequisites",
                "commands",
                "expected outputs",
            ],
            "must_contain": [
                "copy-paste commands",
            ],
            "must_not_contain": [
                "commands impossible to run from the emitted candidate",
            ],
        },
    ])

    return roles

def _materialize_file_requirements(
    contract: Dict[str, Any],
    family: str,
    artifact_roles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    req_id = str(contract.get("req_id") or "").strip()
    lane = str(contract.get("lane") or "").strip().lower()
    paths = dict(contract.get("paths") or {})
    canonical_family = str(paths.get("canonical_module_family") or "").strip()
    expected_source_roots = list(paths.get("expected_source_roots") or [])
    expected_test_roots = list(paths.get("expected_test_roots") or [])
    create_under = list(paths.get("create_under") or [])
    must_reuse = list(paths.get("must_reuse") or [])

    if not canonical_family:
        for candidate in create_under + must_reuse:
            candidate_value = str(candidate or "").strip()
            if candidate_value.startswith("src/"):
                canonical_family = candidate_value
                break

    if not expected_source_roots:
        expected_source_roots = [str(x).strip() for x in create_under if str(x).strip().startswith("src/")]

    if not expected_test_roots:
        expected_test_roots = [
            str(x).strip()
            for x in create_under
            if str(x).strip().startswith(("test/", "tests/"))
        ]

    if not canonical_family:
        if family == "runtime_profile_slice":
            canonical_family = "src/shared/adapters"
        elif family == "schema_backbone":
            canonical_family = "src/data/schema"
        elif family == "ui_feature":
            canonical_family = "src/frontend/features"

    def _stage(path: str) -> str:
        return f"runs/kit/{req_id}/{path}".strip()

    def _strip_root_prefix(value: str) -> str:
        v = str(value or "").strip().replace("\\", "/").lstrip("/")
        if v.startswith("src/"):
            return v[len("src/"):].strip("/")
        if v.startswith("tests/"):
            return v[len("tests/"):].strip("/")
        if v.startswith("test/"):
            return v[len("test/"):].strip("/")
        return v.strip("/")

    source_root = (
        _strip_root_prefix(expected_source_roots[0])
        if expected_source_roots
        else _strip_root_prefix(canonical_family)
    ) or "feature"

    if expected_test_roots:
        test_root = _strip_root_prefix(expected_test_roots[0])
    elif canonical_family == "src/shared/adapters":
        test_root = "shared/adapters"
    elif canonical_family == "src/data/schema":
        test_root = "data/schema"
    elif canonical_family.startswith("src/frontend/"):
        test_root = "frontend"
    else:
        test_root = source_root

    role_to_path_hint = {
        "primary_contract_or_schema": _stage("src/data/schema/core_lifecycle/contracts.py"),
        "mapping_or_models": _stage("src/data/schema/core_lifecycle/schema.py"),
        "migration": _stage("src/data/migrations/versions/<timestamp>_backbone.py"),
        "primary_implementation": _stage(f"src/{source_root}/implementation.py"),
        "boundary_contract": _stage(f"src/{source_root}/contracts.py"),
        "entry_binding": _stage(f"src/{source_root}/binding.py"),
        "workflow_component": _stage(f"src/{source_root}/workflow.py"),
        "primary_ui_feature": _stage(f"src/{source_root}/feature.ts"),
        "adapter_contract": _stage(f"src/{source_root}/adapter_contract.py"),
        "acceptance_tests": _stage(f"test/{test_root}/test_req_behavior.py"),
        "integration_smoke": _stage(f"test/{test_root}/test_integration_smoke.py"),
        "operational_readme": _stage(f"docs/README_{req_id}.md"),
        "kit_notes": _stage(f"docs/KIT_{req_id}.md"),
        "execution_contract": _stage("ci/LTC.json"),
        "execution_howto": _stage("ci/HOWTO.md"),
    }
    if canonical_family == "src/shared/adapters":
        role_to_path_hint.update({
            "primary_implementation": _stage("src/shared/adapters/implementation.py"),
            "boundary_contract": _stage("src/shared/adapters/contracts.py"),
            "entry_binding": _stage("src/shared/adapters/binding.py"),
            "workflow_component": _stage("src/shared/adapters/workflow.py"),
            "adapter_contract": _stage("src/shared/adapters/adapter_contract.py"),
            "acceptance_tests": _stage("test/shared/adapters/test_req_behavior.py"),
            "integration_smoke": _stage("test/shared/adapters/test_integration_smoke.py"),
        })

    if canonical_family == "src/data/schema":
        role_to_path_hint.update({
            "primary_contract_or_schema": _stage("src/data/schema/contracts.py"),
            "mapping_or_models": _stage("src/data/schema/schema.py"),
            "migration": _stage("src/data/migrations/versions/<timestamp>_backbone.py"),
            "acceptance_tests": _stage("test/data/schema/test_req_behavior.py"),
            "integration_smoke": _stage("test/data/schema/test_integration_smoke.py"),
        })
    required_outputs: List[Dict[str, Any]] = []
    for role in artifact_roles:
        role_name = str(role.get("role") or "").strip()
        path_hint = role_to_path_hint.get(role_name)
        if not path_hint:
            continue

        item = dict(role)
        item["path_hint"] = path_hint
        item["kind"] = (
            "doc" if role_name in {"operational_readme", "kit_notes"}
            else "ci" if role_name == "execution_contract"
            else "ci_doc" if role_name == "execution_howto"
            else "test" if role_name in {"acceptance_tests", "integration_smoke"}
            else "source"
        )
        required_outputs.append(item)

    if lane == "python":
        required_outputs.append({
            "role": "python_requirements",
            "path_hint": _stage("ci/requirements.txt"),
            "kind": "ci",
            "required": True,
            "purpose": "Minimal Python dependency set required to run emitted source and tests for this REQ candidate.",
            "must_cover": [
                "runtime dependencies for emitted code",
                "test dependencies for emitted tests",
            ],
            "must_contain": [
                "only dependencies actually needed by emitted files",
            ],
            "must_not_contain": [
                "unrelated speculative dependencies",
            ],
        })

    return {
        "version": "1.0.0",
        "req_id": req_id,
        "lane": lane,
        "family": family,
        "canonical_module_family": canonical_family,
        "expected_source_roots": expected_source_roots,
        "expected_test_roots": expected_test_roots,
        "required_outputs": required_outputs,
    }

def _build_file_requirements(contract: Dict[str, Any], core_blobs: Dict[str, Any]) -> Dict[str, Any]:
    lane_policy = _load_lane_guide_policy(contract, core_blobs)
    family = _resolve_requirement_family(contract, lane_policy)
    artifact_roles = _derive_artifact_roles(contract, family, lane_policy)
    return _materialize_file_requirements(contract, family, artifact_roles)

def _read_json_stage_file_from_files(
    files: List[Dict[str, Any]],
    req_id: str,
    relative_path: str,
) -> Optional[Dict[str, Any]]:
    target_path = f"runs/kit/{req_id}/{relative_path}".strip()

    for item in files or []:
        path = str(item.get("path") or "").strip()
        if path != target_path:
            continue
        try:
            data = json.loads(str(item.get("content") or ""))
        except Exception as exc:
            log.warning("failed to parse stage json file path=%s error=%s", path, exc)
            return None
        if isinstance(data, dict):
            return data
        return None

    return None


def _should_run_promotion_hardener(
    files: List[Dict[str, Any]],
    req_id: str,
) -> tuple[bool, str]:
    report = _read_json_stage_file_from_files(files, req_id, "ci/INTEGRITY_EVAL.json")
    if not report:
        return True, "unknown"

    verdict = str(report.get("verdict") or "").strip().lower()
    hardening_required = report.get("hardening_required")

    if isinstance(hardening_required, bool):
        return hardening_required, verdict or "unknown"

    return verdict in {"salvageable", "needs_more_hardening"}, verdict or "unknown"


def _read_promotion_eval_report(
    files: List[Dict[str, Any]],
    req_id: str,
) -> Optional[Dict[str, Any]]:
    return _read_json_stage_file_from_files(files, req_id, "ci/PROMOTION_EVAL.json")


def _detect_bootstrap_blockers(
    req_id: str,
    candidate_files: List[Dict[str, Any]],
    core_blobs: Dict[str, Any],
) -> List[str]:
    blockers: List[str] = []

    composition_manifest = str(core_blobs.get("REPO_COMPOSITION_MANIFEST.md") or "")

    existing_entrypoints = "`app.py`" in composition_manifest
    existing_shared_settings = "Shared Settings / Config Modules Already Present" in composition_manifest

    staged_paths = [str(item.get("path") or "").strip() for item in candidate_files if item.get("path")]

    staged_apps = [p for p in staged_paths if p.endswith("/app.py")]
    staged_local_config = [p for p in staged_paths if p.endswith("/config.py") or p.endswith("/settings.py")]

    if existing_entrypoints and staged_apps:
        blockers.append(
            f"REQ {req_id} emits new application entrypoints {staged_apps} even though canonical app composition already exists"
        )

    if existing_shared_settings:
        suspicious_local = [
            p for p in staged_local_config
            if "/shared/" not in f"/{p}"
        ]
        if suspicious_local:
            blockers.append(
                f"REQ {req_id} emits local config/settings modules {suspicious_local} while shared settings/config modules already exist"
            )

    return blockers

def _filter_core_blobs_for_target_req(
    core_blobs: Dict[str, Any],
    target_req_id: str,
) -> Dict[str, Any]:
    """
    Keep the normative context required for a single target REQ.

    This filter must preserve:
    - global normative artifacts
    - REQ-specific promotion manifest
    - repo manifests
    - generated guardrails
    """
    if not core_blobs:
        return {}

    kept: Dict[str, Any] = {}

    always_keep_suffixes = (
        "spec.md",
        "plan.md",
        "plan.json",
        "tech_constraints.yaml",
        "target_contract.json",
        "file_requirements.json",
    )

    always_keep_exact = {
        "REQ_PROMOTION_MANIFEST.md",
        "REPO_ACCESS_MANIFEST.md",
        "REPO_STRUCTURE_EVIDENCE.json",
        "REPO_COMPOSITION_MANIFEST.md",
    }

    for raw_name, value in core_blobs.items():
        name = str(raw_name or "").strip()
        lname = name.lower()

        if name in always_keep_exact:
            kept[name] = value
            continue

        if any(lname.endswith(sfx) for sfx in always_keep_suffixes):
            kept[name] = value
            continue

        if name.startswith("REQ_PROMOTION_MANIFEST"):
            text = str(value or "")
            if target_req_id in name or f"REQ Promotion Manifest — {target_req_id}" in text:
                kept[name] = value
            continue

    return kept


def _inject_candidate_blobs(
    base_core_blobs: Dict[str, Any],
    candidate_files: List[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(base_core_blobs or {})
    for item in candidate_files or []:
        path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if path and content:
            merged[f"candidate::{path}"] = content
    return merged



def _stage_artifact_path(req_id: str, relative_path: str) -> Path:
    runs_dir = os.getenv("RUNS_DIR", "/runs")
    return Path(runs_dir).resolve() / "kit" / req_id / relative_path


def _write_stage_artifact(req_id: str, relative_path: str, content: str) -> Optional[str]:
    try:
        target = _stage_artifact_path(req_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target.as_posix()
    except Exception as exc:
        log.warning("failed to write stage artifact req=%s path=%s error=%s", req_id, relative_path, exc)
        return None


def _collect_candidate_files_from_output(out: Dict[str, Any], req_id: str) -> Dict[str, str]:
    files = out.get("files") or []
    target_prefix = f"runs/kit/{req_id}/"
    collected: Dict[str, str] = {}

    for item in files:
        path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if not path or not content:
            continue
        if not path.startswith(target_prefix):
            continue
        collected[path] = content

    return collected

def _append_runtime_guardrail_files(
    files: List[Dict[str, Any]],
    req_id: str,
    *,
    target_contract_text: str,
    file_requirements_text: str,
    promotion_manifest: str | None,
) -> List[Dict[str, Any]]:
    runtime_files: List[Dict[str, Any]] = [
        {
            "path": f"runs/kit/{req_id}/ci/TARGET_CONTRACT.json",
            "content": target_contract_text,
        },
        {
            "path": f"runs/kit/{req_id}/ci/FILE_REQUIREMENTS.json",
            "content": file_requirements_text,
        },
    ]

    if promotion_manifest:
        runtime_files.append(
            {
                "path": f"runs/kit/{req_id}/ci/REQ_PROMOTION_MANIFEST.md",
                "content": promotion_manifest,
            }
        )

    return _merge_file_lists_by_path(files or [], runtime_files)
def _merge_file_lists_by_path(base_files: List[Dict[str, Any]], override_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for item in base_files or []:
        path = str(item.get("path") or "").strip()
        if path:
            merged[path] = dict(item)

    for item in override_files or []:
        path = str(item.get("path") or "").strip()
        if path:
            merged[path] = dict(item)

    return list(merged.values())


async def run_phase(phase: str, req_payload: Dict[str, Any]) -> Dict[str, Any]:
    # --- Normalizzazione in dict ---
    if hasattr(req_payload, "model_dump"):
        payload = req_payload.model_dump()   # pydantic -> dict
    elif isinstance(req_payload, dict):
        payload = dict(req_payload)          # copia difensiva
    else:
        # fallback estremo
        try:
            payload = dict(req_payload)      # tipo mapping-like
        except Exception:
            raise ValueError("Invalid request payload type for HarperService.run_phase")

    merged: Dict[str, Any] = dict(payload or {})
    merged["phase"] = phase
    merged.setdefault("cmd", phase)
    merged.setdefault("flags", {})
    merged = await _normalize_message(merged)


    repo_ctx = merged.get("repository_context") or {}
    core_blobs = dict(merged.get("core_blobs") or {})

    repo_access_manifest = build_repo_access_manifest(repo_ctx)
    if repo_access_manifest:
        core_blobs["REPO_ACCESS_MANIFEST.md"] = repo_access_manifest

    repo_structure_evidence = build_repo_structure_evidence(repo_ctx)
    if repo_structure_evidence:
        core_blobs["REPO_STRUCTURE_EVIDENCE.json"] = repo_structure_evidence

    repo_composition_manifest = build_repo_composition_manifest(repo_ctx)
    if repo_composition_manifest:
        core_blobs["REPO_COMPOSITION_MANIFEST.md"] = repo_composition_manifest

    # Make enriched core blobs authoritative for the whole phase.
    merged["core_blobs"] = core_blobs


    target_req_id: Optional[str] = None

    if merged.get("phase") == "kit":
        kit = merged.get("kit") or {}
        targets = kit.get("targets") or []
        if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], str) or not targets[0].strip():
            raise ValueError("Harper /kit requires exactly one target REQ-ID in kit.targets, e.g. { kit: { targets: ['REQ-001'] } }")

        target_req_id = targets[0].strip()
        requested_kit_phases = _normalize_requested_kit_phases(kit)

        filtered_core_blobs = _filter_core_blobs_for_target_req(
            core_blobs,
            target_req_id,
        )

        repo_ctx = merged.get("repository_context") or {}
        

        working_core_blobs = dict(filtered_core_blobs or {})

        target_contract_text = ""
        file_requirements_text = ""
        promotion_manifest_text = ""
        
        promotion_manifest = build_req_promotion_manifest(repo_ctx, target_req_id)
        promotion_manifest_text = str(promotion_manifest or "")
        if promotion_manifest_text:
            working_core_blobs["REQ_PROMOTION_MANIFEST.md"] = promotion_manifest_text

        target_contract = _extract_target_contract(working_core_blobs, target_req_id)
        if not target_contract:
            raise ValueError(f"TARGET_CONTRACT cannot be derived for {target_req_id}")

        file_requirements = _build_file_requirements(target_contract, working_core_blobs)


        target_contract_text = json.dumps(
            target_contract,
            ensure_ascii=False,
            indent=2,
        )
        file_requirements_text = json.dumps(
            file_requirements,
            ensure_ascii=False,
            indent=2,
        )

        working_core_blobs["TARGET_CONTRACT.json"] = target_contract_text
        working_core_blobs["FILE_REQUIREMENTS.json"] = file_requirements_text

        if promotion_manifest:
            working_core_blobs["REQ_PROMOTION_MANIFEST.md"] = promotion_manifest
            _write_stage_artifact(
                target_req_id,
                "ci/REQ_PROMOTION_MANIFEST.md",
                promotion_manifest,
            )

        _write_stage_artifact(
            target_req_id,
            "ci/TARGET_CONTRACT.json",
            target_contract_text,
        )

        _write_stage_artifact(
            target_req_id,
            "ci/FILE_REQUIREMENTS.json",
            file_requirements_text,
        )

        merged["core_blobs"] = working_core_blobs
        log.info(
            "harper.kit guardrails ready req=%s target_contract=%s file_requirements=%s required_outputs=%d repo_access=%s repo_structure=%s repo_composition=%s canonical_family=%s source_roots=%s test_roots=%s",
            target_req_id,
            "TARGET_CONTRACT.json" in working_core_blobs,
            "FILE_REQUIREMENTS.json" in working_core_blobs,
            len((file_requirements or {}).get("required_outputs") or []),
            "REPO_ACCESS_MANIFEST.md" in working_core_blobs,
            "REPO_STRUCTURE_EVIDENCE.json" in working_core_blobs,
            "REPO_COMPOSITION_MANIFEST.md" in working_core_blobs,
            (file_requirements or {}).get("canonical_module_family"),
            (file_requirements or {}).get("expected_source_roots"),
            (file_requirements or {}).get("expected_test_roots"),
        )


    
    # --- routing modello (unica fonte di verità) ---
    model_override = merged.get("model")
    profile_hint = merged.get("profileHint")

    try:
        llm_sel = await resolve_llm_selection(
            base_url=str(getattr(settings, "GATEWAY_URL", "http://localhost:8000")).rstrip("/"),
            mode="harper",
            phase=phase,
            requested_model=model_override or "auto",
            requested_provider=merged.get("provider"),
            profile_hint=profile_hint,
        )

        if llm_sel.get("model"):
            merged["model"] = llm_sel["model"]
        if llm_sel.get("provider"):
            merged["provider"] = llm_sel["provider"]
        if llm_sel.get("remote_name"):
            merged["remote_name"] = llm_sel["remote_name"]
        if llm_sel.get("profile"):
            merged["profileHint"] = llm_sel["profile"]

        merged["mode_contract"] = llm_sel.get("mode_contract") or {}

        log.info(
            "harper.routing resolved model=%s provider=%s profile=%s override=%s",
            merged.get("model"),
            merged.get("provider"),
            merged.get("profileHint"),
            model_override,
        )
        
    except Exception as e:
        log.warning("harper.routing failed (%s) → proceeding with provided model=%s", e, model_override)
    # runId di default se manca
    merged.setdefault("runId", f"{merged.get('runId')}")

    if phase == "kit" and target_req_id:
        if "kit" in requested_kit_phases:
            out = await _post_json("/v1/harper/run", merged)
        else:
            existing_candidate_artifacts = _load_existing_req_candidate_artifacts(target_req_id)
            if not existing_candidate_artifacts:
                raise ValueError(
                    f"No existing candidate files found for {target_req_id}. "
                    f"Run /kit for the base candidate first, or include 'kit' in kit.phases."
                )

            out = {
                "ok": True,
                "phase": "kit",
                "echo": f"Reusing existing candidate files for {target_req_id}",
                "text": "",
                "files": existing_candidate_artifacts,
                "diffs": [],
                "tests": {"passed": 0, "failed": 0, "summary": "n/a"},
                "warnings": [f"base_kit_reused_from_disk:{target_req_id}"],
                "errors": [],
                "runId": merged.get("runId"),
            }
    else:
        out = await _post_json("/v1/harper/run", merged)


    log.info(
        "GATEWAY HARPER RUN RES keys=%s files=%d text=%s",
        ",".join(sorted(out.keys())),
        len(out.get("files") or []),
        "yes" if out.get("text") else "no",
    )

    # --- Optional KIT follow-up phases (manual by default, chained only if requested) ---
    if phase == "kit" and target_req_id:
        selected_phases = set(requested_kit_phases)
        candidate_files = _collect_candidate_files_from_output(out, target_req_id)

        integrity_review_files: List[Dict[str, Any]] = []
        hardener_required = True
        integrity_verdict = "not_run"

        if "integrity_eval" in selected_phases:
            if candidate_files:
                integrity_payload = dict(merged)
                integrity_payload["phase"] = "integrity_eval"
                integrity_payload["cmd"] = "integrity_eval"

                base_core_blobs = _filter_core_blobs_for_target_req(
                    dict(integrity_payload.get("core_blobs") or {}),
                    target_req_id,
                )
                candidate_artifacts = [
                    {"path": path, "content": content}
                    for path, content in candidate_files.items()
                ]
                integrity_payload["core_blobs"] = _inject_candidate_blobs(
                    base_core_blobs,
                    candidate_artifacts,
                )

                integrity_payload["integrity_eval"] = {
                    "req_id": target_req_id,
                    "mode": "candidate_review",
                }

                log.info(
                    "harper.kit invoking integrity eval req=%s files=%d",
                    target_req_id,
                    len(candidate_files),
                )

                integrity_start = time.time()
                integrity_out = await _post_json("/v1/harper/run", integrity_payload)
                integrity_elapsed = time.time() - integrity_start

                integrity_review_files = _filter_req_stage_files(
                    integrity_out.get("files") or [],
                    target_req_id,
                )

                log.info(
                    "harper.kit integrity eval completed req=%s elapsed=%.3fs valid_files=%d",
                    target_req_id,
                    integrity_elapsed,
                    len(integrity_review_files),
                )

                if integrity_review_files:
                    base_files = out.get("files") or []
                    out["files"] = _merge_file_lists_by_path(base_files, integrity_review_files)
                    out["integrity_eval_applied"] = True
                    out["integrity_eval_file_count"] = len(integrity_review_files)
                else:
                    out["integrity_eval_applied"] = False
                    out["integrity_eval_file_count"] = 0

                hardener_required, integrity_verdict = _should_run_promotion_hardener(
                    integrity_review_files,
                    target_req_id,
                )
                out["integrity_eval_verdict"] = integrity_verdict
                out["promotion_hardener_required"] = hardener_required
            else:
                out["integrity_eval_applied"] = False
                out["integrity_eval_file_count"] = 0
                out["integrity_eval_verdict"] = "no_candidate_files"
                out["promotion_hardener_required"] = False
        else:
            out["integrity_eval_applied"] = False
            out["integrity_eval_file_count"] = 0
            out["integrity_eval_verdict"] = "not_requested"
            out["promotion_hardener_required"] = True

        candidate_file_artifacts = _collect_candidate_file_artifacts_from_output(out, target_req_id)
        req_path_blockers = _detect_req_path_mismatch(target_req_id, candidate_file_artifacts)

        if req_path_blockers:
            out["promotion_eval_applied"] = False
            out["promotion_eval_status"] = "blocked_req_path_mismatch"
            out["promotion_eval_blockers"] = req_path_blockers
            log.warning(
                "harper.kit promotion blockers req=%s blockers=%s",
                target_req_id,
                req_path_blockers,
            )
            return out

        if "promotion_hardener" in selected_phases:
            bootstrap_blockers = _validate_pre_promotion_contracts(
                target_req_id,
                dict(merged.get("core_blobs") or {}),
            )

            if bootstrap_blockers:
                out["promotion_eval_applied"] = False
                out["promotion_eval_status"] = "blocked_pre_eval"
                out["promotion_eval_blockers"] = bootstrap_blockers
                log.warning(
                    "harper.kit promotion pre-eval blockers req=%s blockers=%s",
                    target_req_id,
                    bootstrap_blockers,
                )
                return out

            if candidate_file_artifacts:
                hardener_payload = dict(merged)
                hardener_payload["phase"] = "promotion_hardener"
                hardener_payload["cmd"] = "promotion_hardener"

                hardener_base_core_blobs = _filter_core_blobs_for_target_req(
                    dict(hardener_payload.get("core_blobs") or {}),
                    target_req_id,
                )
                hardener_payload["core_blobs"] = _inject_candidate_blobs(
                    hardener_base_core_blobs,
                    candidate_file_artifacts,
                )

                hardener_payload["promotion_hardener"] = {
                    "req_id": target_req_id,
                    "mode": "promotion_ready",
                    "integrity_verdict": out.get("integrity_eval_verdict"),
                }

                log.info(
                    "harper.promotion_hardener core_blobs req=%s target_contract=%s file_requirements=%s req_manifest=%s repo_access=%s repo_structure=%s repo_composition=%s",
                    target_req_id,
                    "TARGET_CONTRACT.json" in (hardener_payload.get("core_blobs") or {}),
                    "FILE_REQUIREMENTS.json" in (hardener_payload.get("core_blobs") or {}),
                    "REQ_PROMOTION_MANIFEST.md" in (hardener_payload.get("core_blobs") or {}),
                    "REPO_ACCESS_MANIFEST.md" in (hardener_payload.get("core_blobs") or {}),
                    "REPO_STRUCTURE_EVIDENCE.json" in (hardener_payload.get("core_blobs") or {}),
                    "REPO_COMPOSITION_MANIFEST.md" in (hardener_payload.get("core_blobs") or {}),
                )

                hardener_start = time.time()
                hardener_out = await _post_json("/v1/harper/run", hardener_payload)
                hardener_elapsed = time.time() - hardener_start

                hardener_files = _filter_req_stage_files(
                    hardener_out.get("files") or [],
                    target_req_id,
                )

                log.info(
                    "harper.kit promotion hardener completed req=%s elapsed=%.3fs valid_files=%d",
                    target_req_id,
                    hardener_elapsed,
                    len(hardener_files),
                )

                if hardener_files:
                    base_files = out.get("files") or []
                    out["files"] = _merge_file_lists_by_path(base_files, hardener_files)
                    out["promotion_hardener_applied"] = True
                    out["promotion_hardener_file_count"] = len(hardener_files)
                    out["promotion_hardener_status"] = "applied"
                else:
                    out["promotion_hardener_applied"] = False
                    out["promotion_hardener_file_count"] = 0
                    out["promotion_hardener_status"] = "no_changes"
            else:
                out["promotion_hardener_applied"] = False
                out["promotion_hardener_file_count"] = 0
                out["promotion_hardener_status"] = "no_candidate_files"
        else:
            out["promotion_hardener_applied"] = False
            out["promotion_hardener_file_count"] = 0
            out["promotion_hardener_status"] = "not_requested"

        candidate_after_hardening = _collect_candidate_file_artifacts_from_output(out, target_req_id)

        if "promotion_eval" in selected_phases:
            if candidate_after_hardening:
                promotion_eval_payload = dict(merged)
                promotion_eval_payload["phase"] = "promotion_eval"
                promotion_eval_payload["cmd"] = "promotion_eval"

                promotion_eval_base_core_blobs = _filter_core_blobs_for_target_req(
                    dict(promotion_eval_payload.get("core_blobs") or {}),
                    target_req_id,
                )
                promotion_eval_payload["core_blobs"] = _inject_candidate_blobs(
                    promotion_eval_base_core_blobs,
                    candidate_after_hardening,
                )
                promotion_eval_payload["promotion_eval"] = {
                    "req_id": target_req_id,
                    "mode": "promotion_review",
                    "integrity_verdict": out.get("integrity_eval_verdict"),
                    "promotion_hardener_status": out.get("promotion_hardener_status"),
                }

                log.info(
                    "harper.promotion_eval core_blobs req=%s target_contract=%s file_requirements=%s req_manifest=%s repo_access=%s repo_structure=%s repo_composition=%s",
                    target_req_id,
                    "TARGET_CONTRACT.json" in (promotion_eval_payload.get("core_blobs") or {}),
                    "FILE_REQUIREMENTS.json" in (promotion_eval_payload.get("core_blobs") or {}),
                    "REQ_PROMOTION_MANIFEST.md" in (promotion_eval_payload.get("core_blobs") or {}),
                    "REPO_ACCESS_MANIFEST.md" in (promotion_eval_payload.get("core_blobs") or {}),
                    "REPO_STRUCTURE_EVIDENCE.json" in (promotion_eval_payload.get("core_blobs") or {}),
                    "REPO_COMPOSITION_MANIFEST.md" in (promotion_eval_payload.get("core_blobs") or {}),
                )

                promotion_eval_start = time.time()
                try:
                    promotion_eval_out = await _post_json("/v1/harper/run", promotion_eval_payload)
                    promotion_eval_elapsed = time.time() - promotion_eval_start
                    log.info(
                        "harper.kit promotion eval completed req=%s elapsed=%.3fs files=%d",
                        target_req_id,
                        promotion_eval_elapsed,
                        len((promotion_eval_out or {}).get("files") or []),
                    )
                except httpx.HTTPError as exc:
                    promotion_eval_elapsed = time.time() - promotion_eval_start
                    log.warning(
                        "harper.kit promotion eval transient failure req=%s elapsed=%.3fs error=%s",
                        target_req_id,
                        promotion_eval_elapsed,
                        exc,
                    )
                    out["promotion_eval_applied"] = False
                    out["promotion_eval_status"] = "transient_failure"
                    out["promotion_eval_error"] = str(exc)
                    return out

                promotion_eval_files = _filter_req_stage_files(
                    promotion_eval_out.get("files") or [],
                    target_req_id,
                )

                if promotion_eval_files:
                    base_files = out.get("files") or []
                    out["files"] = _merge_file_lists_by_path(base_files, promotion_eval_files)
                    out["promotion_eval_applied"] = True
                    out["promotion_eval_file_count"] = len(promotion_eval_files)

                    promotion_eval_report = _read_promotion_eval_report(
                        promotion_eval_files,
                        target_req_id,
                    )
                    if promotion_eval_report:
                        out["promotion_eval_verdict"] = str(
                            promotion_eval_report.get("verdict") or ""
                        ).strip()
                else:
                    out["promotion_eval_applied"] = False
                    out["promotion_eval_file_count"] = 0
            else:
                out["promotion_eval_applied"] = False
                out["promotion_eval_file_count"] = 0
                out["promotion_eval_status"] = "no_candidate_files"
        else:
            out["promotion_eval_applied"] = False
            out["promotion_eval_file_count"] = 0
            out["promotion_eval_status"] = "not_requested"
        out["files"] = _append_runtime_guardrail_files(
            out.get("files") or [],
            target_req_id,
            target_contract_text=target_contract_text,
            file_requirements_text=file_requirements_text,
            promotion_manifest=promotion_manifest_text or None,
        )
    log.info(
        "GATEWAY HARPER RUN RES keys=%s files=%d text=%s integrity=%s hardener=%s promotion_eval=%s",
        ",".join(sorted(out.keys())),
        len(out.get("files") or []),
        "yes" if out.get("text") else "no",
        out.get("integrity_eval_applied"),
        out.get("promotion_hardener_applied"),
        out.get("promotion_eval_applied"),
    )
    return out  
