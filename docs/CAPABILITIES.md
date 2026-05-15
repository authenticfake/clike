# CLike Capabilities, Skills, Packs, and Design Profiles

## Purpose

CLike capabilities are the project-local mechanism used to guide AI-native software delivery without turning the system into a vendor-specific agent or an uncontrolled prompt bundle.

CLike is not just an agent that writes code; it is an AI-native platform that orchestrates verifiable capabilities across specs, plans, code, tests, reviews, and release gates.

Capabilities provide structured, reusable constraints for the Harper pipeline:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

They help CLike stay:

- agent-agnostic
- model-agnostic
- language-agnostic
- domain-agnostic
- runtime-agnostic
- cloud/local/on-prem/edge/hybrid ready
- governed by evidence, not by model confidence

Capabilities do not replace requirements. They refine how requirements are planned, implemented, evaluated, and gated.

---

## Core Concepts

CLike uses three capability types:

```text
Skills          = atomic operational capabilities
Packs           = scenario-level capability bundles
Design Profiles = UI/UX constraints for frontend or operator-facing requirements
```

Each capability type has a different responsibility.

| Type | Purpose | Scope | Used by |
|---|---|---|---|
| Skill | Enforce one operational behavior | Narrow and atomic | PLAN, KIT, EVAL, GATE |
| Pack | Represent a business/technical scenario | Composite | PLAN, KIT, EVAL, GATE |
| Design Profile | Constrain UI/UX output | UI/UX only | PLAN, KIT, EVAL, GATE |

The goal is not to add more prompts. The goal is to make the AI pipeline more reliable, testable, and auditable.

---

## Workspace Structure

Capabilities live inside the application workspace under `.clike/`.

```text
.clike/
  project.json
  capabilities.yaml
  skills/
  packs/
  design-profiles/
```

The VS Code extension template initializes these folders during `/init`.

These files are project-local because every application can have different runtime constraints, domains, UI needs, compliance rules, and engineering standards.

---

## Capability Manifest

CLike reads local capability files and generates a normalized manifest/index:

```text
CLIKE_CAPABILITY_MANIFEST.md
CLIKE_CAPABILITY_INDEX.json
```

These generated artifacts are the primary capability context consumed by cloud models and local agents.

Agents should not randomly inspect `.clike/` and infer behavior from arbitrary files. They should use:

- the capability manifest
- the capability index
- the capabilities explicitly selected by PLAN
- the REQ contract
- SPEC, PLAN, TECH_CONSTRAINTS, and repository evidence

This keeps behavior reproducible and reviewable.

---

## Capability Contract

A capability is valid only if it can participate in the Harper pipeline:

| Phase | Capability responsibility |
|---|---|
| PLAN | Select only relevant packs, skills, and design profiles |
| KIT | Apply selected capabilities while generating code, tests, docs, and CI artifacts |
| EVAL | Produce evidence that selected capabilities were respected |
| GATE | Enforce capability-related promotion rules based on evidence |

A capability must not:

- override SPEC
- override TECH_CONSTRAINTS
- override explicit user instructions
- override repository evidence
- weaken acceptance criteria
- promote code
- replace canonical Gate
- make unsupported production-readiness claims

---

## Skills

Skills are atomic operational capabilities.

A skill should answer one question:

> What behavior must be enforced when this kind of requirement is implemented?

Skills are used when a REQ needs a concrete engineering obligation, such as backend contract stability, RAG evaluation, local/cloud parity, accessibility, or industrial simulation.

### Skill File Format

Each skill is stored as:

```text
.clike/skills/<skill-name>/SKILL.md
```

Each skill should use this structure:

```markdown
# Skill: <Name>

## Intent
## Use when
## Do not use when
## Signals
## Required behavior
## Forbidden behavior
## Evidence required
## Repair guidance
## Gate implications
## Examples
## Non-examples
```

### Current Skills

| Skill | Purpose |
|---|---|
| `local-cloud-parity` | Ensures infrastructure-facing REQs support local and production-like runtime boundaries |
| `eval-contract-writer` | Ensures runnable REQs produce LTC/HOWTO evidence and executable validation commands |
| `gate-risk-reviewer` | Ensures promotion is based on evidence and policy, not model confidence |
| `frontend-state-accessibility` | Ensures UI work includes state handling, accessibility, and user-flow evidence |
| `backend-contract-boundary` | Ensures backend work preserves explicit API, event, adapter, and persistence boundaries |
| `ai-rag-eval-guardrails` | Ensures LLM/RAG/agent behavior is grounded, evaluated, and safely bounded |
| `ml-experiment-reproducibility` | Ensures ML/data science work is reproducible and metric-driven |
| `mobile-offline-parity` | Ensures mobile and PWA work handles offline, reconnect, device, and sync states |
| `mendix-extension-boundary` | Ensures Mendix-related code respects platform boundaries and manual validation requirements |
| `industrial-safety-simulator` | Ensures industrial/edge/PLC/SCADA work is simulator-first and safety-bounded |
| `mvp-e2e-promotability` | Convert requirements into narrow but end-to-end promotable MVP slices instead of shallow demos or decorative code. |
| `backoffice-workflow-ux` | Generate enterprise backoffice workflows with route-based capability pages, scalable lists, task flows, filters, actions, and role-aware UX. |
| `enterprise-solution-architecture` | Keep enterprise solutions coherent across requirements, runtime profiles, integration boundaries, observability, audit, and release readiness. |
| `secure-config-secrets` | nforce safe configuration, secret handling, auth boundaries, restricted egress, and security evidence for promotable software. |


### Example: Backend REQ

A backend API REQ may select:

```text
skills:
  - backend-contract-boundary
  - eval-contract-writer
  - gate-risk-reviewer
```

Expected impact:

- PLAN defines contract boundaries.
- KIT generates API/service/tests/docs.
- EVAL runs contract-relevant checks.
- GATE blocks promotion if contract evidence is missing.

### Example: AI/RAG REQ

An AI/RAG REQ may select:

```text
skills:
  - ai-rag-eval-guardrails
  - backend-contract-boundary
  - eval-contract-writer
  - gate-risk-reviewer
```

Expected impact:

- Model/provider code stays behind adapters where practical.
- Prompt assembly, retrieval, parsing, and eval cases are testable.
- Provider-backed checks can be optional, but deterministic local checks must exist.
- Gate blocks promotion if AI behavior has no eval evidence.

---

## Packs

Packs are scenario-level bundles.

A pack should answer one question:

> What kind of solution are we building, and which constraints should shape every REQ in that scenario?

Packs are not long prompts. They are compact scenario constraints that help PLAN select the right capabilities.

### Pack File Format

Each pack is stored as:

```text
.clike/packs/<pack-name>/PACK.md
```

Each pack should use this structure:

```markdown
# Pack: <Name>

## Intent
## Scenario signals
## Use when
## Do not use when
## Required capabilities
## Runtime assumptions
## Security/compliance assumptions
## Architecture constraints
## Eval expectations
## Gate implications
```

### Current Packs

| Pack | Purpose |
|---|---|
| `enterprise-onprem` | Enterprise, on-prem, hybrid, private-network, and air-gapped scenarios |
| `industrial-manufacturing` | Manufacturing, shop-floor, MES, PLC, SCADA, HMI, and edge scenarios |
| `consumer-saas` | Consumer/product-led SaaS flows |
| `enterprise-solution` | General enterprise-grade applications requiring governance, contracts, auditability, and runtime configurability |
| `startup-solution` | MVP/startup/product-led delivery with lean but verifiable implementation |
| `industrial-solution` | Industrial systems with simulator-first validation and safety boundaries |
| `mendix-solution` | Mendix and low-code platform scenarios with safe extension boundaries |
| `mobile-app` | Mobile, tablet, PWA, field app, and offline/sync scenarios |
| `ai-native-agent-platform` | AI-native platforms, RAG, LLM orchestration, model routing, and agent/tool workflows |

### Pack Selection Rules

PLAN should select packs with restraint.

Recommended rules:

- Prefer one primary pack per REQ.
- Use two packs only when the REQ clearly spans two scenarios.
- Do not attach every pack.
- Do not invent pack names.
- Do not use a pack to weaken acceptance criteria.
- Use scenario evidence from SPEC, IDEA, TECH_CONSTRAINTS, repository structure, or explicit user instruction.

### Example: Industrial Mobile REQ

A field maintenance REQ may select:

```text
packs:
  - industrial-solution
  - mobile-app

skills:
  - industrial-safety-simulator
  - mobile-offline-parity
  - frontend-state-accessibility
  - eval-contract-writer
  - gate-risk-reviewer

design_profiles:
  - mobile-operator-app
```

Expected impact:

- KIT must not assume always-on connectivity.
- Local tests must use simulator/fake equipment.
- UI must show sync/offline/failure states.
- Gate must block unsafe real-equipment behavior.

---

## Design Profiles

Design profiles are UI/UX constraints.

A design profile should answer one question:

> What should the generated UI optimize for?

Design profiles are not brand clones. They do not copy external products or proprietary visual systems. They constrain layout, UX behavior, accessibility expectations, and evidence requirements.

Design profiles apply only to UI/UX-scoped REQs.

### Design Profile File Format

Each design profile is stored as:

```text
.clike/design-profiles/<profile-name>/DESIGN.md
```

Each design profile should use this structure:

```markdown
# Design Profile: <Name>

## Intent
## Use when
## Do not use when
## Visual principles
## UX principles
## Components/patterns
## Accessibility expectations
## Evidence required
## Gate implications
```

### Current Design Profiles

| Design Profile | Purpose |
|---|---|
| `enterprise-console` | Enterprise dashboards, admin panels, back-office tools, and governed internal consoles |
| `industrial-control-room` | Control-room dashboards, operator UIs, alarm/status views, and industrial monitoring |
| `startup-product-app` | SaaS, MVP, product-led, onboarding, and user-facing product flows |
| `mobile-operator-app` | Mobile/tablet/field-operator workflows with offline and constrained-use support |
| `developer-tooling-console` | Developer tools, eval dashboards, Harper pipeline views, logs, traces, and tool/configuration consoles |

### Design Profile Selection Rules

PLAN should select a design profile only when the REQ includes UI/UX work.

Do not select design profiles for:

- backend-only REQs
- infrastructure-only REQs
- data-only REQs
- CLI-only REQs
- documentation-only REQs
- model-only REQs with no UI

### Example: Developer Tooling UI

A Harper eval dashboard REQ may select:

```text
packs:
  - ai-native-agent-platform

skills:
  - frontend-state-accessibility
  - ai-rag-eval-guardrails
  - gate-risk-reviewer

design_profiles:
  - developer-tooling-console
```

Expected impact:

- UI must show evidence, run IDs, REQ IDs, logs, artifacts, and status.
- Model output must not be shown as authoritative without evidence.
- Write actions should be dry-run or approval-gated.
- Gate blocks promotion if UI misrepresents eval/gate state.

---

## How Capabilities Are Used by the Harper Pipeline

### SPEC

SPEC does not normally select capabilities directly.

SPEC defines:

- business intent
- functional requirements
- non-functional requirements
- acceptance criteria
- testing expectations
- constraints

Capabilities may be hinted by SPEC, but they are selected during PLAN.

### PLAN

PLAN is the main capability selection phase.

For each REQ, PLAN should decide:

```jsonc
{
  "id": "REQ-001",
  "lane": "python",
  "domain": "backend",
  "runtime_profile": "local-cloud",
  "packs": ["enterprise-solution"],
  "skills": [
    "backend-contract-boundary",
    "local-cloud-parity",
    "eval-contract-writer",
    "gate-risk-reviewer"
  ],
  "design_profiles": [],
  "main_module_boundary": "src/my_app/api/orders.py",
  "gate_expectations": [
    "unit tests pass",
    "contract tests pass",
    "no hardcoded secrets",
    "local adapter path documented"
  ]
}
```

PLAN should keep capability selection small and justified.

### KIT

KIT applies selected capabilities to generate:

```text
runs/kit/<REQ-ID>/src/
runs/kit/<REQ-ID>/test/
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
```

KIT must respect:

- functional scope
- technical scope
- main module boundary
- selected skills
- selected packs
- selected design profiles
- future compatibility notes
- gate expectations

KIT must not generate decorative architecture. A few strong files are better than many weak files.

### EVAL

EVAL uses capability requirements as evidence expectations.

Examples:

- `eval-contract-writer` expects runnable LTC/HOWTO.
- `ai-rag-eval-guardrails` expects deterministic AI/RAG eval cases.
- `industrial-safety-simulator` expects simulator/fake-device evidence.
- `frontend-state-accessibility` expects UI state/accessibility evidence.
- `backend-contract-boundary` expects API/adapter/contract tests.

EVAL produces evidence. It does not promote.

### GATE

GATE is the deterministic promotion boundary.

Gate must evaluate:

- test results
- lint/type/build/security checks
- policy requirements
- capability evidence
- REQ dependencies
- required artifacts
- promotion safety

Gate must not be overridden by:

- model confidence
- local agent summary
- cloud model summary
- plugin/tool result
- generated prose
- `PASS_WITH_WARNINGS`

Promotion requires a full PASS and satisfied policy.

---

## Agent and Cloud Behavior

CLike supports both cloud-model execution and local agent execution.

Both execution paths should receive equivalent capability context through:

```text
CLIKE_CAPABILITY_MANIFEST.md
CLIKE_CAPABILITY_INDEX.json
AGENT_EXECUTION_CONTEXT.json
AGENT_EVAL_CONTEXT.json
TARGET_CONTRACT.json
FILE_REQUIREMENTS.json
```

The local agent may:

- read promoted source/test code
- read target REQ candidate files
- read previous KIT artifacts for compatibility
- diagnose failing checks
- repair candidate artifacts inside the target REQ folder
- improve LTC/HOWTO when they are not executable

The local agent must not:

- modify promoted `src/`
- modify promoted `test/` or `tests/`
- modify other REQ candidate folders
- perform Git operations
- promote code
- override Gate
- treat model confidence as evidence

---

## Reliability Model

Capabilities improve reliability by converting implicit expectations into explicit evidence.

| Risk | Capability response |
|---|---|
| AI generates demo-code | Skills require tests, HOWTO, and gate evidence |
| UI looks good but does not work | Frontend skill requires states, flows, and accessibility |
| Backend breaks contracts | Backend skill requires explicit schemas, errors, and contract tests |
| RAG hallucinates | AI/RAG skill requires retrieval and eval evidence |
| ML claims are unverifiable | ML skill requires metrics, fixtures, and reproducibility |
| Mobile assumes always-online | Mobile skill requires offline/reconnect/sync behavior |
| Industrial code touches real systems | Industrial skill requires simulator-first validation |
| Mendix artifacts are blindly edited | Mendix skill enforces platform extension boundaries |
| Agent overreaches | Gate skill and policy prevent promotion without evidence |

---

## Capability Authoring Guidelines

When adding a new skill, pack, or design profile:

1. Keep it short and operational.
2. Define when it applies and when it does not.
3. Define evidence that EVAL can verify.
4. Define when GATE should block promotion.
5. Avoid vendor lock-in.
6. Avoid brand cloning.
7. Avoid replacing acceptance criteria.
8. Avoid vague quality claims.
9. Prefer concrete examples and non-examples.
10. Keep it reusable across projects.

A good capability should change generated behavior and evaluation evidence.

A bad capability only adds style preferences, vague architecture opinions, or generic motivational text.

---

## Recommended Capability Mappings

| Scenario | Packs | Skills | Design Profiles |
|---|---|---|---|
| Startup SaaS UI | `startup-solution` | `frontend-state-accessibility`, `eval-contract-writer`, `gate-risk-reviewer` | `startup-product-app` |
| Enterprise backend API | `enterprise-solution` | `backend-contract-boundary`, `local-cloud-parity`, `eval-contract-writer`, `gate-risk-reviewer` | none |
| Enterprise admin console | `enterprise-solution` | `frontend-state-accessibility`, `backend-contract-boundary`, `gate-risk-reviewer` | `enterprise-console` |
| AI/RAG service | `ai-native-agent-platform` | `ai-rag-eval-guardrails`, `backend-contract-boundary`, `eval-contract-writer`, `gate-risk-reviewer` | optional |
| AI developer tooling UI | `ai-native-agent-platform` | `frontend-state-accessibility`, `ai-rag-eval-guardrails`, `gate-risk-reviewer` | `developer-tooling-console` |
| Industrial monitoring | `industrial-solution` | `industrial-safety-simulator`, `backend-contract-boundary`, `eval-contract-writer`, `gate-risk-reviewer` | `industrial-control-room` |
| Industrial mobile field app | `industrial-solution`, `mobile-app` | `industrial-safety-simulator`, `mobile-offline-parity`, `frontend-state-accessibility` | `mobile-operator-app` |
| Mendix extension | `mendix-solution` | `mendix-extension-boundary`, `backend-contract-boundary`, `eval-contract-writer` | optional |
| ML evaluation pipeline | optional domain pack | `ml-experiment-reproducibility`, `eval-contract-writer`, `gate-risk-reviewer` | none |

---

## Current Non-Goals

The capability system is not a plugin marketplace.

It does not yet implement:

- external tool runtime
- marketplace distribution
- automatic third-party skill import
- autonomous promotion
- Evo-like optimization loops
- uncontrolled multi-agent workflows

Those areas should be introduced later through explicit CLike contracts, such as:

```text
CLike Tool Adapter
Evo-like Hardening Loop
```

Both must remain subordinate to canonical CLike Gate.

---

## Summary

CLike capabilities make AI-native software generation more reliable by giving models and agents explicit operational constraints.

They keep the system practical:

- Packs describe the scenario.
- Skills define enforceable engineering obligations.
- Design profiles constrain UI/UX output.
- Manifest/index make capabilities portable.
- EVAL produces evidence.
- GATE decides promotion.

This keeps CLike aligned with its core principle:

```text
The runner produces evidence.
The agent diagnoses and repairs.
Canonical EvalRunner and Gate decide.
```
