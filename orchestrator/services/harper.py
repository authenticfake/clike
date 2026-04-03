# Phase services (SPEC/PLAN/KIT) orchestrating prompts, evals and runs.
# Iterations: each call may update documents and re-run gates.
# Branching (future): for KIT change-requests, create feature branches per request.
# Phase services (SPEC/PLAN/KIT/BUILD) orchestrating routing and gateway calls.
from __future__ import annotations
from typing import Dict, Any, Optional, List
import os, logging, time
from datetime import datetime
from services.llm_contracts import resolve_llm_selection
from config import settings
from services.repository_manifest import build_req_promotion_manifest
import httpx  # ensure available in requirements
from pathlib import Path

GATEWAY_URL = os.environ.get("CL_GATEWAY_URL", "http://gateway:8000")
log = logging.getLogger("orcehstrator:service:harper")
TIMEOUT =float(os.environ.get("TIMEOUT", 720.0))


async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{GATEWAY_URL}{path}"
    start_time = time.time()

    log.info("POST %s keys=%s idea_md=%s core=%d atts=%d time=%.4f",
             url,
             ",".join(sorted(payload.keys())),
             bool(payload.get("idea_md")),
             len(payload.get("core") or []),
             len(payload.get("attachments") or []), start_time)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=payload)
        end_time = time.time()
        elapsed_time = end_time - start_time
        log.info(f"POST (elapsed): {elapsed_time:.4f} secondi.")


        r.raise_for_status()
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


    target_req_id: Optional[str] = None

    if merged.get("phase") == "kit":
        kit = merged.get("kit") or {}
        targets = kit.get("targets") or []
        if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], str) or not targets[0].strip():
            raise ValueError("Harper /kit requires exactly one target REQ-ID in kit.targets, e.g. { kit: { targets: ['REQ-001'] } }")

        target_req_id = targets[0].strip()
        repo_ctx = merged.get("repository_context") or {}
        log.info("harper.kit target_req_id=%s repo_root=%s branch=%s", target_req_id, repo_ctx.get("repo_root"), repo_ctx.get("branch"))
        promotion_manifest = build_req_promotion_manifest(repo_ctx, target_req_id)
        if promotion_manifest:
            core_blobs = dict(merged.get("core_blobs") or {})
            core_blobs["REQ_PROMOTION_MANIFEST.md"] = promotion_manifest
            merged["core_blobs"] = core_blobs

            log.info(
                "harper.kit promotion_manifest attached req=%s repo_root=%s branch=%s",
                target_req_id,
                repo_ctx.get("repo_root"),
                repo_ctx.get("branch"),
            )
        else:
            log.info("harper.kit promotion_manifest skipped req=%s (no repository context)", target_req_id)

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

    out = await _post_json("/v1/harper/run", merged)

    log.info(
        "GATEWAY HARPER RUN RES keys=%s files=%d text=%s",
        ",".join(sorted(out.keys())),
        len(out.get("files") or []),
        "yes" if out.get("text") else "no",
    )

    # --- INTEGRITY_EVAL pass (internal, same /kit command) ---
    if phase == "kit" and target_req_id:
        candidate_files = _collect_candidate_files_from_output(out, target_req_id)

        if candidate_files:
            integrity_payload = dict(merged)
            integrity_payload["phase"] = "integrity_eval"
            integrity_payload["cmd"] = "integrity_eval"

            core_blobs = dict(integrity_payload.get("core_blobs") or {})
            for path, content in candidate_files.items():
                core_blobs[f"candidate::{path}"] = content
            integrity_payload["core_blobs"] = core_blobs

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
            log.info(
                "harper.kit integrity eval completed req=%s elapsed=%.3fs files=%d",
                target_req_id,
                integrity_elapsed,
                len((integrity_out or {}).get("files") or []),
            )
            if isinstance(integrity_out, dict) and integrity_out.get("files"):
                integrity_files = integrity_out.get("files") or []
                base_files = out.get("files") or []
                out["files"] = _merge_file_lists_by_path(base_files, integrity_files)
                out["integrity_eval_applied"] = True
                out["integrity_eval_file_count"] = len(integrity_files)
            else:
                out["integrity_eval_applied"] = False
                out["integrity_eval_file_count"] = 0
        else:
            out["integrity_eval_applied"] = False
            out["integrity_eval_file_count"] = 0
    
    # --- PROMOTION_HARDENER + PROMOTION_EVAL pipeline ---
    if phase == "kit" and target_req_id:
        candidate_file_artifacts = _collect_candidate_file_artifacts_from_output(out, target_req_id)

        # 1) PROMOTION_HARDENER
        if candidate_file_artifacts:
            hardener_payload = dict(merged)
            hardener_payload["phase"] = "promotion_hardener"
            hardener_payload["cmd"] = "promotion_hardener"

            hardener_core_blobs = dict(hardener_payload.get("core_blobs") or {})
            for item in candidate_file_artifacts:
                path = str(item.get("path") or "").strip()
                content = str(item.get("content") or "")
                if path and content:
                    hardener_core_blobs[f"candidate::{path}"] = content
            hardener_payload["core_blobs"] = hardener_core_blobs

            hardener_payload["promotion_hardener"] = {
                "req_id": target_req_id,
                "mode": "promotion_ready",
            }

            log.info(
                "harper.kit invoking promotion hardener req=%s files=%d",
                target_req_id,
                len(candidate_file_artifacts),
            )

            hardener_start = time.time()
            hardener_out = await _post_json("/v1/harper/run", hardener_payload)
            hardener_elapsed = time.time() - hardener_start

            hardener_files = _filter_req_stage_files(hardener_out.get("files") or [], target_req_id)
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
            else:
                out["promotion_hardener_applied"] = False
                out["promotion_hardener_file_count"] = 0

            # 2) PROMOTION_EVAL
            candidate_after_hardening = _collect_candidate_file_artifacts_from_output(out, target_req_id)
            if candidate_after_hardening:
                promotion_eval_payload = dict(merged)
                promotion_eval_payload["phase"] = "promotion_eval"
                promotion_eval_payload["cmd"] = "promotion_eval"

                promotion_eval_core_blobs = dict(promotion_eval_payload.get("core_blobs") or {})
                for item in candidate_after_hardening:
                    path = str(item.get("path") or "").strip()
                    content = str(item.get("content") or "")
                    if path and content:
                        promotion_eval_core_blobs[f"candidate::{path}"] = content
                promotion_eval_payload["core_blobs"] = promotion_eval_core_blobs

                promotion_eval_payload["promotion_eval"] = {
                    "req_id": target_req_id,
                    "mode": "promotion_review",
                }

                log.info(
                    "harper.kit invoking promotion eval req=%s files=%d",
                    target_req_id,
                    len(candidate_after_hardening),
                )

                promotion_eval_start = time.time()
                promotion_eval_out = await _post_json("/v1/harper/run", promotion_eval_payload)
                promotion_eval_elapsed = time.time() - promotion_eval_start

                promotion_eval_files = _filter_req_stage_files(promotion_eval_out.get("files") or [], target_req_id)
                log.info(
                    "harper.kit promotion eval completed req=%s elapsed=%.3fs valid_files=%d",
                    target_req_id,
                    promotion_eval_elapsed,
                    len(promotion_eval_files),
                )

                if promotion_eval_files:
                    base_files = out.get("files") or []
                    out["files"] = _merge_file_lists_by_path(base_files, promotion_eval_files)
                    out["promotion_eval_applied"] = True
                    out["promotion_eval_file_count"] = len(promotion_eval_files)
                else:
                    out["promotion_eval_applied"] = False
                    out["promotion_eval_file_count"] = 0
            else:
                out["promotion_eval_applied"] = False
                out["promotion_eval_file_count"] = 0
        else:
            out["promotion_hardener_applied"] = False
            out["promotion_hardener_file_count"] = 0
            out["promotion_eval_applied"] = False
            out["promotion_eval_file_count"] = 0

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
