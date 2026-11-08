"""Quality context of a Harper phase: the REQ capacity profile and the journey scenarios.

Same text for every executor: the cloud prompt gets it at the end of the user message, a local agent
(Claude Code, Codex) in its package prompt and as a package file (services/context_sources.py). The
scenarios come from the project's journey skills (`.clike/skills/journey-*/SKILL.md`, frontmatter
`scenarios`: `ID | required|conditional | Title | EARS statement`): the SPEC includes or excludes each
scenario a use case implies, the PLAN gives each included scenario to one REQ (`reqs[].scenarios`),
the KIT proves each with a blocking check, and the eval (`acceptance::coverage`) blocks a REQ whose
scenario has no proof. A project without journey skills (planned before them) gets the profile only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.capabilities import _extract_frontmatter

SCENARIO_LINE = re.compile(
    r"^\s*([A-Z]{2,6}-\d{2,3})\s*\|\s*(required|conditional)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$", re.IGNORECASE
)
SCENARIO_ID = re.compile(r"\b([A-Z]{2,6}-\d{2,3})\b")

# Unit of work per executor capacity (docs/_private analysis 51/52): the plan sizes REQs on it.
CAPACITY_PROFILES: Dict[str, Dict[str, str]] = {
    "C1": {
        "executor": "cloud, one generation call per REQ (bounded output)",
        "unit": "one REQ of one domain",
        "criteria": "6–8 acceptance criteria",
        "size": "about 2–3k lines of source and tests",
        "domains": "1 business domain",
    },
    "C2": {
        "executor": "coding agent (multi-turn, runs its own checks)",
        "unit": "one vertical slice: API, data, UI and tests of the same capability in one REQ",
        "criteria": "10–14 acceptance criteria",
        "size": "about 3–6k lines of source and tests",
        "domains": "up to 3 business domains",
    },
    "C3": {
        "executor": "long-running coding agent, or a cloud loop driven by CLike, one feature per step",
        "unit": "one epic with an internal feature list (each feature a C1/C2-sized slice)",
        "criteria": "5–15 features; every feature lists its acceptance and scenarios",
        "size": "no fixed cap per epic; each feature stays within the C2 size",
        "domains": "one bounded context per epic",
    },
}


def resolve_capacity_profile(payload: Dict[str, Any], execution_mode: str) -> str:
    """The explicit profile of the run (`capacityProfile`: C1|C2|C3), else C2 for a local agent and
    C1 for the cloud."""
    flags = payload.get("flags") if isinstance(payload.get("flags"), dict) else {}
    explicit = str(payload.get("capacityProfile") or flags.get("capacityProfile") or "").strip().upper()
    if explicit in CAPACITY_PROFILES:
        return explicit
    return "C2" if str(execution_mode or "").strip() == "local_agent" else "C1"


def _skill_texts(core_blobs: Dict[str, Any], workspace_root: Optional[Path]) -> Dict[str, str]:
    texts: Dict[str, str] = {}
    for raw, content in (core_blobs or {}).items():
        rel = str(raw or "").replace("\\", "/").lstrip("/")
        m = re.match(r"^\.clike/skills/(journey-[a-z0-9-]+)/SKILL\.md$", rel, re.IGNORECASE)
        if m and str(content or "").strip():
            texts[m.group(1)] = str(content)
    if not texts and workspace_root is not None:
        base = Path(workspace_root) / ".clike" / "skills"
        for path in sorted(base.glob("journey-*/SKILL.md")) if base.is_dir() else []:
            try:
                texts[path.parent.name] = path.read_text(encoding="utf-8")
            except OSError:
                continue
    return texts


def load_scenario_catalog(core_blobs: Optional[Dict[str, Any]] = None, workspace_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """[{skill, description, scenarios: [{id, level, title, ears}]}] in skill-name order."""
    catalog: List[Dict[str, Any]] = []
    for name, text in sorted(_skill_texts(core_blobs or {}, workspace_root).items()):
        meta = _extract_frontmatter(text)
        scenarios = []
        for line in meta.get("scenarios") or []:
            m = SCENARIO_LINE.match(str(line))
            if m:
                scenarios.append({"id": m.group(1).upper(), "level": m.group(2).lower(), "title": m.group(3), "ears": m.group(4)})
        if scenarios:
            catalog.append({"skill": str(meta.get("name") or name), "description": str(meta.get("description") or ""), "scenarios": scenarios})
    return catalog


def scenario_index(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["id"]: {**s, "skill": entry["skill"]} for entry in catalog for s in entry["scenarios"]}


def req_scenarios(req: Optional[Dict[str, Any]]) -> List[str]:
    """Scenario ids a REQ owns: `scenarios` of plan.json (ids, or objects with an id)."""
    out: List[str] = []
    for item in (req or {}).get("scenarios") or []:
        raw = item.get("id") if isinstance(item, dict) else item
        m = SCENARIO_ID.search(str(raw or "").upper())
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _plan_req(core_blobs: Dict[str, Any], workspace_root: Optional[Path], req_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not req_id:
        return None
    text = next((str(v) for k, v in (core_blobs or {}).items() if str(k).replace("\\", "/").endswith("docs/harper/plan.json")), "")
    if not text and workspace_root is not None:
        try:
            text = (Path(workspace_root) / "docs" / "harper" / "plan.json").read_text(encoding="utf-8")
        except OSError:
            text = ""
    try:
        reqs = (json.loads(text or "{}") or {}).get("reqs") or []
    except ValueError:
        return None
    return next((r for r in reqs if isinstance(r, dict) and str(r.get("id") or "").upper() == req_id.upper()), None)


def _catalog_lines(catalog: List[Dict[str, Any]], with_ears: bool) -> List[str]:
    lines: List[str] = []
    for entry in catalog:
        lines.append(f"### {entry['skill']} — {entry['description']}".rstrip(" —"))
        for s in entry["scenarios"]:
            tail = f" — {s['ears']}" if with_ears else ""
            lines.append(f"- {s['id']} ({s['level']}) {s['title']}{tail}")
        lines.append("")
    return lines


def _profile_lines(profile: str) -> List[str]:
    p = CAPACITY_PROFILES[profile]
    lines = [
        f"### REQ capacity profile: {profile} — {p['executor']}",
        f"- Unit of work: {p['unit']}.",
        f"- Budget per unit: {p['criteria']}; {p['size']}; {p['domains']}.",
        "- Size by verifiable outcome, not by lines of prose: the largest unit with one clear, machine-checkable"
        " definition of done that fits the budget.",
        "- Never split one capability by technical layer (API in one REQ, its UI in another) when the budget"
        " holds both; merge REQs that only add bookkeeping; split a unit that exceeds the budget.",
    ]
    if profile == "C3":
        lines += [
            "- Plan epics: each `reqs[]` item is an epic with `\"profile\": \"C3\"` and `\"features\": [{\"id\": \"F01\","
            " \"title\": \"…\", \"acceptance\": [\"…\"], \"scenarios\": [\"IAM-02\"]}]` in dependency order. The epic's"
            " `acceptance` and `scenarios` are the union of its features'.",
        ]
    else:
        lines.append(f"- Write `\"profile\": \"{profile}\"` on every REQ of plan.json.")
    return lines


SEAM_RULES = [
    "### Shared seams (fewer regressions)",
    "- The first REQ that creates an application owns its extension points: routes/modules registered by"
    " convention (one file per feature), one migration file per REQ, a service/adapter registry.",
    "- Later REQs add files and register through these seams; they do not rewrite shared composition files"
    " (application entrypoint, router wiring, migration chain heads). Each REQ's technical scope names the seam it uses.",
]


def _spec_block(catalog: List[Dict[str, Any]]) -> str:
    lines = [
        "## CLIKE QUALITY CONTEXT — journey scenarios (mandatory)",
        "Every capability implies a known set of scenarios beyond the happy path. For each use case, find the"
        " journeys of the catalog below it touches, and add a `## Scenarios` section to SPEC.md with one line per"
        " scenario of every touched journey:",
        "- `IAM-03 — included — <how it applies to this product>`",
        "- `IAM-03 — excluded — <reason>` (valid reasons: out of the product scope stated in IDEA; delegated to a"
        " named system — its integration point stays included; not applicable to this runtime).",
        "Every `required` scenario of a touched journey appears, included or excluded; a `conditional` one appears"
        " when its condition holds. Included scenarios also appear in the use case's alternate/error flows, written"
        " as EARS statements, and the acceptance criteria cover them.",
        "",
        *_catalog_lines(catalog, with_ears=True),
    ]
    return "\n".join(lines).rstrip()


def _plan_block(catalog: List[Dict[str, Any]], profile: str) -> str:
    lines = ["## CLIKE QUALITY CONTEXT — capacity profile, seams and scenarios", "", *_profile_lines(profile), "", *SEAM_RULES, ""]
    if catalog:
        lines += [
            "### Scenarios",
            "- Read the `## Scenarios` section of SPEC.md. Give every included scenario to exactly one REQ (the one that"
            " owns the behavior): its id in `reqs[].scenarios`, and an acceptance bullet that starts with the id"
            " (e.g. `IAM-03: If … then the system shall …`). Excluded scenarios go to no REQ.",
            "- A REQ with a user interface proves its journeys end to end (browser or device test, or the lane's equivalent).",
            "",
            *_catalog_lines(catalog, with_ears=False),
        ]
    return "\n".join(lines).rstrip()


def _kit_block(catalog: List[Dict[str, Any]], req: Optional[Dict[str, Any]], req_id: str) -> str:
    index = scenario_index(catalog)
    owned = req_scenarios(req)
    lines: List[str] = []
    if owned:
        lines += [
            f"## CLIKE QUALITY CONTEXT — journey scenarios of {req_id} (part of the acceptance)",
            "Implement every scenario below and prove each with a blocking check of ci/LTC.json. In"
            " docs/ACCEPTANCE.json add one criterion per scenario with the scenario id as `id` (status, checks), or"
            " list the scenario ids under `scenarios` of the criterion that proves them. The eval blocks the REQ when"
            " a scenario has no blocking check.",
            "- Prove the rule, not only the status: assert the message/state the user or the caller sees (the error"
            " text shown in the UI, the error body of the API, the safe state of the device).",
            "- Never happy-path only: each error, empty, denied, expired or limit case of the scenario has its own test.",
            "- Tag the test that proves a scenario with its id (test name, docstring or comment, e.g."
            " `test_iam_03_wrong_credentials_shows_generic_message`): the eval looks for the id in the KIT's tests.",
            "",
        ]
        for sid in owned:
            s = index.get(sid)
            lines.append(f"- {sid} {s['title']} — {s['ears']}" if s else f"- {sid} (not in the catalog: prove it as the plan states it)")
        lines.append("")
    if str((req or {}).get("profile") or "").upper() == "C3":
        lines += [
            f"## CLIKE QUALITY CONTEXT — epic {req_id}, one feature at a time (C3)",
            f"- First write runs/kit/{req_id}/docs/FEATURES.json: {{\"epic\": \"{req_id}\", \"features\": [{{\"id\": \"F01\","
            " \"title\": \"…\", \"criteria\": [\"A01\"], \"scenarios\": [\"…\"], \"status\": \"todo\", \"checks\": []}]}"
            " from the plan's features, in dependency order. After that only `status` (todo | done | blocked) and"
            " `checks` change; features are never removed or rewritten.",
            "- Then for each feature in order: implement it with its tests, run the checks it touches, set it done with the"
            f" blocking checks that prove it, and append one line to runs/kit/{req_id}/docs/PROGRESS.md (feature, files,"
            " checks run, result). Resume from PROGRESS.md when restarted.",
            "- A feature is done only with its checks run and passing; the epic is done when every feature is done.",
            "",
        ]
    return "\n".join(lines).rstrip()


def build_quality_context(
    *, phase: str, payload: Dict[str, Any], execution_mode: str, req_id: Optional[str], workspace_root: Optional[Path],
) -> Dict[str, Any]:
    """{phase, profile, scenarios: [ids in the block], text} — text is '' when nothing applies."""
    lphase = str(phase or "").strip().lower()
    core_blobs = payload.get("core_blobs") if isinstance(payload.get("core_blobs"), dict) else {}
    catalog = load_scenario_catalog(core_blobs, workspace_root)
    profile = resolve_capacity_profile(payload, execution_mode)
    text = ""
    scenarios: List[str] = []
    if lphase == "spec" and catalog:
        text = _spec_block(catalog)
    elif lphase in {"plan", "extend"}:
        text = _plan_block(catalog, profile)
    elif lphase in {"kit", "acceptance", "eval"} and req_id:
        req = _plan_req(core_blobs, workspace_root, req_id)
        scenarios = req_scenarios(req)
        text = _kit_block(catalog, req, req_id)
    return {"phase": lphase, "profile": profile, "scenarios": scenarios, "text": text}
