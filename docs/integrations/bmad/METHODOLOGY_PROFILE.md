# BMAD Methodology Profile

The BMAD methodology profile is a CLike-owned integration layer that maps Harper phases to BMAD-style roles. The profile is intentionally compact and operational. It is metadata and guidance, not an executor.

BMAD exists inside CLike to improve how phases reason, not to replace the Harper workflow. A role can emphasize discovery, product clarity, architecture, implementation focus, UX quality, QA repair guidance, or documentation polish. CLike still owns the artifacts and the decisions that make work governed and promotable.

## Supported Methodology

- `bmad`

No external BMAD runtime is required. CLike does not install BMAD, execute BMAD CLIs, or invoke the official BMAD package-runner command.

## Reference and Provenance

The BMAD-aware profile is CLike-owned. BMAD Method is treated as a methodology reference, not as a runtime dependency or automatically synchronized upstream source.

The manifest records machine-readable provenance under `provenance` and manual review rules under `reference_review_policy`. CLike does not auto-track BMAD latest at runtime. Maintainers must review a selected BMAD release or commit manually, compare optional fixture workspaces when useful, record the mapping in `docs/integrations/bmad/PROFILE_SYNC_REPORT.md`, update only CLike-owned profile content, and run the required tests before merge.

See `docs/integrations/bmad/PROVENANCE.md` and `docs/integrations/bmad/PROFILE_SYNC_REPORT.md`.

## Artifact-Producing Profiles

The BMAD-aware profiles are no longer only role labels. Each agent and workflow file describes the adopted BMAD concept, the CLike adaptation, expected artifact outputs, handoff consumers, and governance constraints. This keeps the profile operational while preserving CLike ownership.

CLike adopts concepts such as agent taxonomy, workflow sequencing, PRD-to-architecture-to-story handoff, implementation readiness checks, UX positioning, QA risk and fix guidance, customization, and project-context modeling. CLike does not copy official BMAD prompts, does not vendor BMAD runtime content, and does not execute BMAD tooling.

Canonical outputs remain governed by Harper phases. Companion outputs are additive and bounded:

- IDEA analyst notes live under `docs/harper/bmad/idea/**`.
- SPEC PM notes live under `docs/harper/bmad/spec/**`.
- SPEC UX notes live under `docs/harper/ux/**`.
- PLAN architect notes live under `docs/harper/bmad/architecture/**`.
- PLAN PM notes live under `docs/harper/bmad/plan/**`.
- KIT developer notes live under `runs/kit/<REQ-ID>/docs/**`.
- EVAL QA advisory notes live under `runs/kit/<REQ-ID>/docs/**`.
- FINALIZE writer notes live under `docs/harper/bmad/finalize/**`.

When companion material conflicts with canonical Harper artifacts, canonical wins. Companion artifacts may enrich later phases, but they cannot expand write boundaries, change eval/gate authority, alter promotable status, or bypass promotion.

The orchestrator also discovers companion artifacts server-side from controlled roots. The current collector reads bounded snippets from `docs/harper/bmad/**`, `docs/harper/ux/**`, and `runs/kit/<REQ-ID>/docs/**` when a REQ is active. The resulting inventory is added to `methodology_context.discovered_companion_artifacts` and to `core_blobs` with stable `companion::...` keys. This makes companion context available to cloud prompts and local-agent packages without trusting arbitrary client-controlled paths.

## SPEC PM And UX Safety

SPEC has a deliberate ownership split in the current MVP.

`/spec --methodology bmad --agent pm` may update canonical `docs/harper/SPEC.md` through normal CLike SPEC governance and may produce PM companion artifacts under `docs/harper/bmad/spec/**`.

`/spec --methodology bmad --agent ux` is companion-only. It must not overwrite `docs/harper/SPEC.md`. UX outputs belong under `docs/harper/ux/**`, including `DESIGN.md`, `EXPERIENCE.md`, `USER_JOURNEYS.md`, `INTERACTION_STATES.md`, and `SPEC_UX_APPENDIX.md`. These artifacts are consumed by `/plan` as bounded context.

## Request Fields

Methodology-aware requests may include:

- `methodology`
- `agent`
- `methodology_context`

The orchestrator is the single resolver for `methodology_context`. Clients may pass user intent through `methodology` and `agent`, but resolved authority, defaults, advisory flags, workflow focus, and phase mapping belong to the orchestrator. Client-supplied `methodology_context` is not trusted as authority.

## Phase Mapping

| Harper phase | Default BMAD role | Allowed roles | Notes |
| --- | --- | --- | --- |
| `idea` | `analyst` | `analyst` | Discovery and intent framing |
| `spec` | `pm` | `pm`, `ux` | Requirements and UX acceptance detail |
| `plan` | `architect` | `architect`, `pm` | Technical slicing and dependencies |
| `kit` | `developer` | `developer` | Candidate implementation guidance |
| `eval` | `qa` | `qa`, `developer` | Advisory only; EvalRunner remains authoritative |
| `gate` | none | none | CLike-only authority |
| `finalize` | `tech-writer` | `tech-writer` | Release and documentation guidance |

## PLAN Phase Profile

For `/plan`, BMAD `architect` and `pm` roles guide requirement shaping while CLike owns the canonical `PLAN.md` and `plan.json` artifacts.

The PLAN phase should produce REQs that are implementation-ready for `/kit`. Each REQ should include or clearly imply Functional Scope, Technical Scope, Non-Functional Requirements, Security Requirements, Compliance and Privacy Requirements when applicable, Observability and Operations, Integration Contracts, Data Contracts, Dependencies, Acceptance Criteria, Test Strategy, Risk and Mitigation, TECH_CONSTRAINTS obligations, the main module boundary, what this REQ builds now, what this REQ intentionally defers, and what downstream REQs may assume.

`plan.json` should preserve machine-readable detail sufficient for `/kit`, including `id`, `title`, `status`, `lane`, `dependsOn`, `acceptance`, `functional_scope`, `technical_scope`, `non_functional_requirements`, `security_requirements`, `compliance_requirements`, `operational_requirements`, `integration_contracts`, `data_contracts`, `test_strategy`, `risk_notes`, `main_module_boundary`, `runtime_profile` when known, and `gate_expectations` when relevant.

BMAD methodology guidance must not choose a technology stack by default. Python, Node, cloud provider, runtime, database, queue, identity, deployment target, and framework choices must come from TECH_CONSTRAINTS, SPEC, repository evidence, or explicit user input.

## Prompt And Package Injection

For cloud Harper runs, the resolved methodology context is sent to Gateway so the cloud prompt can include compact role and workflow guidance.

For local-agent execution, the resolved methodology context is written into local-agent package files such as `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`. Gateway is not used for local-agent prompt construction.

In both cases, prompt guidance is compact. CLike-owned BMAD profiles are intentionally bounded and do not copy or vendor external BMAD runtime content.

For cloud verification, inspect Gateway `prompt_debug` artifacts for `BMAD Companion Artifact Inventory`, companion artifact contracts, governance boundaries, downstream handoff, and BMAD quality contracts when SPEC or PLAN context includes them.

For local-agent verification, inspect `AGENT_EXECUTION_CONTEXT.json` and `AGENT_EVAL_CONTEXT.json` under `runs/kit/<REQ-ID>/docs/`. BMAD-enabled packages should include `methodology_context`, `companion_documents`, discovered companion inventory when present, BMAD expected outputs, and unchanged write boundaries.

## Quality Scorecard

BMAD quality contracts are deterministic review aids for SPEC, PLAN, `plan.json`, lane-guides, and fixture-based IDEA comparison. They do not claim automatic quality improvement and they do not replace human review.

The scorecard checks structural signals such as testability, acceptance hooks, security/privacy/compliance, observability/operations, data lifecycle, deployment portability, technology constraints richness, downstream handoff readiness, and traceability. Passing scorecard tests proves evaluator sensitivity for the fixtures and artifacts under test; it does not prove live model quality.

## Methodology Is Not Execution

Methodology identity is separate from:

- `profileHint`
- cloud model routing
- `localAgentExecutor`
- Claude Code or Codex CLI selection
- eval/gate verdicts

BMAD enriches the work style for a phase. It does not decide where execution runs, what model is used, what files can be written, or whether a REQ is promotable.

## Current MVP Boundaries

The current integration does not implement a BMAD runtime, `npx bmad-method` runtime invocation, the BMAD importer, TEA/Test Architect, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, or automatic latest BMAD tracking at runtime. It does not add a hard dependency on BMAD packages.
