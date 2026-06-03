from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ScorecardDimension:
    name: str
    keywords: Sequence[str]
    section_terms: Sequence[str]
    improvement_note: str
    min_hits: int = 1


IDEA_DIMENSIONS: Sequence[ScorecardDimension] = (
    ScorecardDimension(
        name="section_coverage",
        keywords=("vision", "problem statement", "target users", "value", "out of scope", "risks", "sources"),
        section_terms=("vision", "problem", "target users", "value", "out of scope"),
        improvement_note="Add the core IDEA sections needed for downstream SPEC preparation.",
        min_hits=5,
    ),
    ScorecardDimension(
        name="measurable_outcomes",
        keywords=("≤", ">=", "≥", "%", "minutes", "target", "metric", "outcome"),
        section_terms=("value", "outcomes", "success metrics"),
        improvement_note="Add measurable outcome targets instead of only qualitative benefits.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="acceptance_hooks",
        keywords=("acceptance", "given", "when", "then", "done", "success means", "problem solved"),
        section_terms=("acceptance", "handoff readiness", "success"),
        improvement_note="Add acceptance hooks that SPEC and PLAN can convert into testable requirements.",
        min_hits=2,
    ),
    ScorecardDimension(
        name="non_functional_anchors",
        keywords=("performance", "reliability", "availability", "latency", "accessibility", "retention", "rpo", "rto"),
        section_terms=("non-functional", "technology constraints", "data management"),
        improvement_note="Add non-functional anchors such as performance, reliability, accessibility, retention, RPO, or RTO.",
        min_hits=2,
    ),
    ScorecardDimension(
        name="security_privacy_compliance",
        keywords=("security", "privacy", "compliance", "gdpr", "oidc", "rbac", "secrets", "encryption", "audit"),
        section_terms=("security", "privacy", "compliance"),
        improvement_note="Add security, privacy, compliance, identity, secret handling, and audit expectations.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="observability_operations",
        keywords=("observability", "operations", "logging", "metrics", "prometheus", "grafana", "tracing", "health"),
        section_terms=("observability", "operations", "technology constraints"),
        improvement_note="Add operational visibility expectations such as logs, metrics, traces, health, or dashboards.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="data_lifecycle",
        keywords=("data", "retention", "backup", "migration", "rpo", "rto", "pii", "postgres", "transactional"),
        section_terms=("data management", "data lifecycle", "technology constraints"),
        improvement_note="Add data lifecycle detail for storage, retention, backup, migration, and sensitive data handling.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="deployment_portability",
        keywords=("deployment portability", "on-prem", "kubernetes", "local", "parity", "allowed differences", "profiles"),
        section_terms=("deployment portability", "technology constraints profile"),
        improvement_note="Add deployment portability rules and profile differences that downstream phases can preserve.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="technology_constraints_richness",
        keywords=("tech_constraints", "lanes", "runtime", "framework", "ci_cd", "eval_profiles", "dependency_policy", "deployment_target"),
        section_terms=("technology constraints", "technology constraints profile"),
        improvement_note="Add SPEC-ready technology constraints with lanes, runtime evidence, CI, eval profiles, and dependency policy.",
        min_hits=4,
    ),
    ScorecardDimension(
        name="downstream_handoff_readiness",
        keywords=("/spec handoff readiness", "spec-ready", "plan-ready", "req", "handoff", "slice-1", "deferred"),
        section_terms=("handoff readiness", "/spec handoff readiness"),
        improvement_note="Add a handoff section that tells /spec what is ready, what is deferred, and what must become requirements.",
        min_hits=3,
    ),
    ScorecardDimension(
        name="traceability_source_references",
        keywords=("sources", "inspiration", "reference", "assumption", "existing", "internal", "standards"),
        section_terms=("sources", "assumptions", "risks"),
        improvement_note="Add source references, assumptions, and provenance notes for later review.",
        min_hits=2,
    ),
)


def parse_markdown_sections(markdown_text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    matches = list(HEADING_RE.finditer(markdown_text or ""))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        sections.append(
            {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
                "body": markdown_text[start:end].strip(),
            }
        )
    return sections


def _contains_term(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def _hit_count(text: str, terms: Iterable[str]) -> int:
    return sum(1 for term in terms if _contains_term(text, term))


def _section_hit_count(sections: Sequence[Dict[str, Any]], terms: Iterable[str]) -> int:
    titles = "\n".join(str(section.get("title") or "") for section in sections)
    return _hit_count(titles, terms)


def score_idea_markdown(markdown_text: str) -> Dict[str, Any]:
    text = markdown_text or ""
    sections = parse_markdown_sections(text)
    section_count = len(sections)
    dimension_results: List[Dict[str, Any]] = []

    for dimension in IDEA_DIMENSIONS:
        keyword_hits = _hit_count(text, dimension.keywords)
        section_hits = _section_hit_count(sections, dimension.section_terms)
        hits = keyword_hits + section_hits
        score = 1.0 if hits >= dimension.min_hits else round(hits / dimension.min_hits, 3)
        missing = [] if score >= 1.0 else [dimension.name]
        improvement_notes = [] if score >= 1.0 else [dimension.improvement_note]
        evidence = [
            term
            for term in [*dimension.section_terms, *dimension.keywords]
            if _contains_term(text, term)
        ][:8]

        dimension_results.append(
            {
                "name": dimension.name,
                "score": score,
                "max_score": 1.0,
                "hits": hits,
                "section_hits": section_hits,
                "keyword_hits": keyword_hits,
                "missing": missing,
                "improvement_notes": improvement_notes,
                "evidence": evidence,
            }
        )

    total_score = round(sum(float(item["score"]) for item in dimension_results), 3)
    max_score = float(len(dimension_results))
    missing_dimensions = [
        item["name"]
        for item in dimension_results
        if float(item["score"]) < 1.0
    ]
    improvement_notes = [
        note
        for item in dimension_results
        for note in item["improvement_notes"]
    ]

    return {
        "artifact": "IDEA.md",
        "score": total_score,
        "max_score": max_score,
        "normalized_score": round(total_score / max_score, 3) if max_score else 0.0,
        "section_count": section_count,
        "dimensions": dimension_results,
        "missing": missing_dimensions,
        "improvement_notes": improvement_notes,
        "notes": (
            "Deterministic fixture score only. Passing this scorecard does not prove live model quality "
            "or replace human review."
        ),
    }
