# EVAL runner adapters. Runs Harper "phase gates" and global EDD gates.
# Trigger points:
#  - Phase gates (G0/G1/G2): after SPEC/PLAN/KIT generation (routes /spec, /plan, /kit).
#  - Global gates (EDD): after build iterations (/build-next).
# Behavior:
#  - Execute scripts, parse JSON summaries, return ok + summary.
#  - Non-blocking subprocess return code (interpret JSON content).
#  - Routes/services decide advancement and persist manifests.

import json, subprocess, pathlib
from typing import Dict, Any, List

def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=False)

def run_phase_gates() -> Dict[str, Any]:
    out = {"ok": True, "summary": {}}
    agg = pathlib.Path("eval/out/phase_summary.json")
    try:
        _run(["bash","eval/phase/run_phase_gates.sh"])
        if agg.exists():
            summary = json.loads(agg.read_text(encoding="utf-8"))
            out["summary"] = summary
            out["ok"] = bool(summary.get("ok", True))
    except Exception as e:
        out["ok"] = False
        out["summary"] = {"error": str(e)}
    return out

def run_global_gates() -> Dict[str, Any]:
    out = {"ok": True, "summary": {}}
    agg = pathlib.Path("eval/out/summary.json")
    try:
        _run(["bash","eval/scripts/run_all.sh"])
        if agg.exists():
            summary = json.loads(agg.read_text(encoding="utf-8"))
            out["summary"] = summary
            out["ok"] = bool(summary.get("gate_pass", True))
    except Exception as e:
        out["ok"] = False
        out["summary"] = {"error": str(e)}
    return out

def run_build_gates() -> Dict[str, Any]:
    out = {"ok": True, "summary": {}}
    agg = pathlib.Path("eval/out/build_summary.json")
    try:
        _run(["bash","eval/build/run_build_gates.sh"])
        if agg.exists():
            summary = json.loads(agg.read_text(encoding="utf-8"))
            out["summary"] = summary
            out["ok"] = bool(summary.get("ok", True))
    except Exception as e:
        out["ok"] = False
        out["summary"] = {"error": str(e)}
    return out