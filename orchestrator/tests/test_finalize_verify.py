"""/finalize verification: the solution eval profile (ci/SOLUTION_LTC.json) runs against the
canonical tree, and the prompts of both finalize paths carry its rules and repair."""

from __future__ import annotations

import json
from pathlib import Path

from eval_runner import EvalRunner
from services import finalize_verify


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    (root / "src" / "web" / "app" / "runs").mkdir(parents=True)
    (root / "src" / "web" / "app" / "runs" / "page.tsx").write_text("x\n")
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "test").mkdir()
    (root / "test" / "test_app.py").write_text("x\n")
    (root / "runs" / "kit" / "REQ-001" / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".clike" / "sessions").mkdir(parents=True)
    (root / "docs" / "_private").mkdir(parents=True)
    (root / "docs" / "harper").mkdir(parents=True)
    (root / "ci").mkdir()
    return root


def test_solution_profile_runs_on_the_canonical_tree_without_clike_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKE_EVAL_ROOT", str(tmp_path / "eval"))
    root = _project(tmp_path)
    probe = (
        "python3 -c \"import os,sys; ok=os.path.exists('src/app.py') and os.path.exists('test/test_app.py') "
        "and os.path.exists('src/web/app/runs/page.tsx') and not any(os.path.exists(p) for p in "
        "('runs','.git','.clike','docs/_private')); sys.exit(0 if ok else 1)\""
    )
    ltc = {"req_id": "SOLUTION", "checks": [{"id": "tree", "command": probe, "cwd": ".", "blocking": True}]}
    profile = root / finalize_verify.SOLUTION_PROFILE
    profile.write_text(json.dumps(ltc))
    report = EvalRunner(root).run_profile(profile=str(profile), ltc=ltc, req_id=finalize_verify.SOLUTION_EVAL_ID)
    assert report.status == "PASS", [(c.name, c.stdout, c.stderr) for c in report.cases]


def test_cloud_finalize_prompt_carries_rules_profiles_and_repair():
    from services.cloud_prompt.messages import compose_phase_messages

    verify = {
        "req_profiles": [
            {"req": "REQ-001", "checks": [{"id": "unit", "command": "pytest test"}],
             "environment": {"required_variables": [{"name": "DB_URL", "provision": "postgres_database"}]}},
            {"req": "REQ-002", "checks": [{"id": "lint", "command": "ruff check"}]},
        ],
        "repair": {"cycle": 1, "max_cycles": 3, "failures": [
            {"name": "e2e", "code": 1, "command": "npx playwright test", "output": "Error: element(s) not found"}],
            "files": [{"path": "src/web/app/page.tsx", "content": "export default 1"},
                      {"path": "package-lock.json", "content": "L" * 5000}]},
    }
    payload = {"phase": "finalize", "cmd": "finalize", "finalize_verify": verify, "core_blobs": {
        "TECH_CONSTRAINTS.yaml": 'classification:\n  deployment_context: "on-premises"\n'}}
    text = compose_phase_messages(payload)[-1]["content"]
    assert "## SOLUTION VERIFICATION" in text and "BEGIN_FILE ci/SOLUTION_LTC.json" in text
    # how the REQs ran (environment, services), never their test suites: the gates passed them
    assert '"req": "REQ-001"' in text and "DB_URL" in text
    assert "pytest test" not in text and "REQ-002" not in text
    assert "Do NOT run the REQs' test suites" in text and "FINALIZE_REPORT.md" in text
    assert "MISSING INFORMATION" in text and "scripts/setup_local.sh" in text
    assert "Host ports on the developer's machine" in text
    assert "On-premises / local deployment" in text
    assert "## SOLUTION REPAIR — cycle 1 of 3" in text and "element(s) not found" in text
    assert "#### src/web/app/page.tsx" in text and "LLLL" not in text and "- package-lock.json" in text


def test_deployment_hint_and_cloud_rule():
    payload = {"core_blobs": {"docs/harper/TECH_CONSTRAINTS.yaml": "  deployment_target: azure app service\n"}}
    assert finalize_verify.deployment_hint(payload) == "azure app service"
    assert any("CLIKE_ALLOW_CLOUD_MUTATION" in r for r in finalize_verify.solution_verify_rules("azure app service"))


def test_agent_finalize_lines_offer_the_sandbox_only_when_served():
    with_check = "\n".join(finalize_verify.agent_finalize_lines({"repair": {}}, "", 6))
    assert "node .clike/bin/eval-check.mjs" in with_check and "at most 6 runs" in with_check
    assert "eval-check" not in "\n".join(finalize_verify.agent_finalize_lines({}, "", 0))


def test_agent_finalize_package_serves_eval_checks_of_the_solution_profile():
    from services.local_agent.finalize import build_finalize_local_agent_package

    payload = {"runId": "r", "localAgentExecutor": "gpt_codex", "finalize_verify": {"eval_check": True, "eval_check_max_runs": 5}}
    policy = {"requested": "local_agent", "selected": "local_agent", "reason": "t", "phase_supported": True}
    out = build_finalize_local_agent_package(payload=payload, execution_policy=policy)
    agent = out["local_agent"]
    assert agent["eval_check"] == {"profile": "ci/SOLUTION_LTC.json", "max_runs": 5}
    assert "ci/SOLUTION_LTC.json" in agent["allowed_write_roots"]
    assert "SOLUTION VERIFICATION" in agent["prompt_content"] and "at most 5 runs" in agent["prompt_content"]


def test_rules_cover_the_listening_address_expiring_values_and_the_local_check():
    # test project: the console bridge refused every request in containers (0.0.0.0) while the
    # sandbox smoke passed on loopback; generated fixture sessions expired after a week
    rules = " ".join(finalize_verify.solution_verify_rules(""))
    assert "0.0.0.0" in rules and "Host/Origin" in rules
    assert "listen on every interface" in rules
    assert "renews them when they have expired" in rules
    assert "local::check_solution_local" in rules
    agent = "\n".join(finalize_verify.agent_finalize_lines({}, "", 0))
    assert "0.0.0.0" in agent and "CLike runs the check on the developer's machine" in agent


def test_finalize_follows_the_use_cases_of_the_spec_on_both_paths():
    # the journeys to verify are the SPEC use cases; the report has a status per use case
    import services.finalize_verify as fv

    cloud = fv.cloud_finalize_section({}, "")
    local = "\n".join(fv.agent_finalize_lines({}, ""))
    for text in (cloud, local):
        assert "`## Use Cases` of docs/harper/SPEC.md" in text
        assert "FINALIZE_REPORT.md has a `## Use cases` table" in text
