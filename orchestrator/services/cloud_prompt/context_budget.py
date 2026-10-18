"""Bounded project context for cloud models.

A local agent reads the workspace; a cloud model sees only what the prompt carries. These helpers
cut the large Harper documents to what a phase needs (the REQ's slice of PLAN.md and plan.json, a
digest of the whole plan) and render bounded material verbatim, so the cloud receives the same
information without overflowing its context window. Every cut is stated in the prompt.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional, Tuple

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BOLD_REQ_RE = re.compile(r"^\*\*(REQ-\d+)\b")
_REQ_RE = re.compile(r"\bREQ-\d+\b")


def bounded(text: str, max_chars: int) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + f"\n…[truncated by CLike: {len(text) - max_chars} more chars]"


def _req_ids(values: Iterable[str]) -> List[str]:
    return [str(v).strip().upper() for v in values if str(v or "").strip()]


def plan_json_slice(plan_text: str, target: str, include_dependencies: bool = True) -> str:
    """plan.json reduced to the target REQ and its direct dependencies (full objects)."""
    try:
        plan = json.loads(plan_text or "") or {}
    except ValueError:
        return ""
    reqs = [r for r in (plan.get("reqs") or plan.get("req") or []) if isinstance(r, dict)]
    by_id = {str(r.get("id") or "").upper(): r for r in reqs}
    item = by_id.get(str(target or "").upper())
    if not item:
        return ""
    deps = [by_id[d.upper()] for d in (item.get("dependsOn") or []) if str(d).upper() in by_id] if include_dependencies else []
    return json.dumps({"target": item, "dependencies": deps}, indent=2, ensure_ascii=False)


def plan_json_index(plan_text: str) -> str:
    """One line per REQ: the shape of the whole plan without every REQ's detail."""
    try:
        plan = json.loads(plan_text or "") or {}
    except ValueError:
        return ""
    rows = []
    for r in plan.get("reqs") or plan.get("req") or []:
        if not isinstance(r, dict):
            continue
        extra = " ".join(f"{k}={r[k]}" for k in ("release", "change") if r.get(k))
        deps = ",".join(str(d) for d in (r.get("dependsOn") or [])) or "-"
        rows.append(f"- {r.get('id')} [{r.get('status') or 'open'}] {r.get('lane') or ''} deps={deps} {extra} — {r.get('title') or ''}".rstrip())
    return "\n".join(rows)


def plan_md_slice(plan_md: str, req_ids: Iterable[str], max_chars: int = 40_000) -> str:
    """The parts of PLAN.md about the given REQs: their table rows and their sections (a heading
    or a **REQ-x** block naming one of them, up to the next block of the same or higher level)."""
    wanted = set(_req_ids(req_ids))
    if not plan_md or not wanted:
        return ""
    lines = str(plan_md).split("\n")
    out: List[str] = []
    rows = [l for l in lines if l.startswith("|") and set(_REQ_RE.findall(l.split("|")[1] if l.count("|") > 2 else "")) & wanted]
    if rows:
        out += ["REQ table rows:", *rows, ""]
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING_RE.match(line)
        bold = _BOLD_REQ_RE.match(line)
        ids = set(_REQ_RE.findall(line))
        if (heading or bold) and ids & wanted and not line.startswith("|"):
            level = len(heading.group(1)) if heading else 7
            block = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                h = _HEADING_RE.match(nxt)
                if h and len(h.group(1)) <= level:
                    break
                if level == 7 and (h or _BOLD_REQ_RE.match(nxt)):
                    break
                block.append(nxt)
                i += 1
            out += [*block, ""]
            continue
        i += 1
    return bounded("\n".join(out).strip(), max_chars)


def plan_md_digest(plan_md: str, max_chars: int = 30_000) -> str:
    """The outline of PLAN.md (headings) and its REQ table: the whole plan at a glance."""
    lines = str(plan_md or "").split("\n")
    outline = [l for l in lines if _HEADING_RE.match(l) and len(_HEADING_RE.match(l).group(1)) <= 2]
    table = [l for l in lines if l.startswith("| REQ-") or l.startswith("| ID ")]
    return bounded("\n".join(["Outline:", *outline, "", "REQ table:", *table]).strip(), max_chars)


def render_bounded_blobs(
    items: Iterable[Tuple[str, str]], *, title: str, max_each: int, max_total: int,
) -> Tuple[List[str], List[str]]:
    """Verbatim sections for (name, content) pairs within a budget; returns (lines, omitted names)."""
    lines: List[str] = []
    omitted: List[str] = []
    used = 0
    for name, content in items:
        text = str(content or "").strip()
        if not text:
            continue
        room = min(max_each, max_total - used)
        if room < 500:
            omitted.append(name)
            continue
        shown = bounded(text, room)
        used += len(shown)
        lines += [f"### {name} ({title}, verbatim)", shown, ""]
    return lines, omitted
