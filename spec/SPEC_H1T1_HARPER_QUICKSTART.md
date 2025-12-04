# SPEC — H1-T1 Harper Quickstart (Multi-agent / LangGraph)

## Context

CLike already supports the Harper pipeline (SPEC → PLAN → KIT → EVAL → GATE → FINALIZE) via explicit commands and docs. However, starting a new run from IDEA or SPEC still requires multiple manual calls and setup steps.

Harper Quickstart should provide a single entrypoint that, starting from `IDEA.md` or `SPEC.md`, prepares the full Harper flow and optionally runs the first execution slice, without polluting the chat UI and while keeping the process observable and reversible.

## Problem Statement

Developers need too many manual steps to go from an initial IDEA/SPEC to a structured Harper run (SPEC, PLAN, lanes, LTC/HOWTO, first KIT/EVAL/GATE). This slows down the first iteration and makes demos and onboarding harder.

## Goal

Provide a single “Harper Quickstart” entrypoint that:

- Starts from `IDEA.md` or `SPEC.md` (or auto-detects the best starting point).
- Builds a Harper Flow Graph (LangGraph-based) that encodes IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE.
- Generates or normalizes SPEC, PLAN, plan.json, lane-guides, and LTC/HOWTO skeletons.
- Optionally runs a first KIT/EVAL/GATE slice in a controlled way.
- Keeps the VS Code chat clean (1 recap message) and exposes details via panels + telemetry.

## Out of Scope

- Full automatic FINALIZE without explicit human confirmation.
- Advanced error recovery strategies beyond basic fail-fast + logging.
- Multi-repo orchestration (Quickstart acts on the current project only).

## Requirements

### REQ-H1T1-001 — Harper Quickstart API & Command

**Goal**  
Expose a single “Harper Quickstart” entrypoint that can start from `IDEA.md` or `SPEC.md` and create a Harper flow run.

**Acceptance criteria**

- A backend endpoint (e.g. `POST /v1/harper/quickstart`) accepts:
  - `startFrom` = `"idea"` | `"spec"` | `"auto"`,
  - `mode` = `"plan-only"` | `"first-kit"` | `"e2e-manual"`,
  - `profile` (cloud/on-prem, model profile, etc.).
- A VS Code command “CLike: Harper Quickstart” calls this endpoint with sensible defaults.
- If only `IDEA.md` exists, `startFrom="auto"` resolves to `"idea"`.
- If `SPEC.md` already exists, `startFrom="auto"` resolves to `"spec"`.
- On success, the API returns:
  - a `runId`,
  - list of Harper phases executed,
  - paths of generated/updated artifacts.

---

### REQ-H1T1-002 — Harper Flow Graph Definition (LangGraph)

**Goal**  
Encode the Harper pipeline (`IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE`) as a reusable, stateful graph.

**Acceptance criteria**

- A “Harper Flow Graph” is defined with nodes representing:
  - `IdeaNode` (optional / no-op if starting from SPEC),
  - `SpecNode`,
  - `PlanNode`,
  - `LaneGuidesNode`,
  - `LtcHowtoNode`,
  - `KitNode`,
  - `EvalNode`,
  - `GateNode`,
  - `FinalizeNode`.
- Graph configuration is stored under `runs/<runId>/harper.flow.json`:
  - includes executed nodes, pending nodes, and any failure reason.
- The graph can be invoked with a “cut point”:
  - `mode="plan-only"` executes up to `LaneGuidesNode` and `LtcHowtoNode`,
  - `mode="first-kit"` continues with one `KitNode` + `EvalNode` + `GateNode` for the first REQ,
  - `mode="e2e-manual"` configures all nodes but does not auto-run destructive steps without a confirmation hook.

---

### REQ-H1T1-003 — SPEC Generation / Normalization Agent

**Goal**  
Create or normalize `docs/harper/SPEC.md` starting from `IDEA.md` and existing repository context, aligned with the official Harper process docs.

**Acceptance criteria**

- When starting from IDEA:
  - A `SPEC.md` file is generated under `docs/harper/`.
  - The SPEC includes:
    - problem statement, target users, values & outcomes,
    - feature-level requirements with REQ-IDs,
    - explicit “out-of-scope” section.
- When starting from an existing SPEC:
  - The flow validates basic structure (sections, REQ-IDs),
  - Optionally normalizes headings and structure without breaking custom content.
- SPEC generation/normalization is logged in `harper.quickstart.report.json`.

---

### REQ-H1T1-004 — PLAN & plan.json Generation

**Goal**  
Generate/refresh `PLAN.md` and `plan.json` from `SPEC.md`, respecting the conventions defined in PROCESS_IO.

**Acceptance criteria**

- `docs/harper/PLAN.md` is created or updated, listing:
  - all REQ-IDs,
  - short, testable acceptance criteria,
  - dependencies between REQ-IDs,
  - lane assignment where applicable.
- `docs/harper/plan.json` is created or updated as structural source of truth:
  - for each REQ-ID: id, status, lane, dependsOn, test_profile, gate_policy_ref.
- PLAN changes are idempotent:
  - re-running Quickstart doesn’t duplicate REQ-IDs or scramble the structure.

---

### REQ-H1T1-005 — Lane Guides Generation

**Goal**  
Generate lane-guide documents based on PLAN and `TECH_CONSTRAINTS.yaml`.

**Acceptance criteria**

- For each lane referenced in `plan.json`, a file exists:
  - `docs/harper/lane-guides/<lane>.md`.
- Each lane-guide follows the expected Harper structure:
  - tools for tests/lint/types/security/build,
  - CLI examples, report formats, default gate policy, notes on runners.
- If a lane-guide already exists, Quickstart appends or updates only the LLM-generated sections, preserving manual edits when possible.

---

### REQ-H1T1-006 — LTC & HOWTO Skeletons for REQ-IDs

**Goal**  
Provide minimal LTC and HOWTO scaffolding for REQ-IDs so that later `/eval` and `/gate` can work properly.

**Acceptance criteria**

- For each REQ-ID in `plan.json`, if missing:
  - a skeleton `docs/harper/LTC-<REQ-ID>.yaml` is created,
  - a skeleton `docs/harper/HOWTO-<REQ-ID>.md` is created.
- Skeletons include:
  - placeholder commands,
  - placeholder report paths,
  - TODO sections for human refinement.
- Re-running Quickstart does not overwrite existing LTC/HOWTO files that have been manually edited (or at least warns/logs).

---

### REQ-H1T1-007 — DX & Telemetry for Quickstart

**Goal**  
Provide clear UX and observability for Quickstart runs.

**Acceptance criteria**

- VS Code:
  - “CLike: Harper Quickstart” command is visible in the palette and optional Harper panel.
  - After a successful run, a single, concise message appears in chat with:
    - runId,
    - phases executed,
    - key artifacts with clickable links.
- Telemetry:
  - `runs/<runId>/harper.quickstart.report.json` contains:
    - input options (startFrom, mode, profile),
    - phases executed and their status,
    - models used and token usage (if available),
    - errors and warnings.
- Failure paths:
  - if a phase fails (e.g. SPEC generation), the error is recorded and surfaced to the user without corrupting existing artifacts.
