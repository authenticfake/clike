"""Harper benchmark: run IDEA -> SPEC -> PLAN -> KIT -> EVAL -> GATE on sample projects and
measure promotability, quality, efficiency and governance (see benchmark/README.md).

It talks to a running CLike stack exactly like the VS Code extension does (same payloads,
same core blobs, files written into a real workspace that eval/gate read from disk).

Usage (stack running, CLIKE_API_TOKEN exported):
    python benchmark/run_benchmark.py --model openai:gpt-6.1-sol --max-reqs 2 [--projects pingboard,shortlink]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = "extensions/vscode/templates/harper-init/"
ORCH = os.getenv("CLIKE_ORCHESTRATOR_URL", "http://localhost:8080")
TIMEOUT_S = float(os.getenv("CLIKE_BENCH_TIMEOUT_S", "1800"))


# --------------------------------------------------------------------------- workspace


def _projects_dir() -> Path:
    env = REPO / "docker" / ".env"
    if os.getenv("CLIKE_PROJECTS_DIR"):
        return Path(os.environ["CLIKE_PROJECTS_DIR"])
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("CLIKE_PROJECTS_DIR="):
            return Path(line.split("=", 1)[1].strip())
    sys.exit("CLIKE_PROJECTS_DIR is not set (docker/.env): workspaces must be visible to the containers")


def _tracked_template_files() -> List[str]:
    # -z: no quoting of non-ASCII names (the template has a file with an em dash)
    out = subprocess.check_output(["git", "ls-files", "-z", TEMPLATE], cwd=REPO).decode().split("\0")
    return [f for f in out if f and "/vendor/" not in f]


def prepare_workspace(root: Path, idea_md: str) -> Path:
    """A fresh project like `CLike: init` would create (tracked template files only)."""
    if root.exists():
        shutil.rmtree(root)
    for rel in _tracked_template_files():
        dst = root / rel[len(TEMPLATE):]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, dst)
    harper = root / "docs" / "harper"
    for stale in ("SPEC.md",):  # template placeholders the phases regenerate
        (harper / stale).unlink(missing_ok=True)
    (harper / "IDEA.md").write_text(idea_md, encoding="utf-8")
    return root


_TC_RE = re.compile(r"```ya?ml\s*\n(.*?tech_constraints.*?)```", re.S | re.I)


def split_tech_constraints(idea_md: str) -> tuple[str, Optional[str]]:
    """Like the extension: TECH_CONSTRAINTS.yaml is extracted from IDEA.md for /spec."""
    m = _TC_RE.search(idea_md)
    if not m:
        return idea_md, None
    return idea_md[: m.start()] + idea_md[m.end():], m.group(1).strip() + "\n"


def core_blobs(root: Path, names: List[str]) -> Dict[str, str]:
    harper = root / "docs" / "harper"
    blobs: Dict[str, str] = {}
    for name in names:
        p = harper / name
        if p.is_file():
            blobs[name] = p.read_text(encoding="utf-8")
    for p in sorted((harper / "lane-guides").glob("*.md")) if (harper / "lane-guides").is_dir() else []:
        blobs[f"docs/harper/lane-guides/{p.name}"] = p.read_text(encoding="utf-8")
    for p in sorted((root / ".clike").rglob("*")):
        if p.is_file() and p.suffix in {".md", ".yaml", ".yml", ".json"}:
            blobs[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return blobs


def write_files(root: Path, files: List[Dict[str, Any]]) -> List[str]:
    written = []
    for f in files or []:
        rel = str(f.get("path") or "").lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(f.get("content") or "", encoding="utf-8")
        written.append(rel)
    return written


# --------------------------------------------------------------------------- calls


class Client:
    def __init__(self, token: str):
        self.http = httpx.Client(timeout=TIMEOUT_S, headers={"Authorization": f"Bearer {token}"})

    def phase(self, phase: str, body: Dict[str, Any]) -> Dict[str, Any]:
        t = time.time()
        try:
            r = self.http.post(f"{ORCH}/v1/harper/{phase}", json=body)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:500]}
        except httpx.HTTPError as exc:
            return {"phase": phase, "status": 0, "seconds": round(time.time() - t, 1), "error": f"{type(exc).__name__}: {exc}"}
        out = data.get("out", data) if isinstance(data, dict) else {}
        return {
            "phase": phase,
            "status": r.status_code,
            "seconds": round(time.time() - t, 1),
            "ok": out.get("ok") if isinstance(out, dict) else None,
            "files": (out.get("files") if isinstance(out, dict) else None) or [],
            "usage": (out.get("usage") if isinstance(out, dict) else None) or {},
            "warnings": (out.get("warnings") if isinstance(out, dict) else None) or [],
            "errors": (out.get("errors") if isinstance(out, dict) else None) or [],
            "detail": str(data.get("detail"))[:800] if isinstance(data, dict) and data.get("detail") else None,
        }

    def check(self, kind: str, root: Path, project: str, req: str) -> Dict[str, Any]:
        profile = f"runs/kit/{req}/ci/LTC.json"
        ltc_path = root / profile
        if not ltc_path.is_file():
            return {"status": None, "skipped": "no LTC.json"}
        params = {"profile": profile, "project_root": str(root), "req_id": req, "project_name": project}
        url = f"{ORCH}/v1/{'eval/run' if kind == 'eval' else 'gate/check'}"
        t = time.time()
        try:
            r = self.http.post(url, params=params, json={"ltc": json.loads(ltc_path.read_text(encoding="utf-8"))})
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": 0, "error": str(exc)}
        return {
            "status": r.status_code,
            "seconds": round(time.time() - t, 1),
            "result": data.get("gate") or data.get("status") if isinstance(data, dict) else None,
            "passed": data.get("passed") if isinstance(data, dict) else None,
            "failed": data.get("failed") if isinstance(data, dict) else None,
            "reason_code": data.get("reason_code") if isinstance(data, dict) else None,
            "detail": str(data.get("detail"))[:400] if isinstance(data, dict) and data.get("detail") else None,
        }


# --------------------------------------------------------------------------- local agent runner

_SECRET_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "OPENAI_PROJECT_ID", "OPENAI_ORG_ID",
               "CLIKE_API_TOKEN")


def _snapshot(root: Path) -> Dict[str, float]:
    return {p.relative_to(root).as_posix(): p.stat().st_mtime for p in root.rglob("*")
            if p.is_file() and ".git/" not in p.as_posix()}


def run_agent_phase(client: "Client", phase: str, body: Dict[str, Any], root: Path, executor: str, agent_model: str) -> Dict[str, Any]:
    """Like the extension with execution = agent: package -> CLI in the workspace -> /local-agent/complete."""
    t0 = time.time()
    body = {**body, "executionPreference": "local_agent_only", "localAgentExecutor": executor,
            "localAgentCapabilities": {executor: {"available": True}}}
    r = client.http.post(f"{ORCH}/v1/harper/{phase}", json=body)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:500]}
    out = data.get("out", data) if isinstance(data, dict) else {}
    pkg = (out or {}).get("local_agent") or {}
    if r.status_code != 200 or not pkg:
        return {"phase": phase, "status": r.status_code, "ok": False, "seconds": round(time.time() - t0, 1), "files": [],
                "usage": {}, "warnings": [], "errors": (out or {}).get("errors") or [], "detail": str((data or {}).get("detail"))[:500] if isinstance(data, dict) else None}
    package_paths = set()
    for f in pkg.get("package_files") or []:
        items = f if isinstance(f, list) else [f]
        for item in items:
            if isinstance(item, dict) and item.get("path") and item.get("content") is not None:
                package_paths.add(item["path"])
                write_files(root, [item])
    before = _snapshot(root)
    inv = pkg["invocation"]
    args = list(inv["args"]) + (["--model", agent_model] if agent_model else [])
    if executor == "claude_code":
        args += ["--output-format", "json"]
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_ENV}
    cmd = ["claude" if executor == "claude_code" else "codex", *args]
    stdin = None
    if inv.get("prompt_transport") == "stdin":
        stdin = pkg["prompt_content"]
    else:
        cmd.append(pkg["prompt_content"])
    t_agent = time.time()
    try:
        proc = subprocess.run(cmd, cwd=root, env=env, input=stdin, capture_output=True, text=True,
                              timeout=int(inv.get("timeout_seconds") or 1800))
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr = 124, str(exc.stdout or ""), "timeout"
    agent_seconds = round(time.time() - t_agent, 1)
    usage = {}
    try:
        env_json = json.loads(stdout)
        u = env_json.get("usage") or {}
        usage = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                 "total_tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
                 + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
                 "cost_usd_equivalent": env_json.get("total_cost_usd")}
    except (ValueError, AttributeError):
        pass
    after = _snapshot(root)
    changed = [p for p, m in after.items() if p not in package_paths and (p not in before or before[p] != m)]
    files = [{"path": p, "content": (root / p).read_text(encoding="utf-8", errors="replace")} for p in sorted(changed)]
    done = {"phase": phase, "req_id": (body.get("kit") or {}).get("targets", [None])[0] if isinstance(body.get("kit"), dict) else None,
            "runId": body.get("runId"), "executionPreference": "local_agent_only", "localAgentExecutor": executor,
            "allowed_write_roots": pkg.get("allowed_write_roots") or [], "forbidden_paths": pkg.get("forbidden_paths") or [],
            "infra_profile": pkg.get("infra_profile"), "runtime_service_profile": pkg.get("runtime_service_profile"),
            "cloud_provisioning_profile": pkg.get("cloud_provisioning_profile"),
            "available_capabilities": pkg.get("available_capabilities"), "capability_metadata": pkg.get("capability_metadata"),
            "exit_code": exit_code, "stdout": stdout[-4000:], "stderr": stderr[-4000:], "files": files}
    c = client.http.post(f"{ORCH}/v1/harper/local-agent/complete", json=done)
    cd = c.json() if c.headers.get("content-type", "").startswith("application/json") else {}
    co = cd.get("out", cd) if isinstance(cd, dict) else {}
    return {"phase": phase, "status": c.status_code, "ok": co.get("ok"), "seconds": round(time.time() - t0, 1),
            "agent_seconds": agent_seconds, "agent_exit": exit_code, "files": [],  # already in the workspace
            "agent_written": [f["path"] for f in files], "usage": usage,
            "warnings": (co.get("warnings") or [])[:10], "errors": (co.get("errors") or [])[:6],
            "detail": str(cd.get("detail"))[:500] if isinstance(cd, dict) and cd.get("detail") else None}


# --------------------------------------------------------------------------- run


def _base(project: str, model: str, run_id: str, root: Path) -> Dict[str, Any]:
    return {
        "project_id": f"bench_{project}",
        "project_name": project,
        "mode": "harper",
        "model": model,
        "docRoot": "docs/harper",
        "attachments": [],
        "flags": {},
        "executionPreference": "cloud_only",
        "runId": run_id,
        "repository_context": {"repo_root": str(root), "workspace_folder": str(root), "git_detected": False,
                               "local_snapshot_verified": True, "github_verified": False},
    }


def _stack_compliance(root: Path, req: str, constraints: Optional[str]) -> Optional[bool]:
    """Does generated source use the framework declared in TECH_CONSTRAINTS (when one is declared)?"""
    if not constraints:
        return None
    frameworks = re.findall(r"framework:\s*([A-Za-z0-9_.-]+)", constraints)
    frameworks = [f.lower() for f in frameworks if f.lower() not in {"none", "unknown"}]
    if not frameworks:
        return None
    src = root / "runs" / "kit" / req / "src"
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore").lower() for p in src.rglob("*") if p.is_file()) if src.is_dir() else ""
    return bool(text) and any(f in text for f in frameworks)


def run_project(client: Client, project: Dict[str, Any], model: str, max_reqs: int, ws_root: Path, stamp: str,
                runner: str = "cloud", executor: str = "claude_code", agent_model: str = "") -> Dict[str, Any]:
    name = project["name"]
    idea_full = (REPO / project["idea"]).read_text(encoding="utf-8")
    root = prepare_workspace(ws_root / name, idea_full)
    idea_md, constraints = split_tech_constraints(idea_full)
    if constraints:
        (root / "docs/harper/TECH_CONSTRAINTS.yaml").write_text(constraints, encoding="utf-8")
    res: Dict[str, Any] = {"project": name, "workspace": str(root), "runner": runner, "steps": [], "reqs": []}

    def step(phase: str, extra: Dict[str, Any], core: List[str]) -> Dict[str, Any]:
        body = {**_base(name, model, f"bench-{stamp}-{name}-{phase}", root), "cmd": phase, "phase": phase,
                "messages": [{"role": "user", "content": f"/{phase}"}], "core": core,
                "core_blobs": core_blobs(root, core), **extra}
        if runner == "agent":
            out = run_agent_phase(client, phase, body, root, executor, agent_model)
            out["written"] = out.get("agent_written") or []
        else:
            out = client.phase(phase, body)
            out["written"] = write_files(root, out.get("files"))
        res["steps"].append({k: v for k, v in out.items() if k != "files"})
        print(f"  {name} {phase:<5} status={out['status']} ok={out.get('ok')} files={len(out['written'])} "
              f"tokens={(out.get('usage') or {}).get('total_tokens')} {out.get('seconds')}s "
              f"{(out.get('detail') or '')[:160]}", flush=True)
        return out

    tc = ["TECH_CONSTRAINTS.yaml"]
    step("spec", {"idea_md": idea_md}, ["IDEA.md", *tc])
    if not (root / "docs/harper/SPEC.md").is_file():
        return res
    step("plan", {}, ["IDEA.md", "SPEC.md", *tc])
    plan_path = root / "docs/harper/plan.json"
    if not plan_path.is_file():
        return res
    try:
        reqs = [r["id"] for r in json.loads(plan_path.read_text(encoding="utf-8")).get("reqs", [])]
    except ValueError:
        res["plan_json_invalid"] = True
        return res
    res["plan_reqs"] = len(reqs)
    for req in reqs[:max_reqs]:
        kit = step("kit", {"kit": {"targets": [req]}, "todo_ids": [req], "rag_strategy": "deps_only"},
                   ["IDEA.md", "SPEC.md", "PLAN.md", "plan.json", *tc])
        entry = {"req": req, "kit_status": kit["status"], "kit_ok": kit.get("ok"), "kit_files": len(kit["written"]),
                 # only meaningful when the KIT was accepted and written
                 "stack_compliant": _stack_compliance(root, req, constraints) if kit.get("ok") and kit["written"] else None}
        if kit.get("ok") and kit["written"]:
            entry["eval"] = client.check("eval", root, name, req)
            entry["gate"] = client.check("gate", root, name, req)
        res["reqs"].append(entry)
        print(f"  {name} {req} eval={entry.get('eval', {}).get('result')} gate={entry.get('gate', {}).get('result')} "
              f"stack_ok={entry['stack_compliant']}", flush=True)
    return res


# --------------------------------------------------------------------------- report


def _pricing(model: str) -> Optional[Dict[str, float]]:
    catalog = yaml.safe_load((REPO / "configs/models.yaml").read_text(encoding="utf-8"))
    for m in catalog.get("models", []):
        if m.get("id") == model and m.get("pricing"):
            return m["pricing"]
    return None


def summarize(results: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    price = _pricing(model)
    rows, tot = [], {"tokens": 0, "seconds": 0.0, "reqs": 0, "kit_ok": 0, "eval_pass": 0, "gate_pass": 0, "stack_ok": 0,
                     "stack_checked": 0, "rejected": 0}
    for r in results:
        steps = r["steps"]
        tokens = sum(int((s.get("usage") or {}).get("total_tokens") or 0) for s in steps)
        seconds = sum(float(s.get("seconds") or 0) for s in steps)
        rejected = sum(1 for s in steps if s.get("status") != 200 or s.get("ok") is False)
        kit_ok = sum(1 for q in r["reqs"] if q.get("kit_ok"))
        eval_pass = sum(1 for q in r["reqs"] if str((q.get("eval") or {}).get("result") or "").upper().startswith("PASS"))
        gate_pass = sum(1 for q in r["reqs"] if str((q.get("gate") or {}).get("result") or "").upper() == "PASS")
        stack = [q.get("stack_compliant") for q in r["reqs"] if q.get("stack_compliant") is not None]
        phases = {s["phase"]: ("ok" if s.get("status") == 200 and s.get("ok") is not False else f"✗ {s.get('status')}") for s in steps if s["phase"] != "kit"}
        rows.append({"project": r["project"], "spec": phases.get("spec", "—"), "plan": phases.get("plan", "—"),
                     "plan_reqs": r.get("plan_reqs"), "reqs_run": len(r["reqs"]), "kit_ok": kit_ok, "eval_pass": eval_pass,
                     "gate_pass": gate_pass, "stack_ok": f"{sum(stack)}/{len(stack)}" if stack else "n/a",
                     "rejected_steps": rejected, "tokens": tokens, "minutes": round(seconds / 60, 1)})
        for k, v in (("tokens", tokens), ("seconds", seconds), ("reqs", len(r["reqs"])), ("kit_ok", kit_ok), ("eval_pass", eval_pass),
                     ("gate_pass", gate_pass), ("stack_ok", sum(stack)), ("stack_checked", len(stack)), ("rejected", rejected)):
            tot[k] += v
    cost = None
    if price:
        # without an input/output split per step we bound the cost with the output price
        cost = round(tot["tokens"] / 1000 * float(price.get("output_per_1k", 0)), 2)
    return {"model": model, "rows": rows, "totals": tot, "cost_upper_bound_usd": cost,
            "tokens_per_promoted_req": (tot["tokens"] // tot["gate_pass"]) if tot["gate_pass"] else None}


def render_md(summary: Dict[str, Any], stamp: str) -> str:
    t = summary["totals"]
    runner = "agent" if str(summary["model"]).startswith("agent:") else "cloud"
    lines = [f"# Harper benchmark — {stamp}", "", f"Model: `{summary['model']}` · runner: {runner}", "",
             "| Project | SPEC | PLAN | REQs in plan | REQs run | KIT ok | EVAL pass | GATE pass | Stack | Rejected steps | Tokens | Minutes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in summary["rows"]:
        lines.append(f"| {r['project']} | {r['spec']} | {r['plan']} | {r['plan_reqs'] if r['plan_reqs'] is not None else '—'} | {r['reqs_run']} | "
                     f"{r['kit_ok']} | {r['eval_pass']} | {r['gate_pass']} | {r['stack_ok']} | {r['rejected_steps']} | {r['tokens']} | {r['minutes']} |")
    lines += ["", f"**Promotability:** {t['gate_pass']}/{t['reqs']} REQs pass the gate; {t['eval_pass']}/{t['reqs']} pass eval; "
              f"{t['kit_ok']}/{t['reqs']} KITs accepted.",
              f"**Quality:** stack compliance {t['stack_ok']}/{t['stack_checked']}.",
              f"**Efficiency:** {t['tokens']} tokens, {round(t['seconds'] / 60, 1)} min; tokens per promoted REQ: "
              f"{summary['tokens_per_promoted_req'] or 'n/a'}; cost upper bound: "
              f"{('$' + str(summary['cost_upper_bound_usd'])) if summary['cost_upper_bound_usd'] is not None else 'n/a (no pricing in catalog)'}.",
              f"**Governance:** {t['rejected']} steps rejected by validation or contracts."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="openai:gpt-6.1-sol")
    ap.add_argument("--max-reqs", type=int, default=2, help="KIT/EVAL/GATE only the first N REQs of each plan (cost cap)")
    ap.add_argument("--projects", default="", help="comma-separated subset of benchmark/projects.yaml")
    ap.add_argument("--runner", choices=["cloud", "agent"], default="cloud",
                    help="cloud: model via the gateway API; agent: local CLI agent in the workspace (like Execution = agent)")
    ap.add_argument("--executor", choices=["claude_code", "gpt_codex"], default="claude_code")
    ap.add_argument("--agent-model", default="", help="model passed to the agent CLI (--model); empty = CLI default")
    ap.add_argument("--resummarize", default="", help="rebuild SUMMARY.md from an existing results directory (no calls)")
    args = ap.parse_args()
    if args.resummarize:
        out_dir = Path(args.resummarize)
        data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
        for proj in data["projects"]:
            for q in proj["reqs"]:
                if not q.get("kit_ok"):
                    q["stack_compliant"] = None
        summary = summarize(data["projects"], data["summary"]["model"])
        data["summary"] = summary
        (out_dir / "results.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / "SUMMARY.md").write_text(render_md(summary, out_dir.name), encoding="utf-8")
        print(render_md(summary, out_dir.name))
        return
    token = os.getenv("CLIKE_API_TOKEN") or sys.exit("export CLIKE_API_TOKEN")
    projects = yaml.safe_load((REPO / "benchmark/projects.yaml").read_text(encoding="utf-8"))["projects"]
    if args.projects:
        wanted = set(args.projects.split(","))
        projects = [p for p in projects if p["name"] in wanted]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ws_root = _projects_dir() / "clike-bench" / stamp
    client = Client(token)
    results = []
    for p in projects:
        print(f"== {p['name']} ({p['complexity']})", flush=True)
        results.append(run_project(client, p, args.model, args.max_reqs, ws_root, stamp,
                                   runner=args.runner, executor=args.executor, agent_model=args.agent_model))
    label = args.model if args.runner == "cloud" else f"agent:{args.executor}{(':' + args.agent_model) if args.agent_model else ''}"
    summary = summarize(results, label)
    out_dir = REPO / "benchmark" / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps({"summary": summary, "projects": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(render_md(summary, stamp), encoding="utf-8")
    print(render_md(summary, stamp))
    print(f"results: {out_dir}  workspaces: {ws_root}")


if __name__ == "__main__":
    main()
