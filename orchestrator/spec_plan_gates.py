# orchestrator/app/spec_plan_gates.py
# SPEC/PLAN gate checks (structure, ambiguity, traceability, non-functionals, security-lite stub).
# Emits exit code !=0 on failures. Output is JSON (stdout) for EvalRunner.

import sys, argparse, re, json
from pathlib import Path

RE_REQUIRED_SECTIONS = {
    "SPEC": ["Problem", "Objectives", "Scope", "Non-Goals", "Constraints", "KPIs", "Assumptions", "Risks", "Acceptance Criteria", "Sources & Evidence", "Technology Constraints"],
    "PLAN": ["Work Breakdown", "Traceability", "Test Strategy", "Milestones", "Risks & Mitigations", "Non-Functionals", "Environment Profiles"]
}

AMBIGUOUS = re.compile(r"\b(TBD|TBC|may|should|could)\b", re.I)

def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf8")

def _has_section(doc: str, section: str) -> bool:
    return f"## {section}" in doc or f"### {section}" in doc

def _missing_sections(doc: str, sections: list[str]) -> list[str]:
    return [s for s in sections if not _has_section(doc, s)]

def _yaml_block_present(doc: str, key: str) -> bool:
    return "tech_constraints:" in doc

def check_spec(file: Path) -> list[str]:
    e: list[str] = []
    txt = _load_text(file)
    miss = _missing_sections(txt, RE_REQUIRED_SECTIONS["SPEC"])
    if miss: e.append(f"SPEC missing sections: {', '.join(miss)}")
    amb = AMBIGUOUS.findall(txt)
    if amb: e.append(f"Ambiguity found: {len(amb)} occurrence(s)")
    if "## KPIs" in txt and "measurement" not in txt.lower():
        e.append("KPIs must include measurement method and metric source")
    if not _yaml_block_present(txt, "tech_constraints"):
        e.append("Technology Constraints YAML block missing or not parseable")
    if "## Acceptance Criteria" not in txt:
        e.append("Acceptance Criteria required per requirement (ID→test)")
    if "## Sources & Evidence" not in txt:
        e.append("Provenance missing: list attachments and relevance")
    return e

def check_plan(file: Path) -> list[str]:
    e: list[str] = []
    txt = _load_text(file)
    miss = _missing_sections(txt, RE_REQUIRED_SECTIONS["PLAN"])
    if miss: e.append(f"PLAN missing sections: {', '.join(miss)}")
    if "Traceability" in txt and "Coverage: 100%" not in txt:
        e.append("Traceability must declare 100% SPEC→PLAN coverage")
    hooks = ["Unit", "Functional", "Integration", "Security", "UAT"]
    for h in hooks:
        if f"{h} Tests" not in txt and f"{h} tests" not in txt:
            e.append(f"Missing test hook section: {h} Tests")
    if "Non-Functionals" in txt and "Performance" not in txt:
        e.append("Non-Functionals must include Performance targets")
    if "Environment Profiles" not in txt:
        e.append("Environment Profiles must reflect tech_constraints profiles (e.g., onprem/cloud)")
    return e

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("check-spec"); sp.add_argument("--file", type=Path, required=True)
    pl = sub.add_parser("check-plan"); pl.add_argument("--file", type=Path, required=True)
    args = ap.parse_args()

    if args.cmd == "check-spec":
        errs = check_spec(args.file)
    else:
        errs = check_plan(args.file)

    if errs:
        print(json.dumps({"passed": False, "errors": errs}, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"passed": True, "errors": []}, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
