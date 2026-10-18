# Harper Playbook — ${project.name}


---

## Overview
Harper turns a high-level IDEA into a working solution via short, testable steps: IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE, then `/idea --extend` for each next release.

## How to author IDEA.md
- Problem Statement (users, pains, opportunity)
- Outcomes & KPIs (what changes, how measured)
- Constraints (budget, timeline, compliance)
- Strategic Fit (stakeholders, policies)
- Non-Goals (what is out of scope)

## How to author SPEC.md
- Goals & Non-Goals
- Functional Requirements (user stories/capabilities)
- Non-Functional (security, performance, scalability)
- Data & Integrations (APIs, ownership)
- Acceptance Criteria & KPIs
- Risks & Mitigations
- **Gate G0 Checklist** (Definition of Ready)

## Commands
- `/idea` → Produce/update IDEA from the inputs in `docs/inputs/` (and attachments).
- `/spec` → Use IDEA as source-of-truth, produce/update SPEC.
- `/plan` → Use SPEC to produce/update PLAN (WBS, milestones, acceptance).
- `/kit`  → Implement in short loops with tests.
- `/eval REQ-xxx [--fix]`, `/gate REQ-xxx [--fix]` → Verify each REQ; a passing gate promotes it.
- `/finalize` → Final release packaging, howto, solution verified running, developer report.
- `/idea --extend` → Next release: inputs in `docs/inputs/vN/`, new REQs appended to the plan.

## Gates
- **G0 (SPEC)**: requirements coherent, constraints explicit, acceptance clear.
- **G1 (PLAN)**: tasks/owners/dependencies clear, testability defined.
- **G2/EDD (KIT)**: tests green, quality thresholds met, risks addressed.

---
## `docs/harper/PLAYBOOK.md`
```markdown
# Harper PLAYBOOK — ${project.name}

This section summarizes the SPEC → PLAN → KIT workflow and the commands to run.

## Phases & Commands

- `/init <project_name> [path] [--force]`  
  Scaffold a new workspace with README, .clike/, and docs/harper/.
- `/where` · `/status` · `/switch <project>`  
  Inspect/switch workspace & model settings.

### Authoring
- `/spec` → Generate SPEC from IDEA & context. Iterate until developer validation.
- `/plan` → Generate PLAN from SPEC. Iterate until developer validation.
- `/kit`  → Generate initial kit/scaffold and then incremental build steps.

### RAG
- `/ragIndex [glob]`  
  Ingest/update the vector store with docs and attachments.
- `/ragSearch <query>`  
  Search docs by vector.

### Evals & Gates
- `/eval <REQ> [--fix]` → Run the REQ's checks in the CLike eval sandbox and show PASS/FAIL; `--fix` repairs failing checks.
- `/gate <REQ> [--fix]` → Enforce the gate for the REQ; on PASS it is promoted into `src/` and `test/`.

## Workflow Expectations

1. **SPEC** must contain all required sections, including **Technology Constraints** and KPIs with a **measurement** statement.  
2. **PLAN** must declare **Traceability Coverage: 100%** and include hooks for Unit/Functional/Integration/Security/UAT tests, plus **Environment Profiles** aligned to constraints.  
3. **KIT** runs lint/type/tests/security based on `.clike/policy.yaml` and `.clike/capabilities.yaml`.  
4. Use Git PRs; CI checks (SPEC/PLAN/KIT Gates) are required before merging.

## Git Conventions (short)
- Branches: `feat/*`, `fix/*`, `chore/*`
- PR template must include Gates status and PLAN checklist updates.
- Tags: `SPEC-APPROVED`, `PLAN-APPROVED`, `vX.Y.Z` (release).

## Before running `/kit`
- SPEC approved, constraints synced.
- PLAN approved with 100% traceability and test hooks.
- Local environment ready (deps, env vars, secrets).
