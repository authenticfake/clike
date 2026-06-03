# BMAD Quality Scorecard

BMAD-aware methodology profiles are intended to improve the clarity and readiness of CLike-owned Harper artifacts. The scorecard does not claim automatic quality improvement. It defines deterministic checks and human review prompts that help maintainers see whether SPEC, PLAN, `plan.json`, and lane-guides are useful for downstream `/kit`, `/eval`, and `/gate` work.

CLike remains the governance runtime. TECH_CONSTRAINTS remains authoritative for runtime, provider, deployment, identity, dependency, command, and environment assumptions. The scorecard must not hardcode Python, Node, AWS, a database, a queue, a UI framework, an IaC tool, or any other stack choice unless that choice is evidenced by TECH_CONSTRAINTS, SPEC, PLAN, `plan.json`, repository manifests, existing source, or explicit user input.

## Auto-Checkable Criteria

The deterministic validators are structural. They can identify shallow artifacts, missing fields, and absent quality topics, but they cannot prove product correctness.

For `docs/harper/SPEC.md`, the validator checks for coverage of completeness, testability, acceptance criteria precision, functional requirement clarity, UX or user journey quality, non-functional requirements, security/privacy/compliance, observability/operations, scope and non-goals, and traceability to IDEA and companion artifacts.

For `docs/harper/plan.json`, each REQ should include `id`, `title`, `status`, `dependsOn`, `lane`, `domain`, `runtime_profile`, `functional_scope`, `technical_scope`, `non_functional_requirements`, `security_requirements`, `operational_requirements`, `integration_contracts`, `data_contracts`, `acceptance`, `test_strategy`, `risk_notes`, `main_module_boundary`, `gate_expectations`, and `kit_readiness`.

For `docs/harper/lane-guides/<lane>.md`, each guide should describe lane purpose, runtime constraints, expected files, test commands, lint/type/build/security commands when applicable, contract boundaries, integration points, forbidden shortcuts, and eval/gate expectations.

## Fixture Regression Tests

The repository includes a fixture-based native-vs-BMAD regression test for IDEA quality. The native fixture is copied from `CoffeeBuddy/IDEA_cb_clike.md` into `orchestrator/tests/fixtures/native/IDEA.md`. The BMAD experimental fixture is copied from the provided CoffeeBuddy BMAD IDEA file into `orchestrator/tests/fixtures/bmad_experimental/IDEA.md`.

This regression test exists to prove evaluator sensitivity. It checks that the deterministic scorecard can detect richer BMAD-style IDEA detail such as `/spec Handoff Readiness`, deployment portability, SPEC-ready technology constraints, downstream handoff readiness, and traceability. It does not prove live model quality, does not benchmark runtime behavior, and does not claim that BMAD will always improve future outputs.

The fixture acceptance threshold is intentionally narrow:

- both copied fixtures must exist and parse as Markdown sections;
- the BMAD experimental fixture must score higher than the native fixture;
- the BMAD experimental fixture must contain `/spec Handoff Readiness`;
- the native fixture must lack at least some high-fidelity sections;
- the scorecard must return a numeric score plus missing and improvement notes.

## Human Review Criteria

Human reviewers should verify that the artifact is coherent, not merely populated. A rich `plan.json` still needs review for whether REQ boundaries are sensible, dependencies are realistic, acceptance criteria are measurable, security and operational obligations are relevant, and `kit_readiness` reflects real evidence.

Reviewers should also check that companion artifacts improve downstream work. BMAD companion material should clarify product intent, UX expectations, architecture, risk, implementation notes, or QA repair guidance. More files are not a success metric by themselves.

## Failure Interpretation

A failed structural score means the artifact is likely too shallow for governed downstream execution. It does not mean BMAD is broken, and it does not decide eval or gate outcomes. EvalRunner remains authoritative for eval evidence, and gate remains CLike-owned.

When a scorecard warning appears, the preferred repair is to improve the canonical Harper artifact or bounded companion artifact that carries the missing context. Do not weaken CLike governance, expand write roots, bypass candidate-first generation, or introduce runtime assumptions to silence the warning.
