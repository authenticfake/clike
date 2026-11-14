"""The project inputs /idea writes next to IDEA.md (docs/harper/inputs/), for every executor.

Customer material arrives as it is (documents, spreadsheets, notes, in any format): /idea turns it
into structured inputs that /spec and /plan read in place of the raw documents — every statement
addressable by ID and traced to its source, the edge cases explicit, the open decisions named — so
the coverage of a project does not depend on how its requirements were written. One contract for
the cloud prompt and the local agents (same files, same rules).
"""
from __future__ import annotations

from typing import List, Tuple

INPUTS_DIR = "docs/harper/inputs"

# (path, what it holds). Order: what /spec and /plan read first.
INPUT_FILES: Tuple[Tuple[str, str], ...] = (
    (f"{INPUTS_DIR}/REQUIREMENTS.md", "functional and non-functional requirements by area, with IDs and sources"),
    (f"{INPUTS_DIR}/EDGE_CASES.md", "edge cases: situation, expected result, requirements they test"),
    (f"{INPUTS_DIR}/JOURNEYS.md", "end-to-end journeys across the requirements"),
    (f"{INPUTS_DIR}/TEST_SCENARIOS.md", "test strategy, faked systems, golden fixtures"),
    (f"{INPUTS_DIR}/DECISIONS.md", "open decisions, assumptions, constraints, data sources"),
    (f"{INPUTS_DIR}/COVERAGE.md", "every source section mapped to the IDs that cover it"),
)
INPUT_PATHS: Tuple[str, ...] = tuple(path for path, _ in INPUT_FILES)
# What /spec and /plan read as requirements (COVERAGE is traceability, read by /idea only).
READ_BY_LATER_PHASES: Tuple[str, ...] = tuple(p for p in INPUT_PATHS if not p.endswith("/COVERAGE.md"))

MAX_FILE_CHARS = 50_000
MAX_TOTAL_CHARS = 120_000

# The edge-case checklist applied to every functional area (only what applies).
EDGE_CASE_CHECKLIST = (
    "inputs and files (empty, oversized, wrong encoding, malformed or duplicated rows, missing columns); "
    "identity and deduplication; text normalisation (case, accents, whitespace, special characters); "
    "numbers, dates, time zones, currencies and locales; addresses and geography; state transitions "
    "(allowed, invalid, repeated); concurrency and idempotency (double submit, retry, replay); "
    "authorisation and tenancy (wrong role, another tenant, expired session); external systems (timeout, "
    "error, rate limit, partial or stale data, unavailable); limits and pagination; privacy, retention and "
    "audit; recovery after a crash or restart"
)


def idea_inputs_rules() -> List[str]:
    """The rules of the inputs, one per line (prompt bullets for the cloud and the agents)."""
    files = "; ".join(f"`{path}` ({what})" for path, what in INPUT_FILES)
    return [
        f"Besides IDEA.md, write the project inputs: {files}. /spec and /plan read them in place of the raw "
        "documents, so nothing of the sources may be lost and everything must be addressable by ID.",
        "Sources: the attachments of this run and the project context sources (requirements and reference). "
        "Never invent facts, vendors, endpoints, quantities or rules: what the sources leave open or a choice they "
        "do not make goes to DECISIONS.md as an open decision (question, options, impact, proposed default marked "
        "as an assumption).",
        "Organise by functional area, never by delivery: no REQs, epics, stories, sprints or phases (/plan slices "
        "the work). Write in the language of the sources, like IDEA.md.",
        "IDs: FR-<AREA>-nn and NFR-<AREA>-nn (AREA a 2–4 letter code per functional area), EC-<AREA>-nn, "
        "E2E-nn, TS-nn, D-nn. When previous inputs exist (docs/harper/inputs/ among the context sources), keep "
        "every ID with its meaning, add new IDs after the last number, mark removed ones `withdrawn` (never reuse "
        "an ID), and start each file with `## Changes` against the previous version (`First version` otherwise).",
        "REQUIREMENTS.md: one testable statement per requirement with its rule and values (limits, formats, states, "
        "messages), the source (file and section or page) and the EC IDs that test it.",
        "EDGE_CASES.md: tables `ID | Situation / input | Expected result | Requirements`, derived systematically "
        f"for every area with this checklist (only what applies): {EDGE_CASE_CHECKLIST}. Every expected result is "
        "concrete and observable (value, message, state, record), never `handled gracefully`.",
        "JOURNEYS.md: E2E-nn paths from the trigger (a user, a schedule, an incoming file or event) to the "
        "observable outcome: steps, the FR and EC IDs they cross, the final state.",
        "TEST_SCENARIOS.md: the test strategy per layer (unit, integration on the real database, contract, "
        "end-to-end and browser), which external systems are faked and how, the golden fixtures (name, content, "
        "purpose, the IDs they cover) and the time and size bounds of the tests.",
        "DECISIONS.md: open decisions D-nn, then the fixed constraints and the data sources and references the "
        "sources name.",
        "COVERAGE.md: a table mapping every section of every source (file § heading or page) to the IDs that "
        "cover it, the statements deliberately not turned into requirements with the reason, and counts per file. "
        "A source section with no ID is a defect: cover it or explain it.",
        f"Size: compact tables over prose; each file at most {MAX_FILE_CHARS:,} characters, the six together at "
        f"most {MAX_TOTAL_CHARS:,} (later phases read them in full). IDEA.md stays concise and points to them.",
    ]


def idea_inputs_section() -> str:
    """The rules as a prompt section."""
    return "\n".join(["## PROJECT INPUTS (docs/harper/inputs/)", "", *[f"- {rule}" for rule in idea_inputs_rules()]])
