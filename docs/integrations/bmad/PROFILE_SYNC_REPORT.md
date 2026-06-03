# BMAD Profile Sync Report

This template records a manual reference review for the CLike-owned BMAD-aware methodology profile. It is not generated at runtime and it is not evidence of automatic upstream synchronization.

## Reviewed BMAD Reference

- Reference name: BMAD Method
- Reference repository: `manual-review-pending`
- Reference documentation: `manual-review-pending`
- Reviewed version: `manual-review-pending`
- Reviewed commit: `manual-review-pending`
- Reviewed at: `manual-review-pending`
- Reviewed by: `manual-review-pending`

## Reviewed Materials

List the exact materials reviewed. Include release notes, repository paths, documentation pages, role definitions, workflow descriptions, checklist material, and any fixture workspace used for comparison.

- `manual-review-pending`

## Adopted Concepts

Record concepts adopted into the CLike-owned profile and explain where they appear in the manifest, agent profile, workflow profile, documentation, or tests.

- Agent responsibilities: `manual-review-pending`
- Workflow sequence: `manual-review-pending`
- Artifact expectations: `manual-review-pending`
- Handoff rules: `manual-review-pending`
- Checklist patterns: `manual-review-pending`
- Customization model: `manual-review-pending`
- Project-context model: `manual-review-pending`

## CLike Adaptation

Explain how each adopted concept was adapted to preserve Harper governance.

- CLike remains the governance runtime.
- Methodology is not executor.
- The orchestrator resolves `methodology_context`.
- Gateway is used only for cloud prompt composition.
- `local_agent_package` is the local-agent injection point.
- EvalRunner remains authoritative.
- Gate remains CLike-owned.
- Candidate-first generation and write boundaries are preserved.

## Excluded Concepts

Record concepts reviewed but intentionally excluded from the CLike profile.

- Runtime dependency: excluded.
- CLI execution: excluded.
- Uncontrolled writes: excluded.
- Gate authority: excluded.
- Copied official prompts: excluded.
- Latest auto-pulled in production: excluded.

## Fixture Comparison Notes

Fixture workspace comparison is optional and manual only. If used, record the fixture location, scenario, generated artifacts, observations, and any CLike profile changes that resulted.

- Fixture workspace: `manual-review-pending`
- Scenario: `manual-review-pending`
- Observations: `manual-review-pending`
- Resulting CLike changes: `manual-review-pending`

## Scorecard And Verification Notes

Record whether deterministic scorecards were run and whether they were used only as review aids. Passing scorecard output does not prove live model quality.

- SPEC/PLAN/plan.json/lane-guide scorecard result: `manual-review-pending`
- IDEA native-vs-BMAD fixture scorecard result: `manual-review-pending`
- Gateway `prompt_debug` reviewed: `manual-review-pending`
- Local-agent `AGENT_EXECUTION_CONTEXT.json` reviewed: `manual-review-pending`
- Local-agent `AGENT_EVAL_CONTEXT.json` reviewed: `manual-review-pending`
- Companion artifact inventory reviewed: `manual-review-pending`

## Required Tests Before Merge

Run these before merging a profile sync:

```text
python -m json.tool orchestrator/methodologies/bmad/manifest.json
python -m compileall orchestrator gateway
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_methodology_resolver.py orchestrator/tests/test_bmad_safety_boundaries.py orchestrator/tests/test_bmad_quality_contracts.py orchestrator/tests/test_bmad_quality_scorecard.py
```

Also run the implementation checklist safety grep for official BMAD package-runner and process-spawn patterns across `orchestrator`, `gateway`, `extensions`, `docs`, and `README.md`. It should produce no runtime invocation findings. If it returns documentation text, rewrite the documentation so it states the boundary without matching runtime-call patterns.

Current out-of-scope roadmap items include BMAD runtime execution, `npx bmad-method` runtime invocation, the BMAD importer, TEA, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, and automatic latest BMAD tracking at runtime. Do not mark any of these as reviewed current behavior unless the implementation actually exists.
