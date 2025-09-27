# orchestrator/app/constraints/canonicalize.py
# Extract the `tech_constraints:` YAML block from IDEA.md or SPEC.md and write a canonical JSON.
# Updates .clike/tech_constraints.cjson and returns an impact summary for the caller.

from __future__ import annotations
from pathlib import Path
import re, json, yaml, hashlib

FENCE = re.compile(r"(?s)```(?:ya?ml)?\s*(tech_constraints:.*?)```", re.I)

def extract_yaml(text: str) -> dict:
    m = FENCE.search(text)
    if not m:
        idx = text.find("tech_constraints:")
        if idx == -1:
            return {}
        snippet = text[idx:]
        stop = snippet.find("\n## ")
        snippet = snippet if stop == -1 else snippet[:stop]
        return yaml.safe_load(snippet) or {}
    return yaml.safe_load(m.group(1)) or {}

def canonicalize_tc(tc: dict) -> dict:
    out = {"version": "1.0.0", **tc.get("tech_constraints", tc)}
    caps = out.get("capabilities") or out.get("capability") or []
    norm_caps = []
    for c in caps:
        t = (c.get("type") or "").lower()
        v = (c.get("vendor") or "").lower()
        params = c.get("params") or {}
        norm_caps.append({"type": t, "vendor": v, "params": params} | {k:v for k,v in c.items() if k.startswith("x-")})
    out["capabilities"] = norm_caps
    return out

def sync_constraints(md_path: str, output_dir: str) -> dict:
    p = Path(md_path)
    txt = p.read_text(encoding="utf8")
    raw = extract_yaml(txt)
    can = canonicalize_tc(raw)
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    cjson = outdir / "tech_constraints.cjson"
    prev = cjson.read_text(encoding="utf8") if cjson.exists() else ""
    prev_hash = hashlib.sha256(prev.encode("utf8")).hexdigest()
    new = json.dumps(can, ensure_ascii=False, indent=2)
    new_hash = hashlib.sha256(new.encode("utf8")).hexdigest()
    cjson.write_text(new, encoding="utf8")
    return {"updated": prev_hash != new_hash, "path": str(cjson), "hash": new_hash}
