# HOWTO — Build CoffeeBuddy with CLike BMAD Governance

> Recommended path for the new CLike BMAD-aware methodology profile.
>
> CoffeeBuddy is an on-prem Slack workflow for office coffee runs. The target slice coordinates order capture, fair runner assignment, reminders, run summary, preference memory, and audit/operations evidence without public-cloud dependency.

---

## 1. Operating model

This HOWTO uses CLike as the governing Harper runtime and BMAD as a CLike-owned methodology profile.

The canonical lifecycle remains:

```text
IDEA -> SPEC -> PLAN -> KIT -> EVAL -> GATE -> FINALIZE
```

CLike owns:

- canonical Harper artifacts;
- methodology resolution;
- cloud prompt governance;
- local-agent package generation;
- candidate isolation;
- eval;
- gate;
- telemetry;
- audit;
- promotion.

BMAD adds:

- stronger agent role discipline;
- mandatory companion artifacts;
- richer handoff context;
- PRD, epic, story, architecture, UX, implementation-readiness, QA advisory, and documentation review material.

BMAD does **not** add:

- a runtime dependency;
- `npx bmad-method` runtime invocation;
- direct source/test writes;
- eval/gate authority;
- promotion authority;
- MCP write tools;
- a parallel Harper pipeline.

---

## 2. CoffeeBuddy target scope

Use this CoffeeBuddy intent as the source of truth while reviewing generated artifacts.

### Product intent

CoffeeBuddy reduces office coffee-run coordination from scattered Slack threads to a controlled on-prem Slack workflow. Users should be able to submit an order, see the run summary, and know who is assigned as runner in under 2 minutes.

### Slice-1 outcomes

- Coordination time from `/coffee` to order summary is less than or equal to 2 minutes.
- Missed or ambiguous orders are less than or equal to 5% of submitted orders in pilot runs.
- No eligible teammate is assigned more than 2 consecutive runs.
- 100% of active runs show runner, order list, and current status.
- At least 60% of invited pilot users complete one order in week 1.

### Primary functional anchors

- Slack command starts or joins an active coffee run.
- Order capture stores drink, optional notes, Slack user ID, and timestamp.
- Fair runner assignment excludes unavailable or opted-out users.
- Reminder workflow notifies pending participants and the assigned runner.
- Run summary publishes status, orders, runner, and current state.
- Preference memory suggests prior drink preferences.
- Audit and operations endpoints support IT/security stakeholders.

### Technology baseline

CoffeeBuddy slice-1 should stay aligned with:

```text
FastAPI
Python 3.12
PostgreSQL
Apache Kafka
OIDC via Ory Hydra and Ory Kratos
Kong Gateway / NGINX ingress
HashiCorp Vault
Prometheus / Grafana
Jenkins
on-prem Kubernetes
restricted internet egress
```

AI/RAG behavior is disabled for slice-1 unless a later approved requirement adds it.

---

## 3. Prerequisites

Before starting, verify:

```bash
git status
```

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8000/health
```

Recommended local service checks:

```bash
curl -s http://localhost:8080/v1/harper/health
curl -s http://localhost:8000/v1/models/validate
```

If you want local-agent KIT/EVAL support, verify at least one executor:

```bash
codex --version
```

or:

```bash
claude --version
```

If those commands are unavailable, use Cloud Only for implementation until the local agent path is configured.

---

## 4. Initialize the project

Create or open the CoffeeBuddy workspace in VS Code, then run:

```text
/init CoffeeBuddy
```

Optional explicit folder:

```text
/init CoffeeBuddy ./coffeebuddy_bmad
```

Developer checkpoint:

- Confirm the workspace is the intended CoffeeBuddy repository.
- Confirm `.clike/project.json` exists when project metadata is expected.
- Confirm Git is clean before generating Harper artifacts.

---

## 5. Seed the IDEA input

Use the strongest CoffeeBuddy source material available.

Recommended input file:

```text
docs/input/coffee_buddy_idea_seed.md
```

The seed should include:

- product vision;
- problem statement;
- target users;
- measurable outcomes;
- slice-1 scope and non-goals;
- SPEC-ready technology constraints;
- deployment portability rule;
- security, privacy, observability, and data lifecycle anchors;
- `/spec` handoff readiness acceptance hooks.

Developer checkpoint:

- Do not start BMAD IDEA from a vague paragraph if a richer CoffeeBuddy brief exists.
- Prefer the high-fidelity CoffeeBuddy IDEA as the initial source because it already contains measurable outcomes and downstream acceptance hooks.

---

## 6. Run BMAD IDEA — analyst

Recommended execution mode:

```text
Cloud Only
```

Command:

```text
/idea --methodology bmad --agent analyst
```

Expected canonical artifact:

```text
docs/harper/IDEA.md
```

Expected BMAD companion artifacts:

```text
docs/harper/bmad/idea/BRIEF.md
docs/harper/bmad/idea/PRFAQ_NOTES.md
docs/harper/bmad/idea/ASSUMPTIONS.md
docs/harper/bmad/idea/RESEARCH_QUESTIONS.md
```

Open-ended BMAD artifacts are also valid when useful, for example:

```text
docs/harper/bmad/idea/DEEP_DIVE_SLACK_WORKFLOW.md
docs/harper/bmad/idea/ON_PREM_RISK_NOTES.md
```

Review checklist:

- `IDEA.md` preserves CoffeeBuddy as an on-prem Slack workflow.
- Outcomes are measurable.
- Slice-1 is explicit.
- Payments, POS/vendor integrations, mobile app, web portal, and AI/RAG are out of scope.
- Technology constraints preserve FastAPI, Python 3.12, PostgreSQL, Kafka, OIDC/Ory, Kong/NGINX, Vault, Prometheus/Grafana, Jenkins, and on-prem Kubernetes.
- BMAD companion docs improve the downstream `/spec` prompt instead of duplicating `IDEA.md`.

Verification:

```bash
ls -la docs/harper docs/harper/bmad/idea
```

```bash
rg -n "BMAD Companion Artifact Contract|BMAD Companion Artifact Inventory|BRIEF.md|PRFAQ_NOTES.md|ASSUMPTIONS.md|RESEARCH_QUESTIONS.md" telemetry gateway/runs runs .clike 2>/dev/null
```

---

## 7. Optional RAG indexing after IDEA

If the CoffeeBuddy workspace contains long docs, architecture notes, Slack API notes, or enterprise runbooks, index them instead of dumping them into prompts.

```text
/ragIndex docs/**
```

Recommended targets:

```text
/ragIndex docs/harper/**
/ragIndex docs/input/**
/ragIndex .clike/**
```

Use RAG for large context. Use inline/core context for small deterministic files.

---

## 8. Run BMAD SPEC — PM owns canonical SPEC

Recommended execution mode:

```text
Cloud Only
```

Command:

```text
/spec --methodology bmad --agent pm
```

Expected canonical artifact:

```text
docs/harper/SPEC.md
```

Expected BMAD PM companion artifacts:

```text
docs/harper/bmad/spec/PRD.md
docs/harper/bmad/spec/EPICS.md
docs/harper/bmad/spec/ACCEPTANCE_MODEL.md
docs/harper/bmad/spec/SCOPE_DECISIONS.md
```

Review checklist:

- `SPEC.md` is testable, not just descriptive.
- Functional requirements map to CoffeeBuddy flows.
- Acceptance criteria use observable evidence.
- Security/privacy covers Slack IDs, display names, preferences, tokens, Vault, restricted egress, RBAC, and audit logging.
- Observability covers structured logs, correlation IDs, Prometheus metrics, Grafana dashboard, and incident diagnostics.
- Data lifecycle covers preference deletion, retention, masking, logs, and transactional data.
- Non-goals remain strict.
- Companion artifacts clarify PRD, epics, acceptance model, and scope decisions.

Verification:

```bash
ls -la docs/harper/bmad/spec
```

```bash
rg -n "PRD.md|EPICS.md|ACCEPTANCE_MODEL.md|SCOPE_DECISIONS.md|BMAD Companion Artifact Inventory" telemetry gateway/runs runs .clike 2>/dev/null
```

---

## 9. Run BMAD SPEC — UX companion-only

Recommended execution mode:

```text
Cloud Only
```

Command:

```text
/spec --methodology bmad --agent ux
```

Expected canonical artifact:

```text
none
```

Expected UX companion artifacts:

```text
docs/harper/ux/DESIGN.md
docs/harper/ux/EXPERIENCE.md
docs/harper/ux/USER_JOURNEYS.md
docs/harper/ux/INTERACTION_STATES.md
docs/harper/ux/SPEC_UX_APPENDIX.md
```

Hard rule:

```text
/spec --methodology bmad --agent ux must not overwrite docs/harper/SPEC.md
```

Review checklist:

- UX docs focus on Slack modal/message flows, interaction states, error states, concise copy, accessibility, and adoption risks.
- UX docs do not claim canonical requirement authority.
- `SPEC_UX_APPENDIX.md` is useful for `/plan` and references concrete CoffeeBuddy flows.

Verification:

```bash
ls -la docs/harper/ux
```

```bash
git diff -- docs/harper/SPEC.md docs/harper/ux
```

Confirm any `SPEC.md` diff came from the PM SPEC run, not the UX run.

---

## 10. Run BMAD PLAN — architect

Recommended execution mode:

```text
Cloud Only
```

Command:

```text
/plan --methodology bmad --agent architect
```

Expected canonical artifacts:

```text
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/lane-guides/*.md
```

Expected BMAD architecture companion artifacts:

```text
docs/harper/bmad/architecture/ARCHITECTURE.md
docs/harper/bmad/architecture/DECISIONS.md
docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md
docs/harper/bmad/architecture/RISKS.md
```

Review checklist:

- REQs are small enough for `/kit`.
- Dependencies are explicit.
- `plan.json` is valid JSON.
- Each REQ includes `runtime_profile`, `integration_contracts`, `data_contracts`, `gate_expectations`, and `main_module_boundary`.
- Lane-guides contain expected files, commands, test strategy, forbidden shortcuts, and gate expectations.
- TECH_CONSTRAINTS remain authoritative.

Suggested CoffeeBuddy REQ slicing to validate against:

```text
REQ-001 — Slack command and active run lifecycle
REQ-002 — Order capture and preference memory
REQ-003 — Fair runner assignment
REQ-004 — Reminder and status update workflow
REQ-005 — Audit records and operator health endpoints
REQ-006 — Security, secrets, config, and on-prem deployment readiness
REQ-007 — Slack contract fixtures and app manifest validation, if needed
```

Do not force this exact split if the generated PLAN has a better dependency-aware decomposition, but use it as a review baseline.

Verification:

```bash
python -m json.tool docs/harper/plan.json >/tmp/coffeebuddy_plan_check.json
```

```bash
ls -la docs/harper/lane-guides docs/harper/bmad/architecture
```

```bash
rg -n "runtime_profile|integration_contracts|data_contracts|gate_expectations|main_module_boundary|kit_readiness" docs/harper/PLAN.md docs/harper/plan.json docs/harper/lane-guides
```

---

## 11. Optional BMAD PLAN — PM story/readiness refinement

Use this only if you want a PM-led refinement pass over stories and implementation readiness.

Command:

```text
/plan --methodology bmad --agent pm
```

Expected canonical artifacts:

```text
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/lane-guides/*.md
```

Expected BMAD plan companion artifacts:

```text
docs/harper/bmad/plan/STORIES.md
docs/harper/bmad/plan/STORY_MAP.md
docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md
```

Developer checkpoint:

- This run may update canonical PLAN artifacts.
- Review the diff carefully.
- Keep the architect-produced architecture boundaries if they are still valid.
- Do not accept a PM plan refinement that weakens `plan.json` machine-readability or KIT readiness.

Verification:

```bash
git diff -- docs/harper/PLAN.md docs/harper/plan.json docs/harper/lane-guides docs/harper/bmad/plan
```

---

## 12. Prepare local-agent execution for KIT

For implementation, prefer the local-agent path when Codex or Claude Code is installed and configured.

In CLike Chat, set Execution to one of:

```text
Prefer Agent
Agent Only
```

If your build supports chat-side executor selection, use:

```text
/agent-default codex
```

or:

```text
/agent-default claude
```

or:

```text
/agent-default auto
```

If chat-side executor selection is not available in your local build, configure the VS Code settings instead:

```jsonc
{
  "clike.localAgent.enabled": true,
  "clike.localAgent.preferredExecutor": "gpt_codex",
  "clike.localAgent.allowEval": true
}
```

---

## 13. Run BMAD KIT — developer

Start with the first open dependency-ready REQ.

Command:

```text
/kit REQ-001 --methodology bmad --agent developer
```

Expected candidate roots:

```text
runs/kit/REQ-001/src/**
runs/kit/REQ-001/test/**
runs/kit/REQ-001/ci/**
runs/kit/REQ-001/docs/**
```

Expected BMAD developer companion docs:

```text
runs/kit/REQ-001/docs/BMAD_DEV_STORY.md
runs/kit/REQ-001/docs/IMPLEMENTATION_NOTES.md
runs/kit/REQ-001/docs/SELF_REVIEW.md
runs/kit/REQ-001/docs/RUNBOOK.md
```

Expected local-agent package files when using local agents:

```text
runs/kit/REQ-001/docs/AGENT_EXECUTION_CONTEXT.json
runs/kit/REQ-001/docs/AGENT_PROMPT.md
```

Hard rules:

- Do not write directly to canonical `src/`, `test/`, or `tests/` during KIT.
- Do not modify `docs/harper/PLAN.md` or `docs/harper/plan.json` from local-agent KIT.
- Do not run Git commands from local agents.
- Do not promote from KIT.

Verification:

```bash
find runs/kit/REQ-001 -maxdepth 3 -type f | sort
```

```bash
rg -n "methodology_context|companion_documents|BMAD_DEV_STORY.md|IMPLEMENTATION_NOTES.md|SELF_REVIEW.md|RUNBOOK.md|allowed_write_roots|forbidden_paths" runs/kit/REQ-001/docs
```

---

## 14. Run BMAD EVAL — QA advisory only

Command:

```text
/eval REQ-001 --methodology bmad --agent qa
```

Canonical eval remains CLike-owned.

Expected BMAD QA advisory docs:

```text
runs/kit/REQ-001/docs/BMAD_QA_ADVISORY.md
runs/kit/REQ-001/docs/FIX_GUIDANCE.md
runs/kit/REQ-001/docs/MISSING_TESTS.md
runs/kit/REQ-001/docs/RISK_REVIEW.md
```

Expected local-agent eval files when local eval pre-pass is used:

```text
runs/kit/REQ-001/docs/AGENT_EVAL_CONTEXT.json
runs/kit/REQ-001/docs/AGENT_EVAL_PROMPT.md
```

Review checklist:

- Eval verdict fields remain canonical CLike fields.
- BMAD QA docs give repair guidance only.
- Missing tests and risk review are actionable.
- No BMAD file claims pass/fail authority.

Verification:

```bash
rg -n "BMAD_QA_ADVISORY.md|FIX_GUIDANCE.md|MISSING_TESTS.md|RISK_REVIEW.md|canonical EvalRunner|advisory" runs/kit/REQ-001/docs runs 2>/dev/null
```

---

## 15. Run CLike GATE — no BMAD authority

Correct command:

```text
/gate REQ-001
```

Optional manual gate when evidence has been manually verified:

```text
/gate REQ-001 manual pass
```

Rejected command for safety verification:

```text
/gate REQ-001 --methodology bmad --agent qa
```

Expected behavior:

- The BMAD gate command is rejected.
- Gate remains CLike-owned.
- Promotion only happens through CLike gate/promotion policy.

Verification:

```bash
rg -n "REQ-001|promoted|blocked|eligible|gate" runs docs/harper/plan.json 2>/dev/null
```

---

## 16. Repeat the REQ loop

For each remaining REQ:

```text
/kit REQ-002 --methodology bmad --agent developer
/eval REQ-002 --methodology bmad --agent qa
/gate REQ-002
```

Then:

```text
/kit REQ-003 --methodology bmad --agent developer
/eval REQ-003 --methodology bmad --agent qa
/gate REQ-003
```

Continue until `plan.json` has no open dependency-ready REQs remaining.

---

## 17. Run BMAD FINALIZE — tech writer

Recommended command:

```text
/finalize --methodology bmad --agent tech-writer
```

Expected canonical finalize artifacts may include:

```text
docs/harper/RELEASE_NOTES.md
docs/harper/PR_BODY.md
docs/harper/SANITY_CHECKS.md
docs/harper/TODO_NEXT.md
```

Expected BMAD finalize companion artifacts:

```text
docs/harper/bmad/finalize/DOC_REVIEW.md
docs/harper/bmad/finalize/RELEASE_NARRATIVE.md
docs/harper/bmad/finalize/STAKEHOLDER_SUMMARY.md
```

Review checklist:

- Release narrative references implemented REQs and evidence.
- Stakeholder summary is understandable by product, IT/security, office management, and delivery leads.
- Remaining risks are explicit.
- No finalize artifact claims unverified production readiness.

---

## 18. BMAD companion closed-loop verification

After each BMAD phase, verify that generated companion artifacts are visible to later phases.

Prompt debug grep:

```bash
rg -n "Governed Methodology Profile|BMAD Companion Artifact Contract|BMAD Companion Artifact Inventory|docs/harper/bmad|docs/harper/ux|runs/kit/REQ-001/docs|DEEP_DIVE|PRD.md|ARCHITECTURE.md|IMPLEMENTATION_READINESS.md" telemetry gateway/runs runs .clike 2>/dev/null
```

Local-agent context grep:

```bash
rg -n "methodology_context|discovered_companion_artifacts|companion_documents|docs/harper/bmad|docs/harper/ux|runs/kit/REQ-001/docs" runs/kit/REQ-001/docs/AGENT_EXECUTION_CONTEXT.json runs/kit/REQ-001/docs/AGENT_EVAL_CONTEXT.json 2>/dev/null
```

Expected result:

- Mandatory companion artifacts appear.
- Freely generated BMAD artifacts appear when created.
- UX artifacts appear in PLAN/KIT context.
- REQ-level BMAD docs appear in EVAL/repair context.

---

## 19. Quality scorecard for CoffeeBuddy

Do not claim BMAD improved CoffeeBuddy only because more files exist.

Compare native vs BMAD outputs using these dimensions:

### SPEC quality

- Completeness
- Testability
- Acceptance criteria precision
- Functional requirement clarity
- UX/user journey quality
- Non-functional requirements
- Security/privacy/compliance coverage
- Observability/operations coverage
- Scope and non-goals quality
- Traceability to IDEA and BMAD companion artifacts

### PLAN quality

- REQ granularity
- Implementation readiness
- Dependency modeling
- Architecture boundary clarity
- Risk/mitigation clarity
- Runtime/lane consistency
- TECH_CONSTRAINTS adherence
- Test strategy quality
- Eval/gate readiness

### plan.json quality

- Machine-readability
- Acceptance structure
- Dependency structure
- `functional_scope`
- `technical_scope`
- `non_functional_requirements`
- `security_requirements`
- `operational_requirements`
- `integration_contracts`
- `data_contracts`
- `test_strategy`
- `risk_notes`
- `main_module_boundary`
- `kit_readiness`

### lane-guide quality

- Lane-specific implementation guidance
- Runtime constraints
- Expected files
- Test commands
- Contract boundaries
- Integration points
- Forbidden shortcuts
- Eval/gate expectations

---

## 20. Runtime safety checks

Runtime forbidden invocation grep:

```bash
rg -n "npx\s+bmad-method|bmad-method install|subprocess\.(run|Popen).*bmad|os\.system\(.*bmad|child_process\.(exec|spawn).*bmad" orchestrator gateway extensions --glob '!**/tests/**'
```

Expected result:

```text
no output
```

Documentation policy grep:

```bash
rg -n "BMAD runtime execution|npx bmad-method runtime invocation|BMAD importer|TEA|Party Mode|MCP write tools|automatic latest BMAD tracking" README.md docs/integrations/bmad
```

Expected result:

- Matches may appear only as forbidden, not implemented, or out-of-scope documentation.

---

## 21. Telemetry review

Open the Harper telemetry UI:

```text
http://localhost:8000/v1/metrics/harper/ui
```

Review:

- phase sequence;
- model/provider used;
- token usage;
- duration;
- generated files;
- eval outcomes;
- gate decisions;
- cloud vs local-agent execution behavior.

Use telemetry to detect prompt bloat, missing companion ingestion, repeated eval failures, and model quality regressions.

---

## 22. Recommended full command sequence

```text
/init CoffeeBuddy
/idea --methodology bmad --agent analyst
/spec --methodology bmad --agent pm
/spec --methodology bmad --agent ux
/plan --methodology bmad --agent architect
/plan --methodology bmad --agent pm
/kit REQ-001 --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/gate REQ-001
/kit REQ-002 --methodology bmad --agent developer
/eval REQ-002 --methodology bmad --agent qa
/gate REQ-002
/finalize --methodology bmad --agent tech-writer
```

If you want the safer first pass, skip the PM PLAN refinement and run only:

```text
/plan --methodology bmad --agent architect
```

Then add the PM PLAN refinement only if stories or implementation readiness are still weak.

---

## 23. Do not do this

Do not run:

```text
/gate REQ-001 --methodology bmad --agent qa
```

Do not call:

```bash
npx bmad-method
```

Do not let local agents write to:

```text
src/**
test/**
tests/**
docs/harper/PLAN.md
docs/harper/plan.json
```

Do not accept BMAD companion docs as canonical authority when they conflict with:

```text
docs/harper/IDEA.md
docs/harper/SPEC.md
docs/harper/PLAN.md
docs/harper/plan.json
EvalRunner output
Gate decisions
```

---

## 24. Final developer checkpoint

CoffeeBuddy is ready to claim BMAD value only when evidence shows:

- `SPEC.md` is more complete and testable than native output.
- `PLAN.md` and `plan.json` are more implementation-ready.
- Lane-guides provide executable guidance.
- KIT local-agent context includes BMAD and UX companion docs.
- EVAL repair guidance improves candidate quality without mutating canonical verdicts.
- GATE remains CLike-owned.
- Telemetry and prompt_debug prove that companion artifacts were actually consumed downstream.

The goal is not more files.

The goal is better governed software delivery.
