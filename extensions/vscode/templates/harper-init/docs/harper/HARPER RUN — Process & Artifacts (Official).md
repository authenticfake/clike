# HARPER RUN — Process & Artifacts (Official)


## Overview

Harper Run is a **structured, iterative pipeline** for featurelets:

```
IDEA.md → /spec → /plan → (/kit → /eval → /gate)* → /finalize → Solution
```

* **Idea** Vision, Problem Statement, Value & Outcomes and tech constraints.
* **Spec** defines the contract (what & why).
* **Plan** breaks down work into **REQ-IDs** with acceptance and dependencies.
* **Kit** implements one or more REQ-IDs (code + tests + docs).
* **Eval** runs the suite (tests/lint/type/security/build) and records outcomes **per REQ-ID**.
* **Gate** promotes REQ-IDs that pass, marking them **done** and advancing the next target.
* **Finalize** cuts notes/tags and (optionally) merges.

Artifacts are versioned; **telemetry** is captured per phase.

---

## Inputs & Knowledge Model

Each phase uses the same knowledge inputs, with **minimal scope** for efficiency:

* **Chat history (Harper mode)** with history scope (`singleModel` or `allModels`). Only **user/assistant** messages (system excluded).
* **Core docs** in `docs/harper/`:

  * **explicit core list** (e.g., `["IDEA.md","SPEC.md"]`)
  * **auto-discovery by prefix**: a core entry like `SPEC.md` implies **all files** starting with `SPEC` (e.g., `SPEC_verAndrea.md`).
* **RAG attachments**: large files are chunked & retrieved **only if relevant** to the active REQ-ID(s).
* **Constraints**: tech constraints synced from IDEA/SPEC to canonical `docs/harper/constraints.json`.

---

## Folder Structure (key paths)

```
docs/harper/
  IDEA.md
  SPEC.md
  PLAN.md
  plan.json
  KIT.md
  RELEASE_NOTES.md
  constraints.json
runs/<runId>/
  kit.report.json
  eval.summary.json
  gate.decisions.json
  telemetry.json
  logs/
src/… (project code)
tests/… (generated and/or existing tests)
```

* `docs/harper/*` = **canonical documents** (human-readable + machine-readable `plan.json`).
* `runs/<runId>/` = **ephemeral but versioned state** per iteration:

  * `kit.report.json`: which **REQ-ID(s)** were targeted, which files changed, and test files generated.
  * `eval.summary.json`: test & checks results **by REQ-ID** + aggregates.
  * `gate.decisions.json`: promotion decisions for the batch.
  * `telemetry.json`: timing, token usage, model, context, counts.

> **Why `runs/`?** To keep **state & telemetry** coherent across iterations, reproducible reviews, and to let `/eval` and `/gate` reason on **REQ-ID** instead of raw diffs.

---

## Phases

### `/spec` → `SPEC.md`

* **Input**: `IDEA.md`, chat history, `docs/harper/*` by prefix, RAG attachments.
* **Output**: `docs/harper/SPEC.md` (concise, testable, with mandatory Acceptance Criteria).
* **Git**: commit on `harper/spec/<runId>`; optional PR.
* **Telemetry**: prompt size, ctx window, model, tokens, duration.

### `/plan` → `PLAN.md` + `plan.json`

* **Input**: `SPEC.md` (+ same knowledge pipeline as `/spec`).
* **Output**:

  * `docs/harper/PLAN.md` – narrative plan with **REQ-IDs** (stable identifiers).
  * `docs/harper/plan.json` – canonical machine-readable plan:

    ```json
    {
      "req": [
        { "id": "REQ-001", "title": "...", "acceptance": [...], "dependsOn": [], "status": "open" }
      ]
    }
    ```
* **Git**: commit on `harper/plan/<runId>`; optional PR.
* **Telemetry**: tasks count, coverage of SPEC AC, dependency graph density.

### `/kit` → code+tests+docs (iterative)

* **Goal**: implement **one or more REQ-IDs** (default: the next **open** REQ respecting dependencies).
* **CLI**:

  * `/kit` → next open REQ
  * `/kit <REQ-ID>` → target a specific REQ
* **Output**:

  * **Source changes** (minimal scope).
  * **Tests** for the targeted REQ(s).
  * `docs/harper/KIT.md` – append a **new iteration block**:

    * Targeted REQ(s) with rationale and deltas.
    * What’s in/out of scope.
    * How to run tests & prerequisites (cloud/on-prem).
    * **Product Owner Notes** (user comments & requested scope changes).
  * **README** (module-level or root):

    * prerequisites (tooling, proxies, secrets layout),
    * commands to run tests,
    * dependencies and how to mock them,
    * expected `/eval` checks.
  * `runs/<runId>/kit.report.json` – index of files, tests, REQ mapping.
* **Git**: commit on `harper/kit/<runId>`; optional PR.
* **Telemetry**: files added/changed, test count, prompt ctx size actually used.

> **Rescoping**: `KIT.md` contains **Product Owner Notes**; with `/kit --rescope` the system updates `plan.json` (adds/removes REQ, updates acceptance). A subsequent `/plan` can regenerate `PLAN.md` from the updated `plan.json` if desired.

### `/eval` → `eval.summary.json`

* **Goal**: execute **the suite** consistent with the stack and profile:

  * **Tests** (pytest, jest, mvn surefire, etc.)
  * **Lint** (ruff, eslint)
  * **Type check** (mypy, pyright, tsc)
  * **Format check** (black, prettier — check mode)
  * **Build/package** validation (maven/gradle/npm/docker)
  * **Security/SCA** *(optional by profile)* (bandit, trivy, snyk)
* **Scoping**:

  * Default: only the **REQ-IDs targeted** in the last `/kit` batch.
  * `--all`: run full suite mapped to all REQ (open+done) for regression.
* **Output**: `runs/<runId>/eval.summary.json`, **indexed by REQ-ID**, with pass/fail + logs/paths.
* **Telemetry**: duration per tool, pass/fail counts, flakiness signals.

### `/gate` → promotion decisions

* **Goal**: mark **REQ-IDs as done** when their checks are green.
* **Default policy**: all REQ in the **last batch** must be green → mark them `done` in `plan.json` and tick them in `PLAN.md`.
* **Smart advance**: when a batch is promoted, the **next open REQ** becomes the default target for the next `/kit`.
* **Options**:

  * `--all`: consider all open REQ that are currently green and promote them.
  * `--manual <REQ-ID> pass|fail`: (rare) override a specific REQ.
* **Output**: `runs/<runId>/gate.decisions.json`, and updated `plan.json` / `PLAN.md`.
* **Git**: commit on `harper/gate/<runId>`; merge still blocked unless policy says otherwise.

### `/finalize` → notes + tag + PR/merge

* **Prereq**: all mandatory REQ marked **done** (or agreed scope).
* **Output**:

  * `docs/harper/RELEASE_NOTES.md` (summarize by REQ, highlights, links to diffs).
  * Git **tag** (e.g., `harper/v0.1-spec`, `harper/v0.2-plan`, `harper/v0.3-finalize`).
  * **PR/merge** according to governance toggles.
* **Git**: commit/tag + PR/merge if enabled.

---

## Git Governance

* **Branch naming**: `harper/<phase>/<runId>`
* **Commit messages**: `harper(<phase>): <title> [runId=…] [model=…] [profile=…]`
* **Gates**:

  * If `/eval` fails, `/gate` denies promotion → **no merge**.
  * Optional **PR** after `/plan` and `/kit` with CI checks.
* **Config toggles**:

  * `git.autoCommit=true|false`
  * `git.createPR=true|false`
  * `git.mergeOnGate=true|false` (default false)

---

## Telemetry (per phase)

* Provider, model, **context window**, **prompt tokens~**, **max completion cap**, temperature/top-p.
* `prep_payload_ms`, `llm_call_ms`, `postprocess_ms`, `git_ms`, `total_ms`.
* Files written/changed, #tests generated, #tests run, pass/fail.
* Gate decisions count.
* Prompt system hash (for audit/repro).

Saved at: `runs/<runId>/telemetry.json`.

---

## Commands & Flags (summary)

* `/spec`
* `/plan`
* `/kit [<REQ-ID>]`
* `/eval [--all]`
* `/gate [--all] [--manual <REQ-ID> pass|fail]`
* `/finalize`

---

## Cloud & On-Prem Profiles

All commands must honor **profile constraints** (cloud, on-prem, enterprise):

* network egress (proxies, gateways),
* secrets management (Vault, KMS),
* build runners (Docker-in-Docker vs privileged pods),
* security checks required by policy,
* CI orchestration (Jenkins/GitHub Actions).

Prerequisites and execution paths must be explicitly documented in the **KIT iteration README**.

---

## KIT Iteration — README Template (suggested)

```
# KIT Iteration — <runId> — <REQ-ID(s)>

## Scope
- In scope:
- Out of scope:

## Prerequisites
- Tooling: <python/node/java versions>, docker, make, …
- On-prem specifics: proxy/gateway, allowed endpoints
- Secrets: how to provide them (mock/fake for tests)

## How to Run
- Unit tests: …
- Lint: …
- Type check: …
- Build: …
- (Optional) Security/SCA: …

## What to Expect
- Passing criteria for this iteration
- Known limitations or follow-ups

## Dependencies / Mocks
- External services and how they are mocked

## Product Owner Notes (from KIT.md)
- <copied summary of the notes affecting scope>
```

---

## Rescoping

* Add comments in `docs/harper/KIT.md` under **Product Owner Notes**.
* Run `/kit --rescope` to update `plan.json` (and regenerate `PLAN.md` on next `/plan` if desired).
* Subsequent `/kit` iterations will use the refreshed set of **open REQ-ID**.
