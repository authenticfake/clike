from __future__ import annotations

import json
import re
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from services.harper import _build_file_requirements, _extract_target_contract
from services.rag_store import RagStore
from services.repository_manifest import (
    build_repo_access_manifest,
    build_repo_composition_manifest,
    build_repo_structure_evidence,
    build_req_promotion_manifest,
)
from services.router import _load_cfg, resolve_explain

from mcp.server.fastmcp import FastMCP

log = logging.getLogger("orchestrator.mcp")

mcp = FastMCP(
    "CLike MCP",
    instructions=(
        "Read-only MCP server for CLike. "
        "Exposes Harper context, contracts, run artifacts, routing metadata, and RAG retrieval. "
        "No phase execution, no git mutation, no arbitrary shell or filesystem writes."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workspace_root() -> Path:
    root = Path(getattr(settings, "WORKSPACE_ROOT", ".")).expanduser().resolve()
    return root


def _runs_root() -> Path:
    root = Path(getattr(settings, "RUNS_DIR", "./runs")).expanduser().resolve()
    return root


def _doc_root(doc_root: str = "docs/harper") -> Path:
    return (_workspace_root() / doc_root).resolve()


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("mcp read text failed path=%s error=%s", path, exc)
        return None


def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    raw = _safe_read_text(path)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception as exc:
        log.warning("mcp read json failed path=%s error=%s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _safe_child(base: Path, relative_path: str) -> Path:
    rel = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("relative_path is required")
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if not str(target).startswith(str(base_resolved)):
        raise ValueError("path escapes allowed root")
    return target


def _git_branch(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _repository_context() -> Dict[str, Any]:
    root = _workspace_root()
    return {
        "repo_root": str(root),
        "workspace_folder": str(root),
        "branch": _git_branch(root),
        "git_detected": (root / ".git").exists(),
        "repo_url": "",
    }


def _plan_data(doc_root: str = "docs/harper") -> Dict[str, Any]:
    path = _doc_root(doc_root) / "plan.json"
    return _safe_read_json(path) or {}


def _reqs(plan_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    reqs = plan_data.get("reqs")
    if isinstance(reqs, list):
        return [x for x in reqs if isinstance(x, dict)]
    reqs = plan_data.get("req")
    if isinstance(reqs, list):
        return [x for x in reqs if isinstance(x, dict)]
    return []


def _req_by_id(plan_data: Dict[str, Any], req_id: str) -> Optional[Dict[str, Any]]:
    rid = str(req_id or "").strip().upper()
    for item in _reqs(plan_data):
        if str(item.get("id") or "").strip().upper() == rid:
            return item
    return None


def _load_lane_guides(doc_root: str = "docs/harper") -> Dict[str, str]:
    guides_dir = _doc_root(doc_root) / "lane-guides"
    out: Dict[str, str] = {}
    if not guides_dir.exists() or not guides_dir.is_dir():
        return out

    for path in sorted(guides_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".markdown"}:
            continue
        rel = path.relative_to(_workspace_root()).as_posix()
        raw = _safe_read_text(path)
        if raw:
            out[rel] = raw
    return out


def _core_blobs_for_prepare(doc_root: str = "docs/harper") -> Dict[str, str]:
    root = _doc_root(doc_root)
    blobs: Dict[str, str] = {}

    for name in ("IDEA.md", "SPEC.md", "PLAN.md", "plan.json", "constraints.json", "KIT.md"):
        raw = _safe_read_text(root / name)
        if raw:
            blobs[name] = raw

    blobs.update(_load_lane_guides(doc_root))
    return blobs


def _latest_run_dirs(limit: int = 20) -> List[Path]:
    runs_root = _runs_root()
    if not runs_root.exists() or not runs_root.is_dir():
        return []

    dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[: max(1, int(limit))]


def _read_run_bundle(run_dir: Path) -> Dict[str, Any]:
    bundle: Dict[str, Any] = {
        "run_id": run_dir.name,
        "path": str(run_dir),
    }

    for name in ("manifest.json", "eval.summary.json", "gate.decisions.json", "telemetry.json", "kit.report.json"):
        full = run_dir / name
        data = _safe_read_json(full)
        if data is not None:
            bundle[name] = data

    return bundle


def _latest_file_by_name(filename: str) -> Optional[Path]:
    for run_dir in _latest_run_dirs(limit=100):
        candidate = run_dir / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _default_project_id() -> str:
    root = _workspace_root()
    name = root.name or "default"
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return normalized or "default"


async def _rag_docs_context(
    *,
    query: str,
    path_prefix: str = "docs",
    limit_docs: int = 8,
    max_chars_per_doc: int = 2500,
) -> Dict[str, Any]:
    project_id = _default_project_id()
    store = RagStore(project_id)

    try:
        matches = await store.search(query, top_k=max(8, limit_docs * 4))
    except Exception as exc:
        log.warning("mcp rag search failed query=%s error=%s", query, exc)
        matches = []

    filtered_paths = []
    seen = set()
    for item in matches:
        p = str(item.get("path") or "").strip()
        if not p:
            continue
        if not p.lower().startswith(path_prefix.lower().rstrip("/") + "/") and p.lower() != path_prefix.lower():
            continue
        if p in seen:
            continue
        seen.add(p)
        filtered_paths.append(p)

    docs: List[Dict[str, Any]] = []
    if filtered_paths:
        try:
            docs = await store.fetch_docs_by_paths(
                filtered_paths[:limit_docs],
                max_chars_per_doc=max_chars_per_doc,
                limit_points=max(100, limit_docs * 50),
            )
        except Exception as exc:
            log.warning("mcp rag fetch by paths failed query=%s error=%s", query, exc)
            docs = []

    if not docs:
        try:
            docs = await store.fetch_docs_by_prefix(
                path_prefix,
                max_chars_per_doc=max_chars_per_doc,
                limit_points=max(100, limit_docs * 50),
                limit_docs=limit_docs,
            )
        except Exception as exc:
            log.warning("mcp rag fetch by prefix failed prefix=%s error=%s", path_prefix, exc)
            docs = []

    return {
        "project_id": project_id,
        "query": query,
        "path_prefix": path_prefix,
        "docs": docs,
    }

def _is_probably_text_file(path: Path, max_bytes: int = 512 * 1024) -> bool:
    try:
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size <= 0 or path.stat().st_size > max_bytes:
            return False
        raw = path.read_bytes()[:4096]
        if b"\x00" in raw:
            return False
        return True
    except Exception:
        return False


def _collect_workspace_text_items(
    *,
    glob_pattern: str = "docs/**/*",
    max_files: int = 2000,
    max_bytes: int = 512 * 1024,
) -> List[Dict[str, Any]]:
    root = _workspace_root()
    pattern = str(glob_pattern or "docs/**/*").strip() or "docs/**/*"

    excluded_parts = {
        ".git",
        "node_modules",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        "__pycache__",
        "dist",
        "build",
        "out",
        ".next",
    }

    allowed_suffixes = {
        ".md", ".markdown", ".txt", ".rst",
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".json", ".yaml", ".yml", ".toml", ".ini",
        ".sql", ".sh", ".bash", ".ps1",
        ".html", ".css", ".scss",
        ".http", ".curl",
    }

    items: List[Dict[str, Any]] = []

    for path in sorted(root.glob(pattern)):
        if len(items) >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        if not _is_probably_text_file(path, max_bytes=max_bytes):
            continue

        try:
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            log.warning("mcp collect text failed path=%s error=%s", path, exc)
            continue

        if not text.strip():
            continue

        items.append(
            {
                "path": rel,
                "text": text[:max_bytes],
            }
        )

    return items

def _doc_summaries(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in docs or []:
        text = str(item.get("text") or "").strip()
        out.append(
            {
                "path": item.get("path"),
                "chunks": item.get("chunks"),
                "excerpt": text[:800],
            }
        )
    return out

# ---------------------------------------------------------------------------
# MCP tools (read-only / contract-first)
# ---------------------------------------------------------------------------

@mcp.tool()
def clike_capabilities_list() -> Dict[str, Any]:
    return {
        "server": "CLike MCP",
        "version": "v1",
        "mode": "read_only",
        "transport": "streamable_http",
        "tools": [
            "clike_capabilities_list",
            "clike_health_get",
            "clike_models_list",
            "clike_profiles_list",
            "clike_routing_resolve",
            "harper_project_read_core",
            "clike_about",
            "clike_harper_workflow_explain",
            "clike_artifacts_explain",
            "harper_doc_read",
            "harper_plan_read",
            "harper_req_list",
            "harper_req_get",
            "harper_req_next",
            "harper_kit_prepare",
            "rag_search",
            "runs_list",
            "runs_read",
            "eval_read_summary",
            "gate_read_decision",
            "harper_status_read",
            "clike_operational_model_explain",
            "rag_docs_status",
            "rag_reindex_docs",
            "rag_reindex_docs_if_empty",
        ],
        "not_exposed": [
            "phase execution from orchestrator MCP",
            "git mutation",
            "arbitrary shell",
            "arbitrary filesystem write",
            "raw provider proxying",
            "UI/session mutation",
        ],
    }


@mcp.tool()
def clike_health_get() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "orchestrator",
        "workspace_root": str(_workspace_root()),
        "runs_root": str(_runs_root()),
        "doc_root_default": "docs/harper",
    }


@mcp.tool()
def clike_models_list() -> Dict[str, Any]:
    cfg = _load_cfg() or {}
    return {
        "ok": True,
        "models": cfg.get("models") or [],
    }


@mcp.tool()
def clike_profiles_list() -> Dict[str, Any]:
    cfg = _load_cfg() or {}
    profiles = list((cfg.get("profiles") or {}).keys())
    profiles.sort()
    return {
        "ok": True,
        "profiles": profiles,
    }


@mcp.tool()
def clike_routing_resolve(
    task: str,
    hint: str = "",
    model: str = "auto",
    provider: str = "",
) -> Dict[str, Any]:
    explained = resolve_explain(
        task=str(task or "").strip(),
        hint=(str(hint or "").strip() or None),
        model=(str(model or "").strip() or None),
        provider=(str(provider or "").strip() or None),
    )
    return {
        "ok": True,
        "resolved": explained.get("resolved") or {},
        "catalog_entry": explained.get("catalog_entry") or {},
        "explanation": explained,
    }

@mcp.tool()
async def clike_about() -> Dict[str, Any]:
    rag = await _rag_docs_context(
        query="CLike overview architecture harper workflow extension orchestrator gateway RAG local agent",
        path_prefix="docs",
        limit_docs=8,
        max_chars_per_doc=2500,
    )

    return {
        "ok": True,
        "name": "CLike",
        "summary": (
            "CLike is an AI-native software generation pipeline that combines "
            "a Harper-style workflow with retrieval grounding, multi-model routing, "
            "local agent execution, and eval-driven quality gates."
        ),
        "core_components": [
            "VS Code extension",
            "orchestrator",
            "gateway",
            "RAG",
            "Harper artifacts",
            "local agent executors",
        ],
        "primary_modes": [
            "free",
            "coding",
            "harper",
        ],
        "rag_context": {
            "project_id": rag["project_id"],
            "query": rag["query"],
            "docs": _doc_summaries(rag["docs"]),
        },
    }
@mcp.tool()
async def clike_harper_workflow_explain() -> Dict[str, Any]:
    rag = await _rag_docs_context(
        query="Harper workflow IDEA SPEC PLAN KIT EVAL GATE FINALIZE run artifacts acceptance criteria",
        path_prefix="docs",
        limit_docs=8,
        max_chars_per_doc=2500,
    )

    return {
        "ok": True,
        "workflow": [
            "IDEA",
            "SPEC",
            "PLAN",
            "KIT",
            "EVAL",
            "GATE",
            "FINALIZE",
        ],
        "summary": {
            "IDEA": "Defines business intent, problem, users, outcomes, and constraints.",
            "SPEC": "Turns intent into testable requirements and acceptance criteria.",
            "PLAN": "Breaks work into REQ units with dependencies and implementation order.",
            "KIT": "Generates candidate code, tests, and delivery artifacts for one or more REQs.",
            "EVAL": "Runs checks and normalizes results.",
            "GATE": "Applies quality and dependency policy to decide promotion eligibility.",
            "FINALIZE": "Produces release-oriented artifacts and summaries.",
        },
        "notes": [
            "CLike keeps canonical Harper artifacts in docs/harper.",
            "Run outputs and iteration evidence are stored under runs/<runId>/.",
            "Local agent execution may assist KIT and EVAL, but canonical gating remains owned by CLike.",
        ],
        "rag_context": {
            "project_id": rag["project_id"],
            "query": rag["query"],
            "docs": _doc_summaries(rag["docs"]),
        },
    }

@mcp.tool()
async def clike_artifacts_explain(doc_root: str = "docs/harper") -> Dict[str, Any]:
    root = _doc_root(doc_root)
    rag = await _rag_docs_context(
        query="Harper artifacts plan.json PLAN.md SPEC.md IDEA.md KIT.md eval.summary.json gate.decisions.json AGENT_EXECUTION_CONTEXT",
        path_prefix="docs",
        limit_docs=8,
        max_chars_per_doc=2500,
    )

    return {
        "ok": True,
        "doc_root": str(root),
        "artifacts": {
            "IDEA.md": "Business and technical intent.",
            "SPEC.md": "Requirements and acceptance criteria.",
            "PLAN.md": "Human-readable plan.",
            "plan.json": "Canonical machine-readable REQ plan.",
            "KIT.md": "Iteration notes and product-owner rescoping context.",
            "constraints.json": "Normalized constraints used by Harper flows.",
            "runs/<runId>/kit.report.json": "KIT output index and changed files.",
            "runs/<runId>/eval.summary.json": "Normalized eval results.",
            "runs/<runId>/gate.decisions.json": "Promotion decisions and rationale.",
            "runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json": "Local execution contract for agent-assisted flows.",
        },
        "rag_context": {
          "project_id": rag["project_id"],
          "query": rag["query"],
          "docs": _doc_summaries(rag["docs"]),
        },
    }

@mcp.tool()
def harper_project_read_core(doc_root: str = "docs/harper") -> Dict[str, Any]:
    root = _doc_root(doc_root)
    core_names = [
        "IDEA.md",
        "SPEC.md",
        "PLAN.md",
        "plan.json",
        "KIT.md",
        "constraints.json",
        "RELEASE_NOTES.md",
    ]
    docs: List[Dict[str, Any]] = []

    for name in core_names:
        path = root / name
        docs.append(
            {
                "name": name,
                "path": str(path),
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() and path.is_file() else 0,
            }
        )

    lane_guides_dir = root / "lane-guides"
    lane_guides = []
    if lane_guides_dir.exists() and lane_guides_dir.is_dir():
        lane_guides = [
            p.relative_to(_workspace_root()).as_posix()
            for p in sorted(lane_guides_dir.rglob("*"))
            if p.is_file()
        ]

    return {
        "ok": True,
        "doc_root": str(root),
        "docs": docs,
        "lane_guides": lane_guides,
    }


@mcp.tool()
def harper_doc_read(path: str, doc_root: str = "docs/harper") -> Dict[str, Any]:
    root = _doc_root(doc_root)
    target = _safe_child(root, path)
    raw = _safe_read_text(target)
    if raw is None:
        return {
            "ok": False,
            "path": str(target),
            "error": "document not found",
        }

    return {
        "ok": True,
        "path": str(target),
        "content": raw,
    }


@mcp.tool()
def harper_plan_read(doc_root: str = "docs/harper") -> Dict[str, Any]:
    root = _doc_root(doc_root)
    plan_json = _safe_read_json(root / "plan.json") or {}
    plan_md = _safe_read_text(root / "PLAN.md") or ""
    reqs = _reqs(plan_json)

    return {
        "ok": True,
        "path_plan_json": str(root / "plan.json"),
        "path_plan_md": str(root / "PLAN.md"),
        "plan_json": plan_json,
        "plan_md": plan_md,
        "req_count": len(reqs),
    }


@mcp.tool()
def harper_req_list(doc_root: str = "docs/harper") -> Dict[str, Any]:
    plan_json = _plan_data(doc_root)
    reqs = _reqs(plan_json)

    slim = []
    for item in reqs:
        slim.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "lane": item.get("lane"),
                "track": item.get("track"),
                "dependsOn": item.get("dependsOn") or [],
                "gate_policy_ref": item.get("gate_policy_ref"),
                "test_profile": item.get("test_profile"),
            }
        )

    return {
        "ok": True,
        "reqs": slim,
        "count": len(slim),
    }


@mcp.tool()
def harper_req_get(req_id: str, doc_root: str = "docs/harper") -> Dict[str, Any]:
    plan_json = _plan_data(doc_root)
    item = _req_by_id(plan_json, req_id)

    if not item:
        return {
            "ok": False,
            "req_id": req_id,
            "error": "REQ not found",
        }

    return {
        "ok": True,
        "req": item,
    }


@mcp.tool()
def harper_req_next(doc_root: str = "docs/harper") -> Dict[str, Any]:
    plan_json = _plan_data(doc_root)
    reqs = _reqs(plan_json)

    done = {
        str(item.get("id") or "").strip().upper()
        for item in reqs
        if str(item.get("status") or "").strip().lower() == "done"
    }

    for item in reqs:
        status = str(item.get("status") or "").strip().lower()
        if status == "done":
            continue

        deps = [
            str(x or "").strip().upper()
            for x in (item.get("dependsOn") or [])
            if str(x or "").strip()
        ]
        if all(dep in done for dep in deps):
            return {
                "ok": True,
                "req": item,
                "reason": "first non-done req with satisfied dependencies",
            }

    return {
        "ok": True,
        "req": None,
        "reason": "no eligible REQ found",
    }


@mcp.tool()
def harper_kit_prepare(req_id: str, doc_root: str = "docs/harper") -> Dict[str, Any]:
    rid = str(req_id or "").strip().upper()
    if not rid:
        raise ValueError("req_id is required")

    core_blobs = _core_blobs_for_prepare(doc_root)
    if "plan.json" not in core_blobs:
        return {
            "ok": False,
            "req_id": rid,
            "error": "docs/harper/plan.json not found",
        }

    target_contract = _extract_target_contract(core_blobs, rid)
    if not target_contract:
        return {
            "ok": False,
            "req_id": rid,
            "error": "TARGET_CONTRACT cannot be derived",
        }

    file_requirements = _build_file_requirements(target_contract, core_blobs)
    repo_ctx = _repository_context()

    return {
        "ok": True,
        "req_id": rid,
        "target_contract": target_contract,
        "file_requirements": file_requirements,
        "promotion_manifest": build_req_promotion_manifest(repo_ctx, rid),
        "repo_access_manifest": build_repo_access_manifest(repo_ctx),
        "repo_structure_evidence": json.loads(build_repo_structure_evidence(repo_ctx) or "{}"),
        "repo_composition_manifest": build_repo_composition_manifest(repo_ctx),
        "core_docs_available": sorted(core_blobs.keys()),
    }


@mcp.tool()
async def rag_search(project_id: str, query: str, top_k: int = 8) -> Dict[str, Any]:
    pid = str(project_id or "").strip() or "default"
    q = str(query or "").strip()
    if not q:
        raise ValueError("query is required")

    store = RagStore(pid)
    hits = await store.search(q, top_k=max(1, int(top_k)))

    return {
        "ok": True,
        "project_id": pid,
        "query": q,
        "top_k": int(top_k),
        "matches": hits,
    }


@mcp.tool()
def runs_list(limit: int = 20) -> Dict[str, Any]:
    runs = []
    for run_dir in _latest_run_dirs(limit=max(1, int(limit))):
        runs.append(
            {
                "run_id": run_dir.name,
                "path": str(run_dir),
                "mtime": run_dir.stat().st_mtime,
                "files": sorted([p.name for p in run_dir.iterdir() if p.is_file()]),
            }
        )

    return {
        "ok": True,
        "runs": runs,
        "count": len(runs),
    }


@mcp.tool()
def runs_read(run_id: str) -> Dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        raise ValueError("run_id is required")

    run_dir = _runs_root() / rid
    if not run_dir.exists() or not run_dir.is_dir():
        return {
            "ok": False,
            "run_id": rid,
            "error": "run not found",
        }

    return {
        "ok": True,
        "bundle": _read_run_bundle(run_dir),
    }


@mcp.tool()
def eval_read_summary(run_id: str = "") -> Dict[str, Any]:
    if run_id:
        path = _runs_root() / str(run_id).strip() / "eval.summary.json"
    else:
        path = _latest_file_by_name("eval.summary.json")

    data = _safe_read_json(path) if path else None
    return {
        "ok": data is not None,
        "path": str(path) if path else None,
        "eval_summary": data,
    }


@mcp.tool()
def gate_read_decision(run_id: str = "") -> Dict[str, Any]:
    if run_id:
        path = _runs_root() / str(run_id).strip() / "gate.decisions.json"
    else:
        path = _latest_file_by_name("gate.decisions.json")

    data = _safe_read_json(path) if path else None
    return {
        "ok": data is not None,
        "path": str(path) if path else None,
        "gate_decision": data,
    }


@mcp.tool()
def harper_status_read(doc_root: str = "docs/harper") -> Dict[str, Any]:
    plan_json = _plan_data(doc_root)
    reqs = _reqs(plan_json)

    open_reqs = []
    done_reqs = []

    for item in reqs:
        if str(item.get("status") or "").strip().lower() == "done":
            done_reqs.append(item.get("id"))
        else:
            open_reqs.append(item.get("id"))

    latest_eval = _latest_file_by_name("eval.summary.json")
    latest_gate = _latest_file_by_name("gate.decisions.json")

    return {
        "ok": True,
        "workspace_root": str(_workspace_root()),
        "doc_root": str(_doc_root(doc_root)),
        "req_total": len(reqs),
        "req_done": len(done_reqs),
        "req_open": len(open_reqs),
        "next_req": (harper_req_next(doc_root).get("req") or {}).get("id"),
        "latest_eval_path": str(latest_eval) if latest_eval else None,
        "latest_gate_path": str(latest_gate) if latest_gate else None,
    }



@mcp.tool()
async def clike_operational_model_explain() -> Dict[str, Any]:
    rag = await _rag_docs_context(
        query="CLike model 2 agent extension MCP orchestrator Harper kit eval gate finalize rag reindex",
        path_prefix="docs",
        limit_docs=8,
        max_chars_per_doc=2500,
    )

    return {
        "ok": True,
        "model": "Model 2 — Agent interacts with CLike",
        "summary": (
            "An external/local agent should interact with the VS Code extension operational MCP surface. "
            "The extension dispatches normal CLike slash commands and keeps the orchestrator as workflow owner."
        ),
        "flow": [
            "Agent calls CLike Extension MCP tool.",
            "Extension dispatches a normal slash command such as /kit REQ-001, /eval REQ-001, /gate REQ-001, /finalize, or /ragIndex docs/**/*.",
            "The existing CLike extension flow sends the request to the orchestrator where required.",
            "The orchestrator keeps Harper semantics, local-agent contracts, RAG, eval, and gate ownership.",
        ],
        "division_of_responsibility": {
            "extension_mcp": [
                "Operational surface for Agent -> CLike.",
                "Dispatch normal chat slash commands.",
                "Expose next action helper.",
                "Expose RAG docs reindex helper through workspace access.",
            ],
            "orchestrator_mcp": [
                "Informational/service surface.",
                "Explain CLike, Harper, artifacts, capabilities, and RAG context.",
                "Provide docs reindex service when orchestrator has workspace access.",
                "Do not execute phases directly.",
            ],
        },
        "allowed_agent_commands": [
            "/agent-default claude|codex|auto",
            "/kit <REQ-ID>",
            "/eval <REQ-ID>",
            "/gate <REQ-ID>",
            "/finalize",
            "/ragIndex docs/**/*",
            "/ragSearch <query>",
        ],
        "completion_policy": {
            "when_next_req_exists": "Agent may request /kit, /eval, and /gate for the eligible REQ.",
            "when_no_req_exists": "CLike reports finalize_only; agent should request /finalize.",
            "canonical_judgement": "Eval and Gate remain CLike-owned.",
        },
        "rag_context": {
            "project_id": rag["project_id"],
            "query": rag["query"],
            "docs": _doc_summaries(rag["docs"]),
        },
    }


@mcp.tool()
async def rag_docs_status(project_id: str = "") -> Dict[str, Any]:
    pid = str(project_id or _default_project_id()).strip() or "default"
    store = RagStore(pid)

    try:
        docs = await store.fetch_docs_by_prefix(
            "docs",
            max_chars_per_doc=300,
            limit_points=100,
            limit_docs=3,
        )
    except Exception as exc:
        return {
            "ok": False,
            "project_id": pid,
            "docs_count": 0,
            "empty": True,
            "error": str(exc),
        }

    return {
        "ok": True,
        "project_id": pid,
        "docs_count": len(docs),
        "empty": len(docs) == 0,
        "docs": _doc_summaries(docs),
    }


@mcp.tool()
async def rag_reindex_docs(
    project_id: str = "",
    glob_pattern: str = "docs/**/*",
    max_files: int = 2000,
) -> Dict[str, Any]:
    pid = str(project_id or _default_project_id()).strip() or "default"
    items = _collect_workspace_text_items(
        glob_pattern=glob_pattern or "docs/**/*",
        max_files=max(1, int(max_files or 2000)),
    )

    if not items:
        return {
            "ok": False,
            "project_id": pid,
            "glob_pattern": glob_pattern,
            "indexed_items": 0,
            "error": "No text documents found for indexing.",
        }

    store = RagStore(pid)
    result = await store.index_texts(items)

    return {
        "ok": True,
        "project_id": pid,
        "glob_pattern": glob_pattern,
        "indexed_items": len(items),
        "rag_result": result,
    }


@mcp.tool()
async def rag_reindex_docs_if_empty(
    project_id: str = "",
    glob_pattern: str = "docs/**/*",
    max_files: int = 2000,
) -> Dict[str, Any]:
    status = await rag_docs_status(project_id=project_id)
    if status.get("ok") and not status.get("empty"):
        return {
            "ok": True,
            "reindexed": False,
            "status": status,
            "message": "RAG docs context already exists.",
        }

    result = await rag_reindex_docs(
        project_id=project_id,
        glob_pattern=glob_pattern or "docs/**/*",
        max_files=max_files,
    )

    return {
        "ok": bool(result.get("ok")),
        "reindexed": bool(result.get("ok")),
        "previous_status": status,
        "result": result,
        "message": "RAG docs context was empty or unavailable; docs reindex attempted.",
    }