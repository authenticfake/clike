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
# /adopt also writes the project's run guide and integrates the root README (every existing section kept)
ADOPT_EXTRA_WRITE_ROOTS = ["README.md", "docs/harper/HOWTO_RUN.md"]


def extra_write_roots(cascade: Optional[Dict[str, Any]]) -> List[str]:
    if not cascade:
        return []
    adopt = str(cascade.get("mode") or "").lower() == "adopt"
    return CASCADE_EXTRA_WRITE_ROOTS + (ADOPT_EXTRA_WRITE_ROOTS if adopt else [])


def extend_options(payload: Dict[str, Any]) -> Dict[str, Any]:
    opts = payload.get("extend") if isinstance(payload.get("extend"), dict) else {}
    return dict(opts or {})


def cascade_options(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The cascade options of an extend payload (a release cascade, or the adoption of an existing project:
    both write IDEA, SPEC, PLAN and TECH_CONSTRAINTS in one run), or None for the plan-only /extend."""
    opts = extend_options(payload)
    return opts if str(opts.get("mode") or "").lower() in ("cascade", "adopt") else None


def cascade_title(opts: Dict[str, Any]) -> str:
    return "Adoption of an existing project (/adopt)" if str(opts.get("mode") or "").lower() == "adopt" else "Release cascade (/idea --extend)"


def adopt_rules(opts: Dict[str, Any]) -> List[str]:
    """/adopt: the Harper documents of a project CLike did not create, as it is (docs/adopt.md)."""
    areas = opts.get("areas") if isinstance(opts.get("areas"), list) else []
    shown = "; ".join(
        f"{a.get('name')} (root {a.get('root')}, baseline {a.get('baseline_req')})" for a in areas if isinstance(a, dict)
    ) or "the repository root"
    survey = str(opts.get("survey_report") or "docs/harper/ADOPT_<date>.md")
    return [
        "Adoption: write the Harper documents of this project AS IT IS — nothing is designed, nothing is invented. "
        "The truth of what exists is the code, its tests and git; documents (README, docs/, ADRs, howtos, tutorials, "
        "the API/event/tool contracts, CHANGELOGs, AGENTS.md / CLAUDE.md, backlogs and decision records in docs/inputs/) "
        "are declarations to reconcile with the code.",
        f"Areas (from .clike/project.json): {shown}. The survey, the baseline (the tests each area already runs, "
        f"and their result in the eval sandbox) and the git history per area are in {survey}: read it first.",
        "Sources, in this order: (1) docs/harper/CODEMAP.md — the complete inventory CLike extracted from the code, "
        "per area: modules and public symbols, entry points, routes, calls to other areas, contracts, configuration, "
        "tests; a capability it does not show is not in the code; (2) the code itself — the key files given (or the "
        "repository, for a local agent) and the project memory, which holds the code and the documentation by path; "
        "(3) git — features and fixes per area: what was built and when, observed only when the code map or the tests "
        "show it; (4) the documents. Without git, the code and the documents; without documents, the code alone.",
        "Interactions: from the routes, the calls to other areas (client, method, path), the references between areas "
        "and the contracts, write who calls whom, on which protocol and interface, and each area's role and "
        "responsibilities — in SPEC (interfaces) and in the README (architecture).",
        "Label every statement you derive: (observed) found in code or tests, (declared) written in a document and not "
        "verified in code, (open) unknown or undecided — a question for the owner. Never turn an open point into a default.",
        "IDEA.md: vision, users, outcomes and scope as the documents state them; decisions already taken (decision "
        "records) under Decisions; what nobody wrote stays open.",
        "SPEC.md: the canonical SPEC sections with what exists — capabilities per area, interfaces (the contracts between "
        "areas), data, security, operations, non-functional requirements — and ## Use Cases: the end-to-end journeys "
        "the howtos, tutorials and tests show (UC-nn with numbered steps UC-nn.n, errors, prerequisites), across areas "
        "when they cross them.",
        "TECH_CONSTRAINTS.yaml: the stacks, runtime versions, frameworks, infrastructure and conventions observed per area.",
        "plan.json and PLAN.md: the baseline REQs exist already (one per area, status done, origin adopted: its LTC runs "
        "the area's own checks) — keep them unchanged. Add one REQ per capability per area (not per file, no history): "
        "\"area\": the area name, \"origin\": \"adopted\", acceptance in (observed) terms; status \"done\" with "
        "\"covered_by\": the area's baseline REQ when the capability is in the code and the area's tests cover it, "
        "status \"open\" when it is documented or planned but not found, or found without tests. Work still to do in "
        "a backlog becomes open REQs with \"origin\": \"import:backlog:<id>\", its acceptance and its blockers as "
        "readiness questions. A journey across areas is a REQ with the areas it touches.",
        "Lane guides: one docs/harper/lane-guides/<area>.md per area from its AGENTS.md / CLAUDE.md and its observed "
        "conventions (layout, commands, tests, style), so every KIT follows them.",
        "Report: the EXTEND report file is the adoption analysis — the capability → files → tests map per area, the "
        "reconciliation (declared and found; declared and not found; found and not declared), the open questions, the "
        "risks. CLike appends its own verification.",
        "docs/harper/HOWTO_RUN.md: how to set up, run and test the project as it is, area by area — prerequisites and "
        "runtime versions, the setup / run / test / lint commands from its Makefile, scripts, manifests and CI (each "
        "with the area folder it runs in), configuration files and environment variables by name only, the local "
        "services it needs. Only commands backed by a file of the repository; what cannot be run locally is said so.",
        "README.md (repository root): integrate the existing README, never replace it — every existing heading stays, "
        "with its content, in its order, and every existing line stays word for word (where the code contradicts a "
        "line, keep it and add a note right after it, and say so in the report; a README that loses a line is put "
        "back). Add CLike's "
        "release-grade presentation as finalize does: a badge row after the H1 (status adopted, the CLike badge linked "
        "to https://github.com/authenticfake/clike, the Harper badge \"adopt\" linked to "
        f"{survey}), a short summary blockquote, and the sections it lacks — Project Overview, Areas (a table: area, "
        "root, stack, runtime, commands), Architecture (the areas and the contracts between them), Requirements "
        "Coverage (the baseline REQs and the capability REQs, done / open), How to Run and How to Test (pointing to "
        "docs/harper/HOWTO_RUN.md), Known Limitations, Next Steps, and last Made with CLike (adopted with CLike, "
        "evolving through the Harper process; links to docs/harper/ and the reports). No badge claims eval or gate "
        "results the baseline did not produce. No README of an area is changed.",
        "Write only docs/harper/ (the files above) and the root README.md. Never change the project's code, tests, "
        "scripts, CI, the areas' README files or docs/.",
    ]


def context_phases(payload: Dict[str, Any], phase: str) -> List[str]:
    """Phases whose context sources this run reads: the cascade does the work of idea, spec and plan."""
    return [phase, "idea", "spec", "plan"] if phase == "extend" and cascade_options(payload) else [phase]


def cascade_rules(opts: Dict[str, Any]) -> List[str]:
    if str(opts.get("mode") or "").lower() == "adopt":
        return adopt_rules(opts)
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
        f"SPEC.md `## Use Cases` (as /spec writes them): every journey {release} adds or changes is a use case "
        "`### UC-nn — <name>` with numbered steps `UC-nn.1`, `UC-nn.2`… (actor action → system response, "
        "interface, data read/written; sign-in, expiry, denials, empty states, retries included), alternate and "
        "error flows, the data path, postconditions and Prerequisites. A changed journey updates its use case "
        f"(steps marked `({release})`, replaced steps `superseded in {release}`); a new one continues the UC "
        "numbering. A SPEC without the section gets it, with at least the journeys this release touches. "
        f"Every step of a {release} use case is covered by a {release} REQ (`covers: [\"UC-nn.n\" | \"UC-nn\"]` "
        "in plan.json) or by a delivered REQ that already does it.",
        "plan.json: existing REQs are read-only (CLike restores any change). New REQs continue the ID "
        f"sequence, status `open`, and carry `release: \"{release}\"`, `change` (ADDED | MODIFIED | "
        f"REMOVED) and `origin: \"extend:<report file name>\"`. Prefer ADDED REQs that extend an existing "
        "seam (a new adapter behind a port, a new step in an existing flow) over MODIFIED ones.",
        "MODIFIED (changes behavior a delivered REQ verifies): `amends: [\"REQ-x\"]`; acceptance restates in "
        "full every criterion it changes; `supersedes: [{\"check\": \"REQ-x#<check id from "
        "runs/kit/REQ-x/ci/LTC.json, or test id>\", \"reason\": \"...\"}]` names exactly the checks that stop "
        "holding — always with the REQ prefix, a test too (e.g. `REQ-016#test/v2/login.test.tsx::restores the "
        "workspace`). A delivered test that pins a complete list or the latest item the new REQ extends (the "
        "last migration or schema version, the set of routes, services, files or menu entries) stops holding "
        "too: name it, and the REQ that extends it is MODIFIED. `unchanged: [...]` names what REQ-x keeps doing. "
        "REMOVED (retires a capability): "
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
        lines += ["", f"### {cascade_title(cascade)}", *[f"- {rule}" for rule in cascade_rules(cascade)]]
        lines += ["- Return the complete files: docs/harper/IDEA.md, docs/harper/SPEC.md, docs/harper/PLAN.md, "
                  "docs/harper/plan.json, the EXTEND report, and docs/harper/TECH_CONSTRAINTS.yaml when it changes."
                  + (" Also docs/harper/TECH_CONSTRAINTS.yaml, docs/harper/HOWTO_RUN.md, the lane guides and the root "
                     "README.md (the existing one, integrated)." if str(cascade.get("mode") or "").lower() == "adopt" else "")]
        lines += adopt_documents(cascade)
    return "\n".join(lines)


def adopt_documents(opts: Dict[str, Any], limit: int = 400000) -> List[str]:
    """/adopt on cloud: the survey report, the agent context files and the READMEs the extension read (a local
    agent reads the repository itself); the rest of the documentation is in the project memory."""
    if str(opts.get("mode") or "").lower() != "adopt":
        return []
    docs = [d for d in (opts.get("documents") or []) if isinstance(d, dict) and str(d.get("text") or "").strip()]
    out: List[str] = []
    used = 0
    for d in docs:
        text = str(d.get("text"))
        if used + len(text) > limit:
            break
        used += len(text)
        out += ["", f"### Project document: {str(d.get('path') or '').strip()}", "", text.rstrip()]
    return (["", "### Project documents (read-only: describe them, never rewrite them)"] + out) if out else []
