---
name: mendix-extension-boundary
description: Use when a REQ touches a Mendix application (Java actions, pluggable widgets, REST/OData integrations, modules), to generate only what lives in supported extension points — never the binary project model — with checks that run without the proprietary runtime and model changes delivered as exact Studio Pro steps.
phases: ["plan", "kit", "eval"]
lanes: ["Mendix", "java", "typescript", "frontend", "backend"]
domains: ["enterprise", "industrial"]
runtime_profiles: ["local", "on-prem", "cloud", "hybrid"]
gate_required: true
obligations:
  - Never create or edit the project model (.mpr) or other platform-owned artifacts as text
  - Java action code only between the BEGIN USER CODE / END USER CODE markers of the generated stub
  - Model changes (entities, microflows, pages, security) delivered as numbered Studio Pro steps in HOWTO
  - Blocking checks run without Studio Pro or the Mendix runtime
eval_checks:
  - extension-code-builds-and-tests
gate_implications:
  - block-if-platform-artifacts-edited
evidence_required:
  - Build and test commands for the generated extension code
  - HOWTO with the Studio Pro steps and the target Mendix version
---

# Mendix Extension Boundary

## Intent

Low-code platforms own their model; generated code that edits it as text corrupts the project. This
skill keeps generation inside the supported extension points and makes every check runnable in the
sandbox.

## Use when

Mendix applications and modules: Java actions, pluggable widgets, REST/OData integrations,
deployment packages.

## Do not use when

Code that does not touch Mendix artifacts or runtime.

## Extension points (what the KIT may generate)

- **Java actions** — `javasource/<module>/actions/<Action>.java`: only the code between
  `// BEGIN USER CODE` and `// END USER CODE` (and the EXTRA CODE block); Studio Pro regenerates the
  rest. Put real logic in plain classes under `javasource/<module>/impl/` tested with JUnit without
  the runtime (pass values in, not `IContext`, where possible). Target the Java version of the
  project's Mendix version; extra libraries go to `userlib/` with their license.
- **Pluggable widgets** — a widget package built with the standard pluggable-widgets tooling: the
  widget XML definition, the TypeScript/React component, `npm run lint`, `npm test` and
  `npm run build` producing the `.mpk`. Component states tested with Testing Library.
- **Integrations** — consumed/published REST or OData described by their contract (OpenAPI), with
  the mapping logic in Java or widget code that tests can reach; endpoints and credentials are
  constants or configuration set per environment, never literals.
- **Model changes** — entities, associations, microflows, pages, security roles: numbered Studio Pro
  steps in `ci/HOWTO.md` with exact names, types and settings, plus what to verify after.

## Checks

- Blocking: JUnit for the plain Java classes, the widget's lint/test/build, contract tests of the
  mapping code. Non-blocking with `environment_requirements`: a headless project build or tests
  that need the Mendix runtime or Studio Pro.

## Forbidden

- Writing `.mpr`, `.mpk` contents by hand, or invented model XML.
- Java outside the user-code markers of generated stubs; hardcoded endpoints or credentials.
- Claiming deployability without a runtime build; manual steps left undocumented.
