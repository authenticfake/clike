"""`/idea --extend`: the release cascade of the extend phase (IDEA → SPEC → PLAN delta).

`/extend` (plan mode) appends REQs to the plan. `/idea --extend` (cascade mode) evolves a project to
its next release: the release inputs are merged into IDEA, SPEC and TECH_CONSTRAINTS, and the
PLAN receives the delta — new REQs typed ADDED / MODIFIED / REMOVED — while every delivered REQ
stays read-only. The rules live here once, for the cloud prompt and the local-agent package; the
extension checks the result deterministically (extensions/vscode/extend-guard.js).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CHANGE_TYPES = ("ADDED", "MODIFIED", "REMOVED")
CASCADE_EXTRA_WRITE_ROOTS = ["docs/harper/TECH_CONSTRAINTS.yaml"]


def extend_options(payload: Dict[str, Any]) -> Dict[str, Any]:
    opts = payload.get("extend") if isinstance(payload.get("extend"), dict) else {}
    return dict(opts or {})


def cascade_options(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The cascade options of an extend payload, or None for the plan-only /extend."""
    opts = extend_options(payload)
    return opts if str(opts.get("mode") or "").lower() == "cascade" else None


def context_phases(payload: Dict[str, Any], phase: str) -> List[str]:
    """Phases whose context sources this run reads: the cascade does the work of idea, spec and plan."""
    return [phase, "idea", "spec", "plan"] if phase == "extend" and cascade_options(payload) else [phase]


def cascade_rules(opts: Dict[str, Any]) -> List[str]:
    release = str(opts.get("release") or "the next release")
    baseline = str(opts.get("baseline") or "the current release")
    report = "docs/harper/EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md"
    return [
        f"Release cascade: evolve the project from {baseline} (everything IDEA, SPEC, PLAN and plan.json "
        f"say now, delivered and verified) to {release}. Continuity first: what {baseline} delivers keeps "
        "working unless the input explicitly changes it.",
        f"Inputs: the attachments and the context sources marked `release {release}` are the new needs. "
        "Sources of earlier releases are history: they explain what exists, they are never new requirements. "
        "Read the source code of the areas the new needs touch (read-only) when you can, so the delta is "
        "grounded in the code that exists.",
        "Merge, never regenerate. IDEA.md, SPEC.md and TECH_CONSTRAINTS.yaml keep every section and "
        f"statement of earlier releases. Add {release} content inside the canonical sections it belongs to, "
        f"marked `({release})`, plus one section `## Release {release}` with goals, scope, out of scope and "
        "the decisions the input states. A statement the input changes stays, marked "
        f"`superseded in {release}: <new statement>`. TECH_CONSTRAINTS.yaml changes only by addition.",
        f"SPEC.md: new capabilities, interfaces, data, integrations, non-functional requirements and "
        f"acceptance of {release} merged into the relevant sections (no appended 'Extension Scope'); the "
        "acceptance of delivered REQs is unchanged.",
        "plan.json: existing REQs are read-only (CLike restores any change). New REQs continue the ID "
        f"sequence, status `open`, and carry `release: \"{release}\"`, `change` (ADDED | MODIFIED | "
        f"REMOVED) and `origin: \"extend:<report file name>\"`. Prefer ADDED REQs that extend an existing "
        "seam (a new adapter behind a port, a new step in an existing flow) over MODIFIED ones.",
        "MODIFIED (changes behavior a delivered REQ verifies): `amends: [\"REQ-x\"]`; acceptance restates in "
        "full every criterion it changes; `supersedes: [{\"check\": \"REQ-x#<check id from "
        "runs/kit/REQ-x/ci/LTC.json, or test id>\", \"reason\": \"...\"}]` names exactly the checks that stop "
        "holding; `unchanged: [...]` names what REQ-x keeps doing. REMOVED (retires a capability): "
        "`retires: [\"REQ-x\"]` with acceptance proving the removal. A REQ that is `in_progress` is never amended.",
        f"PLAN.md: keep every existing REQ section; add a `## Release {release}` section with the new REQs in "
        "the same per-REQ format. The sections that index every REQ (REQ-IDs table, dependency graph, test "
        "strategy, KIT readiness, milestones) list the new REQs too, appended after the delivered ones. "
        "snapshot counts match the REQs. Bounded, testable REQs; new REQs may depend on delivered ones.",
        "Shared files (composition roots, test runner configs, compose files, manifests, .env.example) are "
        "extended by new REQs, never rewritten: say so in their acceptance where relevant.",
        "Open questions: a decision the input leaves open that a REQ needs (provider, licensing, privacy, "
        "credentials, budget) is listed in the report with the REQs it blocks; never invent a default the "
        "input does not state.",
        f"Report {report}: release and baseline; input sources by role; IDEA, SPEC and TECH_CONSTRAINTS "
        "changes (sections added or changed, and why); the delta table (REQ, change, title, amends / retires "
        "/ supersedes, dependsOn); impact on delivered REQs (areas and files touched); behaviors that stay "
        "unchanged; open questions; risks. CLike appends its own verification section.",
    ]


def cloud_extend_section(payload: Dict[str, Any]) -> str:
    """The extend options for the cloud prompt (plan mode and cascade)."""
    opts = extend_options(payload)
    if not opts:
        return ""
    cascade = cascade_options(payload)
    lines = ["## EXTEND REQUEST"]
    for key, label in (("anchorReq", "anchor"), ("explicitReq", "requested REQ id"), ("rawInput", "request"),
                       ("release", "target release"), ("baseline", "baseline release")):
        value = str(opts.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    if opts.get("fromAttachment"):
        lines.append("- source: the attachments of this run")
    if cascade:
        lines += ["", "### Release cascade (/idea --extend)", *[f"- {rule}" for rule in cascade_rules(cascade)]]
        lines += ["- Return the complete files: docs/harper/IDEA.md, docs/harper/SPEC.md, docs/harper/PLAN.md, "
                  "docs/harper/plan.json, the EXTEND report, and docs/harper/TECH_CONSTRAINTS.yaml when it changes."]
    return "\n".join(lines)
