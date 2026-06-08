import json
from pathlib import Path

from services.capabilities import (
    _extract_frontmatter,
    build_capability_metadata_map,
    enrich_plan_capabilities,
    enrich_plan_json_text,
    validate_capability_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "extensions/vscode/templates/harper-init/.clike"

REPRESENTATIVE = [
    ("skill", TEMPLATE / "skills/secure-config-secrets/SKILL.md"),
    ("skill", TEMPLATE / "skills/frontend-state-accessibility/SKILL.md"),
    ("pack", TEMPLATE / "packs/enterprise-onprem/PACK.md"),
    ("design_profile", TEMPLATE / "design-profiles/enterprise-console/DESIGN.md"),
]


# --- A. Capability file structure ---

def test_representative_files_have_required_sections_and_operational_frontmatter():
    for kind, path in REPRESENTATIVE:
        text = path.read_text(encoding="utf-8")
        result = validate_capability_markdown(text, kind)
        assert result["ok"], f"{path.name} missing sections: {result['missing_sections']}"
        assert result["has_frontmatter"], f"{path.name} has no frontmatter"
        assert result["missing_operational_frontmatter"] == [], (
            f"{path.name} missing operational frontmatter: {result['missing_operational_frontmatter']}"
        )


def _all_capability_files():
    import glob

    groups = [
        ("skill", str(TEMPLATE / "skills/*/SKILL.md")),
        ("pack", str(TEMPLATE / "packs/*/PACK.md")),
        ("design_profile", str(TEMPLATE / "design-profiles/*/DESIGN.md")),
    ]
    for kind, pattern in groups:
        for path in sorted(glob.glob(pattern)):
            yield kind, Path(path)


def test_all_template_capability_files_are_compliant():
    failures = []
    total = 0
    for kind, path in _all_capability_files():
        total += 1
        result = validate_capability_markdown(path.read_text(encoding="utf-8"), kind)
        if not result["ok"]:
            failures.append(
                (
                    path.parent.name,
                    result["missing_sections"],
                    result["missing_operational_frontmatter"],
                    result["generic_boilerplate"],
                )
            )
    assert total >= 28
    assert not failures, f"non-compliant capability files: {failures}"


def test_no_template_capability_file_contains_generic_boilerplate():
    offenders = []
    for kind, path in _all_capability_files():
        result = validate_capability_markdown(path.read_text(encoding="utf-8"), kind)
        if result["generic_boilerplate"]:
            offenders.append((path.parent.name, result["generic_boilerplate"]))
    assert not offenders, f"files still contain generic boilerplate: {offenders}"


def test_every_capability_file_has_full_operational_frontmatter():
    offenders = []
    for kind, path in _all_capability_files():
        result = validate_capability_markdown(path.read_text(encoding="utf-8"), kind)
        if result["missing_operational_frontmatter"]:
            offenders.append((path.parent.name, result["missing_operational_frontmatter"]))
    assert not offenders, f"files missing operational frontmatter: {offenders}"


def test_validator_flags_missing_sections():
    bad = "---\nname: x\n---\n\n## Intent\nonly intent\n"
    result = validate_capability_markdown(bad, "skill")
    assert result["ok"] is False
    assert "## Use when" in result["missing_sections"]


# --- B. Frontmatter parser (block lists no longer dropped) ---

def test_block_yaml_list_is_parsed_not_dropped():
    text = (
        "---\n"
        "name: demo\n"
        "recommended_skills:\n"
        "  - alpha\n"
        "  - beta, with comma\n"
        "eval_checks: [\"c1\", \"c2\"]\n"
        "---\n\n# Body\n"
    )
    meta = _extract_frontmatter(text)
    assert meta["recommended_skills"] == ["alpha", "beta, with comma"]  # comma preserved
    assert meta["eval_checks"] == ["c1", "c2"]  # inline list still works


def test_pack_recommended_skills_now_discovered():
    text = (TEMPLATE / "packs/enterprise-onprem/PACK.md").read_text(encoding="utf-8")
    meta = _extract_frontmatter(text)
    assert isinstance(meta.get("recommended_skills"), list)
    assert "secure-config-secrets" in meta["recommended_skills"]


# --- C/D. Selection/propagation + plan/kit readiness ---

INDEX = {
    "skills": [
        {
            "name": "secure-config-secrets",
            "metadata": {
                "obligations": ["externalize secrets"],
                "eval_checks": ["no-hardcoded-secrets"],
                "gate_implications": ["block-if-hardcoded-secrets"],
                "evidence_required": [".env.example"],
            },
        }
    ],
    "packs": [
        {
            "name": "enterprise-onprem",
            "metadata": {
                "obligations": ["runnable on-prem"],
                "gate_implications": ["block-if-cloud-only-when-onprem-required"],
            },
        }
    ],
    "design_profiles": [
        {
            "name": "enterprise-console",
            "metadata": {
                "ui_obligations": ["route-based-information-architecture"],
                "accessibility_expectations": ["accessible-forms-and-tables"],
                "eval_checks": ["ui-states-tested"],
            },
        }
    ],
}


def _metadata():
    return build_capability_metadata_map(INDEX)


def test_selected_capabilities_expand_into_structured_block():
    plan = {
        "reqs": [
            {
                "id": "REQ-1",
                "packs": ["enterprise-onprem"],
                "skills": ["secure-config-secrets"],
                "design_profiles": ["enterprise-console"],
            }
        ]
    }
    out = enrich_plan_capabilities(plan, _metadata())
    caps = out["reqs"][0]["capabilities"]

    skill = caps["skills"][0]
    assert skill["id"] == "secure-config-secrets"
    assert skill["source"] == "plan"
    assert skill["obligations"] == ["externalize secrets"]
    assert skill["eval_checks"] == ["no-hardcoded-secrets"]
    assert skill["gate_implications"] == ["block-if-hardcoded-secrets"]

    assert caps["packs"][0]["gate_implications"] == ["block-if-cloud-only-when-onprem-required"]
    design = caps["design_profiles"][0]
    assert design["ui_obligations"] == ["route-based-information-architecture"]
    assert design["accessibility_expectations"] == ["accessible-forms-and-tables"]


def test_legacy_fields_and_schema_version_preserved():
    plan = {"reqs": [{"id": "REQ-1", "skills": ["secure-config-secrets"]}]}
    out = enrich_plan_capabilities(plan, _metadata())
    assert out["schema_version"] == "1.1.0"
    assert out["reqs"][0]["skills"] == ["secure-config-secrets"]  # legacy preserved


def test_not_applicable_becomes_exclusion_not_blanket_string():
    plan = {"reqs": [{"id": "REQ-1", "skills": ["secure-config-secrets"], "packs": "not_applicable"}]}
    out = enrich_plan_capabilities(plan, _metadata())
    req = out["reqs"][0]
    # skills populated, packs recorded as a reasoned exclusion
    assert req["capabilities"]["skills"]
    assert req["capabilities"]["packs"] == []
    assert any(e["kind"] == "packs" for e in req.get("capability_exclusions", []))


def test_unknown_capability_name_is_recorded_not_dropped():
    plan = {"reqs": [{"id": "REQ-1", "skills": ["not-in-index"]}]}
    out = enrich_plan_capabilities(plan, _metadata())
    entry = out["reqs"][0]["capabilities"]["skills"][0]
    assert entry["id"] == "not-in-index"
    assert entry.get("unresolved") is True


def test_enrichment_is_idempotent():
    plan = {"reqs": [{"id": "REQ-1", "skills": ["secure-config-secrets"]}]}
    once = enrich_plan_capabilities(plan, _metadata())
    snapshot = json.dumps(once, sort_keys=True)
    twice = enrich_plan_capabilities(once, _metadata())
    assert json.dumps(twice, sort_keys=True) == snapshot


def test_enrich_text_wrapper_is_defensive_on_bad_json():
    assert enrich_plan_json_text("{not json", _metadata()) == "{not json"


# --- H. Cloud/local parity: same helper => same shape ---

def test_local_normalizer_enriches_plan_json_from_capability_metadata():
    from services.local_agent_package import normalize_local_agent_result

    plan_md = "# PLAN — Demo\n\n## REQ-1 — A\nVerification checkpoints: tests.\n"
    plan_json = json.dumps(
        {
            "snapshot": {"total": 1},
            "reqs": [
                {
                    "id": "REQ-1",
                    "title": "A",
                    "status": "open",
                    "acceptance": ["a1"],
                    "dependsOn": [],
                    "skills": ["secure-config-secrets"],
                }
            ],
        }
    )
    result = normalize_local_agent_result(
        {
            "phase": "plan",
            "req_id": "SOLUTION",
            "runId": "plan-run",
            "exit_code": 0,
            "capability_metadata": _metadata(),
            "files": [
                {"path": "docs/harper/PLAN.md", "content": plan_md},
                {"path": "docs/harper/plan.json", "content": plan_json},
            ],
        }
    )
    assert result["ok"] is True
    enriched = next(
        json.loads(f["content"]) for f in result["files"] if f["path"].endswith("plan.json")
    )
    assert enriched["schema_version"] == "1.1.0"
    skill = enriched["reqs"][0]["capabilities"]["skills"][0]
    assert skill["id"] == "secure-config-secrets"
    assert skill["eval_checks"] == ["no-hardcoded-secrets"]
    assert enriched["reqs"][0]["skills"] == ["secure-config-secrets"]  # legacy preserved


def test_capability_coverage_diagnostic():
    from services.capabilities import build_capability_coverage

    plan = {
        "reqs": [
            {"id": "REQ-1", "skills": ["secure-config-secrets"], "packs": ["enterprise-onprem"]},
            {"id": "REQ-2", "skills": ["not-in-index"]},
            {"id": "REQ-3", "skills": "not_applicable"},  # no coverage, no exclusion recorded yet
        ]
    }
    enriched = enrich_plan_capabilities(plan, _metadata())
    cov = build_capability_coverage(enriched, _metadata())

    assert "secure-config-secrets" in cov["selected"]["skills"]
    assert "enterprise-onprem" in cov["selected"]["packs"]
    # eval_checks/gate_implications from the index are aggregated
    assert "no-hardcoded-secrets" in cov["expected_eval_checks"]
    assert "block-if-hardcoded-secrets" in cov["expected_gate_implications"]
    # unknown capability flagged
    assert "not-in-index" in cov["unresolved_capability_ids"]
    # REQ-3 became an exclusion (packs/skills not_applicable) -> not "uncovered"
    assert "REQ-3" not in cov["reqs_without_capabilities"]


def test_local_normalizer_surfaces_capability_coverage_warnings():
    from services.local_agent_package import normalize_local_agent_result

    plan_md = "# PLAN — Demo\n\n## REQ-1 — A\nVerification checkpoints: tests.\n"
    plan_json = json.dumps(
        {
            "snapshot": {"total": 1},
            "reqs": [
                {
                    "id": "REQ-1",
                    "title": "A",
                    "status": "open",
                    "acceptance": ["a1"],
                    "dependsOn": [],
                    "skills": ["not-in-index"],  # selected but unresolved
                }
            ],
        }
    )
    result = normalize_local_agent_result(
        {
            "phase": "plan",
            "req_id": "SOLUTION",
            "runId": "plan-run",
            "exit_code": 0,
            "capability_metadata": _metadata(),
            "files": [
                {"path": "docs/harper/PLAN.md", "content": plan_md},
                {"path": "docs/harper/plan.json", "content": plan_json},
            ],
        }
    )
    assert any(w.startswith("capability_unresolved:") and "not-in-index" in w for w in result["warnings"])


def test_cloud_and_local_use_same_enrichment_shape():
    plan_cloud = {"reqs": [{"id": "REQ-1", "skills": ["secure-config-secrets"]}]}
    plan_local = {"reqs": [{"id": "REQ-1", "skills": ["secure-config-secrets"]}]}
    cloud = json.loads(enrich_plan_json_text(json.dumps(plan_cloud), _metadata()))
    local = json.loads(enrich_plan_json_text(json.dumps(plan_local), _metadata()))
    assert cloud["reqs"][0]["capabilities"] == local["reqs"][0]["capabilities"]
    assert cloud["schema_version"] == local["schema_version"] == "1.1.0"
