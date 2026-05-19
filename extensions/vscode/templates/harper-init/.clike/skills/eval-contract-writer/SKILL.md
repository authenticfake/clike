---
name: eval-contract-writer
description: Require every runnable KIT to emit deterministic validation artifacts for EVAL and GATE.
phases: ["kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "ai-native"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
---

# Eval Contract Writer Skill

## Intent

Every runnable KIT must produce enough executable validation evidence for CLike EVAL and GATE to judge the REQ deterministically.

This skill prevents vague HOWTOs, non-runnable LTC files, shallow tests, fake pass claims, and generated code that cannot be evaluated.

## Use when

Use this skill for every KIT that generates or modifies source code, tests, CI artifacts, adapters, infrastructure code, frontend components, backend services, model/RAG behavior, MCP/tooling behavior, or runtime integration behavior.

## Do not use when

Do not use this skill for pure prose-only documentation changes with no executable validation path.

## Signals

Apply this skill when the REQ, PLAN, TARGET_CONTRACT, FILE_REQUIREMENTS, or selected capabilities mention tests, lint, type checks, build checks, smoke checks, security checks, model quality checks, external runners, LTC, HOWTO, evaluation evidence, or gate expectations.

## KIT Generation Rules

The KIT must generate validation artifacts as part of the candidate output.

Required candidate paths:

```text
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
```

When dependencies are needed only for the generated candidate, prefer:

```text
runs/kit/<REQ-ID>/ci/requirements.txt
```

or the project-native equivalent, if already established.

## Required LTC Behavior

`ci/LTC.json` must be machine-readable and should include:

- `req_id`;
- `lane`;
- `runtime_profile`;
- `commands[]` or `cases[]`;
- blocking local checks;
- optional external checks;
- expected report paths when available;
- gate-relevant thresholds;
- notes for environment-blocked checks;
- enough detail for EvalRunner or an agent to execute and diagnose.

A blocking command must not require unavailable cloud credentials, internet access, private runners, or production infrastructure unless the REQ explicitly requires that environment and the infrastructure is available.

## Required HOWTO Behavior

`ci/HOWTO.md` must be human-readable and copy-paste runnable.

It must include:

- workspace/root assumption;
- prerequisites;
- local validation commands;
- expected results;
- troubleshooting;
- external validation steps if any;
- configuration variables;
- known limitations;
- what evidence EVAL/GATE should inspect.

## Test Generation Rules

For each acceptance criterion, the KIT should produce one of:

- a unit test;
- an integration-style test using local fake infrastructure;
- a smoke check;
- a static validation;
- a documented external check when local execution is impossible.

The KIT must not silently skip acceptance criteria.

## Forbidden Behavior

- Do not write “run the tests” without exact commands.
- Do not claim checks passed unless logs or execution evidence exists.
- Do not put production-only checks into blocking local validation.
- Do not omit dependency instructions when generated tests require dependencies.
- Do not generate placeholder tests that only assert `true`.
- Do not rely only on import tests when behavior is required.
- Do not point LTC/HOWTO to unrelated canonical files unless the REQ explicitly requires it.
- Do not make EVAL infer critical commands from prose.

## Required Evidence

The KIT satisfies this skill only when:

- `ci/LTC.json` exists;
- `ci/HOWTO.md` exists;
- local commands are concrete;
- tests/checks map to acceptance criteria;
- external checks are clearly marked as blocking or non-blocking;
- missing infrastructure is documented honestly;
- reproduction steps are clear enough for a local agent or developer.

## Preferred LTC Shape

Use the project schema if one exists. Otherwise prefer a compact structure like:

```json
{
  "req_id": "REQ-001",
  "lane": "python",
  "runtime_profile": "local-cloud",
  "commands": [
    {
      "id": "unit-tests",
      "description": "Run local deterministic tests for REQ-001.",
      "cmd": "PYTHONPATH=runs/kit/REQ-001/src pytest -q runs/kit/REQ-001/test",
      "blocking": true,
      "requires_external_infra": false
    }
  ],
  "reports": [],
  "gate_policy": {
    "requires": ["unit-tests"],
    "promote_on_pass_only": true
  }
}
```

Adapt command syntax to the repository language and tooling.

## Repair Guidance

If LTC is malformed:

- repair LTC first before changing source;
- keep JSON valid;
- reduce schema complexity rather than inventing unsupported fields.

If HOWTO is vague:

- rewrite the command section;
- add root path assumption;
- add expected output;
- add troubleshooting.

If tests are shallow:

- add behavior tests;
- add failure-path tests;
- add contract tests around boundaries.

If tests assert exception/error semantics:

- preserve assertions on retryability, classification, status/statusCode, provider codes, system codes, cause, and domain failure categories;
- use the active language's safe narrowing, casting, matching, downcast, typed-exception, or adapter mechanism before reading custom exception/error metadata;
- do not remove failure-path assertions merely to satisfy static analysis;
- do not disable type checking, linting, compiler checks, or static-analysis rules globally;
- keep the repair local to the candidate source, test, or CI utility file.

If promoted or dependency tests become stale because the current REQ intentionally extends behavior:

- do not modify canonical `test/` or `tests/` roots during KIT;
- add an updated same-relative-path test under `runs/kit/<REQ-ID>/test/` so the official eval overlay shadows stale expectations;
- preserve the original regression intent while updating expected additive behavior;
- prefer scoped queries and unique accessible names over positional selectors;
- do not delete meaningful assertions to hide regressions.

If external services are unavailable:

- split local deterministic checks from opt-in external checks;
- keep local checks blocking;
- mark external checks as non-blocking or environment-blocked.

## MVP and Solution Runnability Evidence

When `mvp-e2e-promotability`, `enterprise-solution-architecture`, `backoffice-workflow-ux`, or an enterprise pack is selected, validation artifacts must include evidence appropriate to the selected scope.

For backend/API work, prefer:

- app import or boot check;
- route/API smoke check;
- service behavior tests;
- failure-path tests;
- local fake/in-memory adapter checks when external infrastructure is unavailable.

For frontend/UI work, prefer:

- route/page smoke checks;
- component state tests;
- build/type/lint checks;
- API client boundary checks;
- accessibility-oriented assertions where tooling exists.

For Node/TypeScript frontend work:

- install dependencies through the runnable package manifest used by the execution area;
- keep Vitest/Jest/ESLint/TypeScript config files inside the same runnable package root when they import package dependencies;
- when tests live outside the package root, make all external test imports explicitly resolvable through runner aliases or equivalent package-root resolution;
- declare every imported test dependency in devDependencies, including @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jest-axe, jsdom, vitest, and framework-specific test helpers;
- do not remove meaningful tests to hide dependency-resolution failures.

For Node/TypeScript frontend work:

- install dependencies through the runnable package manifest used by the execution area;
- keep Vitest/Jest/ESLint/TypeScript config files inside the same runnable package root when they import package dependencies;
- when tests live outside the package root, make all external test imports explicitly resolvable through runner aliases or equivalent package-root resolution;
- declare every imported test dependency in devDependencies, including @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jest-axe, jsdom, vitest, and framework-specific test helpers;
- do not remove meaningful tests to hide dependency-resolution failures.

For full-stack work, prefer:

- local backend run/check command;
- local frontend run/build command;
- route parity check when frontend calls backend APIs;
- `.env.example` validation;
- HOWTO commands aligned with actual scripts.

For FINALIZE, validation artifacts should verify:

- manifest parse;
- script presence;
- backend/frontend boot or build;
- route/API parity when applicable;
- junk artifact cleanup;
- docs truthfulness against actual commands.

Do not claim MVP or solution runnability without executable evidence.

## Gate Impact

Gate must BLOCK promotion when:

- runnable source has no LTC;
- runnable source has no HOWTO;
- blocking validation cannot execute locally and no valid external runner evidence exists;
- acceptance-critical behavior has no test/check/evidence;
- LTC/HOWTO claims success without evidence;
- validation commands point to missing paths.

Gate may WARN when:

- external integration checks are documented but not executed;
- local checks pass and external validation is clearly non-blocking;
- coverage is partial but acceptance-critical behavior is covered.

## Success Definition

This skill is satisfied when a developer, local agent, cloud worker, or EvalRunner can understand and execute the validation path without guessing.
