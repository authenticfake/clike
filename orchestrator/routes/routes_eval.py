from __future__ import annotations
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from eval_runner import EvalReport, EvalRunner

router = APIRouter()
log = logging.getLogger("routes_eval")


class EvalRunRequest(BaseModel):
    profile: Optional[str] = None
    project_root: Optional[str] = None
    req_id: Optional[str] = None
    mode: Optional[str] = None
    verdict: Optional[str] = None
    ltc: Optional[Dict[str, Any]] = None
    project_name: Optional[str] = None

    class Config:
        extra = "ignore"


class GateCheckRequest(BaseModel):
    profile: Optional[str] = None
    project_root: Optional[str] = None
    mode: Optional[str] = "auto"
    verdict: Optional[str] = None
    req_id: Optional[str] = None
    promote: Optional[bool] = False
    ltc: Optional[Dict[str, Any]] = None
    project_name: Optional[str] = None

    class Config:
        extra = "ignore"


_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _sanitize_project_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    value = name.strip()
    if not _PROJECT_NAME_RE.match(value):
        return None
    return value


def _resolve_project_root_from_env(project_name: Optional[str]) -> Optional[Path]:
    dev = os.getenv("DEV_FOLDER", "").strip()
    pname = _sanitize_project_name(project_name)
    if not dev or not pname:
        return None

    candidate = Path(dev) / pname
    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        return None
    return None


def _resolve_project_root(project_root: Optional[str], project_name: Optional[str]) -> Path:
    env_root = _resolve_project_root_from_env(project_name)
    if env_root is not None:
        return env_root

    if project_root:
        p = Path(project_root)
        return (p if p.is_absolute() else Path.cwd() / p).resolve()

    return Path.cwd().resolve()


_RUNTIME_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "mix.exs",
    "pubspec.yaml",
    "deno.json",
    "RUNTIME_MANIFEST.md",
    "Makefile",
    "CMakeLists.txt",
}

_COMPOSITION_ROOT_NAMES = {
    "app.py",
    "main.py",
    "server.py",
    "asgi.py",
    "wsgi.py",
    "index.js",
    "main.js",
    "server.js",
    "app.js",
    "index.ts",
    "main.ts",
    "server.ts",
    "app.ts",
    "index.tsx",
    "main.tsx",
    "App.tsx",
    "index.jsx",
    "main.jsx",
    "App.jsx",
    "index.html",
    "main.go",
    "Program.cs",
    "Startup.cs",
    "Main.java",
    "Application.java",
    "main.rs",
    "lib.rs",
    "main.rb",
    "config.ru",
}


def _load_file_requirements(project_root: Path, req_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not req_id:
        return None

    candidates = [
        project_root / "runs" / "kit" / req_id / "ci" / "FILE_REQUIREMENTS.json",
        project_root / "runs" / "kit" / req_id / "docs" / "FILE_REQUIREMENTS.json",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            log.warning("gate.file_requirements unreadable path=%s", candidate, exc_info=True)
            return None
    return None


def _has_runtime_manifest_under_candidate(req_root: Path) -> bool:
    search_roots = [req_root / "src"]
    # Some ecosystems keep the promotion-ready manifest at the candidate package root.
    search_roots.append(req_root)

    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if "ci" in path.relative_to(req_root).parts:
                continue
            if path.name in _RUNTIME_MANIFEST_NAMES:
                return True
            if path.suffix.lower() in {".csproj", ".fsproj", ".vbproj", ".sln", ".mpr"}:
                return True
    return False


def _has_composition_root_under_candidate(req_root: Path) -> bool:
    src_root = req_root / "src"
    if not src_root.exists():
        return False

    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _COMPOSITION_ROOT_NAMES:
            return True
        if path.name.endswith("Application.java"):
            return True
        if path.suffix.lower() in {".mpr"}:
            return True
    return False


def _required_output_blockers(project_root: Path, req_id: Optional[str]) -> List[Dict[str, str]]:
    file_requirements = _load_file_requirements(project_root, req_id)
    if not file_requirements or not req_id:
        return []

    req_root = project_root / "runs" / "kit" / req_id
    required_outputs = file_requirements.get("required_outputs") or []
    blockers: List[Dict[str, str]] = []

    for item in required_outputs:
        if not item or item.get("required") is not True:
            continue

        role = str(item.get("role") or "").strip()

        if role == "execution_area_runtime_manifest" and not _has_runtime_manifest_under_candidate(req_root):
            blockers.append({
                "role": role,
                "reason": "FILE_REQUIREMENTS requires a promotion-ready runtime manifest for a runnable execution area, but no ecosystem-native manifest was found outside ci/.",
            })

        if role in {"solution_composition_root", "module_launcher"} and not _has_composition_root_under_candidate(req_root):
            blockers.append({
                "role": role,
                "reason": "FILE_REQUIREMENTS requires a runnable composition root/launcher, but no cross-language composition entry was found under candidate src/.",
            })

    return blockers


def _manual_verdict(
    mode: Optional[str],
    body_verdict: Optional[str],
    query_verdict: Optional[str],
) -> Optional[str]:
    if (mode or "auto").lower() != "manual":
        return None
    return body_verdict or query_verdict


def _merge_eval_args(
    *,
    profile_q: Optional[str],
    project_root_q: Optional[str],
    project_name_q: Optional[str],
    mode_q: Optional[str],
    verdict_q: Optional[str],
    req_id_q: Optional[str],
    body: Optional[EvalRunRequest],
) -> EvalRunRequest:
    body = body or EvalRunRequest()
    mode = (body.mode or mode_q or "auto").lower()
    return EvalRunRequest(
        profile=body.profile or profile_q,
        project_root=body.project_root or project_root_q,
        mode=mode,
        verdict=_manual_verdict(mode, body.verdict, verdict_q),
        req_id=body.req_id or req_id_q,
        project_name=body.project_name or project_name_q,
        ltc=body.ltc if body.ltc else None,
    )


def _merge_gate_args(
    *,
    profile_q: Optional[str],
    project_root_q: Optional[str],
    project_name_q: Optional[str],
    mode_q: Optional[str],
    verdict_q: Optional[str],
    req_id_q: Optional[str],
    promote_q: Optional[bool],
    body: Optional[GateCheckRequest],
) -> GateCheckRequest:
    body = body or GateCheckRequest()
    mode = (body.mode or mode_q or "auto").lower()
    return GateCheckRequest(
        profile=body.profile or profile_q,
        project_root=body.project_root or project_root_q,
        mode=mode,
        verdict=_manual_verdict(mode, body.verdict, verdict_q),
        req_id=body.req_id or req_id_q,
        ltc=body.ltc if body.ltc else None,
        project_name=body.project_name or project_name_q,
        promote=bool(body.promote if body.promote is not None else promote_q),
    )


def _case_payload(case: Any) -> Dict[str, Any]:
    return {
        "name": case.name,
        "passed": case.passed,
        "code": case.code,
        "stdout": case.stdout,
        "stderr": case.stderr,
        "cmd": case.cmd,
        "cwd": case.cwd,
        "expect": case.expect,
        "blocked": case.blocked,
        "blocking": case.blocking,
    }


def _eval_payload(rep: EvalReport, req_id: Optional[str]) -> Dict[str, Any]:
    blocking_failures = [
        c.name for c in rep.cases
        if not c.passed and c.blocking
    ]
    environment_blocked = [
        c.name for c in rep.cases
        if not c.passed and c.blocked
    ]
    quality_passed = rep.status == "PASS" and not blocking_failures
    promotable = quality_passed and not environment_blocked and rep.blocked == 0 and rep.warnings == 0

    return {
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "status": rep.status,
        "passed": promotable,
        "execution_ok": not environment_blocked,
        "quality_passed": quality_passed,
        "promotable": promotable,
        "blocking_failures": blocking_failures,
        "environment_blocked": environment_blocked,
        "failed": rep.failed,
        "passed_count": rep.passed,
        "blocked_count": rep.blocked,
        "warning_count": rep.warnings,
        "junit": rep.junit_path,
        "json": rep.json_path or f"runs/eval/{req_id or rep.req_id or 'REQ-UNKNOWN'}",
        "cases": [_case_payload(c) for c in rep.cases],
    }


@router.post("/v1/eval/run")
def eval_run(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    project_name: Optional[str] = Query(default=None),
    payload: Optional[EvalRunRequest] = Body(default=None),
):
    args = _merge_eval_args(
        profile_q=profile,
        project_root_q=project_root,
        project_name_q=project_name,
        mode_q=mode,
        verdict_q=verdict,
        req_id_q=req_id,
        body=payload,
    )

    log.info(
        "eval_run profile=%s project_root=%s mode=%s req_id=%s project_name=%s inline_ltc=%s",
        args.profile,
        args.project_root,
        args.mode,
        args.req_id,
        args.project_name,
        bool(args.ltc),
    )

    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(
            status_code=422,
            detail="Provide either 'ltc' inline OR 'profile' + 'project_root'",
        )

    prj = _resolve_project_root(args.project_root, args.project_name)
    runner = EvalRunner(prj)

    try:
        rep = runner.run_profile(
            profile=args.profile or "LTC.json",
            ltc=args.ltc,
            mode=args.mode or "auto",
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("eval_run unexpected")
        raise HTTPException(status_code=500, detail=f"eval_run error: {exc}") from exc

    return _eval_payload(rep, args.req_id)


@router.post("/v1/gate/check")
def gate_check(
    profile: Optional[str] = Query(default=None),
    project_root: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default="auto"),
    verdict: Optional[str] = Query(default=None),
    req_id: Optional[str] = Query(default=None),
    promote: Optional[bool] = Query(default=False),
    project_name: Optional[str] = Query(default=None),
    payload: Optional[GateCheckRequest] = Body(default=None),
):
    args = _merge_gate_args(
        profile_q=profile,
        project_root_q=project_root,
        project_name_q=project_name,
        mode_q=mode,
        verdict_q=verdict,
        req_id_q=req_id,
        promote_q=promote,
        body=payload,
    )

    log.info(
        "gate_check profile=%s project_root=%s mode=%s req_id=%s promote=%s inline_ltc=%s",
        args.profile,
        args.project_root,
        args.mode,
        args.req_id,
        args.promote,
        bool(args.ltc),
    )

    if not args.ltc and (not args.profile or not args.project_root):
        raise HTTPException(
            status_code=422,
            detail="Provide either 'ltc' inline OR 'profile' + 'project_root'",
        )

    prj = _resolve_project_root(args.project_root, args.project_name)
    runner = EvalRunner(prj)

    try:
        rep = runner.run_profile(
            profile=args.profile or "LTC.json",
            ltc=args.ltc,
            mode=args.mode or "auto",
            verdict=args.verdict,
            req_id=args.req_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("gate_check unexpected")
        raise HTTPException(status_code=500, detail=f"gate_check error: {exc}") from exc

    structural_blockers = _required_output_blockers(prj, args.req_id or rep.req_id)
    effective_status = "FAIL" if structural_blockers else rep.status
    hard_gate = "PASS" if effective_status == "PASS" else "FAIL"

    reason_code = "GATE_PASS"
    if structural_blockers:
        reason_code = "GATE_BLOCKED_REQUIRED_OUTPUTS_MISSING"
    elif rep.status == "PASS_WITH_WARNINGS":
        reason_code = "GATE_BLOCKED_WARNINGS_PRESENT"
    elif rep.status == "FAIL":
        reason_code = "GATE_BLOCKED_FAILED_CHECKS"
    else:
        reason_code = f"GATE_BLOCKED_STATUS_{rep.status}"

    return {
        "gate": hard_gate,
        "status": effective_status,
        "raw_eval_status": rep.status,
        "reason_code": reason_code,
        "structural_blockers": structural_blockers,
        "profile": rep.profile,
        "req_id": rep.req_id,
        "mode": rep.mode,
        "passed": effective_status == "PASS",
        "failed": rep.failed,
        "passed_count": rep.passed,
        "blocked_count": rep.blocked,
        "warning_count": rep.warnings,
        "json": f"runs/gate/{args.req_id or rep.req_id or 'REQ-UNKNOWN'}",
        "promote": bool(args.promote) if args.promote else None,
        "promote_info": None,
        "cases": [_case_payload(c) for c in rep.cases],
    }