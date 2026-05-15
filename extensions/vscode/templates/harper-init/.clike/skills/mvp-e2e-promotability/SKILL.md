---
name: mvp-e2e-promotability
description: Convert requirements into narrow but end-to-end promotable MVP slices instead of shallow demos or decorative code.
phases: ["spec", "plan", "kit", "eval", "gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "ai-native", "iac"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
gate_required: true
---

# MVP E2E Promotability Skill

## Intent

A REQ should produce a small but complete slice that can be run, tested, evaluated, promoted, and extended.

This skill prevents CLike from generating outputs that look plausible but are not useful as an MVP step: decorative dashboards, isolated modules with no entrypoint, fake local success, missing run commands, missing API wiring, missing route/page composition, or tests that do not prove acceptance criteria.

## Use when

Use this skill when a REQ contributes to a user-facing feature, API capability, workflow, service boundary, integration, persistence path, AI feature, runtime profile, or product slice that should be promotable.

## Do not use when

Do not use this skill for pure prose-only documents, isolated research notes, or deliberate spike/prototype REQs that are explicitly non-promotable.

## Signals

Apply this skill when the REQ mentions:

- MVP;
- E2E;
- demo-ready;
- pilot-ready;
- promotable;
- backoffice;
- app;
- frontend/backend integration;
- workflow;
- route;
- API;
- local run;
- validation;
- archive;
- export;
- Q&A;
- runtime profile;
- launch script;
- finalize;
- runnability.

## Required behavior

When selected, KIT or FINALIZE must:

- reuse existing source before creating new layers;
- patch existing composition before creating parallel composition;
- wire existing services, routers, pages, clients, or adapters when available;
- provide a local deterministic run path;
- provide exact commands for local verification;
- produce or update tests/checks mapped to acceptance criteria;
- make the primary user or service flow executable;
- expose clear failure, empty, loading, deny, and success states where relevant;
- keep external integrations behind adapters or opt-in checks;
- document what is MVP-complete and what remains out of scope.

## Minimum MVP evidence

A promotable MVP slice should include at least one of these evidence sets, depending on stack:

### Backend/API

- application import or boot check;
- route/API smoke check;
- service behavior tests;
- failure-path tests;
- local fake/in-memory adapter when external infrastructure is unavailable.

### Frontend/UI

- route/page exists;
- API client boundary exists;
- loading/empty/error/success states exist;
- build/type/lint checks pass when tooling exists;
- component or route smoke tests when test tooling exists.

### Full-stack

- frontend calls are mapped to backend routes;
- local backend and frontend launch commands exist;
- route parity check exists or is documented;
- `.env.example` or equivalent exists.

### Data/persistence

- migration/model/schema validation exists;
- local database or deterministic repository path exists;
- no-side-effect failure test exists when persistence changes are acceptance-critical.

## Forbidden behavior

- Do not generate a single decorative page when the requirement implies multiple operational capabilities.
- Do not create fake “completed” flows that only update local component state when backend APIs are required.
- Do not duplicate backend lifecycle or authorization rules in the frontend.
- Do not claim runnability without a command.
- Do not hide missing composition root behind module-level tests.
- Do not create one launcher per feature when a project-level launcher is required.
- Do not rewrite working modules when wiring them is enough.
- Do not promote a slice that cannot be explained as a coherent user or service journey.

## Planning guidance

When a broad requirement is too large, split it into MVP-promotable REQs such as:

- shell/navigation/composition;
- core API contract;
- persistence boundary;
- primary workflow;
- search/filtering;
- admin/configuration;
- AI assistant UX;
- local run/finalize integration.

Do not split so aggressively that no REQ is useful by itself.

Each REQ should have:

- a user or service outcome;
- concrete source boundary;
- concrete verification path;
- explicit out-of-scope;
- dependency mapping;
- promotion evidence.

## KIT guidance

During KIT, the model should ask:

1. What already exists that can be reused?
2. What is the smallest complete flow that satisfies the REQ?
3. What entrypoint or route proves the flow?
4. What local command proves it?
5. What failure path proves robustness?
6. What must remain out of scope?

## FINALIZE guidance

During FINALIZE, the model must close the gap between promoted slices and an integrated runnable solution.

It should create or verify, when applicable:

- composition root;
- settings/env loader;
- repository/dependency factory;
- DB/session factory;
- local-dev profile;
- local run scripts;
- route/API parity;
- README/HOWTO/SANITY docs;
- junk artifact cleanup;
- manifest validity.

## Gate implications

Gate must BLOCK promotion when:

- the REQ claims MVP/E2E behavior but lacks an executable path;
- the main user/service journey is not represented in source;
- local run instructions are missing for runnable code;
- acceptance-critical API/page/route is missing;
- frontend/backend route parity is broken;
- generated output is decorative only;
- tests do not map to acceptance criteria;
- selected skills, packs, or design profiles are ignored.

Gate may WARN when:

- optional external infrastructure is unavailable but local deterministic checks pass;
- visual polish is incomplete but behavior is verifiable;
- full production hardening is deferred and clearly documented.

## Success definition

The skill is satisfied when a reviewer can run the slice locally, inspect evidence, understand limitations, and safely promote it as the next MVP step.