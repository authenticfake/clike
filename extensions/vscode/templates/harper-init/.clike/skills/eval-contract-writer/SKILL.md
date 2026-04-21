---
name: eval-contract-writer
description: Use when KIT must emit runnable test, lint, type, build, security, or runtime validation instructions.
phases: ["kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "ai-native"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
---

# Eval Contract Writer Skill

## Intent

Every implementation REQ must produce enough execution guidance for EVAL and GATE to validate the generated work deterministically.

## Use when

Use this skill for every KIT that produces runnable source code, tests, CI artifacts, adapters, infrastructure code, UI code, model/RAG logic, or integration behavior.

## Do not use when

Do not use this skill for pure prose-only documentation updates with no executable validation path.

## Signals

- The REQ generates `src/`, `test/`, `tests/`, `ci/`, scripts, Dockerfiles, IaC, frontend components, backend services, model evaluation code, or runtime adapters.
- The REQ acceptance criteria mention tests, lint, type checks, build, security, smoke checks, or external runners.
- Gate expectations include tests, lint, types, security, build, model quality, design adherence, runtime profile adherence, or skill adherence.

## Required behavior

- Generate an explicit HOWTO for local execution.
- Generate or update an LTC-style execution contract when the REQ produces runnable code.
- Include exact commands for tests, lint, type checks, build checks, or runtime smoke checks when applicable.
- Mark external integration checks as opt-in.
- Document expected report paths when available.
- Avoid claiming that a check passed unless evidence exists.
- Keep commands copy-pasteable and scoped to the generated REQ.

## Forbidden behavior

- Do not emit vague HOWTO steps such as "run the tests" without exact commands.
- Do not put commands that require unavailable secrets or infrastructure into blocking local checks.
- Do not claim checks passed unless logs or command results exist.
- Do not omit dependency installation instructions when generated tests require dependencies.
- Do not generate LTC/HOWTO that points outside the target REQ candidate root unless explicitly needed.

## Evidence required

- `ci/LTC.json` exists for runnable REQs.
- `ci/HOWTO.md` exists and contains copy-pasteable local commands.
- LTC contains executable `cases[]` or a backward-compatible command mapping accepted by EvalRunner.
- Report paths are declared when reports are generated.
- External checks are explicitly marked opt-in, non-blocking, or environment-blocked when infrastructure is unavailable.
- Generated docs explain how to reproduce validation.

## Repair guidance

- If LTC is malformed, repair LTC before changing source code.
- If HOWTO is vague, rewrite the command section with exact shell commands.
- If dependencies are missing, add `ci/requirements.txt` or document the project-native dependency file.
- If external services are unavailable, split local deterministic checks from opt-in integration checks.

## Gate implications

The REQ satisfies this skill only if:
- generated validation commands are concrete;
- local validation is possible when the runtime profile requires it;
- missing tools or external runners are documented clearly;
- gate expectations are traceable to commands, reports, or documented manual checks.