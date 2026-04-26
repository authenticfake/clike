# Skill: Mendix Extension Boundary

## Intent

Ensure Mendix-related requirements respect the boundary between generated code, Mendix model artifacts, Java actions, microflows, integrations, and platform deployment constraints.

This skill prevents generic code generation from corrupting low-code platform structure.

## Use when

Use this skill when a REQ touches Mendix applications, Mendix modules, Java actions, microflows, nanoflows, domain models, REST integrations, OData, custom widgets, marketplace modules, deployment packages, or on-prem Mendix runtime behavior.

## Do not use when

Do not use this skill for unrelated JavaScript/Python/backend work that does not interact with Mendix artifacts or runtime constraints.

## Signals

- The REQ mentions Mendix, Studio Pro, module, microflow, nanoflow, Java action, entity, domain model, custom widget, marketplace module, OData, published REST service, consumed REST service, deployment package, runtime, or on-prem installation.
- Acceptance criteria involve low-code artifacts plus generated code.
- TECH_CONSTRAINTS references enterprise/on-prem Mendix runtime.

## Required behavior

- Treat Mendix model artifacts as governed platform assets, not arbitrary text files.
- Keep generated custom code inside safe extension points.
- Document which changes are intended for Studio Pro/manual import versus generated source.
- Keep Java actions, widgets, and integration helpers compatible with the target Mendix runtime/version when known.
- Do not assume cloud-only deployment.
- Provide local or static validation checks that do not require proprietary runtime when unavailable.
- Mark Studio Pro/runtime validation as external/non-blocking unless available.

## Forbidden behavior

- Do not invent Mendix internal file formats.
- Do not modify binary/model artifacts blindly.
- Do not generate platform changes that require manual steps without documenting them.
- Do not hardcode environment-specific Mendix endpoints or credentials.
- Do not claim deployability without Studio Pro/runtime validation evidence.
- Do not mix generated helper code with platform-owned artifacts without a boundary.

## Evidence required

- Clear list of generated files and their Mendix role.
- HOWTO explaining manual import/configuration steps when needed.
- Tests or static checks for generated Java/custom widget/helper code where possible.
- External validation section for Studio Pro, runtime, or deployment package checks.
- Compatibility notes for Mendix version/runtime assumptions.

## Repair guidance

- If the output edits unknown Mendix artifacts, replace it with documented manual steps or safe extension files.
- If generated code lacks runtime assumptions, add compatibility notes.
- If deployment validation cannot run, mark it external/non-blocking and provide manual verification steps.
- If integration code hardcodes endpoints, move them to configuration.
- If Java/widget code is generated, add compile/lint/test commands when project tooling exists.

## Gate implications

Gate should block promotion when:
- Generated changes corrupt or blindly rewrite Mendix-owned artifacts.
- Required Java/widget checks fail.
- Manual Mendix steps are required but undocumented.
- Runtime compatibility assumptions are missing for Mendix-scoped REQs.
- Environment-specific secrets or endpoints are hardcoded.

Gate may allow non-blocking warnings when:
- Studio Pro validation is unavailable but generated extension code passes local checks.
- Deployment package validation is external and documented.

## Examples

- A Java action helper is generated with tests and clear Studio Pro integration notes.
- A custom widget change includes build commands and Mendix compatibility notes.
- A REST integration REQ documents consumed service configuration and local validation limits.

## Non-examples

- A generated XML/model file claiming to update a Mendix domain model without platform validation.
- A Mendix deployment claim with no runtime version or manual verification.
- A Java action that hardcodes production credentials.
---

# CLike Promotable KIT Enforcement Layer

## Purpose

This layer makes the skill operational for CLike `/kit` generation.

The goal is not to produce plausible code. The goal is to produce candidate artifacts that can be evaluated, repaired, and promoted through EVAL and GATE with minimal human rework.

## Promotable Code Obligations

When this skill is selected for a REQ, the KIT must:

- respect `main_module_boundary`;
- respect `functional_scope` and `technical_scope`;
- generate the smallest complete implementation slice;
- prefer repository-native conventions over invented abstractions;
- produce source files only under the target KIT source root;
- produce tests only under the target KIT test root;
- keep canonical `src/`, `test/`, and `tests/` read-only during candidate generation;
- document any intentional limitation instead of pretending completeness;
- avoid broad rewrites unless explicitly required by the REQ.

## Required Candidate Artifacts

The KIT should produce or update:

```text
runs/kit/<REQ-ID>/src/
runs/kit/<REQ-ID>/test/
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md
```

If the REQ is documentation-only or policy-only, the KIT must explicitly state why source/test artifacts are not required.

## Code Shape Expectations

Generated code should favor:

- explicit boundaries;
- dependency injection or constructor/function injection where practical;
- small cohesive modules;
- deterministic local behavior;
- typed schemas/contracts when the stack supports them;
- error paths that are visible and testable;
- safe defaults;
- clear adapter seams for external systems.

Generated code must avoid:

- hidden global state;
- hardcoded environment assumptions;
- silent fallbacks;
- fake success;
- speculative framework layers;
- broad unrelated refactors;
- acceptance criteria implemented only in prose.

## Test Expectations

Tests must map to acceptance criteria.

Prefer:

- deterministic unit tests;
- contract tests around adapters and payloads;
- failure-path tests;
- local fake/simulator tests for external dependencies;
- smoke checks only when deeper tests are not possible.

Avoid:

- placeholder tests;
- tests that only import modules when behavior is required;
- tests that require production credentials;
- network-dependent blocking tests unless explicitly scoped.

## LTC Expectations

`ci/LTC.json` must be valid JSON and include enough information for EvalRunner or a local agent to execute checks.

It should include:

- target `req_id`;
- lane/runtime profile when known;
- blocking local commands;
- optional external commands;
- report paths when available;
- environment-blocked status for unavailable infrastructure;
- gate-relevant policy hints.

## HOWTO Expectations

`ci/HOWTO.md` must be clear enough for a developer to run without guessing.

It should include:

- where to run commands from;
- prerequisites;
- local commands;
- expected result;
- troubleshooting;
- required environment variables;
- optional external validation steps;
- limitations and non-goals.

## Gate Impact

GATE should BLOCK promotion when this selected skill is materially violated.

Blocking examples:

- source is not mapped to the target REQ;
- acceptance-critical behavior has no test or executable evidence;
- LTC/HOWTO are missing for runnable code;
- production services or credentials are required for local blocking checks;
- selected capability obligations are ignored;
- generated files modify forbidden canonical roots;
- code claims completeness without evidence.

GATE may WARN when:

- optional external validation is not available but a deterministic local contract check exists;
- documentation is thin but executable evidence is complete;
- future hardening is correctly documented as out of scope.
